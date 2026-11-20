"""End to end: a router-built streaming provider feeding a resolver inside CognitiveRuntime."""

import asyncio
from collections.abc import AsyncIterator, Mapping

from empneon.core.contracts import (
    ActionResult,
    CognitiveRequest,
    Decision,
    DegradationReason,
    WorldEvent,
)
from empneon.core.runtime import ActionRecordStore, CognitiveRuntime
from empneon.core.scheduler.resources import (
    ResourceBudget,
    ResourceEstimate,
    ResourceGovernor,
    ResourceSnapshot,
)
from empneon.core.scheduler.usage import UsageStore
from empneon.db.connection import open_db
from empneon.providers.llm import (
    ConfiguredProviderRouter,
    GenerationRequest,
    GenerationResult,
    LLMProvider,
    Message,
    ModelCapabilities,
    ProviderError,
)


class FakeStreamingProvider:
    """Yields scripted chunks, optionally failing or stalling after them."""

    capabilities = ModelCapabilities(streaming=True)

    def __init__(
        self, chunks: list[str], *, fail: bool = False, stall_s: float = 0.0
    ) -> None:
        self.chunks, self.fail, self.stall_s = chunks, fail, stall_s
        self.requests: list[GenerationRequest] = []

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        raise AssertionError("streaming path must not call generate")

    async def health_check(self) -> bool:
        return True

    async def stream(self, request: GenerationRequest) -> AsyncIterator[str]:
        self.requests.append(request)
        for chunk in self.chunks:
            yield chunk
        if self.stall_s:
            await asyncio.sleep(self.stall_s)
        if self.fail:
            raise ProviderError("down", status=503)


class Adapter:
    def __init__(self) -> None:
        self.executed: list[Decision] = []

    def observe(self) -> tuple[WorldEvent, ...]:
        return ()

    def execute(self, decision: Decision, /) -> ActionResult:
        self.executed.append(decision)
        return ActionResult(decision.id, "succeeded", decision.state_changes)


class StreamingRouter(ConfiguredProviderRouter):
    def __init__(self, provider: FakeStreamingProvider) -> None:
        super().__init__(
            "openai",
            {"openai": {"endpoint": "http://localhost:1234/v1", "model": "m"}},
            {"dialogue": {"streaming": True}},
        )
        self.fake = provider

    def _build_provider(self, config: Mapping[str, object]) -> LLMProvider:
        return self.fake  # type: ignore[return-value]


Built = tuple[CognitiveRuntime, ResourceGovernor, ActionRecordStore, UsageStore]


def build(*, enforce: bool = False) -> Built:
    conn = open_db(":memory:")
    governor = ResourceGovernor(ResourceBudget(256, 64))
    actions = ActionRecordStore(conn)
    usage = UsageStore(conn)
    runtime = CognitiveRuntime(governor, actions, enforce_deadlines=enforce, usage=usage)
    return runtime, governor, actions, usage


def request(deadline_ms: int = 1_000) -> CognitiveRequest:
    return CognitiveRequest(
        "agent-a", 3, WorldEvent("encounter", ("agent-a",)), deadline_ms=deadline_ms
    )


def resolver_for(router: StreamingRouter, seen: list[str]):  # type: ignore[no-untyped-def]
    async def resolve(current: CognitiveRequest) -> Decision:
        provider = router.stream_for("dialogue")
        generation = router.generation_request("dialogue", (Message("user", "Hi"),))
        text = "".join([chunk async for chunk in provider.stream(generation)])
        seen.append(text)
        return Decision(current.agent_id, "say", target_id=text)

    return resolve


def test_streamed_text_becomes_an_executed_and_recorded_decision() -> None:
    router = StreamingRouter(FakeStreamingProvider(["Hel", "lo"]))
    runtime, governor, actions, _ = build()
    adapter, seen = Adapter(), []

    record = asyncio.run(
        runtime.process(request(), adapter, resolver_for(router, seen), ResourceEstimate(32, 16))
    )

    assert seen == ["Hello"]
    assert record.decision.intent == "say" and record.decision.target_id == "Hello"
    assert adapter.executed == [record.decision]
    assert actions.get(record.decision.id) == record
    assert governor.snapshot == ResourceSnapshot(0, 0, 0)
    assert router.fake.requests[0].max_tokens == 350


def test_mid_stream_provider_error_degrades_to_clod1() -> None:
    router = StreamingRouter(FakeStreamingProvider(["Hel"], fail=True))
    runtime, governor, _, usage = build()
    adapter = Adapter()

    record = asyncio.run(
        runtime.process(request(), adapter, resolver_for(router, []), ResourceEstimate(32, 16))
    )

    assert record.decision.intent == "acknowledge"
    assert governor.snapshot == ResourceSnapshot(0, 0, 0)
    assert usage.telemetry()["by_degradation"] == {DegradationReason.PROVIDER_ERROR: 1}


def test_deadline_still_bounds_a_stalled_stream() -> None:
    router = StreamingRouter(FakeStreamingProvider(["Hel"], stall_s=0.5))
    runtime, governor, _, usage = build(enforce=True)

    record = asyncio.run(
        runtime.process(
            request(deadline_ms=20), Adapter(), resolver_for(router, []), ResourceEstimate(32, 16)
        )
    )

    assert record.decision.intent == "acknowledge"
    assert governor.snapshot == ResourceSnapshot(0, 0, 0)
    assert usage.telemetry()["by_degradation"] == {DegradationReason.TIMEOUT: 1}

