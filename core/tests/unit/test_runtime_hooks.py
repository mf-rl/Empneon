import asyncio
import logging
import sqlite3
from collections.abc import Callable

import pytest

from empneon.core.contracts import CognitiveRequest, Decision, DegradationReason, WorldEvent
from empneon.core.ports import Resolver
from empneon.core.runtime import ActionRecordStore, CognitiveRuntime
from empneon.core.scheduler.resources import ResourceBudget, ResourceGovernor
from empneon.core.scheduler.usage import UsageStore
from empneon.db.connection import open_db
from empneon.providers.llm import ProviderError

SECRET = "super-secret-hook-detail"


def request(clod: int = 3, deadline_ms: int = 20) -> CognitiveRequest:
    event = WorldEvent("encounter", ("agent-a",))
    return CognitiveRequest("agent-a", clod, event, deadline_ms=deadline_ms)


Hook = Callable[[DegradationReason], None]


def build(
    hook: Hook | None, *, usage: bool = False, enforce: bool = False
) -> tuple[CognitiveRuntime, sqlite3.Connection]:
    conn = open_db(":memory:")
    runtime = CognitiveRuntime(
        ResourceGovernor(ResourceBudget(256, 64)),
        ActionRecordStore(conn),
        enforce_deadlines=enforce,
        usage=UsageStore(conn) if usage else None,
        on_degrade=hook,
    )
    return runtime, conn


async def provider_down(_: CognitiveRequest) -> Decision:
    raise ProviderError(SECRET, status=503)


async def invalid_payload(_: CognitiveRequest) -> Decision:
    raise ValueError(SECRET)


async def slow(current: CognitiveRequest) -> Decision:
    await asyncio.sleep(0.2)
    return Decision(current.agent_id, "slow-answer")


async def fast(current: CognitiveRequest) -> Decision:
    return Decision(current.agent_id, "fast-answer")


@pytest.mark.parametrize(
    ("resolver", "reason", "enforce"),
    [
        (provider_down, DegradationReason.PROVIDER_ERROR, False),
        (invalid_payload, DegradationReason.INVALID_OUTPUT, False),
        (slow, DegradationReason.TIMEOUT, True),
    ],
)
def test_hook_receives_the_degradation_reason(
    resolver: Resolver, reason: DegradationReason, enforce: bool
) -> None:
    reasons: list[DegradationReason] = []
    runtime, conn = build(reasons.append, enforce=enforce)

    decision = asyncio.run(runtime.decide(request(), resolver))

    assert decision.intent == "acknowledge"
    assert reasons == [reason]
    assert conn.execute("SELECT COUNT(*) FROM cognition_usage").fetchone()[0] == 0


def test_hook_is_not_called_on_success_or_for_clod1() -> None:
    reasons: list[DegradationReason] = []
    runtime, _ = build(reasons.append)
    asyncio.run(runtime.decide(request(), fast))
    asyncio.run(runtime.decide(request(clod=1), provider_down))
    assert reasons == []


def test_hook_and_usage_store_work_together_without_duplicates() -> None:
    reasons: list[DegradationReason] = []
    runtime, conn = build(reasons.append, usage=True)

    asyncio.run(runtime.decide(request(), provider_down))

    assert reasons == [DegradationReason.PROVIDER_ERROR]
    rows = conn.execute("SELECT degradation_reason FROM cognition_usage").fetchall()
    assert [row[0] for row in rows] == ["provider_error"]


def test_raising_hook_neither_masks_the_decision_nor_stops_usage_recording(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broken(_: DegradationReason) -> None:
        raise RuntimeError(SECRET)

    runtime, conn = build(broken, usage=True)
    with caplog.at_level(logging.ERROR, logger="empneon"):
        decision = asyncio.run(runtime.decide(request(), provider_down))

    assert decision.intent == "acknowledge"
    assert conn.execute("SELECT COUNT(*) FROM cognition_usage").fetchone()[0] == 1
    assert "RuntimeError" in caplog.text and SECRET not in caplog.text


def test_failing_usage_recording_still_calls_the_hook() -> None:
    reasons: list[DegradationReason] = []
    runtime, conn = build(reasons.append, usage=True)
    conn.execute("DROP TABLE cognition_usage")

    decision = asyncio.run(runtime.decide(request(), provider_down))

    assert decision.intent == "acknowledge"
    assert reasons == [DegradationReason.PROVIDER_ERROR]


def test_default_runtime_has_no_hook() -> None:
    conn = open_db(":memory:")
    runtime = CognitiveRuntime(ResourceGovernor(ResourceBudget(256, 64)), ActionRecordStore(conn))
    assert asyncio.run(runtime.decide(request(), provider_down)).intent == "acknowledge"
