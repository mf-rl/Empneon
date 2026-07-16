import pytest

from empneon.core.contracts import (
    ActionResult,
    CognitiveRequest,
    Decision,
    StateDelta,
    WorldEvent,
)
from empneon.core.ports import GameAdapter


def test_generic_event_to_decision_contract() -> None:
    event = WorldEvent(
        type="social_interaction",
        actor_ids=("alice", "bob"),
        facts={"outcome": "rejected"},
    )
    request = CognitiveRequest("alice", preferred_clod=3, event=event)
    decision = Decision(
        actor_id=request.agent_id,
        intent="avoid",
        target_id="bob",
        evidence_ids=(event.id,),
        state_changes=(StateDelta("relationships.bob.trust", "increment", -0.1),),
        confidence=0.8,
    )

    assert request.event.type == "social_interaction"
    assert decision.evidence_ids == (event.id,)


@pytest.mark.parametrize("clod", [-1, 5])
def test_request_rejects_invalid_clod(clod: int) -> None:
    with pytest.raises(ValueError, match="preferred_clod"):
        CognitiveRequest("alice", preferred_clod=clod, event=WorldEvent("event"))


def test_request_rejects_negative_context_budget() -> None:
    with pytest.raises(ValueError, match="max_context_tokens"):
        CognitiveRequest(
            "alice",
            preferred_clod=3,
            event=WorldEvent("event"),
            max_context_tokens=-1,
        )


def test_decision_rejects_invalid_confidence() -> None:
    with pytest.raises(ValueError, match="confidence"):
        Decision("alice", "wait", confidence=1.1)


def test_game_adapter_reports_applied_decision() -> None:
    event = WorldEvent("social_interaction", actor_ids=("alice", "bob"))
    change = StateDelta("relationships.bob.trust", "increment", 0.1)
    decision = Decision("alice", "befriend", target_id="bob", state_changes=(change,))

    class FakeAdapter:
        def observe(self) -> tuple[WorldEvent, ...]:
            return (event,)

        def execute(self, decision: Decision, /) -> ActionResult:
            return ActionResult(decision.id, "succeeded", decision.state_changes)

    adapter: GameAdapter = FakeAdapter()
    result = adapter.execute(decision)

    assert adapter.observe() == (event,)
    assert result.decision_id == decision.id
    assert result.applied_changes == (change,)


def test_unsuccessful_action_requires_reason() -> None:
    with pytest.raises(ValueError, match="requires a reason"):
        ActionResult("decision", "failed")
