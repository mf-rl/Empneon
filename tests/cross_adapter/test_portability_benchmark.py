import json
from dataclasses import asdict
from pathlib import Path

from empneon_godot import GodotBridge
from empneon_thesims4 import Sims4Adapter
from empneon.core.clod import resolve_clod1
from empneon.core.contracts import (
    AgentStateSnapshot,
    CognitiveRequest,
    StateDelta,
    WorldEvent,
)


def test_same_scenario_runs_through_both_adapters() -> None:
    path = (
        Path(__file__).parents[2]
        / "adapters"
        / "godot"
        / "portability"
        / "scenario.json"
    )
    scenario = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(scenario, dict)
    event_data = scenario["event"]
    assert isinstance(event_data, dict)
    actor_ids = event_data["actor_ids"]
    facts = event_data["facts"]
    assert isinstance(actor_ids, list) and isinstance(facts, dict)
    state_data = {
        "schema_version": 1,
        "adapter": "godot",
        "agent_id": str(scenario["agent_id"]),
        "affect": {"tags": ["alert"]},
        "needs": {"energy": {"level": 0.63, "urgency": 0.37}},
        "capabilities": {"actions": ["idle"]},
        "native": {"unknown_engine_value": "preserved"},
    }
    event_data["agent_state"] = state_data

    event = WorldEvent(
        id=str(event_data["id"]),
        type=str(event_data["type"]),
        actor_ids=tuple(str(actor_id) for actor_id in actor_ids),
        location=str(event_data["location"]),
        facts=facts,
        happened_at=int(event_data["happened_at"]),
        agent_state=AgentStateSnapshot.from_mapping(state_data),
    )
    request = CognitiveRequest(
        str(scenario["agent_id"]), int(scenario["preferred_clod"]), event
    )
    expected = resolve_clod1(request)

    sims = Sims4Adapter(
        {
            "speaker": {
                "id": event.actor_ids[0],
                "current_mood": "alert",
                "needs": {"energy": 63},
            },
            "listener": {"id": event.actor_ids[1]},
            "event": {"type": event.type},
            "available_actions": ["idle"],
        }
    )
    sims_state = sims.observe()[0].agent_state
    assert sims_state is not None
    sims_result = sims.execute(expected)

    bridge = GodotBridge()
    godot_decision = bridge.decide({"agent_id": request.agent_id, "event": asdict(event)})
    godot_result = bridge.confirm(
        {
            "decision_id": godot_decision["id"],
            "status": "succeeded",
            "applied_changes": [
                {"path": "awareness.godot-b", "operation": "set", "value": True}
            ],
        }
    )

    assert godot_decision == asdict(expected)
    assert sims_result.decision_id == godot_result["decision_id"] == expected.id
    assert sims_result.status == godot_result["status"] == "succeeded"
    assert sims_result.applied_changes == (StateDelta("animation", "set", "idle"),)
    assert godot_result["applied_changes"] == (
        {"path": "awareness.godot-b", "operation": "set", "value": True},
    )
    assert event.agent_state is not None
    assert sims_state.affect == event.agent_state.affect
    assert sims_state.needs == event.agent_state.needs
    assert sims_state.capabilities == event.agent_state.capabilities
    assert sims_state.adapter == "sims4"
    assert event.agent_state.adapter == "godot"
