from empneon.adapters.sims4 import Sims4PocAdapter
from empneon.core.clod import resolve_clod1
from empneon.core.contracts import CognitiveRequest, StateDelta


def test_conversation_response_becomes_validated_sims_action() -> None:
    adapter = Sims4PocAdapter(
        {
            "speaker": {"id": "bella"},
            "listener": {"id": "mortimer"},
            "message": "Hello",
            "location": "Goth Manor",
            "relationship": {"friendship": 72, "trust": 60},
            "event": {"type": "player_conversation", "source": "cheat_console"},
            "available_actions": ["friendly_chat"],
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
    assert event.type == "player_conversation"
    assert event.location == "Goth Manor"
    assert event.facts["relationship"] == {"friendship": 72, "trust": 60}
    assert result.applied_changes[-1] == StateDelta("animation", "set", "friendly_chat")
    assert adapter.response_for(decision, result) == response


def test_autonomous_npc_event_maps_to_available_action() -> None:
    adapter = Sims4PocAdapter(
        {
            "speaker": {"id": "bella"},
            "listener": {"id": "mortimer"},
            "event": {"type": "autonomous_social", "source": "sim_alarm"},
            "available_actions": ["friendly_chat"],
        }
    )
    event = adapter.observe()[0]
    decision = resolve_clod1(CognitiveRequest("bella", 1, event))
    result = adapter.execute(decision)

    assert event.actor_ids == ("bella", "mortimer")
    assert event.facts["source"] == "sim_alarm"
    assert decision.target_id == "mortimer"
    assert result.applied_changes == (StateDelta("animation", "set", "friendly_chat"),)
