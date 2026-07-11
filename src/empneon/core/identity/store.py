"""CRUD operations for Agent identity records."""

import sqlite3
import time

from empneon.core.identity.models import Agent


class AgentStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(self, agent: Agent, *, commit: bool = True) -> Agent:
        self._conn.execute(
            "INSERT INTO agents"
            "(id, name, age, occupation, game_id, adapter, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (
                agent.id,
                agent.name,
                agent.age,
                agent.occupation,
                agent.game_id,
                agent.adapter,
                agent.created_at,
                agent.updated_at,
            ),
        )
        if commit:
            self._conn.commit()
        return agent

    def get(self, agent_id: str) -> Agent | None:
        row = self._conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
        return _to_agent(row) if row is not None else None

    def update(self, agent: Agent, *, commit: bool = True) -> Agent:
        agent.updated_at = int(time.time())
        self._conn.execute(
            "UPDATE agents"
            " SET name=?, age=?, occupation=?, game_id=?, adapter=?, updated_at=?"
            " WHERE id=?",
            (
                agent.name,
                agent.age,
                agent.occupation,
                agent.game_id,
                agent.adapter,
                agent.updated_at,
                agent.id,
            ),
        )
        if commit:
            self._conn.commit()
        return agent

    def delete(self, agent_id: str) -> None:
        self._conn.execute("DELETE FROM agents WHERE id=?", (agent_id,))
        self._conn.commit()

    def list_all(self) -> list[Agent]:
        rows = self._conn.execute("SELECT * FROM agents ORDER BY name").fetchall()
        return [_to_agent(r) for r in rows]

    def list_by_adapter(self, adapter: str) -> list[Agent]:
        rows = self._conn.execute(
            "SELECT * FROM agents WHERE adapter=? ORDER BY name", (adapter,)
        ).fetchall()
        return [_to_agent(r) for r in rows]


def _to_agent(row: sqlite3.Row) -> Agent:
    return Agent(
        id=row["id"],
        name=row["name"],
        age=row["age"],
        occupation=row["occupation"],
        game_id=row["game_id"],
        adapter=row["adapter"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
