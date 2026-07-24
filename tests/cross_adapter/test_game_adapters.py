from collections.abc import Callable
from dataclasses import asdict, dataclass

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


@dataclass(frozen=True)
class RoundTrip:
    event: WorldEvent
    agent_state: AgentStateSnapshot
    actor_id: str
    decision_id: str
    evidence_ids: tuple[str, ...]
    result_decision_id: str
    result_status: str


def _sims4_round_trip(_monkeypatch: pytest.MonkeyPatch) -> RoundTrip:
    adapter = Sims4Adapter(
        {
            "speaker": {"id": "agent-a"},
            "listener": {"id": "agent-b"},
            "event": {"type": "encounter"},
            "available_actions": ["idle"],
        }
    )
    event = adapter.observe()[0]
    decision = resolve_clod1(CognitiveRequest("agent-a", 1, event))
    result = adapter.execute(decision)
    assert event.agent_state is not None
    return RoundTrip(
        event,
        event.agent_state,
        decision.actor_id,
        decision.id,
        decision.evidence_ids,
        result.decision_id,
        result.status,
    )


def _godot_round_trip(monkeypatch: pytest.MonkeyPatch) -> RoundTrip:
    event = WorldEvent(
        "encounter",
        ("agent-a", "agent-b"),
        id="contract-encounter",
        agent_state=AgentStateSnapshot(
            1,
            "godot",
            "agent-a",
            native={"unknown_engine_value": "preserved"},
        ),
    )
    captured = {}
    resolve = bridge_module.resolve_clod1

    def capture(request: CognitiveRequest) -> Decision:
        captured["event"] = request.event
        return resolve(request)

    monkeypatch.setattr(bridge_module, "resolve_clod1", capture)
    bridge = GodotBridge()
    decision = bridge.decide({"agent_id": "agent-a", "event": asdict(event)})
    decision_id = str(decision["id"])
    result = bridge.confirm(
        {
            "decision_id": decision_id,
            "status": "succeeded",
            "applied_changes": [
                {"path": "awareness.agent-b", "operation": "set", "value": True}
            ],
        }
    )
    evidence_ids = decision["evidence_ids"]
    assert isinstance(evidence_ids, (list, tuple))
    reconstructed = captured["event"]
    assert reconstructed.agent_state is not None
    assert reconstructed.agent_state.native == {
        "unknown_engine_value": "preserved"
    }
    return RoundTrip(
        reconstructed,
        reconstructed.agent_state,
        str(decision["actor_id"]),
        decision_id,
        tuple(str(item) for item in evidence_ids),
        str(result["decision_id"]),
        str(result["status"]),
    )


@pytest.mark.parametrize(
    "round_trip", [_sims4_round_trip, _godot_round_trip], ids=["sims4", "godot"]
)
def test_adapter_preserves_generic_contracts(
    round_trip: Callable[[pytest.MonkeyPatch], RoundTrip],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed = round_trip(monkeypatch)

    assert completed.event.actor_ids[0] == completed.actor_id
    assert completed.event.id in completed.evidence_ids
    assert completed.result_decision_id == completed.decision_id
    assert completed.result_status == "succeeded"
    assert completed.agent_state.schema_version == 1
    assert completed.agent_state.adapter in {"sims4", "godot"}
    assert completed.agent_state.agent_id == completed.actor_id


def test_godot_round_trip_preserves_common_attraction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, WorldEvent] = {}
    resolve = bridge_module.resolve_clod1

    def capture(request: CognitiveRequest) -> Decision:
        captured["event"] = request.event
        return resolve(request)

    monkeypatch.setattr(bridge_module, "resolve_clod1", capture)
    bridge = GodotBridge()
    bridge.decide(
        {
            "agent_id": "agent-a",
            "event": asdict(
                WorldEvent(
                    "encounter",
                    ("agent-a", "agent-b"),
                    agent_state=AgentStateSnapshot(
                        1,
                        "godot",
                        "agent-a",
                        relationships={"agent-b": {"attraction": 0.4}},
                    ),
                )
            ),
        }
    )

    assert captured["event"].agent_state is not None
    assert captured["event"].agent_state.relationships == {
        "agent-b": {"attraction": 0.4}
    }


def test_non_sims_adapter_can_carry_common_social_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, WorldEvent] = {}

    def capture(request: CognitiveRequest) -> Decision:
        captured["event"] = request.event
        return Decision(
            request.agent_id,
            "respond_playfully",
            target_id="agent-b",
            evidence_ids=(request.event.id,),
            state_changes=(
                StateDelta("social.response_category", "set", "funny"),
                StateDelta("animation", "set", "social.funny"),
            ),
        )

    monkeypatch.setattr(bridge_module, "resolve_clod1", capture)
    decision = GodotBridge().decide(
        {
            "agent_id": "agent-a",
            "event": asdict(
                WorldEvent(
                    "conversation",
                    ("agent-a", "agent-b"),
                    facts={
                        "social": {
                            "incoming_category": "friendly",
                            "available_response_categories": ["friendly", "funny"],
                        }
                    },
                )
            ),
        }
    )

    assert captured["event"].facts["social"]["incoming_category"] == "friendly"
    assert {change["path"]: change["value"] for change in decision["state_changes"]} == {
        "social.response_category": "funny",
        "animation": "social.funny",
    }
