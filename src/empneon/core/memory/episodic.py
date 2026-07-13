"""Canonical events and separate agent observations and beliefs."""

import sqlite3
import time
import uuid
from dataclasses import dataclass, field


@dataclass
class Event:
    description: str
    participant_ids: list[str]          # agent IDs present at this event
    location: str | None = None
    happened_at: int = field(default_factory=lambda: int(time.time()))
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: int = field(default_factory=lambda: int(time.time()))


@dataclass
class Observation:
    event_id: str
    agent_id: str
    perception: str
    observed_at: int = field(default_factory=lambda: int(time.time()))
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class Belief:
    agent_id: str
    statement: str
    created_at: int = field(default_factory=lambda: int(time.time()))
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


class EpisodicMemoryStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(self, event: Event) -> Event:
        now = int(time.time())
        event.created_at = now
        self._conn.execute(
            "INSERT INTO events(id, description, location, happened_at, created_at)"
            " VALUES (?,?,?,?,?)",
            (event.id, event.description, event.location, event.happened_at, event.created_at),
        )
        self._conn.executemany(
            "INSERT OR IGNORE INTO event_participants(event_id, agent_id) VALUES (?,?)",
            [(event.id, agent_id) for agent_id in event.participant_ids],
        )
        self._conn.commit()
        return event

    def get(self, event_id: str) -> Event | None:
        row = self._conn.execute(
            "SELECT * FROM events WHERE id=?", (event_id,)
        ).fetchone()
        if row is None:
            return None
        return self._attach_participants(_row_to_event(row, []))

    def get_for_agent(self, agent_id: str, limit: int | None = None) -> list[Event]:
        query = (
            "SELECT e.* FROM events e"
            " JOIN event_participants ep ON ep.event_id = e.id"
            " WHERE ep.agent_id=?"
            " ORDER BY e.happened_at DESC"
        )
        args: tuple[str | int, ...] = (agent_id,)
        if limit is not None:
            query += " LIMIT ?"
            args = (agent_id, limit)
        rows = self._conn.execute(query, args).fetchall()
        if not rows:
            return []

        event_ids = [r["id"] for r in rows]
        placeholders = ",".join("?" * len(event_ids))
        participant_rows = self._conn.execute(
            f"SELECT event_id, agent_id FROM event_participants WHERE event_id IN ({placeholders})",
            event_ids,
        ).fetchall()

        participants_by_event: dict[str, list[str]] = {r["id"]: [] for r in rows}
        for pr in participant_rows:
            participants_by_event[pr["event_id"]].append(pr["agent_id"])

        return [_row_to_event(r, participants_by_event[r["id"]]) for r in rows]

    def delete(self, event_id: str) -> None:
        self._conn.execute("DELETE FROM events WHERE id=?", (event_id,))
        self._conn.commit()

    def _attach_participants(self, event: Event) -> Event:
        rows = self._conn.execute(
            "SELECT agent_id FROM event_participants WHERE event_id=?", (event.id,)
        ).fetchall()
        event.participant_ids = [r["agent_id"] for r in rows]
        return event


class ObservationStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(self, observation: Observation) -> Observation:
        self._conn.execute(
            "INSERT INTO event_observations(id, event_id, agent_id, perception, observed_at)"
            " VALUES (?,?,?,?,?)",
            (
                observation.id,
                observation.event_id,
                observation.agent_id,
                observation.perception,
                observation.observed_at,
            ),
        )
        self._conn.commit()
        return observation

    def get_for_event(self, event_id: str) -> list[Observation]:
        rows = self._conn.execute(
            "SELECT * FROM event_observations WHERE event_id=? ORDER BY observed_at, id",
            (event_id,),
        ).fetchall()
        return [_row_to_observation(row) for row in rows]

    def get_for_agent(self, agent_id: str) -> list[Observation]:
        rows = self._conn.execute(
            "SELECT * FROM event_observations WHERE agent_id=? ORDER BY observed_at DESC, id",
            (agent_id,),
        ).fetchall()
        return [_row_to_observation(row) for row in rows]


class BeliefStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(self, belief: Belief) -> Belief:
        self._conn.execute(
            "INSERT INTO beliefs(id, agent_id, statement, created_at) VALUES (?,?,?,?)",
            (belief.id, belief.agent_id, belief.statement, belief.created_at),
        )
        self._conn.commit()
        return belief

    def get_for_agent(self, agent_id: str) -> list[Belief]:
        rows = self._conn.execute(
            "SELECT * FROM beliefs WHERE agent_id=? ORDER BY created_at DESC, id",
            (agent_id,),
        ).fetchall()
        return [_row_to_belief(row) for row in rows]


def _row_to_event(row: sqlite3.Row, participant_ids: list[str]) -> Event:
    return Event(
        id=row["id"],
        description=row["description"],
        location=row["location"],
        happened_at=row["happened_at"],
        created_at=row["created_at"],
        participant_ids=participant_ids,
    )


def _row_to_observation(row: sqlite3.Row) -> Observation:
    return Observation(
        id=row["id"],
        event_id=row["event_id"],
        agent_id=row["agent_id"],
        perception=row["perception"],
        observed_at=row["observed_at"],
    )


def _row_to_belief(row: sqlite3.Row) -> Belief:
    return Belief(
        id=row["id"],
        agent_id=row["agent_id"],
        statement=row["statement"],
        created_at=row["created_at"],
    )
