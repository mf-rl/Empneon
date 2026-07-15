"""Read-only replay and state-delta inspection for confirmed actions."""

import sqlite3
from collections.abc import Sequence
from dataclasses import asdict

from empneon.core.contracts import StateDelta
from empneon.core.memory.episodic import EpisodicMemoryStore
from empneon.core.runtime import ActionRecordStore


def inspect_state_deltas(
    proposed: Sequence[StateDelta], applied: Sequence[StateDelta]
) -> dict[str, list[dict[str, object]]]:
    """Compare proposed and applied deltas while preserving duplicates and order."""
    remaining = list(applied)
    matched: list[StateDelta] = []
    not_applied: list[StateDelta] = []
    for delta in proposed:
        try:
            position = remaining.index(delta)
        except ValueError:
            not_applied.append(delta)
        else:
            matched.append(delta)
            remaining.pop(position)
    return {
        "matched": [asdict(delta) for delta in matched],
        "not_applied": [asdict(delta) for delta in not_applied],
        "additional": [asdict(delta) for delta in remaining],
    }


def replay_action_record(conn: sqlite3.Connection, decision_id: str) -> dict[str, object]:
    """Reconstruct a confirmed action without executing cognition or game mutations."""
    actions = ActionRecordStore(conn)
    record = actions.get(decision_id)
    if record is None:
        raise ValueError("confirmed action does not exist")
    event = EpisodicMemoryStore(conn).get(record.event_id)
    consequences = actions.get_consequences(decision_id)
    return {
        "event_id": record.event_id,
        "event": None if event is None else asdict(event),
        "decision": asdict(record.decision),
        "result": asdict(record.result),
        "deltas": inspect_state_deltas(
            record.decision.state_changes, record.result.applied_changes
        ),
        "consequence_integrity": consequences == record.result.applied_changes,
    }
