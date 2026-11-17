import asyncio
import logging
import math
import sqlite3
from collections.abc import Coroutine, Sequence
from typing import Any, TypeVar

import pytest

from empneon.core.identity.models import Agent
from empneon.core.identity.store import AgentStore
from empneon.core.memory.episodic import EpisodicMemoryStore, Event, Observation, ObservationStore
from empneon.core.memory.semantic import Ownership, SemanticMatch, SemanticMemoryIndex
from empneon.core.memory.vector import VectorMemoryStore
from empneon.db.connection import open_db
from empneon.providers.llm import CircuitOpenError, EmbeddingResult, ProviderError

SECRET = "super-secret-memory-text"
T = TypeVar("T")

# Each topic owns one axis; a text scores on every topic it mentions (synonyms share an axis).
TOPICS = (
    ("dinner", "supper", "meal"),
    ("garden", "yard"),
    ("party", "celebration"),
)


class FakeEmbedder:
    """Deterministic keyword embedder; `dimensions` pads with zeros."""

    def __init__(self, dimensions: int = 4) -> None:
        self.dimensions = dimensions
        self.calls = 0
        self.failure: Exception | None = None

    async def embed(self, texts: Sequence[str]) -> EmbeddingResult:
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        vectors = []
        for text in texts:
            words = text.casefold().split()
            scores = [float(sum(word in topic for word in words)) for topic in TOPICS]
            raw = [*scores, 0.05] + [0.0] * (self.dimensions - len(TOPICS) - 1)
            norm = math.sqrt(sum(v * v for v in raw))
            vectors.append(tuple(v / norm for v in raw))
        return EmbeddingResult(tuple(vectors), prompt_tokens=len(texts), latency_ms=1)

    async def health_check(self) -> bool:
        return True


class World:
    def __init__(self, ownership: Ownership = "participants") -> None:
        self.conn = open_db(":memory:")
        agents = AgentStore(self.conn)
        for agent_id in ("a", "b", "c"):
            agents.create(Agent(agent_id, agent_id.upper()))
        self.events = EpisodicMemoryStore(self.conn)
        self.embedder = FakeEmbedder()
        self.index = SemanticMemoryIndex(self.conn, self.embedder, ownership=ownership)
        self.counter = 0

    def event(self, description: str, *participants: str, happened_at: int = 0) -> Event:
        self.counter += 1
        event_id = f"e{self.counter:03d}"
        return self.events.create(
            Event(description, list(participants), id=event_id, happened_at=happened_at)
        )


def run(coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def indexed(conn: sqlite3.Connection) -> list[str]:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name='vec_memory_index'"
    ).fetchone()
    if exists is None:
        return []
    rows = conn.execute("SELECT event_id FROM vec_memory_index ORDER BY event_id")
    return [row[0] for row in rows]


def test_search_returns_the_nearest_owned_events_first() -> None:
    world = World()
    dinner = world.event("supper with friends", "a")
    garden = world.event("planting the yard", "a")
    party = world.event("birthday celebration", "a")
    run(world.index.index_events([dinner, garden, party]))

    matches = run(world.index.search("a", "dinner", limit=3))

    assert [m.event.id for m in matches][0] == dinner.id
    assert all(isinstance(m, SemanticMatch) for m in matches)
    assert [m.distance for m in matches] == sorted(m.distance for m in matches)
    assert matches[0].event.participant_ids == ["a"]
    assert matches[0].distance < matches[1].distance


def test_other_agents_closer_events_are_never_returned() -> None:
    world = World()
    theirs = world.event("a big dinner", "b")
    mine = world.event("garden work", "a")
    run(world.index.index_events([theirs, mine]))

    assert [m.event.id for m in run(world.index.search("a", "dinner", limit=5))] == [mine.id]
    assert [m.event.id for m in run(world.index.search("b", "dinner", limit=5))] == [theirs.id]
    assert run(world.index.search("c", "dinner", limit=5)) == []


def test_ownership_can_follow_observations_instead_of_participants() -> None:
    by_participants = World()
    event = by_participants.event("dinner party", "a")
    ObservationStore(by_participants.conn).create(Observation(event.id, "b", "I saw dinner"))
    run(by_participants.index.index_event(event))
    assert [m.event.id for m in run(by_participants.index.search("a", "dinner"))] == [event.id]
    assert run(by_participants.index.search("b", "dinner")) == []

    by_observation = World(ownership="observations")
    event = by_observation.event("dinner party", "a")
    ObservationStore(by_observation.conn).create(Observation(event.id, "b", "I saw dinner"))
    run(by_observation.index.index_event(event))
    assert [m.event.id for m in run(by_observation.index.search("b", "dinner"))] == [event.id]
    assert run(by_observation.index.search("a", "dinner")) == []


def test_invalid_ownership_is_rejected() -> None:
    with pytest.raises(ValueError, match="ownership"):
        # A deliberately invalid value: the Literal type is not enforced at runtime.
        World(ownership="everyone")  # type: ignore[arg-type]


def test_matches_beyond_the_initial_over_fetch_are_still_found() -> None:
    world = World()
    crowd = [world.event("a big dinner", "b") for _ in range(25)]
    mine = [
        world.event("garden yard", "a"),
        world.event("yard work", "a"),
        world.event("party celebration", "a"),
    ]
    run(world.index.index_events([*crowd, *mine]))

    matches = run(world.index.search("a", "dinner", limit=3))

    assert {m.event.id for m in matches} == {e.id for e in mine}
    assert len(matches) == 3


def test_fewer_owned_events_than_the_limit_returns_all_and_empty_store_returns_none() -> None:
    world = World()
    assert run(world.index.search("a", "dinner", limit=5)) == []
    only = world.event("dinner", "a")
    run(world.index.index_event(only))
    assert [m.event.id for m in run(world.index.search("a", "dinner", limit=5))] == [only.id]


def test_ties_are_ordered_by_event_id() -> None:
    world = World()
    first = world.event("dinner", "a")
    second = world.event("dinner", "a")
    run(world.index.index_events([second, first]))
    assert [m.event.id for m in run(world.index.search("a", "dinner"))] == [first.id, second.id]


def test_orphaned_vectors_are_skipped_and_remove_deletes_them() -> None:
    world = World()
    gone = world.event("dinner", "a")
    kept = world.event("supper", "a")
    run(world.index.index_events([gone, kept]))
    world.events.delete(gone.id)

    assert [m.event.id for m in run(world.index.search("a", "dinner"))] == [kept.id]
    assert gone.id in indexed(world.conn)
    world.index.remove(gone.id)
    assert gone.id not in indexed(world.conn)


def test_reindexing_replaces_the_vector_and_batches_into_one_embed_call() -> None:
    world = World()
    event = world.event("dinner", "a")
    other = world.event("garden", "a")
    assert run(world.index.index_events([event, other])) == 2
    assert world.embedder.calls == 1

    changed = Event("party celebration", ["a"], id=event.id)
    run(world.index.index_event(changed))
    top = run(world.index.search("a", "party", limit=1))[0]
    assert top.event.id == event.id and top.distance < 0.2
    assert indexed(world.conn) == [event.id, other.id]
    assert run(world.index.index_events([])) == 0


def test_index_unindexed_backfills_only_missing_events_oldest_first() -> None:
    world = World()
    events = [world.event(f"dinner {i}", "a", happened_at=i) for i in range(5)]
    run(world.index.index_events([events[1], events[3]]))
    calls = world.embedder.calls

    assert run(world.index.index_unindexed(limit=2)) == 2
    assert indexed(world.conn) == sorted([events[0].id, events[1].id, events[2].id, events[3].id])
    assert run(world.index.index_unindexed(limit=10)) == 1
    assert indexed(world.conn) == sorted(e.id for e in events)
    calls_after = world.embedder.calls
    assert calls_after == calls + 2
    assert run(world.index.index_unindexed()) == 0
    assert world.embedder.calls == calls_after


def test_dimensions_are_discovered_and_mismatches_fail_clearly() -> None:
    world = World()
    run(world.index.index_event(world.event("dinner", "a")))

    wider = SemanticMemoryIndex(world.conn, FakeEmbedder(dimensions=8))
    with pytest.raises(ValueError, match="dimensions"):
        run(wider.index_event(Event("supper", ["a"], id="e999")))

    existing = World()
    VectorMemoryStore(existing.conn)  # a 384-dimension table, as the Sims adapter creates
    with pytest.raises(ValueError, match="dimensions"):
        run(existing.index.search("a", "dinner"))


@pytest.mark.parametrize("failure", [ProviderError("down", status=503), CircuitOpenError("open")])
def test_embedding_failures_write_nothing_and_propagate(failure: ProviderError) -> None:
    world = World()
    world.embedder.failure = failure
    event = world.event("dinner", "a")
    with pytest.raises(ProviderError):
        run(world.index.index_event(event))
    with pytest.raises(ProviderError):
        run(world.index.search("a", "dinner"))
    assert indexed(world.conn) == []


def test_failure_midway_through_a_batch_rolls_everything_back() -> None:
    class Ragged(FakeEmbedder):
        async def embed(self, texts: Sequence[str]) -> EmbeddingResult:
            good = (1.0, 0.0, 0.0, 0.0)
            return EmbeddingResult((good, (1.0, 0.0)), None, None)  # second vector too short

    world = World()
    world.index = SemanticMemoryIndex(world.conn, Ragged())
    events = [world.event("dinner", "a"), world.event("garden", "a")]

    with pytest.raises(ValueError, match="dimensions"):
        run(world.index.index_events(events))

    assert indexed(world.conn) == []


def test_commit_false_leaves_the_transaction_to_the_caller() -> None:
    world = World()
    event = world.event("dinner", "a")
    run(world.index.index_event(event, commit=False))
    assert indexed(world.conn) == [event.id]
    world.conn.rollback()
    assert indexed(world.conn) == []


def test_invalid_arguments_fail_before_any_embedding_call() -> None:
    world = World()
    with pytest.raises(ValueError):
        run(world.index.search("a", "   "))
    for limit in (0, -1):
        with pytest.raises(ValueError, match="limit"):
            run(world.index.search("a", "dinner", limit=limit))
    with pytest.raises(ValueError):
        run(world.index.index_event(Event("  ", ["a"], id="e1")))
    with pytest.raises(ValueError):
        run(world.index.index_events([Event("ok", ["a"], id="e1"), Event("", ["a"], id="e2")]))
    with pytest.raises(ValueError, match="limit"):
        run(world.index.index_unindexed(limit=0))
    assert world.embedder.calls == 0


def test_event_text_and_queries_are_never_logged(caplog: pytest.LogCaptureFixture) -> None:
    world = World()
    event = world.event(f"dinner {SECRET}", "a")
    with caplog.at_level(logging.DEBUG, logger="empneon"):
        run(world.index.index_event(event))
        run(world.index.search("a", f"dinner {SECRET}"))
    assert SECRET not in caplog.text
