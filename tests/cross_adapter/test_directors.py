"""The same director drives both adapters' real paths through the same Core behavior."""

import asyncio
from collections.abc import Callable
from dataclasses import asdict, dataclass

import pytest
from empneon.core.clod import resolve_clod1
from empneon.core.contracts import AgentStateSnapshot, CognitiveRequest, WorldEvent
from empneon.core.directors import DirectorView, IdleCheckInDirector, run_directors
from empneon.core.runtime import ActionRecordStore, CognitiveRuntime
from empneon.core.scheduler.resources import ResourceBudget, ResourceGovernor
from empneon.db.connection import open_db
from empneon_godot import GodotBridge
from empneon_thesims4 import Sims4Adapter

NOW = 10_000


@dataclass(frozen=True)
class Outcome:
    request: CognitiveRequest
    decision_actor: str
    evidence_ids: tuple[str, ...]
    status: str


def _view(state: AgentStateSnapshot) -> DirectorView:
    quiet = WorldEvent("chat", (state.agent_id, "someone"), happened_at=NOW - 600)
    return DirectorView(NOW, (state,), (quiet,))


def _requests(state: AgentStateSnapshot) -> tuple[CognitiveRequest, ...]:
    return run_directors((IdleCheckInDirector(idle_after_s=60),), _view(state))


async def _resolve(request: CognitiveRequest):  # type: ignore[no-untyped-def]
    return resolve_clod1(request)


def _sims4() -> Outcome:
    adapter = Sims4Adapter(
        {
            "speaker": {"id": "agent-a"},
            "listener": {"id": "agent-b"},
            "event": {"type": "encounter"},
            "available_actions": ["idle"],
        }
    )
    state = adapter.observe()[0].agent_state
    assert state is not None
    (request,) = _requests(state)
    runtime = CognitiveRuntime(
        ResourceGovernor(ResourceBudget(256, 0)), ActionRecordStore(open_db(":memory:"))
    )
    record = asyncio.run(runtime.process(request, adapter, _resolve))
    decision = record.decision
    return Outcome(request, decision.actor_id, decision.evidence_ids, record.result.status)


def _godot() -> Outcome:
    state = AgentStateSnapshot(1, "godot", "agent-a")
    (request,) = _requests(state)
    bridge = GodotBridge()
    decision = bridge.decide({"agent_id": "agent-a", "event": asdict(request.event)})
    result = bridge.confirm({"decision_id": decision["id"], "status": "succeeded"})
    evidence = decision["evidence_ids"]
    assert isinstance(evidence, (list, tuple))
    return Outcome(
        request,
        str(decision["actor_id"]),
        tuple(str(item) for item in evidence),
        str(result["status"]),
    )


@pytest.mark.parametrize("run", [_sims4, _godot], ids=["sims4", "godot"])
def test_idle_director_request_is_handled_by_each_adapter(run: Callable[[], Outcome]) -> None:
    outcome = run()

    assert outcome.request.event.type == "opportunity.idle"
    assert outcome.request.event.facts["director_id"] == "core.idle-check-in"
    assert outcome.request.event.facts["idle_seconds"] == 600
    assert outcome.decision_actor == outcome.request.agent_id == "agent-a"
    assert outcome.request.event.id in outcome.evidence_ids
    assert outcome.status in {"succeeded", "rejected"}


def test_requests_have_the_same_shape_for_both_adapters() -> None:
    sims, godot = _sims4().request, _godot().request

    assert (sims.event.type, sims.urgency, sims.deadline_ms, sims.preferred_clod) == (
        godot.event.type,
        godot.urgency,
        godot.deadline_ms,
        godot.preferred_clod,
    )
    assert {sims.event.agent_state.adapter, godot.event.agent_state.adapter} == {  # type: ignore[union-attr]
        "sims4",
        "godot",
    }
