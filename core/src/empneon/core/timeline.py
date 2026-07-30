"""Read-only developer timeline assembled from canonical Core records."""

import sqlite3
from dataclasses import asdict

from empneon.core.memory.episodic import BeliefStore, EpisodicMemoryStore
from empneon.core.runtime import ActionRecordStore


def agent_timeline(
    conn: sqlite3.Connection, agent_id: str, limit: int | None = None
) -> dict[str, object]:
    """Return an agent's events, confirmed decisions, and beliefs newest first."""
    if limit is not None and limit < 1:
        raise ValueError("timeline limit must be positive")

    entries: list[dict[str, object]] = []
    for event in EpisodicMemoryStore(conn).get_for_agent(agent_id, limit):
        entries.append(
            {
                "type": "event",
                "id": event.id,
                "occurred_at": event.happened_at,
                "data": asdict(event),
            }
        )
    for record in ActionRecordStore(conn).get_for_agent(agent_id, limit):
        entries.append(
            {
                "type": "decision",
                "id": record.decision.id,
                "occurred_at": record.result.completed_at,
                "data": {
                    "event_id": record.event_id,
                    "decision": asdict(record.decision),
                    "result": asdict(record.result),
                },
            }
        )
    for belief in BeliefStore(conn).get_for_agent(agent_id, limit):
        entries.append(
            {
                "type": "belief",
                "id": belief.id,
                "occurred_at": belief.created_at,
                "data": asdict(belief),
            }
        )

    entries.sort(
        key=lambda entry: (entry["occurred_at"], entry["type"], entry["id"]),
        reverse=True,
    )
    return {"agent_id": agent_id, "entries": entries[:limit]}
