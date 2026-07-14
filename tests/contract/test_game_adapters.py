from collections.abc import Callable
from dataclasses import asdict, dataclass

import pytest

from empneon.adapters.godot import GodotBridge
from empneon.adapters.sims4 import Sims4PocAdapter
from empneon.core.clod import resolve_clod1
from empneon.core.contracts import CognitiveRequest, WorldEvent


@dataclass(frozen=True)
class RoundTrip:
    event: WorldEvent
    actor_id: str
    decision_id: str
    evidence_ids: tuple[str, ...]
    result_decision_id: str
    result_status: str


def _sims4_round_trip() -> RoundTrip:
    adapter = Sims4PocAdapter(
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
    return RoundTrip(
        event,
        decision.actor_id,
        decision.id,
        decision.evidence_ids,
        result.decision_id,
        result.status,
    )


def _godot_round_trip() -> RoundTrip:
    event = WorldEvent("encounter", ("agent-a", "agent-b"), id="contract-encounter")
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
    return RoundTrip(
        event,
        str(decision["actor_id"]),
        decision_id,
        tuple(str(item) for item in evidence_ids),
        str(result["decision_id"]),
        str(result["status"]),
    )


@pytest.mark.parametrize(
    "round_trip", [_sims4_round_trip, _godot_round_trip], ids=["sims4", "godot"]
)
def test_adapter_preserves_generic_contracts(round_trip: Callable[[], RoundTrip]) -> None:
    completed = round_trip()

    assert completed.event.actor_ids[0] == completed.actor_id
    assert completed.event.id in completed.evidence_ids
    assert completed.result_decision_id == completed.decision_id
    assert completed.result_status == "succeeded"
