"""Opportunity-driven records reference an event id Core never stores; replay and timeline cope."""

import asyncio

from empneon.core.clod import resolve_clod1
from empneon.core.contracts import (
    ActionResult,
    AgentStateSnapshot,
    CognitiveRequest,
    Decision,
    WorldEvent,
)
from empneon.core.directors import DirectorView, IdleCheckInDirector, run_directors
from empneon.core.identity.models import Agent
from empneon.core.identity.store import AgentStore
from empneon.core.memory.episodic import EpisodicMemoryStore
from empneon.core.replay import replay_action_record
from empneon.core.runtime import ActionRecordStore, CognitiveRuntime
from empneon.core.scheduler.resources import ResourceBudget, ResourceGovernor
from empneon.core.timeline import agent_timeline
from empneon.db.connection import open_db


class _Adapter:
    def observe(self) -> tuple[WorldEvent, ...]:
        return ()

    def execute(self, decision: Decision, /) -> ActionResult:
        return ActionResult(decision.id, "succeeded", ())


async def _resolve(request: CognitiveRequest) -> Decision:
    return resolve_clod1(request)


def _opportunity_record():  # type: ignore[no-untyped-def]
    conn = open_db(":memory:")
    AgentStore(conn).create(Agent("agent-a", "Agent A"))
    quiet = WorldEvent("chat", ("agent-a", "agent-b"), happened_at=0)
    view = DirectorView(500, (AgentStateSnapshot(1, "test", "agent-a"),), (quiet,))
    (request,) = run_directors((IdleCheckInDirector(idle_after_s=60),), view)
    actions = ActionRecordStore(conn)
    runtime = CognitiveRuntime(ResourceGovernor(ResourceBudget(256, 0)), actions)
    record = asyncio.run(runtime.process(request, _Adapter(), _resolve))
    return conn, request, record


def test_the_synthetic_event_is_never_stored() -> None:
    conn, request, _ = _opportunity_record()
    assert EpisodicMemoryStore(conn).get(request.event.id) is None
    assert conn.execute("SELECT count(*) FROM events").fetchone()[0] == 0


def test_replay_of_an_opportunity_driven_record_reports_no_event() -> None:
    conn, request, record = _opportunity_record()

    replay = replay_action_record(conn, record.decision.id)

    assert replay["event"] is None
    assert replay["event_id"] == request.event.id


def test_timeline_lists_the_decision_with_its_unstored_event_id() -> None:
    conn, request, record = _opportunity_record()

    entries = agent_timeline(conn, "agent-a")["entries"]

    decisions = [entry for entry in entries if entry["type"] == "decision"]
    assert [entry["id"] for entry in decisions] == [record.decision.id]
    assert decisions[0]["data"]["event_id"] == request.event.id
    assert not [entry for entry in entries if entry["type"] == "event"]
