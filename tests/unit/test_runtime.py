import asyncio

import pytest

from empneon.adapters.sims4 import Sims4PocAdapter
from empneon.core.contracts import ActionResult, CognitiveRequest, Decision
from empneon.core.runtime import ActionRecordStore, CognitiveRuntime
from empneon.core.scheduler.resources import (
    ResourceBudget,
    ResourceEstimate,
    ResourceGovernor,
    ResourceSnapshot,
)
from empneon.db.connection import open_db


def test_sims_event_executes_and_persists_through_core() -> None:
    adapter = Sims4PocAdapter({"sim": {"id": "bella-goth", "name": "Bella Goth"}})
    event = adapter.observe()[0]
    request = CognitiveRequest("bella-goth", 1, event)
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
    adapter = Sims4PocAdapter(
        {
            "speaker": {"id": "bella"},
            "listener": {"id": "mortimer"},
            "available_actions": ["friendly_chat"],
        }
    )
    event = adapter.observe()[0]
    request = CognitiveRequest("bella", 3, event)
    actions = ActionRecordStore(open_db(":memory:"))
    runtime = CognitiveRuntime(ResourceGovernor(ResourceBudget(256, 0)), actions)

    async def resolve(_: CognitiveRequest) -> Decision:
        return adapter.decision_from_response(
            {
                "dialogue": "Hello.",
                "emotion": "happy",
                "intent": "greet",
                "relationship": {"friendship_delta": 1},
                "memory": {"importance": 0.4, "summary": "Bella greeted Mortimer."},
            },
            event.id,
        )

    record = asyncio.run(runtime.process(request, adapter, resolve))

    assert actions.get_consequences(record.decision.id) == record.result.applied_changes


@pytest.mark.parametrize("failure", [TimeoutError(), MemoryError()])
def test_provider_failure_falls_back_persists_and_releases_resources(
    failure: Exception,
) -> None:
    adapter = Sims4PocAdapter({"sim": {"id": "bella"}})
    request = CognitiveRequest("bella", 3, adapter.observe()[0])
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
    decision = Decision("bella", "greet", target_id="mortimer", id="decision-1")
    proposal = actions.propose("event-1", decision, "friendly_chat")

    result = Sims4PocAdapter({"available_actions": ["friendly_chat"]}).execute(decision)
    record = actions.confirm(result, "friendly_chat")

    assert proposal.decision == decision
    assert record.result == result
    assert actions.get_proposal(decision.id) is None
    assert actions.get(decision.id) == record


def test_failed_game_confirmation_persists_no_consequence() -> None:
    actions = ActionRecordStore(open_db(":memory:"))
    decision = Decision("bella", "greet", id="decision-1")
    actions.propose("event-1", decision, "friendly_chat")

    record = actions.confirm(
        ActionResult(decision.id, "failed", reason="game rejected interaction"),
        "friendly_chat",
    )

    assert record.result.status == "failed"
    assert actions.get_consequences(decision.id) == ()
