import asyncio
import json

import pytest

from empneon.core.clod import DegradationReason, resolve_clod1, resolve_with_fallback
from empneon.core.contracts import CognitiveRequest, Decision, WorldEvent
from empneon.core.scheduler.resources import ResourceLimitExceeded
from empneon.providers.llm import ProviderError


@pytest.mark.parametrize("failure", [ProviderError("unavailable"), TimeoutError(), MemoryError()])
def test_provider_failure_degrades_deterministically_to_clod1(failure: Exception) -> None:
    request = CognitiveRequest("alice", 3, WorldEvent("event", id="event-1"))

    async def failed_provider(_: CognitiveRequest) -> Decision:
        raise failure

    decision = asyncio.run(resolve_with_fallback(request, failed_provider))

    assert decision == resolve_clod1(request)
    assert decision.intent == "acknowledge"


@pytest.mark.parametrize("failure", [ValueError("bad decision"), json.JSONDecodeError("x", "", 0)])
def test_invalid_model_output_degrades_to_clod1(failure: ValueError) -> None:
    request = CognitiveRequest("alice", 3, WorldEvent("event", id="event-1"))

    async def invalid_output(_: CognitiveRequest) -> Decision:
        raise failure

    decision = asyncio.run(resolve_with_fallback(request, invalid_output))

    assert decision == resolve_clod1(request)


@pytest.mark.parametrize(
    ("failure", "reason"),
    [
        (ProviderError("unavailable"), DegradationReason.PROVIDER_ERROR),
        (TimeoutError(), DegradationReason.TIMEOUT),
        (MemoryError(), DegradationReason.MEMORY),
        (ResourceLimitExceeded("budget"), DegradationReason.BUDGET),
        (ValueError("bad decision"), DegradationReason.INVALID_OUTPUT),
    ],
)
def test_degradation_reason_is_reported(failure: Exception, reason: DegradationReason) -> None:
    request = CognitiveRequest("alice", 3, WorldEvent("event", id="event-1"))
    reasons: list[DegradationReason] = []

    async def failed(_: CognitiveRequest) -> Decision:
        raise failure

    asyncio.run(resolve_with_fallback(request, failed, on_degrade=reasons.append))

    assert reasons == [reason]


def test_no_degradation_reported_on_success() -> None:
    request = CognitiveRequest("alice", 3, WorldEvent("event", id="event-1"))
    reasons: list[DegradationReason] = []

    async def succeeds(current: CognitiveRequest) -> Decision:
        return resolve_clod1(current)

    asyncio.run(resolve_with_fallback(request, succeeds, on_degrade=reasons.append))

    assert reasons == []


def test_programming_errors_are_not_swallowed() -> None:
    request = CognitiveRequest("alice", 3, WorldEvent("event", id="event-1"))

    async def buggy(_: CognitiveRequest) -> Decision:
        raise KeyError("bug")

    with pytest.raises(KeyError):
        asyncio.run(resolve_with_fallback(request, buggy))
