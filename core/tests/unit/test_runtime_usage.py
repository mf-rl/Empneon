import asyncio
import logging
import sqlite3

import pytest

from empneon.core.clod import DegradationReason as ClodReason
from empneon.core.clod.fallback import DegradationReason as FallbackReason
from empneon.core.contracts import CognitiveRequest, Decision, DegradationReason, WorldEvent
from empneon.core.runtime import ActionRecordStore, CognitiveRuntime
from empneon.core.scheduler.resources import ResourceBudget, ResourceEstimate, ResourceGovernor
from empneon.core.scheduler.selection import CognitionRoute
from empneon.core.scheduler.usage import UsageRecord, UsageStore
from empneon.db.connection import open_db
from empneon.providers.llm import ModelCapabilities, ProviderError

SECRET = "super-secret-provider-detail"


def request(clod: int = 3, deadline_ms: int = 20, urgency: float = 0.5) -> CognitiveRequest:
    event = WorldEvent("encounter", ("agent-a",))
    return CognitiveRequest("agent-a", clod, event, deadline_ms=deadline_ms, urgency=urgency)


def build(
    *, usage: bool = True, enforce: bool = False
) -> tuple[CognitiveRuntime, sqlite3.Connection]:
    conn = open_db(":memory:")
    runtime = CognitiveRuntime(
        ResourceGovernor(ResourceBudget(256, 64)),
        ActionRecordStore(conn),
        enforce_deadlines=enforce,
        usage=UsageStore(conn) if usage else None,
    )
    return runtime, conn


def rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM cognition_usage").fetchall()


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
        (provider_down, "provider_error", False),
        (invalid_payload, "invalid_output", False),
        (slow, "timeout", True),
    ],
)
def test_each_degradation_is_persisted_with_its_reason(
    resolver: object, reason: str, enforce: bool
) -> None:
    runtime, conn = build(enforce=enforce)
    current = request()
    estimate = ResourceEstimate(32, 16, 100, 50, 900)

    decision = asyncio.run(runtime.decide(current, resolver, estimate))  # type: ignore[arg-type]

    assert decision.intent == "acknowledge"
    (row,) = rows(conn)
    assert (row["provider"], row["model"], row["selected_clod"]) == ("core-rules", "clod1", 1)
    assert row["degradation_reason"] == reason
    assert row["request_id"] == current.id and row["agent_id"] == "agent-a"
    assert (row["estimated_ram_mb"], row["actual_prompt_tokens"]) == (32, 0)


def test_successful_and_clod1_requests_record_nothing() -> None:
    runtime, conn = build()
    assert asyncio.run(runtime.decide(request(), fast)).intent == "fast-answer"
    assert asyncio.run(runtime.decide(request(clod=1), provider_down)).intent == "acknowledge"
    assert rows(conn) == []


def test_nothing_is_written_without_a_usage_store() -> None:
    runtime, conn = build(usage=False)
    assert asyncio.run(runtime.decide(request(), provider_down)).intent == "acknowledge"
    assert rows(conn) == []


def test_recording_failure_never_masks_the_decision(caplog: pytest.LogCaptureFixture) -> None:
    runtime, conn = build()
    conn.execute("DROP TABLE cognition_usage")

    with caplog.at_level(logging.ERROR, logger="empneon"):
        decision = asyncio.run(runtime.decide(request(), provider_down))

    assert decision.intent == "acknowledge"
    assert "OperationalError" in caplog.text
    assert SECRET not in caplog.text and "cognition_usage" not in caplog.text


def test_degradation_reason_has_one_identity_across_import_paths() -> None:
    assert ClodReason is FallbackReason is DegradationReason


def _route(resolver: object) -> CognitionRoute:
    return CognitionRoute(
        "provider",
        3,
        ModelCapabilities(context_window=4_096),
        ResourceEstimate(64, 16, 1_000, 200, 500),
        resolver,  # type: ignore[arg-type]
    )


def test_policy_choice_of_clod1_is_recorded_as_deliberate_not_degraded() -> None:
    runtime, conn = build()
    low_value = CognitiveRequest(
        "agent-a", 3, WorldEvent("encounter", ("agent-a",)), urgency=0.4
    )

    decision = asyncio.run(runtime.decide_dynamic(low_value, (_route(fast),), 0.9))

    assert decision.intent == "acknowledge"
    (row,) = rows(conn)
    assert (row["provider"], row["model"], row["selected_clod"]) == ("core-rules", "clod1", 1)
    assert row["deliberate_clod1"] == 1 and row["degradation_reason"] is None
    telemetry = UsageStore(conn).telemetry()
    assert telemetry["by_degradation"] == {}
    assert telemetry["deliberate_clod1"] == 1


def test_preferred_clod1_is_recorded_as_deliberate() -> None:
    runtime, conn = build()
    asyncio.run(runtime.decide_dynamic(request(clod=1, deadline_ms=1_000), (_route(fast),), 0.9))
    (row,) = rows(conn)
    assert row["deliberate_clod1"] == 1


def test_degradation_is_never_counted_as_deliberate() -> None:
    runtime, conn = build()
    urgent = request(deadline_ms=1_000, urgency=1.0)
    asyncio.run(runtime.decide_dynamic(urgent, (_route(provider_down),), 0.9))
    (row,) = rows(conn)
    assert row["degradation_reason"] == "provider_error" and row["deliberate_clod1"] == 0
    telemetry = UsageStore(conn).telemetry()
    assert telemetry["by_degradation"] == {"provider_error": 1}
    assert telemetry["deliberate_clod1"] == 0


def test_successful_dynamic_cognition_records_nothing() -> None:
    runtime, conn = build()
    urgent = request(deadline_ms=1_000, urgency=1.0)
    assert asyncio.run(runtime.decide_dynamic(urgent, (_route(fast),), 0.9)).intent == "fast-answer"
    assert rows(conn) == []


def test_unaffordable_routes_are_not_recorded_as_deliberate() -> None:
    runtime, conn = build()
    huge = CognitionRoute(
        "provider",
        3,
        ModelCapabilities(context_window=4_096),
        ResourceEstimate(9_999, 0, 1_000, 200, 500),
        fast,
    )
    urgent = request(deadline_ms=1_000, urgency=1.0)
    assert asyncio.run(runtime.decide_dynamic(urgent, (huge,), 0.9)).intent == "acknowledge"
    assert rows(conn) == []


def test_usage_record_rejects_deliberate_degradation() -> None:
    with pytest.raises(ValueError, match="deliberate"):
        UsageRecord(
            "r", "a", "e", "core-rules", "clod1", 1, ResourceEstimate(), 0, 0, 0,
            degradation_reason=DegradationReason.BUDGET, deliberate_clod1=True,
        )  # fmt: skip


def test_deliberate_recording_failure_never_masks_the_decision(
    caplog: pytest.LogCaptureFixture,
) -> None:
    runtime, conn = build()
    conn.execute("DROP TABLE cognition_usage")
    with caplog.at_level(logging.ERROR, logger="empneon"):
        decision = asyncio.run(
            runtime.decide_dynamic(request(clod=1, deadline_ms=1_000), (_route(fast),), 0.9)
        )
    assert decision.intent == "acknowledge" and "OperationalError" in caplog.text


def test_on_deliberate_hook_fires_only_for_a_policy_choice() -> None:
    calls: list[str] = []
    conn = open_db(":memory:")
    runtime = CognitiveRuntime(
        ResourceGovernor(ResourceBudget(256, 64)),
        ActionRecordStore(conn),
        on_deliberate=lambda: calls.append("deliberate"),
    )
    asyncio.run(runtime.decide_dynamic(request(clod=1), (_route(fast),), 0.9))
    huge = CognitionRoute(
        "provider",
        3,
        ModelCapabilities(context_window=4_096),
        ResourceEstimate(9_999, 0, 1_000, 200, 500),
        fast,
    )
    urgent = request(deadline_ms=1_000, urgency=1.0)
    asyncio.run(runtime.decide_dynamic(urgent, (huge,), 0.9))
    assert calls == ["deliberate"]
