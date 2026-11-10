"""Vector similarity search for episodic memory — backed by sqlite-vec."""

import re
import sqlite3
import struct

import sqlite_vec  # type: ignore[import-untyped]


class VectorMemoryStore:
    """Stores float embeddings keyed by event_id and supports Euclidean (L2) KNN search.

    Distances are sqlite-vec `vec0` defaults (L2). Normalize embeddings before storing if
    cosine-equivalent ranking is required.
    """

    def __init__(
        self, conn: sqlite3.Connection, dimensions: int = 384, *, commit: bool = True
    ) -> None:
        self._conn = conn
        self._dim = dimensions
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        existing = _stored_dimensions(conn)
        if existing is not None and existing != dimensions:
            raise ValueError(
                f"vec_memories has {existing} dimensions, requested {dimensions} dimensions"
            )
        conn.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_memories"
            f" USING vec0(embedding FLOAT[{dimensions}])"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS vec_memory_index"
            "(rowid INTEGER PRIMARY KEY, event_id TEXT UNIQUE NOT NULL)"
        )
        if commit:
            conn.commit()

    def upsert(
        self, event_id: str, embedding: list[float], *, commit: bool = True
    ) -> None:
        packed = self._pack(embedding)
        row = self._conn.execute(
            "SELECT rowid FROM vec_memory_index WHERE event_id=?", (event_id,)
        ).fetchone()
        if row is not None:
            rowid = row[0]
            self._conn.execute("DELETE FROM vec_memories WHERE rowid=?", (rowid,))
            self._conn.execute(
                "INSERT INTO vec_memories(rowid, embedding) VALUES (?,?)", (rowid, packed)
            )
        else:
            cursor = self._conn.execute(
                "INSERT INTO vec_memory_index(event_id) VALUES (?)", (event_id,)
            )
            self._conn.execute(
                "INSERT INTO vec_memories(rowid, embedding) VALUES (?,?)",
                (cursor.lastrowid, packed),
            )
        if commit:
            self._conn.commit()

    def search(self, query_embedding: list[float], limit: int = 10) -> list[tuple[str, float]]:
        """Return (event_id, distance) pairs ordered by distance ascending."""
        packed = self._pack(query_embedding)
        rows = self._conn.execute(
            "SELECT rowid, distance FROM vec_memories"
            " WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
            (packed, limit),
        ).fetchall()
        if not rows:
            return []
        rowids = [r[0] for r in rows]
        placeholders = ",".join("?" * len(rowids))
        idx_rows = self._conn.execute(
            f"SELECT rowid, event_id FROM vec_memory_index WHERE rowid IN ({placeholders})",
            rowids,
        ).fetchall()
        event_ids = {r[0]: r[1] for r in idx_rows}
        return [(event_ids[r[0]], r[1]) for r in rows]

    def delete(self, event_id: str) -> None:
        row = self._conn.execute(
            "SELECT rowid FROM vec_memory_index WHERE event_id=?", (event_id,)
        ).fetchone()
        if row is not None:
            self._conn.execute("DELETE FROM vec_memories WHERE rowid=?", (row[0],))
            self._conn.execute("DELETE FROM vec_memory_index WHERE event_id=?", (event_id,))
            self._conn.commit()

    def _pack(self, embedding: list[float]) -> bytes:
        if len(embedding) != self._dim:
            raise ValueError(f"expected {self._dim} dimensions, got {len(embedding)}")
        return struct.pack(f"{self._dim}f", *embedding)


def _stored_dimensions(conn: sqlite3.Connection) -> int | None:
    row = conn.execute("SELECT sql FROM sqlite_master WHERE name='vec_memories'").fetchone()
    if row is None:
        return None
    match = re.search(r"\[(\d+)\]", row[0])
    return int(match.group(1)) if match else None
