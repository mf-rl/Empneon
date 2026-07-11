import pytest

from empneon.core.contracts import CognitiveRequest, Decision, StateDelta, WorldEvent


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


def test_decision_rejects_invalid_confidence() -> None:
    with pytest.raises(ValueError, match="confidence"):
        Decision("alice", "wait", confidence=1.1)
