"""Canonical events and separate agent observations and beliefs."""

import json
import sqlite3
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Literal

BeliefSourceKind = Literal["observation", "belief"]


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
    source_kind: BeliefSourceKind
    source_id: str
    confidence: float
    interpretation: str
    lineage: tuple[str, ...] = ()
    created_at: int = field(default_factory=lambda: int(time.time()))
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        if self.source_kind not in ("observation", "belief"):
            raise ValueError("belief source kind must be observation or belief")
        if not all(
            (
                self.agent_id.strip(),
                self.statement.strip(),
                self.source_id.strip(),
                self.interpretation.strip(),
            )
        ):
            raise ValueError(
                "belief agent, statement, source, and interpretation must not be empty"
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("belief confidence must be between 0 and 1")


class EpisodicMemoryStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(self, event: Event, *, commit: bool = True) -> Event:
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
        if commit:
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

    def create(self, observation: Observation, *, commit: bool = True) -> Observation:
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
        if commit:
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

    def create(self, belief: Belief, *, commit: bool = True) -> Belief:
        if commit:
            with self._conn:
                self._insert(belief)
        else:
            self._insert(belief)
        return belief

    def _insert(self, belief: Belief) -> None:
        if belief.source_kind == "observation":
            source = self._conn.execute(
                "SELECT 1 FROM event_observations WHERE id=? AND agent_id=?",
                (belief.source_id, belief.agent_id),
            ).fetchone()
            belief.lineage = ()
        else:
            source_belief = self.get(belief.source_id)
            source = source_belief
            if source_belief is not None:
                belief.lineage = (*source_belief.lineage, source_belief.id)
        if source is None:
            raise ValueError("belief source does not exist")

        self._conn.execute(
            "INSERT INTO beliefs(id, agent_id, statement, created_at) VALUES (?,?,?,?)",
            (belief.id, belief.agent_id, belief.statement, belief.created_at),
        )
        self._conn.execute(
            "INSERT INTO belief_provenance VALUES (?,?,?,?,?,?)",
            (
                belief.id,
                belief.source_id if belief.source_kind == "observation" else None,
                belief.source_id if belief.source_kind == "belief" else None,
                belief.confidence,
                belief.interpretation,
                json.dumps(belief.lineage),
            ),
        )

    def get(self, belief_id: str) -> Belief | None:
        row = self._conn.execute(
            "SELECT b.*, p.* FROM beliefs b JOIN belief_provenance p ON p.belief_id=b.id"
            " WHERE b.id=?",
            (belief_id,),
        ).fetchone()
        return None if row is None else _row_to_belief(row)

    def get_for_agent(self, agent_id: str) -> list[Belief]:
        rows = self._conn.execute(
            "SELECT b.*, p.* FROM beliefs b JOIN belief_provenance p ON p.belief_id=b.id"
            " WHERE b.agent_id=? ORDER BY b.created_at DESC, b.id",
            (agent_id,),
        ).fetchall()
        return [_row_to_belief(row) for row in rows]

    def get_current_for_agent(self, agent_id: str) -> list[Belief]:
        rows = self._conn.execute(
            "SELECT b.*, p.* FROM beliefs b JOIN belief_provenance p ON p.belief_id=b.id"
            " WHERE b.agent_id=? AND NOT EXISTS ("
            " SELECT 1 FROM belief_relations r WHERE r.related_belief_id=b.id"
            " AND r.relation='revises') ORDER BY b.created_at DESC, b.id",
            (agent_id,),
        ).fetchall()
        return [_row_to_belief(row) for row in rows]

    def record_contradiction(self, first_id: str, second_id: str, reason: str) -> None:
        first = self.get(first_id)
        second = self.get(second_id)
        if first is None or second is None:
            raise ValueError("contradictory belief does not exist")
        if first.agent_id != second.agent_id:
            raise ValueError("contradictory beliefs must belong to the same agent")
        if not reason.strip():
            raise ValueError("contradiction reason must not be empty")
        belief_id, related_id = sorted((first_id, second_id))
        with self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO belief_relations VALUES (?,?,?,?,?)",
                (belief_id, related_id, "contradicts", reason, int(time.time())),
            )

    def get_contradictions(self, belief_id: str) -> list[Belief]:
        rows = self._conn.execute(
            "SELECT b.*, p.* FROM belief_relations r"
            " JOIN beliefs b ON b.id=CASE WHEN r.belief_id=?"
            " THEN r.related_belief_id ELSE r.belief_id END"
            " JOIN belief_provenance p ON p.belief_id=b.id"
            " WHERE r.relation='contradicts'"
            " AND (r.belief_id=? OR r.related_belief_id=?) ORDER BY b.created_at, b.id",
            (belief_id, belief_id, belief_id),
        ).fetchall()
        return [_row_to_belief(row) for row in rows]

    def revise(self, original_id: str, revision: Belief, reason: str) -> Belief:
        original = self.get(original_id)
        if original is None:
            raise ValueError("original belief does not exist")
        if original.agent_id != revision.agent_id:
            raise ValueError("belief revision must belong to the same agent")
        if not reason.strip():
            raise ValueError("revision reason must not be empty")
        if self.get_revision(original_id) is not None:
            raise ValueError("belief has already been revised")
        with self._conn:
            self._insert(revision)
            self._conn.execute(
                "INSERT INTO belief_relations VALUES (?,?,?,?,?)",
                (revision.id, original_id, "revises", reason, int(time.time())),
            )
        return revision

    def get_revision(self, belief_id: str) -> Belief | None:
        row = self._conn.execute(
            "SELECT b.*, p.* FROM belief_relations r"
            " JOIN beliefs b ON b.id=r.belief_id"
            " JOIN belief_provenance p ON p.belief_id=b.id"
            " WHERE r.related_belief_id=? AND r.relation='revises'",
            (belief_id,),
        ).fetchone()
        return None if row is None else _row_to_belief(row)

    def propagate(
        self,
        belief_id: str,
        *,
        max_hops: int = 3,
        max_recipients: int = 20,
        min_confidence: float = 0.1,
        decay: float = 0.9,
    ) -> list[Belief]:
        if max_hops <= 0 or max_recipients <= 0:
            raise ValueError("propagation bounds must be positive")
        if not 0.0 <= min_confidence <= 1.0 or not 0.0 <= decay <= 1.0:
            raise ValueError("propagation confidence settings must be between 0 and 1")
        source = self.get(belief_id)
        if source is None:
            raise ValueError("source belief does not exist")
        if self.get_revision(belief_id) is not None:
            return []

        visited = {source.agent_id}
        if source.lineage:
            placeholders = ",".join("?" * len(source.lineage))
            rows = self._conn.execute(
                f"SELECT agent_id FROM beliefs WHERE id IN ({placeholders})", source.lineage
            ).fetchall()
            visited.update(row["agent_id"] for row in rows)

        queue = deque([(source, 0)])
        propagated: list[Belief] = []
        # ponytail: first BFS path wins; rank competing paths if fidelity tests need it.
        with self._conn:
            while queue and len(propagated) < max_recipients:
                current, hops = queue.popleft()
                if hops >= max_hops:
                    continue
                relationships = self._conn.execute(
                    "SELECT agent_id, trust FROM relationships"
                    " WHERE target_agent_id=? ORDER BY agent_id",
                    (current.agent_id,),
                ).fetchall()
                for relationship in relationships:
                    recipient_id = relationship["agent_id"]
                    if recipient_id in visited:
                        continue
                    confidence = current.confidence * relationship["trust"] * decay
                    if confidence < min_confidence:
                        continue
                    transmitted = Belief(
                        recipient_id,
                        current.statement,
                        "belief",
                        current.id,
                        confidence,
                        f"Relayed from {current.agent_id} with trust {relationship['trust']:.2f}",
                    )
                    self._insert(transmitted)
                    visited.add(recipient_id)
                    propagated.append(transmitted)
                    queue.append((transmitted, hops + 1))
                    if len(propagated) >= max_recipients:
                        break
        return propagated

    def causal_trace(self, belief_id: str) -> dict[str, object]:
        belief = self.get(belief_id)
        if belief is None:
            raise ValueError("belief does not exist")
        chain = [self.get(item_id) for item_id in (*belief.lineage, belief.id)]
        if any(item is None for item in chain):
            raise RuntimeError("belief lineage is incomplete")
        beliefs = [item for item in chain if item is not None]
        root = beliefs[0]
        if root.source_kind != "observation":
            raise RuntimeError("belief lineage has no originating observation")
        row = self._conn.execute(
            "SELECT * FROM event_observations WHERE id=?", (root.source_id,)
        ).fetchone()
        if row is None:
            raise RuntimeError("belief observation is missing")
        observation = _row_to_observation(row)
        event = EpisodicMemoryStore(self._conn).get(observation.event_id)
        if event is None:
            raise RuntimeError("belief event is missing")

        chain_ids = tuple(item.id for item in beliefs)
        placeholders = ",".join("?" * len(chain_ids))
        relations = self._conn.execute(
            f"SELECT * FROM belief_relations WHERE belief_id IN ({placeholders})"
            f" OR related_belief_id IN ({placeholders})"
            " ORDER BY created_at, relation, belief_id, related_belief_id",
            (*chain_ids, *chain_ids),
        ).fetchall()
        return {
            "event": asdict(event),
            "observation": asdict(observation),
            "beliefs": [asdict(item) for item in beliefs],
            "relations": [dict(relation) for relation in relations],
        }


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
        source_kind="observation" if row["source_observation_id"] is not None else "belief",
        source_id=row["source_observation_id"] or row["source_belief_id"],
        confidence=row["confidence"],
        interpretation=row["interpretation"],
        lineage=tuple(json.loads(row["lineage"])),
        created_at=row["created_at"],
    )
