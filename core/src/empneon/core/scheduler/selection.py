"""Value- and budget-aware cognition route selection."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace

from empneon.core.contracts import CognitiveRequest, Decision
from empneon.core.scheduler.resources import ResourceBudget, ResourceEstimate, ResourceGovernor
from empneon.providers.llm import ModelCapabilities

Resolver = Callable[[CognitiveRequest], Awaitable[Decision]]


@dataclass(frozen=True)
class CognitionRoute:
    provider: str
    clod: int
    capabilities: ModelCapabilities
    estimate: ResourceEstimate
    resolver: Resolver

    def __post_init__(self) -> None:
        if not self.provider.strip() or not 2 <= self.clod <= 4:
            raise ValueError("provider is required and route CLOD must be between 2 and 4")
        if self.estimate.completion_tokens <= 0:
            raise ValueError("route completion token estimate must be positive")


@dataclass(frozen=True)
class CognitionPlan:
    clod: int
    provider: str | None
    context_tokens: int
    completion_tokens: int
    estimate: ResourceEstimate
    resolver: Resolver | None


def select_cognition(
    request: CognitiveRequest,
    routes: tuple[CognitionRoute, ...],
    governor: ResourceGovernor,
    deeper_reasoning_value: float,
    minimum_value: float = 0.5,
) -> CognitionPlan:
    """Choose the highest affordable CLOD when deeper reasoning is worthwhile."""
    if not -1 <= deeper_reasoning_value <= 1:
        raise ValueError("deeper reasoning value must be between -1 and 1")
    if not 0 <= minimum_value <= 1:
        raise ValueError("minimum value must be between 0 and 1")
    if request.preferred_clod <= 1 or request.urgency * deeper_reasoning_value < minimum_value:
        return _clod1_plan()

    budget = governor.budget
    candidates = sorted(
        (route for route in routes if route.clod <= request.preferred_clod),
        key=lambda route: (
            -route.clod,
            route.estimate.latency_ms,
            route.estimate.completion_tokens,
            route.estimate.context_tokens,
            route.estimate.ram_mb + route.estimate.vram_mb,
            route.provider,
        ),
    )
    for route in candidates:
        plan = _plan_for_route(route, request, governor, budget)
        if plan is not None:
            return plan
    return _clod1_plan()


def _plan_for_route(
    route: CognitionRoute,
    request: CognitiveRequest,
    governor: ResourceGovernor,
    budget: ResourceBudget,
) -> CognitionPlan | None:
    completion_tokens = min(request.max_tokens, route.estimate.completion_tokens)
    if budget.max_completion_tokens is not None:
        completion_tokens = min(completion_tokens, budget.max_completion_tokens)
    if completion_tokens <= 0 or route.estimate.latency_ms > request.deadline_ms:
        return None

    context_tokens = min(request.max_context_tokens, route.estimate.context_tokens)
    if budget.max_context_tokens is not None:
        context_tokens = min(context_tokens, budget.max_context_tokens)
    if route.capabilities.context_window:
        context_tokens = min(
            context_tokens,
            route.capabilities.context_window - completion_tokens,
        )
    if context_tokens < 0:
        return None

    estimate = replace(
        route.estimate,
        context_tokens=context_tokens,
        completion_tokens=completion_tokens,
    )
    if not governor.can_reserve(estimate):
        return None
    return CognitionPlan(
        route.clod,
        route.provider,
        context_tokens,
        completion_tokens,
        estimate,
        route.resolver,
    )


def _clod1_plan() -> CognitionPlan:
    return CognitionPlan(1, None, 0, 0, ResourceEstimate(), None)
