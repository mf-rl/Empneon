"""Personality vector storage — 5-dimensional OCEAN model per agent."""

import sqlite3
from dataclasses import dataclass


@dataclass
class Personality:
    agent_id: str
    openness: float = 0.5
    conscientiousness: float = 0.5
    extraversion: float = 0.5
    agreeableness: float = 0.5
    neuroticism: float = 0.5


class PersonalityStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def set(self, personality: Personality) -> Personality:
        self._conn.execute(
            "INSERT INTO personality"
            "(agent_id, openness, conscientiousness, extraversion, agreeableness, neuroticism)"
            " VALUES (?,?,?,?,?,?)"
            " ON CONFLICT(agent_id) DO UPDATE SET"
            " openness=excluded.openness,"
            " conscientiousness=excluded.conscientiousness,"
            " extraversion=excluded.extraversion,"
            " agreeableness=excluded.agreeableness,"
            " neuroticism=excluded.neuroticism",
            (
                personality.agent_id,
                personality.openness,
                personality.conscientiousness,
                personality.extraversion,
                personality.agreeableness,
                personality.neuroticism,
            ),
        )
        self._conn.commit()
        return personality

    def get(self, agent_id: str) -> Personality | None:
        row = self._conn.execute(
            "SELECT * FROM personality WHERE agent_id=?", (agent_id,)
        ).fetchone()
        return _to_personality(row) if row is not None else None


def _to_personality(row: sqlite3.Row) -> Personality:
    return Personality(
        agent_id=row["agent_id"],
        openness=row["openness"],
        conscientiousness=row["conscientiousness"],
        extraversion=row["extraversion"],
        agreeableness=row["agreeableness"],
        neuroticism=row["neuroticism"],
    )
