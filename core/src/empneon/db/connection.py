"""SQLite connection factory with schema initialization."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from empneon.db.schema import ALL_DDL, MIGRATIONS, SCHEMA_VERSION


def open_db(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _apply_schema(conn)
        return conn
    except Exception:
        conn.close()
        raise


@contextmanager
def db_session(path: str | Path) -> Iterator[sqlite3.Connection]:
    conn = open_db(path)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _apply_schema(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("BEGIN")
        for ddl in ALL_DDL:
            conn.execute(ddl)

        rows = conn.execute("SELECT version FROM schema_version").fetchall()
        if len(rows) > 1:
            raise RuntimeError("schema_version must contain exactly one row")

        if not rows:
            current_version = 1
            conn.execute("INSERT INTO schema_version VALUES (?)", (current_version,))
        else:
            current_version = int(rows[0][0])

        if current_version < 1:
            raise RuntimeError(f"unsupported database schema version: {current_version}")
        if current_version > SCHEMA_VERSION:
            raise RuntimeError(
                f"database schema {current_version} is newer than runtime schema {SCHEMA_VERSION}"
            )

        while current_version < SCHEMA_VERSION:
            target_version = current_version + 1
            migration = MIGRATIONS.get(target_version)
            if migration is None:
                raise RuntimeError(f"missing database migration to version {target_version}")
            for statement in migration:
                conn.execute(statement)
            conn.execute("UPDATE schema_version SET version=?", (target_version,))
            current_version = target_version

        conn.commit()
    except Exception:
        conn.rollback()
        raise
