"""Reversible memory archiving, recall bookkeeping, and computed salience (all opt-in).

Nothing here creates or rewrites a fact: it only flags existing `events` rows, so the grounding
rule holds. A missing `memory_state` row means an event is active and has never been recalled.
Archiving is one flag per event, so an archived event is hidden from every participant's opted-in
recall. Times are integer seconds and every `now` is supplied by the caller, never read from a
clock.
"""

import logging
import sqlite3
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass

from empneon.core.memory.episodic import EpisodicMemoryStore, Event
from empneon.db.query import validate_limit

_log = logging.getLogger(__name__)
_CHUNK = 500
_PAGE = 256

# `_CANDIDATES` excludes events that must never be archived: those backing a belief (through its
# source observation) and those cited by an action record, as its event or in its evidence.
_CANDIDATES = """
WITH protected(id) AS (
    SELECT o.event_id FROM belief_provenance p
        JOIN event_observations o ON o.id = p.source_observation_id
    UNION SELECT event_id FROM action_results
    UNION SELECT event_id FROM action_proposals
    UNION SELECT j.value FROM action_results r, json_each(r.evidence_ids) j
    UNION SELECT j.value FROM action_proposals r, json_each(r.evidence_ids) j
)
SELECT e.id FROM events e
JOIN event_participants ep ON ep.event_id = e.id AND ep.agent_id = ?
LEFT JOIN memory_state ms ON ms.event_id = e.id
WHERE ms.archived_at IS NULL
  AND COALESCE(ms.last_recalled_at, e.happened_at) <= ?
  AND e.id NOT IN (SELECT id FROM protected)
  AND e.id NOT IN (
      SELECT x.event_id FROM event_participants x JOIN events n ON n.id = x.event_id
      WHERE x.agent_id = ? ORDER BY n.happened_at DESC, n.id DESC LIMIT ?)
  AND (? OR (SELECT COUNT(*) FROM event_participants s WHERE s.event_id = e.id) = 1)
ORDER BY COALESCE(ms.last_recalled_at, e.happened_at), e.id
LIMIT ? OFFSET ?
"""


@dataclass(frozen=True)
class MemoryState:
    event_id: str
    archived_at: int | None
    recall_count: int
    last_recalled_at: int | None


def salience(anchor: int, now: int, half_life_s: int, floor: float = 0.0) -> float:
    """Memory weight: halves every `half_life_s` seconds after `anchor`, never below `floor`."""
    if half_life_s <= 0:
        raise ValueError("half_life_s must be positive")
    if not 0.0 <= floor <= 1.0:
        raise ValueError("floor must be between 0 and 1")
    return max(floor, 0.5 ** (max(0, now - anchor) / half_life_s))


def _chunks(values: Sequence[str]) -> Iterator[Sequence[str]]:
    for start in range(0, len(values), _CHUNK):
        yield values[start : start + _CHUNK]


def _unique(event_ids: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(event_ids))


class MemoryStateStore:
    """Archive and restore events, track recalls, and sweep by a caller-chosen policy."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._events = EpisodicMemoryStore(conn)

    def get(self, event_id: str) -> MemoryState | None:
        row = self._conn.execute(
            "SELECT * FROM memory_state WHERE event_id=?", (event_id,)
        ).fetchone()
        if row is None:
            return None
        return MemoryState(
            row["event_id"], row["archived_at"], row["recall_count"], row["last_recalled_at"]
        )

    def archived_ids(self, event_ids: Sequence[str]) -> set[str]:
        found: set[str] = set()
        for chunk in _chunks(_unique(event_ids)):
            marks = ",".join("?" * len(chunk))
            rows = self._conn.execute(
                "SELECT event_id FROM memory_state WHERE archived_at IS NOT NULL"  # noqa: S608 - only "?" placeholders are interpolated
                f" AND event_id IN ({marks})",
                list(chunk),
            ).fetchall()
            found.update(row[0] for row in rows)
        return found

    def archive(self, event_ids: Sequence[str], *, now: int, commit: bool = True) -> int:
        """Flag existing, not yet archived events; returns how many changed. Idempotent."""
        _validate_now(now)
        changed = 0
        for chunk in _chunks(_unique(event_ids)):
            for event_id in self._existing(chunk):
                cursor = self._conn.execute(
                    "INSERT INTO memory_state (event_id, archived_at) VALUES (?, ?)"
                    " ON CONFLICT(event_id) DO UPDATE SET archived_at = excluded.archived_at"
                    " WHERE memory_state.archived_at IS NULL",
                    (event_id, now),
                )
                changed += cursor.rowcount
        self._finish(commit)
        return changed

    def restore(self, event_ids: Sequence[str], *, commit: bool = True) -> int:
        """Clear the archive flag, keeping recall bookkeeping; returns how many changed."""
        changed = 0
        for chunk in _chunks(_unique(event_ids)):
            marks = ",".join("?" * len(chunk))
            cursor = self._conn.execute(
                "UPDATE memory_state SET archived_at = NULL WHERE archived_at IS NOT NULL"  # noqa: S608 - only "?" placeholders are interpolated
                f" AND event_id IN ({marks})",
                list(chunk),
            )
            changed += cursor.rowcount
        self._finish(commit)
        return changed

    def record_recall(self, event_ids: Sequence[str], *, now: int, commit: bool = True) -> int:
        """Count a recall and refresh `last_recalled_at` for existing events; returns how many."""
        _validate_now(now)
        touched = 0
        for chunk in _chunks(_unique(event_ids)):
            for event_id in self._existing(chunk):
                self._conn.execute(
                    "INSERT INTO memory_state (event_id, recall_count, last_recalled_at)"
                    " VALUES (?, 1, ?) ON CONFLICT(event_id) DO UPDATE SET"
                    " recall_count = recall_count + 1,"
                    " last_recalled_at = excluded.last_recalled_at",
                    (event_id, now),
                )
                touched += 1
        self._finish(commit)
        return touched

    def salience_for(
        self, event_ids: Sequence[str], *, now: int, half_life_s: int, floor: float = 0.0
    ) -> dict[str, float]:
        """Salience of each existing event, anchored on its last recall, else when it happened."""
        salience(0, now, half_life_s, floor)  # validate once
        scores: dict[str, float] = {}
        for chunk in _chunks(_unique(event_ids)):
            marks = ",".join("?" * len(chunk))
            rows = self._conn.execute(
                "SELECT e.id, COALESCE(ms.last_recalled_at, e.happened_at) AS anchor"  # noqa: S608 - only "?" placeholders are interpolated
                " FROM events e LEFT JOIN memory_state ms ON ms.event_id = e.id"
                f" WHERE e.id IN ({marks})",
                list(chunk),
            ).fetchall()
            for row in rows:
                scores[row["id"]] = salience(row["anchor"], now, half_life_s, floor)
        return scores

    def sweep(
        self,
        agent_id: str,
        *,
        now: int,
        older_than_s: int,
        max_rows: int,
        keep_latest: int = 0,
        eligible: Callable[[Event], bool] | None = None,
        include_shared: bool = False,
        commit: bool = True,
    ) -> tuple[str, ...]:
        """Archive up to `max_rows` of an agent's old events, oldest first, and return their ids.

        An event is old when its last recall (else when it happened) is at least `older_than_s`
        before `now`. The agent's newest `keep_latest` events are kept. Events with other
        participants are skipped unless `include_shared`, because archiving hides them from every
        participant. Events backing a belief or cited by an action record are never archived, and
        `eligible` may veto more. Idempotent; logs counts only.
        """
        _validate_now(now)
        validate_limit(max_rows)
        if older_than_s < 0 or keep_latest < 0:
            raise ValueError("older_than_s and keep_latest must not be negative")
        chosen: list[str] = []
        offset = 0
        while len(chosen) < max_rows:
            rows = self._conn.execute(
                _CANDIDATES,
                (
                    agent_id,
                    now - older_than_s,
                    agent_id,
                    keep_latest,
                    include_shared,
                    _PAGE,
                    offset,
                ),
            ).fetchall()
            if not rows:
                break
            offset += len(rows)
            for (event_id,) in rows:
                if len(chosen) == max_rows:
                    break
                if eligible is not None:
                    event = self._events.get(event_id)
                    if event is None or not eligible(event):
                        continue
                chosen.append(event_id)
        self.archive(chosen, now=now, commit=commit)
        _log.debug("memory sweep archived %d events", len(chosen))
        return tuple(chosen)

    def _existing(self, event_ids: Sequence[str]) -> list[str]:
        marks = ",".join("?" * len(event_ids))
        rows = self._conn.execute(
            f"SELECT id FROM events WHERE id IN ({marks})",  # noqa: S608 - only "?" placeholders are interpolated
            list(event_ids),
        ).fetchall()
        present = {row[0] for row in rows}
        return [event_id for event_id in event_ids if event_id in present]

    def _finish(self, commit: bool) -> None:
        if commit:
            self._conn.commit()


def _validate_now(now: int) -> None:
    if now < 0:
        raise ValueError("now must not be negative")


__all__ = ["MemoryState", "MemoryStateStore", "salience"]
