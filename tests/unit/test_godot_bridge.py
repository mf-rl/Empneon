import pytest

from empneon.adapters.godot import GodotBridge


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
