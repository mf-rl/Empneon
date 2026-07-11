"""Long-term goal storage — priority-ranked, status-tracked goals per agent."""

import sqlite3
import time
import uuid
from dataclasses import dataclass, field

GOAL_ACTIVE = "active"
GOAL_COMPLETED = "completed"
GOAL_ABANDONED = "abandoned"


@dataclass
class Goal:
    agent_id: str
    description: str
    priority: float = 0.5       # 0.0 (low) to 1.0 (critical)
    status: str = GOAL_ACTIVE   # active | completed | abandoned
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: int = field(default_factory=lambda: int(time.time()))
    updated_at: int = field(default_factory=lambda: int(time.time()))


class GoalStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(self, goal: Goal) -> Goal:
        now = int(time.time())
        goal.created_at = now
        goal.updated_at = now
        self._conn.execute(
            "INSERT INTO goals"
            "(id, agent_id, description, priority, status, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (
                goal.id,
                goal.agent_id,
                goal.description,
                goal.priority,
                goal.status,
                goal.created_at,
                goal.updated_at,
            ),
        )
        self._conn.commit()
        return goal

    def get(self, goal_id: str) -> "Goal | None":
        row = self._conn.execute(
            "SELECT * FROM goals WHERE id=?",
            (goal_id,),
        ).fetchone()
        return _to_goal(row) if row is not None else None

    def get_all(self, agent_id: str, status: str | None = None) -> list[Goal]:
        if status is not None:
            rows = self._conn.execute(
                "SELECT * FROM goals WHERE agent_id=? AND status=?"
                " ORDER BY priority DESC, created_at ASC",
                (agent_id, status),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM goals WHERE agent_id=?"
                " ORDER BY priority DESC, created_at ASC",
                (agent_id,),
            ).fetchall()
        return [_to_goal(r) for r in rows]

    def update_status(self, goal_id: str, status: str) -> None:
        self._conn.execute(
            "UPDATE goals SET status=?, updated_at=? WHERE id=?",
            (status, int(time.time()), goal_id),
        )
        self._conn.commit()

    def delete(self, goal_id: str) -> None:
        self._conn.execute("DELETE FROM goals WHERE id=?", (goal_id,))
        self._conn.commit()


def _to_goal(row: sqlite3.Row) -> Goal:
    return Goal(
        id=row["id"],
        agent_id=row["agent_id"],
        description=row["description"],
        priority=row["priority"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
