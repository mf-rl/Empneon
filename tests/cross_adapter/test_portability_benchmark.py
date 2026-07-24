import json
from dataclasses import asdict
from pathlib import Path

import empneon_godot.bridge as bridge_module
import pytest
from empneon.core.clod import resolve_clod1
from empneon.core.contracts import (
    AgentStateSnapshot,
    CognitiveRequest,
    Decision,
    StateDelta,
    WorldEvent,
)
from empneon_godot import GodotBridge
from empneon_thesims4 import Sims4Adapter


def test_same_scenario_runs_through_both_adapters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
        "needs": {
            "energy": {
                "level": 0.815,
                "urgency": 0.185,
                "status": "satisfied",
                "native": {"value": 81.5, "minimum": 0, "maximum": 100},
            }
        },
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

    captured = {}
    resolve = bridge_module.resolve_clod1

    def capture(godot_request: CognitiveRequest) -> Decision:
        captured["event"] = godot_request.event
        return resolve(godot_request)

    monkeypatch.setattr(bridge_module, "resolve_clod1", capture)
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
    reconstructed_state = captured["event"].agent_state
    assert reconstructed_state is not None
    assert sims_state.affect == reconstructed_state.affect
    sims_energy = sims_state.needs["energy"]
    godot_energy = reconstructed_state.needs["energy"]
    assert isinstance(sims_energy, dict) and isinstance(godot_energy, dict)
    assert sims_energy["level"] == pytest.approx(godot_energy["level"])
    assert sims_energy["urgency"] == pytest.approx(godot_energy["urgency"])
    assert sims_energy["status"] == godot_energy["status"] == "satisfied"
    assert sims_energy["native"] == {"value": 63, "minimum": -100, "maximum": 100}
    assert godot_energy["native"] == {"value": 81.5, "minimum": 0, "maximum": 100}
    assert sims_state.capabilities == reconstructed_state.capabilities
    assert sims_state.adapter == "sims4"
    assert reconstructed_state.adapter == "godot"
    assert reconstructed_state.agent_id == request.agent_id
    assert reconstructed_state.native == {"unknown_engine_value": "preserved"}
