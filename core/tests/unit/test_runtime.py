import asyncio

import pytest

from empneon.core.contracts import ActionResult, CognitiveRequest, Decision, StateDelta, WorldEvent
from empneon.core.runtime import ActionRecordStore, CognitiveRuntime
from empneon.core.scheduler import CognitionRoute, select_cognition
from empneon.core.scheduler.resources import (
    ResourceBudget,
    ResourceEstimate,
    ResourceGovernor,
    ResourceSnapshot,
)
from empneon.db.connection import open_db
from empneon.providers.llm import ModelCapabilities


class SuccessfulAdapter:
    def __init__(self, event: WorldEvent) -> None:
        self._event = event

    def observe(self) -> tuple[WorldEvent, ...]:
        return (self._event,)

    def execute(self, decision: Decision, /) -> ActionResult:
        return ActionResult(decision.id, "succeeded", decision.state_changes)


def event(actor: str = "agent-a", target: str | None = None) -> WorldEvent:
    actors = (actor, target) if target else (actor,)
    return WorldEvent("encounter", actors)


def test_event_executes_and_persists_through_core() -> None:
    observed = event("agent-a")
    adapter = SuccessfulAdapter(observed)
    request = CognitiveRequest("agent-a", 1, observed)
    actions = ActionRecordStore(open_db(":memory:"))
    runtime = CognitiveRuntime(ResourceGovernor(ResourceBudget(256, 0)), actions)

    async def unused_resolver(_: CognitiveRequest) -> Decision:
        raise AssertionError("CLOD 1 must not call a provider")

    record = asyncio.run(runtime.process(request, adapter, unused_resolver))

    assert record.result.status == "succeeded"
    assert record.decision.intent == "acknowledge"
    assert actions.get(record.decision.id) == record
    assert actions.get_consequences(record.decision.id) == record.result.applied_changes


def test_applied_consequences_persist_in_order() -> None:
    observed = event("agent-a", "agent-b")
    adapter = SuccessfulAdapter(observed)
    request = CognitiveRequest("agent-a", 3, observed)
    actions = ActionRecordStore(open_db(":memory:"))
    runtime = CognitiveRuntime(ResourceGovernor(ResourceBudget(256, 0)), actions)

    async def resolve(_: CognitiveRequest) -> Decision:
        return Decision(
            "agent-a",
            "greet",
            target_id="agent-b",
            evidence_ids=(observed.id,),
            state_changes=(StateDelta("relationship.strength", "increment", 0.1),),
        )

    record = asyncio.run(runtime.process(request, adapter, resolve))

    assert actions.get_consequences(record.decision.id) == record.result.applied_changes


@pytest.mark.parametrize("failure", [TimeoutError(), MemoryError()])
def test_provider_failure_falls_back_persists_and_releases_resources(
    failure: Exception,
) -> None:
    observed = event("agent-a")
    adapter = SuccessfulAdapter(observed)
    request = CognitiveRequest("agent-a", 3, observed)
    actions = ActionRecordStore(open_db(":memory:"))
    governor = ResourceGovernor(ResourceBudget(256, 64))
    runtime = CognitiveRuntime(governor, actions)

    async def failed_provider(_: CognitiveRequest) -> Decision:
        raise failure

    record = asyncio.run(
        runtime.process(request, adapter, failed_provider, ResourceEstimate(32, 16))
    )

    assert record.decision.intent == "acknowledge"
    assert actions.get(record.decision.id) == record
    assert governor.snapshot == ResourceSnapshot(0, 0, 0)


def test_game_confirmation_atomically_replaces_proposal() -> None:
    actions = ActionRecordStore(open_db(":memory:"))
    decision = Decision("agent-a", "greet", target_id="agent-b", id="decision-1")
    proposal = actions.propose("event-1", decision, "friendly_chat")

    result = ActionResult(decision.id, "succeeded", decision.state_changes)
    record = actions.confirm(result, "friendly_chat")

    assert proposal.decision == decision
    assert record.result == result
    assert actions.get_proposal(decision.id) is None
    assert actions.get(decision.id) == record


def test_failed_game_confirmation_persists_no_consequence() -> None:
    actions = ActionRecordStore(open_db(":memory:"))
    decision = Decision("agent-a", "greet", id="decision-1")
    actions.propose("event-1", decision, "friendly_chat")

    record = actions.confirm(
        ActionResult(decision.id, "failed", reason="game rejected interaction"),
        "friendly_chat",
    )

    assert record.result.status == "failed"
    assert actions.get_consequences(decision.id) == ()


def test_dynamic_selection_routes_and_trims_provider_cognition() -> None:
    governor = ResourceGovernor(
        ResourceBudget(
            256,
            128,
            max_context_tokens=800,
            max_completion_tokens=100,
            max_latency_ms=1_000,
        )
    )
    runtime = CognitiveRuntime(governor, ActionRecordStore(open_db(":memory:")))
    request = CognitiveRequest(
        "agent-a",
        4,
        event("agent-a"),
        urgency=1,
        max_tokens=300,
        max_context_tokens=2_000,
        deadline_ms=1_000,
    )
    selected_requests: list[CognitiveRequest] = []

    async def unavailable(request: CognitiveRequest) -> Decision:
        raise AssertionError(f"unavailable route selected for {request.id}")

    async def selected(request: CognitiveRequest) -> Decision:
        selected_requests.append(request)
        return Decision(request.agent_id, "consider context")

    routes = (
        CognitionRoute(
            "large-provider",
            4,
            ModelCapabilities(context_window=4_096),
            ResourceEstimate(128, 256, 2_000, 300, 900),
            unavailable,
        ),
        CognitionRoute(
            "small-provider",
            3,
            ModelCapabilities(context_window=600),
            ResourceEstimate(64, 64, 1_000, 200, 500),
            selected,
        ),
    )

    plan = select_cognition(request, routes, governor, 0.9)
    decision = asyncio.run(runtime.decide_dynamic(request, routes, 0.9))

    assert (plan.clod, plan.provider) == (3, "small-provider")
    assert (plan.context_tokens, plan.completion_tokens) == (500, 100)
    assert decision.intent == "consider context"
    assert len(selected_requests) == 1
    assert selected_requests[0].preferred_clod == 3
    assert selected_requests[0].max_context_tokens == 500
    assert selected_requests[0].max_tokens == 100
    assert governor.snapshot == ResourceSnapshot(0, 0, 0)


def test_dynamic_selection_uses_clod1_when_expected_value_is_low() -> None:
    runtime = CognitiveRuntime(
        ResourceGovernor(ResourceBudget(256, 128)),
        ActionRecordStore(open_db(":memory:")),
    )
    request = CognitiveRequest(
        "agent-a",
        3,
        event("agent-a"),
        urgency=0.4,
    )

    async def unused(_: CognitiveRequest) -> Decision:
        raise AssertionError("low-value cognition must not call a provider")

    route = CognitionRoute(
        "provider",
        3,
        ModelCapabilities(context_window=4_096),
        ResourceEstimate(64, 64, 1_000, 200, 500),
        unused,
    )

    decision = asyncio.run(runtime.decide_dynamic(request, (route,), 0.9))

    assert decision.intent == "acknowledge"


def test_cognition_route_rejects_invalid_provider_or_clod() -> None:
    capabilities = ModelCapabilities()
    estimate = ResourceEstimate(0, 0, 0, 100, 0)
    with pytest.raises(ValueError, match="provider is required"):
        CognitionRoute("", 3, capabilities, estimate, None)


def test_cognition_route_rejects_non_positive_completion_tokens() -> None:
    capabilities = ModelCapabilities()
    estimate = ResourceEstimate(0, 0, 0, 0, 0)
    with pytest.raises(ValueError, match="completion token estimate must be positive"):
        CognitionRoute("provider", 3, capabilities, estimate, None)


def test_dynamic_selection_falls_back_to_clod1_when_no_route_meets_deadline() -> None:
    governor = ResourceGovernor(ResourceBudget(256, 128))
    request = CognitiveRequest("agent-a", 4, event("agent-a"), urgency=1, deadline_ms=100)

    async def unused(_: CognitiveRequest) -> Decision:
        raise AssertionError("no route should be selected")

    route = CognitionRoute(
        "provider",
        4,
        ModelCapabilities(),
        ResourceEstimate(32, 16, 100, 50, 5_000),
        unused,
    )

    plan = select_cognition(request, (route,), governor, 0.9)

    assert plan.clod == 1
    assert plan.resolver is None


def test_dynamic_selection_rejects_route_when_context_window_too_small() -> None:
    governor = ResourceGovernor(ResourceBudget(256, 128))
    request = CognitiveRequest(
        "agent-a", 4, event("agent-a"), urgency=1, max_tokens=300, max_context_tokens=2_000
    )

    async def unused(_: CognitiveRequest) -> Decision:
        raise AssertionError("no route should be selected")

    route = CognitionRoute(
        "provider",
        4,
        ModelCapabilities(context_window=50),
        ResourceEstimate(32, 16, 2_000, 300, 100),
        unused,
    )

    plan = select_cognition(request, (route,), governor, 0.9)

    assert plan.clod == 1
