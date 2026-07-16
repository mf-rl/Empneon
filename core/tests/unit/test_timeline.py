import json

import pytest

from empneon.core.contracts import ActionResult, Decision
from empneon.core.identity.models import Agent
from empneon.core.identity.store import AgentStore
from empneon.core.memory.episodic import (
    Belief,
    BeliefStore,
    EpisodicMemoryStore,
    Event,
    Observation,
    ObservationStore,
)
from empneon.core.runtime import ActionRecordStore
from empneon.core.timeline import agent_timeline
from empneon.db.connection import open_db


def test_agent_timeline_merges_persisted_records_newest_first() -> None:
    conn = open_db(":memory:")
    AgentStore(conn).create(Agent("alice", "Alice"))
    event = EpisodicMemoryStore(conn).create(
        Event("Alice found a key", ["alice"], happened_at=10, id="event-1")
    )
    observation = ObservationStore(conn).create(
        Observation(event.id, "alice", "The key was under a bench", observed_at=15, id="obs-1")
    )
    BeliefStore(conn).create(
        Belief(
            "alice",
            "The bench hides keys",
            "observation",
            observation.id,
            0.8,
            "Alice generalized from the discovery",
            created_at=20,
            id="belief-1",
        )
    )
    decision = Decision("alice", "keep_key", evidence_ids=(event.id,), id="decision-1")
    ActionRecordStore(conn).record(
        event.id, decision, ActionResult(decision.id, "succeeded", completed_at=30)
    )

    timeline = agent_timeline(conn, "alice")

    assert [entry["type"] for entry in timeline["entries"]] == ["decision", "belief", "event"]
    assert timeline["agent_id"] == "alice"
    assert json.loads(json.dumps(timeline))["entries"][0]["id"] == "decision-1"
    assert agent_timeline(conn, "alice", limit=2)["entries"] == timeline["entries"][:2]
    with pytest.raises(ValueError, match="positive"):
        agent_timeline(conn, "alice", limit=0)
