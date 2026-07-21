import pytest

import empneon_godot.bridge as bridge_module
from empneon_godot import GodotBridge


def test_godot_bridge_round_trip_uses_core_contracts() -> None:
    bridge = GodotBridge()
    decision = bridge.decide(
        {
            "agent_id": "godot-a",
            "event": {
                "id": "godot-encounter-1",
                "type": "encounter",
                "actor_ids": ["godot-a", "godot-b"],
                "location": "godot-square",
                "facts": {"distance": 1},
                "happened_at": 1,
            },
        }
    )

    result = bridge.confirm(
        {
            "decision_id": decision["id"],
            "status": "succeeded",
            "applied_changes": [
                {"path": "awareness.godot-b", "operation": "set", "value": True}
            ],
        }
    )

    assert decision["intent"] == "acknowledge"
    assert decision["target_id"] == "godot-b"
    assert result["status"] == "succeeded"
    with pytest.raises(ValueError, match="already confirmed"):
        bridge.confirm({"decision_id": decision["id"], "status": "succeeded"})


def test_godot_bridge_reconstructs_serialized_agent_state(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}
    resolve = bridge_module.resolve_clod1

    def capture(request):
        captured["state"] = request.event.agent_state
        return resolve(request)

    monkeypatch.setattr(bridge_module, "resolve_clod1", capture)
    GodotBridge().decide(
        {
            "agent_id": "godot-a",
            "event": {
                "id": "godot-state-1",
                "type": "encounter",
                "actor_ids": ["godot-a"],
                "facts": {},
                "agent_state": {
                    "schema_version": 1,
                    "adapter": "godot",
                    "agent_id": "godot-a",
                    "native": {"unknown_engine_value": "preserved"},
                },
            },
        }
    )

    state = captured["state"]
    assert state is not None
    assert state.native == {"unknown_engine_value": "preserved"}
