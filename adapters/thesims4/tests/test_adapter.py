import pytest
from empneon.core.clod import resolve_clod1
from empneon.core.contracts import CognitiveRequest, Decision, StateDelta

import empneon_thesims4
from empneon_thesims4 import Sims4Adapter


def test_feature_hash_is_deterministic_and_normalized() -> None:
    assert hasattr(empneon_thesims4, "feature_hash")
    feature_hash = empneon_thesims4.feature_hash
    first = feature_hash("Bella remembers a secret garden")
    second = feature_hash("Bella remembers a secret garden")

    assert first == second
    assert len(first) == 384
    assert sum(value * value for value in first) == pytest.approx(1.0)


def test_player_dialogue_receives_high_dynamic_cognition_value() -> None:
    assert hasattr(empneon_thesims4, "cognition_priority")

    urgency, preferred_clod, value = empneon_thesims4.cognition_priority(
        {"event": {"type": "player_conversation"}},
        novel=True,
        emotion_intensity=0.5,
        goal_relevant=True,
    )

    assert urgency == 1.0
    assert preferred_clod == 3
    assert value == pytest.approx(0.9)


def test_old_payload_has_neutral_optional_cognition_facts() -> None:
    event = Sims4Adapter(
        {"speaker": {"id": "bella"}, "available_actions": ["friendly_chat"]}
    ).observe()[0]

    assert event.facts["needs"] == {}
    assert event.facts["moodlets"] == []
    assert event.facts["aspiration"] == "unknown"
    assert event.facts["career"] == "unknown"
    assert event.facts["skills"] == {}
    assert event.facts["household"] == {}
    assert event.facts["nearby_sims"] == []


def test_malformed_optional_cognition_facts_are_neutral() -> None:
    event = Sims4Adapter(
        {
            "speaker": {
                "id": "bella",
                "needs": "invalid",
                "moodlets": 1,
                "skills": "invalid",
                "household": "invalid",
            },
            "nearby_sims": "invalid",
            "available_actions": "invalid",
        }
    ).observe()[0]

    assert event.facts["needs"] == {}
    assert event.facts["moodlets"] == []
    assert event.facts["skills"] == {}
    assert event.facts["household"] == {}
    assert event.facts["nearby_sims"] == []
    assert event.facts["available_actions"] == []


def test_sims_payload_becomes_normalized_agent_state_without_losing_native_values() -> None:
    event = Sims4Adapter(
        {
            "speaker": {
                "id": "karmine",
                "current_mood": "uncomfortable",
                "needs": {"hunger": 63},
                "identity": {
                    "gender": {"key": "female", "label": "Female"},
                    "age": {"kind": "life_stage", "value": "adult", "label": "Adult"},
                    "traits": [{"id": "good", "label": "Good"}],
                },
                "native": {
                    "mood": "Mood_Uncomfortable",
                    "moodlets": [{"label": "Custom DLC Moodlet"}],
                },
            },
            "listener": {"id": "bernard"},
            "relationship": {
                "friendship": 7,
                "romance": 12,
                "trust": 50,
                "attraction": 2 / 3,
                "native": {
                    "attraction": {
                        "source": "wickedwhims",
                        "value": 2,
                        "label": "HIGH",
                    }
                },
            },
            "available_actions": ["friendly_chat", "flirt"],
        }
    ).observe()[0]

    assert event.agent_state is not None
    assert event.agent_state.affect == {"tags": ["uncomfortable"]}
    assert event.agent_state.needs == {
        "hunger": {
            "level": pytest.approx(0.815),
            "urgency": pytest.approx(0.185),
            "status": "satisfied",
            "native": {"value": 63, "minimum": -100, "maximum": 100},
        }
    }
    assert event.agent_state.relationships["bernard"] == {
        "affinity": 0.07,
        "romance": 0.12,
        "trust": 0.5,
        "attraction": pytest.approx(2 / 3),
    }
    assert event.agent_state.capabilities == {
        "actions": ["friendly_chat", "flirt"]
    }
    assert event.agent_state.identity["gender"]["key"] == "female"
    assert event.agent_state.identity["age"]["value"] == "adult"
    assert event.agent_state.identity["traits"] == [{"id": "good", "label": "Good"}]
    assert event.agent_state.native["moodlets"] == [
        {"label": "Custom DLC Moodlet"}
    ]
    assert event.agent_state.native["relationships"]["bernard"]["attraction"] == {
        "source": "wickedwhims",
        "value": 2,
        "label": "HIGH",
    }


def test_sims_adapter_omits_unavailable_attraction() -> None:
    state = Sims4Adapter(
        {
            "speaker": {"id": "alice"},
            "listener": {"id": "bob"},
            "relationship": {"friendship": 0, "romance": 0},
        }
    ).agent_state()

    assert "attraction" not in state.relationships["bob"]


@pytest.mark.parametrize(
    "native,status,level",
    [
        (-100, "critical", 0.0),
        (-51, "critical", 0.245),
        (-50, "low", 0.25),
        (-26, "low", 0.37),
        (-25, "satisfied", 0.375),
        (100, "satisfied", 1.0),
    ],
)
def test_sims_need_scale_maps_to_common_status(
    native: int, status: str, level: float
) -> None:
    state = Sims4Adapter(
        {"speaker": {"id": "bella", "needs": {"hunger": native}}}
    ).agent_state()

    assert state.needs["hunger"] == {
        "level": pytest.approx(level),
        "urgency": pytest.approx(1 - level),
        "status": status,
        "native": {"value": native, "minimum": -100, "maximum": 100},
    }


def test_live_sim_payload_uses_same_actor_for_event_and_agent_state() -> None:
    event = Sims4Adapter(
        {
            "sim": {
                "id": "live-sim",
                "current_mood": "focused",
                "needs": {"energy": 63},
            },
            "speaker": {"id": "stale-speaker", "current_mood": "sad"},
            "available_actions": ["idle"],
        }
    ).observe()[0]

    assert event.agent_state is not None
    assert event.actor_ids[0] == event.agent_state.agent_id == "live-sim"
    assert event.agent_state.affect == {"tags": ["focused"]}
    assert event.agent_state.needs == {
        "energy": {
            "level": pytest.approx(0.815),
            "urgency": pytest.approx(0.185),
            "status": "satisfied",
            "native": {"value": 63, "minimum": -100, "maximum": 100},
        }
    }


def test_conversation_response_becomes_validated_sims_action() -> None:
    adapter = Sims4Adapter(
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
        "expressed_emotion": "happy",
        "intent": "greet",
        "relationship": {
            "friendship_delta": 1,
            "romance_delta": 0,
            "trust_delta": 0,
        },
        "memory": {"importance": 0.4, "summary": "Bella greeted Mortimer."},
        "suggested_action": "friendly_chat",
    }

    decision = adapter.decision_from_response(response, event.id)
    result = adapter.execute(decision)

    assert result.status == "succeeded"
    assert event.type == "player_conversation"
    assert event.location == "Goth Manor"
    assert event.facts["relationship"] == {"friendship": 72, "trust": 60}
    assert result.applied_changes[-1] == StateDelta("animation", "set", "friendly_chat")
    returned = adapter.response_for(decision, result)
    assert returned["expressed_emotion"] == returned["emotion"] == "happy"
    assert returned["suggested_action"] == returned["animation"] == "friendly_chat"


def test_action_metadata_wins_over_descriptive_intent() -> None:
    adapter = Sims4Adapter(
        {"speaker": {"id": "bella"}, "available_actions": ["friendly_chat", "flirt"]}
    )
    decision = adapter.decision_from_response(
        {
            "dialogue": "That sounds lovely.",
            "intent": "arbitrary descriptive intent",
            "suggested_action": "flirt",
        },
        adapter.observe()[0].id,
    )

    assert adapter.action_for(decision) == "flirt"


def test_autonomous_npc_event_maps_to_available_action() -> None:
    adapter = Sims4Adapter(
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


def test_native_social_intent_whitelist() -> None:
    adapter = Sims4Adapter({"available_actions": ["friendly_chat", "apologize", "flirt"]})

    for intent, action in (
        ("greet", "friendly_chat"),
        ("apologize", "apologize"),
        ("flirt", "flirt"),
    ):
        assert adapter.action_for(Decision("sim", intent)) == action


def test_retained_relationship_changes_later_autonomous_choice() -> None:
    actions = ["friendly_chat", "apologize", "flirt"]
    strained = Sims4Adapter({"available_actions": actions, "relationship": {"raw_score": -20}})
    repaired = Sims4Adapter({"available_actions": actions, "relationship": {"raw_score": 5}})
    decision = Decision("sim", "acknowledge")

    assert strained.action_for(decision) == "apologize"
    assert repaired.action_for(decision) == "friendly_chat"


def test_clod1_dialogue_fallback_reports_model_unavailability_without_memory() -> None:
    response = Sims4Adapter({"available_actions": ["friendly_chat"]}).response_for(
        Decision("sim", "acknowledge")
    )

    assert "unavailable" in response["dialogue"].casefold()
    assert "reliably" in response["dialogue"].casefold()
    assert response["memory"] == {"importance": 0.0, "summary": ""}
