"""Deterministic degradation for unavailable expensive cognition."""

import logging
from collections.abc import Awaitable, Callable
from enum import StrEnum

from empneon.core.clod.rules import resolve_clod1
from empneon.core.contracts import CognitiveRequest, Decision
from empneon.core.scheduler.resources import ResourceLimitExceeded
from empneon.providers.llm import ProviderError

_log = logging.getLogger(__name__)

Resolver = Callable[[CognitiveRequest], Awaitable[Decision]]


class DegradationReason(StrEnum):
    """Why expensive cognition degraded to the deterministic CLOD 1 rule."""

    PROVIDER_ERROR = "provider_error"
    TIMEOUT = "timeout"
    MEMORY = "memory"
    BUDGET = "budget"
    INVALID_OUTPUT = "invalid_output"


async def resolve_with_fallback(
    request: CognitiveRequest,
    resolver: Resolver,
    on_degrade: Callable[[DegradationReason], None] | None = None,
) -> Decision:
    """Resolve requested cognition, degrading failures directly to CLOD 1.

    Provider, timeout, memory, budget, and invalid-output (`ValueError`, including JSON
    decode errors) failures degrade. Other exceptions are programming errors and propagate.
    `on_degrade` receives the reason when a fallback occurs.
    """
    if request.preferred_clod == 0:
        raise ValueError("CLOD 0 requests do not produce cognitive decisions")
    if request.preferred_clod == 1:
        return resolve_clod1(request)
    try:
        return await resolver(request)
    except ProviderError:
        reason = DegradationReason.PROVIDER_ERROR
    except TimeoutError:
        reason = DegradationReason.TIMEOUT
    except MemoryError:
        reason = DegradationReason.MEMORY
    except ResourceLimitExceeded:
        reason = DegradationReason.BUDGET
    except ValueError:
        reason = DegradationReason.INVALID_OUTPUT
    _log.warning(
        "cognition degraded to CLOD 1: reason=%s preferred_clod=%d", reason, request.preferred_clod
    )
    if on_degrade is not None:
        on_degrade(reason)
    return resolve_clod1(request)
