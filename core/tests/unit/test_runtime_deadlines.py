import asyncio
import logging

import pytest

from empneon.core.contracts import ActionResult, CognitiveRequest, Decision, WorldEvent
from empneon.core.runtime import ActionRecordStore, CognitiveRuntime
from empneon.core.scheduler.resources import (
    ResourceBudget,
    ResourceEstimate,
    ResourceGovernor,
    ResourceSnapshot,
)
from empneon.db.connection import open_db

SECRET = "super-secret-adapter-detail"
IDLE = ResourceSnapshot(0, 0, 0)


class Adapter:
    def observe(self) -> tuple[WorldEvent, ...]:
        return ()

    def execute(self, decision: Decision, /) -> ActionResult:
        return ActionResult(decision.id, "succeeded", decision.state_changes)


class RaisingAdapter(Adapter):
    def __init__(self, failure: BaseException) -> None:
        self._failure = failure

    def execute(self, decision: Decision, /) -> ActionResult:
        raise self._failure


def request(clod: int = 3, deadline_ms: int = 20) -> CognitiveRequest:
    event = WorldEvent("encounter", ("agent-a",))
    return CognitiveRequest("agent-a", clod, event, deadline_ms=deadline_ms)


Parts = tuple[CognitiveRuntime, ResourceGovernor, ActionRecordStore]


def runtime(*, enforce: bool | None = None) -> Parts:
    governor = ResourceGovernor(ResourceBudget(256, 64))
    actions = ActionRecordStore(open_db(":memory:"))
    if enforce is None:
        return CognitiveRuntime(governor, actions), governor, actions
    return CognitiveRuntime(governor, actions, enforce_deadlines=enforce), governor, actions


async def slow(current: CognitiveRequest) -> Decision:
    await asyncio.sleep(0.2)
    return Decision(current.agent_id, "slow-answer")


async def fast(current: CognitiveRequest) -> Decision:
    return Decision(current.agent_id, "fast-answer")


def test_deadline_is_not_enforced_by_default() -> None:
    runtime_, _, _ = runtime()
    decision = asyncio.run(runtime_.decide(request(), slow))
    assert decision.intent == "slow-answer"


def test_enforced_deadline_degrades_slow_provider_to_clod1(
    caplog: pytest.LogCaptureFixture,
) -> None:
    runtime_, governor, _ = runtime(enforce=True)
    with caplog.at_level(logging.WARNING, logger="empneon"):
        decision = asyncio.run(runtime_.decide(request(), slow, ResourceEstimate(32, 16)))
    assert decision.intent == "acknowledge"
    assert "timeout" in caplog.text
    assert governor.snapshot == IDLE


def test_enforced_deadline_leaves_fast_and_clod1_requests_alone() -> None:
    runtime_, _, _ = runtime(enforce=True)
    assert asyncio.run(runtime_.decide(request(), fast)).intent == "fast-answer"
    assert asyncio.run(runtime_.decide(request(clod=1), slow)).intent == "acknowledge"


def test_cancelling_an_in_flight_decision_releases_its_reservation() -> None:
    runtime_, governor, _ = runtime(enforce=True)

    async def scenario() -> None:
        task = asyncio.create_task(
            runtime_.decide(request(deadline_ms=5_000), slow, ResourceEstimate(32, 16))
        )
        await asyncio.sleep(0.02)
        assert governor.snapshot == ResourceSnapshot(32, 16, 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    assert governor.snapshot == IDLE


def test_adapter_failure_is_recorded_without_leaking_its_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    runtime_, _, actions = runtime()
    with caplog.at_level(logging.ERROR, logger="empneon"):
        record = asyncio.run(
            runtime_.process(request(clod=1), RaisingAdapter(RuntimeError(SECRET)), fast)
        )

    assert record.result.status == "failed"
    assert record.result.reason == "adapter raised RuntimeError"
    assert record.result.applied_changes == ()
    assert actions.get(record.decision.id) == record
    assert "RuntimeError" in caplog.text
    assert SECRET not in caplog.text


def test_cancellation_inside_adapter_is_not_swallowed() -> None:
    runtime_, _, actions = runtime()
    cancelling = RaisingAdapter(asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(runtime_.process(request(clod=1), cancelling, fast))
    assert actions.get_for_agent("agent-a") == []
