import asyncio
import logging
import sqlite3
from collections.abc import Sequence

import pytest

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
from empneon.core.memory.semantic import SemanticMemoryIndex
from empneon.core.memory.vector import VectorMemoryStore
from empneon.db.connection import open_db
from empneon.providers.llm import EmbeddingResult

SECRET = "super-secret-orphan-description"


class Embedder:
    async def embed(self, texts: Sequence[str]) -> EmbeddingResult:
        return EmbeddingResult(tuple((1.0, float(len(t))) for t in texts))

    async def health_check(self) -> bool:
        return True


class World:
    def __init__(self) -> None:
        self.conn = open_db(":memory:")
        AgentStore(self.conn).create(Agent("a", "A"))
        self.events = EpisodicMemoryStore(self.conn)
        self.counter = 0

    def event(self, description: str = "dinner") -> str:
        self.counter += 1
        event_id = f"e{self.counter}"
        self.events.create(Event(description, ["a"], id=event_id, happened_at=self.counter))
        return event_id

    def vectors(self) -> VectorMemoryStore:
        return VectorMemoryStore(self.conn, dimensions=2)

    def vector_ids(self) -> set[str]:
        rows = self.conn.execute("SELECT event_id FROM vec_memory_index").fetchall()
        return {row[0] for row in rows}

    def vec0_rows(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM vec_memories").fetchone()[0])

    def orphan(self, event_id: str) -> None:
        """Delete an event the way raw SQL would, bypassing the store."""
        self.conn.execute("DELETE FROM events WHERE id=?", (event_id,))
        self.conn.commit()


@pytest.fixture
def world() -> World:
    return World()


def test_deleting_an_event_deletes_its_vector(world: World) -> None:
    gone, kept = world.event(), world.event()
    vectors = world.vectors()
    vectors.upsert(gone, [1.0, 0.0])
    vectors.upsert(kept, [0.0, 1.0])

    world.events.delete(gone)

    assert world.vector_ids() == {kept}
    assert world.vec0_rows() == 1
    assert [event_id for event_id, _ in vectors.search([0.0, 1.0], 5)] == [kept]


def test_deleting_an_event_without_a_vector_leaves_others_alone(world: World) -> None:
    plain, indexed = world.event(), world.event()
    world.vectors().upsert(indexed, [1.0, 0.0])

    world.events.delete(plain)

    assert world.vector_ids() == {indexed}


def test_delete_never_creates_vector_tables(world: World) -> None:
    event = world.event()

    world.events.delete(event)

    names = {row[0] for row in world.conn.execute("SELECT name FROM sqlite_master")}
    assert "vec_memory_index" not in names and "vec_memories" not in names
    assert world.events.get(event) is None


def test_delete_defers_commit_for_event_and_vector(world: World) -> None:
    event = world.event()
    world.vectors().upsert(event, [1.0, 0.0])

    world.events.delete(event, commit=False)
    assert world.events.get(event) is None and world.vector_ids() == set()
    world.conn.rollback()

    assert world.events.get(event) is not None
    assert world.vector_ids() == {event}
    assert world.vec0_rows() == 1


def test_a_belief_backed_event_keeps_event_and_vector(world: World) -> None:
    event = world.event()
    world.vectors().upsert(event, [1.0, 0.0])
    observation = ObservationStore(world.conn).create(Observation(event, "a", "saw it"))
    belief = Belief("a", "it happened", "observation", observation.id, 0.9, "x")
    BeliefStore(world.conn).create(belief)

    with pytest.raises(sqlite3.IntegrityError):
        world.events.delete(event)

    assert world.events.get(event) is not None
    assert world.vector_ids() == {event}


def test_a_failed_vector_delete_rolls_the_event_delete_back(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    event = world.event()
    world.vectors().upsert(event, [1.0, 0.0])

    def broken(self: VectorMemoryStore, event_id: str, *, commit: bool = True) -> None:
        raise sqlite3.OperationalError("vector side failed")

    monkeypatch.setattr(VectorMemoryStore, "delete", broken)
    with pytest.raises(sqlite3.OperationalError):
        world.events.delete(event)

    assert world.events.get(event) is not None
    assert world.vector_ids() == {event}
    assert not world.conn.in_transaction


# ---- prune_orphans -------------------------------------------------------------------------


def test_prune_orphans_removes_only_orphans(world: World) -> None:
    first, second, kept = world.event(), world.event(), world.event()
    vectors = world.vectors()
    for event_id in (first, second, kept):
        vectors.upsert(event_id, [1.0, 0.0])
    world.orphan(first)
    world.orphan(second)

    assert vectors.prune_orphans() == 2

    assert world.vector_ids() == {kept}
    assert world.vec0_rows() == 1
    assert vectors.prune_orphans() == 0


def test_prune_orphans_defers_commit_to_the_caller(world: World) -> None:
    event = world.event()
    vectors = world.vectors()
    vectors.upsert(event, [1.0, 0.0])
    world.orphan(event)

    assert vectors.prune_orphans(commit=False) == 1
    world.conn.rollback()

    assert world.vector_ids() == {event}
    assert world.vec0_rows() == 1


def test_prune_orphans_logs_counts_only(world: World, caplog: pytest.LogCaptureFixture) -> None:
    event = world.event(SECRET)
    vectors = world.vectors()
    vectors.upsert(event, [1.0, 0.0])
    world.orphan(event)
    caplog.set_level(logging.DEBUG)

    vectors.prune_orphans()

    assert "pruned 1" in caplog.text
    assert SECRET not in caplog.text and event not in caplog.text


def test_semantic_index_prune_is_a_no_op_without_vector_tables(world: World) -> None:
    index = SemanticMemoryIndex(world.conn, Embedder())

    assert index.prune_orphans() == 0
    names = {row[0] for row in world.conn.execute("SELECT name FROM sqlite_master")}
    assert "vec_memory_index" not in names


def test_semantic_index_prune_and_search_after_a_raw_delete(world: World) -> None:
    index = SemanticMemoryIndex(world.conn, Embedder())
    gone, kept = world.event("dinner"), world.event("supper")
    asyncio.run(index.index_events([world.events.get(gone), world.events.get(kept)]))  # type: ignore[list-item]
    world.orphan(gone)

    assert [m.event.id for m in asyncio.run(index.search("a", "dinner"))] == [kept]
    assert index.prune_orphans() == 1
    assert world.vector_ids() == {kept}
    assert [m.event.id for m in asyncio.run(index.search("a", "dinner"))] == [kept]


def test_deleting_through_the_store_leaves_nothing_to_prune(world: World) -> None:
    index = SemanticMemoryIndex(world.conn, Embedder())
    gone = world.event("dinner")
    asyncio.run(index.index_events([world.events.get(gone)]))  # type: ignore[list-item]

    world.events.delete(gone)

    assert index.prune_orphans() == 0
    assert world.vector_ids() == set()
