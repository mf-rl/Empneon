"""Small namespaced JSON document store for adapter-neutral memory extensions."""

import json
import sqlite3
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryDocument:
    namespace: str
    key: str
    value: object
    updated_at: int


class DocumentMemoryStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def set(self, namespace: str, key: str, value: object) -> MemoryDocument:
        if not namespace.strip() or not key.strip():
            raise ValueError("memory document namespace and key are required")
        updated_at = time.time_ns()
        self._conn.execute(
            "INSERT INTO memory_documents(namespace, key, value, updated_at) VALUES (?,?,?,?)"
            " ON CONFLICT(namespace, key) DO UPDATE SET"
            " value=excluded.value, updated_at=excluded.updated_at",
            (namespace, key, json.dumps(value), updated_at),
        )
        self._conn.commit()
        return MemoryDocument(namespace, key, value, updated_at)

    def get(self, namespace: str, key: str) -> object | None:
        row = self._conn.execute(
            "SELECT value FROM memory_documents WHERE namespace=? AND key=?",
            (namespace, key),
        ).fetchone()
        return None if row is None else json.loads(row["value"])

    def list(self, namespace: str, limit: int | None = None) -> list[MemoryDocument]:
        query = (
            "SELECT namespace, key, value, updated_at FROM memory_documents"
            " WHERE namespace=? ORDER BY updated_at DESC, key DESC"
        )
        args: tuple[object, ...] = (namespace,)
        if limit is not None:
            query += " LIMIT ?"
            args = (namespace, limit)
        return [
            MemoryDocument(
                row["namespace"], row["key"], json.loads(row["value"]), row["updated_at"]
            )
            for row in self._conn.execute(query, args).fetchall()
        ]

    def delete(self, namespace: str, key: str) -> None:
        self._conn.execute(
            "DELETE FROM memory_documents WHERE namespace=? AND key=?", (namespace, key)
        )
        self._conn.commit()
