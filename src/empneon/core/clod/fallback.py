"""Deterministic degradation for unavailable expensive cognition."""

from collections.abc import Awaitable, Callable

from empneon.core.clod.rules import resolve_clod1
from empneon.core.contracts import CognitiveRequest, Decision
from empneon.core.scheduler.resources import ResourceLimitExceeded
from empneon.providers.llm import ProviderError

Resolver = Callable[[CognitiveRequest], Awaitable[Decision]]


async def resolve_with_fallback(request: CognitiveRequest, resolver: Resolver) -> Decision:
    """Resolve requested cognition, degrading failures directly to CLOD 1."""
    if request.preferred_clod == 0:
        raise ValueError("CLOD 0 requests do not produce cognitive decisions")
    if request.preferred_clod == 1:
        return resolve_clod1(request)
    try:
        return await resolver(request)
    except (ProviderError, ResourceLimitExceeded):
        return resolve_clod1(request)
