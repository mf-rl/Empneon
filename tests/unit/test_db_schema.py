import sqlite3

import pytest

from empneon.db.connection import open_db
from empneon.db.schema import SCHEMA_VERSION

EXPECTED_TABLES = frozenset({
    "schema_version",
    "agents",
    "personality",
    "relationships",
    "emotional_states",
    "goals",
    "voice_profiles",
    "agent_metadata",
})

EXPECTED_INDEXES = frozenset({
    "idx_relationships_agent",
    "idx_relationships_target",
    "idx_goals_agent_status",
    "idx_emotional_states_agent",
})


@pytest.fixture()
def db() -> sqlite3.Connection:
    return open_db(":memory:")


def test_all_tables_exist(db: sqlite3.Connection) -> None:
    tables = {
        row[0]
        for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert EXPECTED_TABLES.issubset(tables)


def test_all_indexes_exist(db: sqlite3.Connection) -> None:
    indexes = {
        row[0]
        for row in db.execute("SELECT name FROM sqlite_master WHERE type='index'")
    }
    assert EXPECTED_INDEXES.issubset(indexes)


def test_schema_version_set(db: sqlite3.Connection) -> None:
    row = db.execute("SELECT version FROM schema_version").fetchone()
    assert row is not None
    assert row[0] == SCHEMA_VERSION


def test_open_db_twice_is_idempotent(tmp_path: pytest.TempPathFactory) -> None:
    p = str(tmp_path) + "/test.db"  # type: ignore[operator]
    open_db(p).close()
    open_db(p).close()  # second open must not raise or corrupt


def test_agent_insert_and_query(db: sqlite3.Connection) -> None:
    db.execute(
        "INSERT INTO agents(id, name, created_at, updated_at) VALUES (?,?,?,?)",
        ("a1", "Alice", 1000, 1000),
    )
    db.commit()
    row = db.execute("SELECT name FROM agents WHERE id=?", ("a1",)).fetchone()
    assert row is not None
    assert row["name"] == "Alice"


def test_foreign_key_cascade_delete(db: sqlite3.Connection) -> None:
    db.execute(
        "INSERT INTO agents(id, name, created_at, updated_at) VALUES (?,?,?,?)",
        ("a1", "Bob", 1000, 1000),
    )
    db.execute("INSERT INTO personality(agent_id) VALUES (?)", ("a1",))
    db.commit()
    db.execute("DELETE FROM agents WHERE id=?", ("a1",))
    db.commit()
    row = db.execute(
        "SELECT * FROM personality WHERE agent_id=?", ("a1",)
    ).fetchone()
    assert row is None


def test_relationship_uniqueness_constraint(db: sqlite3.Connection) -> None:
    for agent_id, name in [("a1", "Alice"), ("a2", "Bob")]:
        db.execute(
            "INSERT INTO agents(id, name, created_at, updated_at) VALUES (?,?,?,?)",
            (agent_id, name, 1000, 1000),
        )
    db.execute(
        "INSERT INTO relationships(id, agent_id, target_agent_id, relationship_type, updated_at)"
        " VALUES (?,?,?,?,?)",
        ("r1", "a1", "a2", "friend", 1000),
    )
    db.commit()
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO relationships"
            "(id, agent_id, target_agent_id, relationship_type, updated_at)"
            " VALUES (?,?,?,?,?)",
            ("r2", "a1", "a2", "rival", 1000),
        )
