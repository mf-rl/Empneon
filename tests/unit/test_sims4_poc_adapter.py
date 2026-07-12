from empneon.adapters.sims4 import Sims4PocAdapter


def test_conversation_response_becomes_validated_sims_action() -> None:
    adapter = Sims4PocAdapter(
        {
            "speaker": {"id": "bella"},
            "listener": {"id": "mortimer"},
            "message": "Hello",
        }
    )
    event = adapter.observe()[0]
    response = {
        "dialogue": "Hello, Mortimer.",
        "emotion": "happy",
        "intent": "greet",
        "relationship": {
            "friendship_delta": 1,
            "romance_delta": 0,
            "trust_delta": 0,
        },
        "memory": {"importance": 0.4, "summary": "Bella greeted Mortimer."},
        "animation": "friendly_chat",
    }

    decision = adapter.decision_from_response(response, event.id)
    result = adapter.execute(decision)

    assert result.status == "succeeded"
    assert result.applied_changes == decision.state_changes
    assert adapter.response_for(decision) == response
