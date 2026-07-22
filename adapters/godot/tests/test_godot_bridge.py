import pytest
from empneon.core.contracts import CognitiveRequest, Decision

import empneon_godot.bridge as bridge_module
from empneon_godot import GodotBridge


def test_godot_bridge_round_trip_uses_core_contracts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}
    resolve = bridge_module.resolve_clod1

    def capture(request: CognitiveRequest) -> Decision:
        captured["event"] = request.event
        return resolve(request)

    monkeypatch.setattr(bridge_module, "resolve_clod1", capture)
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
    state = captured["event"].agent_state
    assert state is not None
    assert state.adapter == "godot"
    assert state.agent_id == "godot-a"
    assert state.capabilities == {"actions": ["acknowledge"]}
    assert state.native == {"facts": {"distance": 1}}
    with pytest.raises(ValueError, match="already confirmed"):
        bridge.confirm({"decision_id": decision["id"], "status": "succeeded"})


def test_godot_bridge_reconstructs_serialized_agent_state(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}
    resolve = bridge_module.resolve_clod1

    def capture(request: CognitiveRequest) -> Decision:
        captured["event"] = request.event
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
                    "affect": {"tags": ["alert"]},
                    "needs": {"energy": {"level": 0.63, "urgency": 0.37}},
                    "capabilities": {"actions": ["idle"]},
                    "native": {"unknown_engine_value": "preserved"},
                },
            },
        }
    )

    state = captured["event"].agent_state
    assert state is not None
    assert state.adapter == "godot"
    assert state.agent_id == "godot-a"
    assert state.affect == {"tags": ["alert"]}
    assert state.needs == {"energy": {"level": 0.63, "urgency": 0.37}}
    assert state.capabilities == {"actions": ["idle"]}
    assert state.native == {"unknown_engine_value": "preserved"}


@pytest.mark.parametrize(
    ("state_agent_id", "state_adapter", "message"),
    [
        ("godot-b", "godot", "agent_id"),
        ("godot-a", "sims4", "adapter"),
    ],
)
def test_godot_bridge_rejects_serialized_state_outside_request_boundary(
    state_agent_id: str,
    state_adapter: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        GodotBridge().decide(
            {
                "agent_id": "godot-a",
                "event": {
                    "id": "godot-invalid-state",
                    "type": "encounter",
                    "actor_ids": ["godot-a", "godot-b"],
                    "facts": {},
                    "agent_state": {
                        "schema_version": 1,
                        "adapter": state_adapter,
                        "agent_id": state_agent_id,
                    },
                },
            }
        )
