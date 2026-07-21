import dataclasses
import json

import pytest

from empneon.core.contracts import (
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
        }
    )
    event = WorldEvent("observation", ("alice",), agent_state=snapshot)

    encoded = json.loads(json.dumps(dataclasses.asdict(event)))

    assert encoded["agent_state"]["native"] == {
        "unknown_mod_state": "preserved"
    }
    assert encoded["agent_state"]["effects"] == []


@pytest.mark.parametrize(
    "section,key,value",
    [
        ("affect", "valence", 1.1),
        ("affect", "intensity", -0.1),
        ("relationships", "affinity", -1.1),
        ("relationships", "romance", 1.1),
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
