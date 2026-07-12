import asyncio

from empneon.core.clod import resolve_clod1, resolve_with_fallback
from empneon.core.contracts import CognitiveRequest, Decision, WorldEvent
from empneon.providers.llm import ProviderError


def test_provider_failure_degrades_deterministically_to_clod1() -> None:
    request = CognitiveRequest("alice", 3, WorldEvent("event", id="event-1"))

    async def failed_provider(_: CognitiveRequest) -> Decision:
        raise ProviderError("unavailable")

    decision = asyncio.run(resolve_with_fallback(request, failed_provider))

    assert decision == resolve_clod1(request)
    assert decision.intent == "acknowledge"
