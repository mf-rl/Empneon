import logging
import sqlite3

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
from empneon.core.memory.state import MemoryState, MemoryStateStore, salience
from empneon.core.runtime import ActionRecordStore
from empneon.db.connection import open_db

SECRET = "super-secret-event-description"
NOW = 100_000


class World:
    def __init__(self) -> None:
        self.conn = open_db(":memory:")
        agents = AgentStore(self.conn)
        for agent_id in ("a", "b", "c"):
            agents.create(Agent(agent_id, agent_id.upper()))
        self.events = EpisodicMemoryStore(self.conn)
        self.state = MemoryStateStore(self.conn)
        self.counter = 0

    def event(
        self, *participants: str, at: int = 0, description: str = "something happened"
    ) -> str:
        self.counter += 1
        event_id = f"e{self.counter:03d}"
        self.events.create(
            Event(description, list(participants or ("a",)), id=event_id, happened_at=at)
        )
        return event_id

    def sweep(self, **overrides: object) -> tuple[str, ...]:
        options: dict[str, object] = {"now": NOW, "older_than_s": 1_000, "max_rows": 100}
        options.update(overrides)
        return self.state.sweep("a", **options)  # type: ignore[arg-type]


@pytest.fixture
def world() -> World:
    return World()


# ---- salience ------------------------------------------------------------------------------


def test_salience_halves_every_half_life() -> None:
    assert salience(0, 0, 100) == 1.0
    assert salience(0, 100, 100) == pytest.approx(0.5)
    assert salience(0, 200, 100) == pytest.approx(0.25)


def test_salience_respects_floor_and_future_anchors() -> None:
    assert salience(0, 10_000, 100, floor=0.1) == 0.1
    assert salience(500, 100, 100) == 1.0


@pytest.mark.parametrize(
    "args", [(0, 1, 0), (0, 1, -5), (0, 1, 10, -0.1), (0, 1, 10, 1.1)]
)
def test_salience_rejects_invalid_arguments(args: tuple[int, ...]) -> None:
    with pytest.raises(ValueError):
        salience(*args)  # type: ignore[arg-type]


def test_salience_for_anchors_on_last_recall_else_happened_at(world: World) -> None:
    old = world.event(at=0)
    recalled = world.event(at=0)
    world.state.record_recall([recalled], now=NOW - 100)

    scores = world.state.salience_for([old, recalled, "unknown"], now=NOW, half_life_s=100)

    assert scores[old] == pytest.approx(0.5 ** (NOW / 100))
    assert scores[recalled] == pytest.approx(0.5)
    assert "unknown" not in scores


# ---- archive, restore, recall --------------------------------------------------------------


def test_archive_and_restore_are_idempotent_and_ignore_unknown_ids(world: World) -> None:
    first, second = world.event(), world.event()

    assert world.state.archive([first, second, "unknown"], now=50) == 2
    assert world.state.archive([first], now=60) == 0
    assert world.state.archived_ids([first, second, "unknown"]) == {first, second}
    assert world.state.get(first) == MemoryState(first, 50, 0, None)

    assert world.state.restore([first, "unknown"]) == 1
    assert world.state.restore([first]) == 0
    assert world.state.archived_ids([first, second]) == {second}


def test_restore_keeps_recall_bookkeeping(world: World) -> None:
    event = world.event()
    world.state.record_recall([event], now=10)
    world.state.archive([event], now=20)
    world.state.restore([event])
    assert world.state.get(event) == MemoryState(event, None, 1, 10)


def test_record_recall_counts_and_timestamps(world: World) -> None:
    event = world.event()
    assert world.state.get(event) is None
    assert world.state.record_recall([event, "unknown"], now=10) == 1
    assert world.state.record_recall([event], now=30) == 1
    assert world.state.get(event) == MemoryState(event, None, 2, 30)


def test_empty_inputs_are_no_ops(world: World) -> None:
    assert world.state.archive([], now=1) == 0
    assert world.state.restore([]) == 0
    assert world.state.record_recall([], now=1) == 0
    assert world.state.archived_ids([]) == set()


def test_large_id_lists_are_chunked(world: World) -> None:
    ids = [world.event() for _ in range(1_200)]
    assert world.state.archive(ids, now=1) == 1_200
    assert len(world.state.archived_ids(ids)) == 1_200


def test_state_follows_event_deletion(world: World) -> None:
    event = world.event()
    world.state.archive([event], now=1)
    world.events.delete(event)
    assert world.state.get(event) is None


def test_mutators_defer_commit_to_the_caller(world: World) -> None:
    event = world.event()
    world.state.archive([event], now=1, commit=False)
    world.state.record_recall([event], now=2, commit=False)
    world.conn.rollback()
    assert world.state.get(event) is None

    world.state.archive([event], now=1)
    world.state.restore([event], commit=False)
    world.conn.rollback()
    assert world.state.archived_ids([event]) == {event}


# ---- sweep ---------------------------------------------------------------------------------


def test_sweep_archives_old_events_oldest_first_and_is_bounded(world: World) -> None:
    ids = [world.event(at=at) for at in (30, 10, 20, 99_500)]

    archived = world.sweep(max_rows=2)

    assert archived == (ids[1], ids[2])
    assert world.state.archived_ids(ids) == {ids[1], ids[2]}
    assert world.sweep() == (ids[0],)
    assert world.sweep() == ()


def test_sweep_uses_the_age_threshold_and_last_recall(world: World) -> None:
    old = world.event(at=0)
    recalled = world.event(at=0)
    recent = world.event(at=NOW - 500)
    world.state.record_recall([recalled], now=NOW - 10)

    assert world.sweep(older_than_s=1_000) == (old,)
    assert world.state.archived_ids([old, recalled, recent]) == {old}


def test_sweep_keeps_the_newest_events(world: World) -> None:
    ids = [world.event(at=at) for at in (1, 2, 3, 4)]
    assert world.sweep(keep_latest=3) == (ids[0],)


def test_sweep_only_considers_the_agents_events(world: World) -> None:
    mine, theirs = world.event("a"), world.event("b")
    assert world.sweep() == (mine,)
    assert world.state.archived_ids([theirs]) == set()


def test_sweep_skips_shared_events_unless_asked(world: World) -> None:
    solo, shared = world.event("a", at=1), world.event("a", "b", at=2)

    assert world.sweep() == (solo,)
    assert world.sweep(include_shared=True) == (shared,)


def test_sweep_applies_the_callers_predicate(world: World) -> None:
    keep = world.event(description="keep me", at=1)
    drop = world.event(description="drop me", at=2)

    archived = world.sweep(eligible=lambda event: event.description.startswith("drop"))

    assert archived == (drop,)
    assert world.state.archived_ids([keep]) == set()


def test_sweep_never_archives_events_backing_a_belief(world: World) -> None:
    backed, derived_root, free = world.event(at=1), world.event(at=2), world.event(at=3)
    observations = ObservationStore(world.conn)
    beliefs = BeliefStore(world.conn)
    first = observations.create(Observation(backed, "a", "saw it"))
    belief = beliefs.create(Belief("a", "it happened", "observation", first.id, 0.9, "why"))
    second = observations.create(Observation(derived_root, "a", "saw that too"))
    root = beliefs.create(Belief("a", "root", "observation", second.id, 0.9, "why"))
    beliefs.create(Belief("a", "derived", "belief", root.id, 0.5, "inferred"))
    assert belief.id and free

    assert world.sweep() == (free,)


def test_sweep_never_archives_events_cited_by_action_records(world: World) -> None:
    by_result = world.event(at=1)
    by_proposal = world.event(at=2)
    by_result_evidence = world.event(at=3)
    by_proposal_evidence = world.event(at=4)
    free = world.event(at=5)
    other = world.event("b", at=6)
    actions = ActionRecordStore(world.conn)
    actions.record(by_result, Decision("a", "wave", id="d1"), ActionResult("d1", "succeeded"))
    actions.propose(by_proposal, Decision("a", "wave", id="d2"), "wave")
    actions.record(
        other,
        Decision("a", "wave", evidence_ids=(by_result_evidence,), id="d3"),
        ActionResult("d3", "succeeded"),
    )
    actions.propose(
        other, Decision("a", "wave", evidence_ids=(by_proposal_evidence,), id="d4"), "wave"
    )

    assert world.sweep() == (free,)


def test_sweep_is_idempotent_and_reversible(world: World) -> None:
    ids = [world.event(at=at) for at in (1, 2)]
    assert world.sweep() == tuple(ids)
    assert world.sweep() == ()
    world.state.restore(ids)
    assert world.sweep() == tuple(ids)


def test_sweep_defers_commit_to_the_caller(world: World) -> None:
    event = world.event()
    assert world.sweep(commit=False) == (event,)
    world.conn.rollback()
    assert world.state.archived_ids([event]) == set()


@pytest.mark.parametrize(
    "overrides",
    [
        {"max_rows": 0},
        {"older_than_s": -1},
        {"keep_latest": -1},
        {"now": -1},
    ],
)
def test_sweep_rejects_invalid_policy(world: World, overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        world.sweep(**overrides)


def test_sweep_logs_counts_only(world: World, caplog: pytest.LogCaptureFixture) -> None:
    world.event(description=SECRET, at=1)
    caplog.set_level(logging.DEBUG)

    world.sweep(eligible=lambda event: True)

    assert "archived 1" in caplog.text
    assert SECRET not in caplog.text


# ---- opt-in recall filters leave defaults alone --------------------------------------------


def test_get_for_agent_hides_archived_only_when_asked(world: World) -> None:
    kept, hidden = world.event(at=2), world.event(at=1)
    world.state.archive([hidden], now=5)

    assert [e.id for e in world.events.get_for_agent("a")] == [kept, hidden]
    assert [e.id for e in world.events.get_for_agent("a", include_archived=False)] == [kept]
    limited = world.events.get_for_agent("a", 1, include_archived=False)
    assert [e.id for e in limited] == [kept]


def test_archived_events_stay_inspectable(world: World) -> None:
    event = world.event()
    world.state.archive([event], now=5)
    assert world.events.get(event) is not None


def test_memory_state_table_is_queryable_directly(world: World) -> None:
    event = world.event()
    world.state.archive([event], now=5)
    row = world.conn.execute("SELECT archived_at FROM memory_state").fetchone()
    assert isinstance(world.conn, sqlite3.Connection) and row[0] == 5
