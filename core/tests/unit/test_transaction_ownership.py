"""Stores must leave commit/rollback to the caller when `commit=False`."""

import sqlite3

import pytest

from empneon.core.contracts import CognitiveRequest, WorldEvent
from empneon.core.identity.emotions import EmotionalState, EmotionalStateStore
from empneon.core.identity.goals import Goal, GoalStore
from empneon.core.identity.models import Agent
from empneon.core.identity.relationships import Relationship, RelationshipStore
from empneon.core.identity.store import AgentStore
from empneon.core.identity.voice import VoiceProfile, VoiceProfileStore
from empneon.core.memory.documents import DocumentMemoryStore
from empneon.core.memory.episodic import (
    Belief,
    BeliefStore,
    EpisodicMemoryStore,
    Event,
    Observation,
    ObservationStore,
)
from empneon.core.memory.vector import VectorMemoryStore
from empneon.core.scheduler.resources import ResourceEstimate
from empneon.core.scheduler.usage import UsageStore
from empneon.db.connection import open_db
from empneon.providers.llm import GenerationResult


@pytest.fixture
def conn() -> sqlite3.Connection:
    connection = open_db(":memory:")
    agents = AgentStore(connection)
    agents.create(Agent("a", "Alice"))
    agents.create(Agent("b", "Bob"))
    return connection


def _count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def test_agent_delete_defers_commit(conn: sqlite3.Connection) -> None:
    AgentStore(conn).delete("b", commit=False)
    conn.rollback()
    assert AgentStore(conn).get("b") is not None


def test_goal_create_update_delete_defer_commit(conn: sqlite3.Connection) -> None:
    goals = GoalStore(conn)
    kept = goals.create(Goal("a", "kept"))
    goals.update_status(kept.id, "completed", commit=False)
    goals.delete(kept.id, commit=False)
    goals.create(Goal("a", "new"), commit=False)
    conn.rollback()
    stored = goals.get(kept.id)
    assert stored is not None and stored.status == "active"
    assert len(goals.get_all("a")) == 1


def test_emotion_delete_defers_commit(conn: sqlite3.Connection) -> None:
    store = EmotionalStateStore(conn)
    store.set(EmotionalState("a", "joy", 0.5))
    store.delete("a", "joy", commit=False)
    conn.rollback()
    assert _count(conn, "emotional_states") == 1


def test_relationship_delete_defers_commit(conn: sqlite3.Connection) -> None:
    store = RelationshipStore(conn)
    store.set(Relationship("a", "b", "friend"))
    store.delete("a", "b", commit=False)
    conn.rollback()
    assert _count(conn, "relationships") == 1


def test_voice_delete_defers_commit(conn: sqlite3.Connection) -> None:
    store = VoiceProfileStore(conn)
    store.set(VoiceProfile("a", provider="piper"))
    store.delete("a", commit=False)
    conn.rollback()
    assert _count(conn, "voice_profiles") == 1


def test_document_delete_defers_commit(conn: sqlite3.Connection) -> None:
    store = DocumentMemoryStore(conn)
    store.set("ns", "key", {"v": 1})
    store.delete("ns", "key", commit=False)
    conn.rollback()
    assert _count(conn, "memory_documents") == 1


def test_event_delete_defers_commit(conn: sqlite3.Connection) -> None:
    store = EpisodicMemoryStore(conn)
    event = store.create(Event("met", ["a", "b"]))
    store.delete(event.id, commit=False)
    conn.rollback()
    assert store.get(event.id) is not None


def test_vector_delete_defers_commit(conn: sqlite3.Connection) -> None:
    vectors = VectorMemoryStore(conn, dimensions=2)
    vectors.upsert("evt", [1.0, 0.0])
    vectors.delete("evt", commit=False)
    conn.rollback()
    assert vectors.search([1.0, 0.0], limit=1)[0][0] == "evt"


def test_usage_record_defers_commit(conn: sqlite3.Connection) -> None:
    request = CognitiveRequest("a", 3, WorldEvent("e", id="event-1"))
    UsageStore(conn).record(
        request, ResourceEstimate(), "p", "m", GenerationResult("x", 1, 1, 1), 3, commit=False
    )
    conn.rollback()
    assert _count(conn, "cognition_usage") == 0


def test_belief_operations_defer_commit(conn: sqlite3.Connection) -> None:
    event = EpisodicMemoryStore(conn).create(Event("met", ["a", "b"]))
    observation = ObservationStore(conn).create(Observation(event.id, "a", "saw"))
    beliefs = BeliefStore(conn)
    first = beliefs.create(Belief("a", "x", "observation", observation.id, 0.9, "i"))
    second = beliefs.create(Belief("a", "y", "observation", observation.id, 0.9, "i"))

    beliefs.record_contradiction(first.id, second.id, "conflict", commit=False)
    revision = Belief("a", "z", "observation", observation.id, 0.8, "i")
    beliefs.revise(first.id, revision, "corrected", commit=False)
    conn.rollback()

    assert beliefs.get_contradictions(first.id) == []
    assert beliefs.get_revision(first.id) is None
    assert beliefs.get(revision.id) is None
