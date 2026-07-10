"""Emotional state storage — ODE triple (value, velocity, acceleration) per emotion."""

import sqlite3
import time
from dataclasses import dataclass, field


@dataclass
class EmotionalState:
    agent_id: str
    emotion: str
    value: float = 0.0         # current intensity, 0.0–1.0
    velocity: float = 0.0      # rate of change per tick
    acceleration: float = 0.0  # rate of velocity change per tick
    updated_at: int = field(default_factory=lambda: int(time.time()))


class EmotionalStateStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def set(self, state: EmotionalState) -> EmotionalState:
        state.updated_at = int(time.time())
        self._conn.execute(
            "INSERT INTO emotional_states"
            "(agent_id, emotion, value, velocity, acceleration, updated_at)"
            " VALUES (?,?,?,?,?,?)"
            " ON CONFLICT(agent_id, emotion) DO UPDATE SET"
            " value=excluded.value,"
            " velocity=excluded.velocity,"
            " acceleration=excluded.acceleration,"
            " updated_at=excluded.updated_at",
            (
                state.agent_id,
                state.emotion,
                state.value,
                state.velocity,
                state.acceleration,
                state.updated_at,
            ),
        )
        self._conn.commit()
        return state

    def get(self, agent_id: str, emotion: str) -> EmotionalState | None:
        row = self._conn.execute(
            "SELECT * FROM emotional_states WHERE agent_id=? AND emotion=?",
            (agent_id, emotion),
        ).fetchone()
        return _to_state(row) if row is not None else None

    def get_all(self, agent_id: str) -> list[EmotionalState]:
        rows = self._conn.execute(
            "SELECT * FROM emotional_states WHERE agent_id=? ORDER BY emotion",
            (agent_id,),
        ).fetchall()
        return [_to_state(r) for r in rows]

    def delete(self, agent_id: str, emotion: str) -> None:
        self._conn.execute(
            "DELETE FROM emotional_states WHERE agent_id=? AND emotion=?",
            (agent_id, emotion),
        )
        self._conn.commit()


def _to_state(row: sqlite3.Row) -> EmotionalState:
    return EmotionalState(
        agent_id=row["agent_id"],
        emotion=row["emotion"],
        value=row["value"],
        velocity=row["velocity"],
        acceleration=row["acceleration"],
        updated_at=row["updated_at"],
    )
