"""Directed relationship edges between agents — weight + trust per edge."""

import sqlite3
import time
import uuid
from dataclasses import dataclass, field


@dataclass
class Relationship:
    agent_id: str
    target_agent_id: str
    relationship_type: str
    strength: float = 0.0  # -1.0 (antagonistic) to 1.0 (close)
    trust: float = 0.5  # 0.0 to 1.0 — governs gossip fidelity
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    updated_at: int = field(default_factory=lambda: int(time.time()))


class RelationshipStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def set(self, rel: Relationship, *, commit: bool = True) -> Relationship:
        rel.updated_at = int(time.time())
        self._conn.execute(
            "INSERT INTO relationships"
            "(id, agent_id, target_agent_id, relationship_type, strength, trust, updated_at)"
            " VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(agent_id, target_agent_id) DO UPDATE SET"
            " relationship_type=excluded.relationship_type,"
            " strength=excluded.strength,"
            " trust=excluded.trust,"
            " updated_at=excluded.updated_at",
            (
                rel.id,
                rel.agent_id,
                rel.target_agent_id,
                rel.relationship_type,
                rel.strength,
                rel.trust,
                rel.updated_at,
            ),
        )
        if commit:
            self._conn.commit()
        return rel

    def get(self, agent_id: str, target_agent_id: str) -> Relationship | None:
        row = self._conn.execute(
            "SELECT * FROM relationships WHERE agent_id=? AND target_agent_id=?",
            (agent_id, target_agent_id),
        ).fetchone()
        return _to_rel(row) if row is not None else None

    def get_all(self, agent_id: str) -> list[Relationship]:
        rows = self._conn.execute(
            "SELECT * FROM relationships WHERE agent_id=? ORDER BY updated_at DESC",
            (agent_id,),
        ).fetchall()
        return [_to_rel(r) for r in rows]

    def delete(self, agent_id: str, target_agent_id: str, *, commit: bool = True) -> None:
        self._conn.execute(
            "DELETE FROM relationships WHERE agent_id=? AND target_agent_id=?",
            (agent_id, target_agent_id),
        )
        if commit:
            self._conn.commit()


def _to_rel(row: sqlite3.Row) -> Relationship:
    return Relationship(
        id=row["id"],
        agent_id=row["agent_id"],
        target_agent_id=row["target_agent_id"],
        relationship_type=row["relationship_type"],
        strength=row["strength"],
        trust=row["trust"],
        updated_at=row["updated_at"],
    )
