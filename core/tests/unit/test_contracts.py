import dataclasses
import json

import pytest

from empneon.core.contracts import (
    SOCIAL_CATEGORIES,
    ActionResult,
    AgentStateSnapshot,
    CognitiveRequest,
    Decision,
    StateDelta,
    WorldEvent,
)
from empneon.core.ports import GameAdapter


def test_agent_state_snapshot_is_json_compatible_and_embedded_in_event() -> None:
    snapshot = AgentStateSnapshot.from_mapping(
        {
            "schema_version": 1,
            "adapter": "test",
            "agent_id": "alice",
            "affect": {"tags": ["calm"], "valence": 0.2, "intensity": 0.5},
            "needs": {"energy": {"level": 0.8, "urgency": 0.2}},
            "native": {"unknown_mod_state": "preserved"},
            "identity": {
                "gender": {"key": "female", "label": "Female"},
                "age": {"kind": "life_stage", "value": "adult", "label": "Adult"},
                "traits": [{"id": "outgoing", "label": "Outgoing"}],
            },
        }
    )
    event = WorldEvent("observation", ("alice",), agent_state=snapshot)

    encoded = json.loads(json.dumps(dataclasses.asdict(event)))

    assert encoded["agent_state"]["native"] == {
        "unknown_mod_state": "preserved"
    }
    assert encoded["agent_state"]["effects"] == []
    assert encoded["agent_state"]["identity"] == {
        "gender": {"key": "female", "label": "Female"},
        "age": {"kind": "life_stage", "value": "adult", "label": "Adult"},
        "traits": [{"id": "outgoing", "label": "Outgoing"}],
    }


def test_agent_state_snapshot_preserves_directed_attraction_and_native_source() -> None:
    snapshot = AgentStateSnapshot.from_mapping(
        {
            "schema_version": 1,
            "adapter": "example-game",
            "agent_id": "alice",
            "relationships": {"bob": {"attraction": -0.75}},
            "native": {
                "relationships": {
                    "bob": {
                        "attraction": {
                            "source": "example_game",
                            "value": "repelled",
                            "label": "Repelled",
                        }
                    }
                }
            },
        }
    )

    encoded = json.loads(json.dumps(dataclasses.asdict(snapshot)))

    assert encoded["relationships"]["bob"]["attraction"] == -0.75
    assert encoded["native"]["relationships"]["bob"]["attraction"] == {
        "source": "example_game",
        "value": "repelled",
        "label": "Repelled",
    }


def test_agent_state_snapshot_rejects_non_json_identity() -> None:
    with pytest.raises(ValueError, match="JSON-compatible"):
        AgentStateSnapshot(
            1,
            "test",
            "alice",
            identity={"traits": [{"id": object()}]},
        )


def test_agent_state_snapshot_ignores_non_mapping_needs_and_relationships() -> None:
    snapshot = AgentStateSnapshot(
        1,
        "test",
        "alice",
        needs={"hunger": "not-a-mapping"},
        relationships={"bob": "not-a-mapping"},
    )

    assert snapshot.needs == {"hunger": "not-a-mapping"}
    assert snapshot.relationships == {"bob": "not-a-mapping"}


def test_agent_state_snapshot_accepts_common_need_status_and_native_scale() -> None:
    snapshot = AgentStateSnapshot.from_mapping(
        {
            "schema_version": 1,
            "adapter": "example-game",
            "agent_id": "alice",
            "needs": {
                "energy": {
                    "level": 0.4,
                    "urgency": 0.6,
                    "status": "low",
                    "native": {"value": 40, "minimum": 0, "maximum": 100},
                }
            },
        }
    )

    energy = snapshot.needs["energy"]
    assert isinstance(energy, dict)
    assert energy["status"] == "low"
    assert energy["native"] == {"value": 40, "minimum": 0, "maximum": 100}


def test_agent_state_snapshot_rejects_unknown_need_status() -> None:
    with pytest.raises(ValueError, match="need status"):
        AgentStateSnapshot.from_mapping(
            {
                "schema_version": 1,
                "adapter": "test",
                "agent_id": "alice",
                "needs": {
                    "energy": {
                        "level": 0.5,
                        "urgency": 0.5,
                        "status": "orange",
                    }
                },
            }
        )


@pytest.mark.parametrize(
    "section,key,value",
    [
        ("affect", "valence", 1.1),
        ("affect", "intensity", -0.1),
        ("relationships", "affinity", -1.1),
        ("relationships", "romance", 1.1),
        ("relationships", "attraction", -1.1),
        ("relationships", "attraction", 1.1),
    ],
)
def test_agent_state_snapshot_rejects_out_of_range_values(
    section: str, key: str, value: float
) -> None:
    data: dict[str, object] = {
        "schema_version": 1,
        "adapter": "test",
        "agent_id": "alice",
    }
    data[section] = (
        {"bob": {key: value}} if section == "relationships" else {key: value}
    )

    with pytest.raises(ValueError, match=key):
        AgentStateSnapshot.from_mapping(data)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_agent_state_snapshot_rejects_non_finite_attraction(value: float) -> None:
    with pytest.raises(ValueError, match="attraction|JSON-compatible"):
        AgentStateSnapshot(
            1,
            "test",
            "alice",
            relationships={"bob": {"attraction": value}},
        )


def test_agent_state_snapshot_rejects_out_of_range_effect_intensity() -> None:
    with pytest.raises(ValueError, match="intensity"):
        AgentStateSnapshot.from_mapping(
            {
                "schema_version": 1,
                "adapter": "test",
                "agent_id": "alice",
                "effects": [{"name": "energized", "intensity": 1.01}],
            }
        )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_agent_state_snapshot_rejects_nested_non_finite_values(value: float) -> None:
    with pytest.raises(ValueError, match="JSON-compatible"):
        AgentStateSnapshot.from_mapping(
            {
                "schema_version": 1,
                "adapter": "test",
                "agent_id": "alice",
                "native": {"nested": [{"sensor": value}]},
            }
        )


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


def test_world_event_accepts_common_social_context() -> None:
    event = WorldEvent(
        "conversation",
        ("alice", "bob"),
        facts={
            "social": {
                "incoming_category": "romance",
                "available_response_categories": list(SOCIAL_CATEGORIES),
            }
        },
    )

    assert event.facts["social"] == {
        "incoming_category": "romance",
        "available_response_categories": list(SOCIAL_CATEGORIES),
    }


@pytest.mark.parametrize("category", ["actions", "neutral", "hostile", "romantic"])
def test_world_event_rejects_unknown_social_category(category: str) -> None:
    with pytest.raises(ValueError, match="social category"):
        WorldEvent(
            "conversation",
            facts={
                "social": {
                    "incoming_category": category,
                    "available_response_categories": ["friendly"],
                }
            },
        )


@pytest.mark.parametrize("clod", [-1, 5])
def test_request_rejects_invalid_clod(clod: int) -> None:
    event = WorldEvent("event")
    with pytest.raises(ValueError, match="preferred_clod"):
        CognitiveRequest("alice", preferred_clod=clod, event=event)


def test_request_rejects_negative_context_budget() -> None:
    event = WorldEvent("event")
    with pytest.raises(ValueError, match="max_context_tokens"):
        CognitiveRequest(
            "alice",
            preferred_clod=3,
            event=event,
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
