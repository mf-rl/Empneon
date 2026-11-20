"""Semantic (embedding-based) recall of an agent's episodic memories.

`SemanticMemoryIndex` embeds event descriptions with an `EmbeddingProvider`, stores the vectors in
`VectorMemoryStore`, and answers "what does this agent remember that is like X?" restricted to the
events that agent owns. Nothing is logged except counts, and provider failures propagate untouched
so the caller decides how to fall back.
"""

import logging
import sqlite3
from collections.abc import Sequence
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from typing import Literal

from empneon.core.memory.episodic import EpisodicMemoryStore, Event
from empneon.core.memory.state import MemoryStateStore
from empneon.core.memory.vector import VectorMemoryStore
from empneon.db.query import validate_limit
from empneon.providers.llm.embeddings import EmbeddingProvider

_log = logging.getLogger(__name__)

Ownership = Literal["participants", "observations"]
_OVERFETCH = 4
_CHUNK = 500  # stays well under SQLite's bound-variable limit
_OWNED_SQL: dict[str, str] = {
    "participants": "SELECT event_id FROM event_participants WHERE agent_id=? AND event_id IN ({})",
    "observations": "SELECT event_id FROM event_observations WHERE agent_id=? AND event_id IN ({})",
}


@dataclass(frozen=True)
class SemanticMatch:
    """A remembered event and its Euclidean distance to the query (0 is identical)."""

    event: Event
    distance: float


class SemanticMemoryIndex:
    """Indexes event descriptions and searches them by meaning, scoped to one agent.

    `ownership` decides which events an agent may recall: those it took part in
    (`"participants"`, the default) or those it recorded an observation for (`"observations"`).
    Vector dimensions come from the embedder's first result; a table with other dimensions raises
    `ValueError`. With `commit=False` the caller owns the transaction.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        embedder: EmbeddingProvider,
        *,
        ownership: Ownership = "participants",
    ) -> None:
        if ownership not in _OWNED_SQL:
            raise ValueError("ownership must be 'participants' or 'observations'")
        self._conn = conn
        self._embedder = embedder
        self._ownership = ownership
        self._events = EpisodicMemoryStore(conn)

    async def index_event(self, event: Event, *, commit: bool = True) -> None:
        await self.index_events([event], commit=commit)

    async def index_events(self, events: Sequence[Event], *, commit: bool = True) -> int:
        """Embed and store every event in one provider call; re-indexing replaces vectors."""
        if not events:
            return 0
        texts = [_text(event) for event in events]
        result = await self._embedder.embed(texts)
        if len(result.vectors) != len(events):
            raise ValueError("embedder returned a different number of vectors than texts")
        with _unit(self._conn, commit):
            store = VectorMemoryStore(self._conn, result.dimensions, commit=False)
            for event, vector in zip(events, result.vectors, strict=True):
                store.upsert(event.id, list(vector), commit=False)
        _log.debug("indexed %d events", len(events))
        return len(events)

    async def index_unindexed(self, *, limit: int = 256, commit: bool = True) -> int:
        """Index up to `limit` events that have no vector yet, oldest first; returns the count."""
        validate_limit(limit)
        if VectorMemoryStore.existing(self._conn, commit=False) is None:
            query = "SELECT id FROM events ORDER BY happened_at, id LIMIT ?"
        else:
            query = (
                "SELECT id FROM events WHERE id NOT IN (SELECT event_id FROM vec_memory_index)"
                " ORDER BY happened_at, id LIMIT ?"
            )
        ids = [row[0] for row in self._conn.execute(query, (limit,)).fetchall()]
        events = [event for event in (self._events.get(i) for i in ids) if event is not None]
        return await self.index_events(events, commit=commit)

    async def search(
        self, agent_id: str, query: str, limit: int = 5, *, include_archived: bool = True
    ) -> list[SemanticMatch]:
        """Return up to `limit` of the agent's events nearest to `query`, closest first.

        `include_archived=False` skips events archived through `MemoryStateStore`; the search
        keeps widening its candidate window so archived events do not shrink the result.
        """
        validate_limit(limit)
        if not query.strip():
            raise ValueError("query must not be blank")
        result = await self._embedder.embed([query])
        if VectorMemoryStore.existing(self._conn, commit=False) is None:
            return []
        store = VectorMemoryStore(self._conn, result.dimensions, commit=False)
        vector = list(result.vectors[0])
        total = int(self._conn.execute("SELECT COUNT(*) FROM vec_memory_index").fetchone()[0])
        fetch = min(total, limit * _OVERFETCH)
        while fetch > 0:
            pairs = store.search(vector, fetch)
            owned = self._owned(agent_id, [event_id for event_id, _ in pairs])
            if not include_archived:
                owned -= MemoryStateStore(self._conn).archived_ids(sorted(owned))
            matches: list[SemanticMatch] = []
            for event_id, distance in sorted(pairs, key=lambda pair: (pair[1], pair[0])):
                event = self._events.get(event_id) if event_id in owned else None
                if event is not None:
                    matches.append(SemanticMatch(event, distance))
                    if len(matches) == limit:
                        return matches
            if fetch >= total:
                return matches
            fetch = min(total, fetch * 2)
        return []

    def remove(self, event_id: str, *, commit: bool = True) -> None:
        """Delete an event's vector.

        `EpisodicMemoryStore.delete` already does this; use `remove` for events deleted by other
        means.
        """
        store = VectorMemoryStore.existing(self._conn, commit=False)
        if store is not None:
            store.delete(event_id, commit=commit)

    def prune_orphans(self, *, commit: bool = True) -> int:
        """Delete vectors whose event no longer exists; returns the count (0 without tables)."""
        store = VectorMemoryStore.existing(self._conn, commit=False)
        return 0 if store is None else store.prune_orphans(commit=commit)

    def _owned(self, agent_id: str, event_ids: Sequence[str]) -> set[str]:
        owned: set[str] = set()
        sql = _OWNED_SQL[self._ownership]
        for start in range(0, len(event_ids), _CHUNK):
            chunk = list(event_ids[start : start + _CHUNK])
            placeholders = ",".join("?" * len(chunk))
            rows = self._conn.execute(
                sql.format(placeholders),  # noqa: S608 - only "?" placeholders are interpolated
                (agent_id, *chunk),
            ).fetchall()
            owned.update(row[0] for row in rows)
        return owned


def _text(event: Event) -> str:
    if not event.description.strip():
        raise ValueError("event description must not be blank")
    return event.description


def _unit(conn: sqlite3.Connection, commit: bool) -> AbstractContextManager[object]:
    """Commit or roll back on exit when this index owns the transaction."""
    return conn if commit else nullcontext()
