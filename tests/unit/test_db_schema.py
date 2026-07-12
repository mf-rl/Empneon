import sqlite3

import pytest

from empneon.db.connection import _apply_schema, open_db
from empneon.db.schema import ALL_DDL, SCHEMA_VERSION

EXPECTED_TABLES = frozenset(
    {
        "schema_version",
        "agents",
        "personality",
        "relationships",
        "emotional_states",
        "goals",
        "voice_profiles",
        "agent_metadata",
        "cognition_usage",
    }
)

EXPECTED_INDEXES = frozenset(
    {
        "idx_relationships_agent",
        "idx_relationships_target",
        "idx_goals_agent_status",
        "idx_emotional_states_agent",
    }
)

EXPECTED_TRIGGERS = frozenset(
    {
        "validate_agents_insert",
        "validate_agents_update",
        "validate_personality_insert",
        "validate_personality_update",
        "validate_relationships_insert",
        "validate_relationships_update",
        "validate_emotions_insert",
        "validate_emotions_update",
        "validate_goals_insert",
        "validate_goals_update",
        "validate_voice_insert",
        "validate_voice_update",
    }
)


@pytest.fixture()
def db() -> sqlite3.Connection:
    return open_db(":memory:")


def test_all_tables_exist(db: sqlite3.Connection) -> None:
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert EXPECTED_TABLES.issubset(tables)


def test_all_indexes_exist(db: sqlite3.Connection) -> None:
    indexes = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert EXPECTED_INDEXES.issubset(indexes)


def test_all_validation_triggers_exist(db: sqlite3.Connection) -> None:
    triggers = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
    assert EXPECTED_TRIGGERS == triggers


def test_schema_version_set(db: sqlite3.Connection) -> None:
    row = db.execute("SELECT version FROM schema_version").fetchone()
    assert row is not None
    assert row[0] == SCHEMA_VERSION


def test_migrates_v1_schema_to_current() -> None:
    conn = sqlite3.connect(":memory:")
    for ddl in ALL_DDL:
        conn.execute(ddl)
    conn.execute("INSERT INTO schema_version VALUES (1)")
    conn.commit()

    _apply_schema(conn)

    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == SCHEMA_VERSION
    assert conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='trigger' AND name='validate_personality_insert'"
    ).fetchone() == (1,)


def test_rejects_database_newer_than_runtime() -> None:
    conn = sqlite3.connect(":memory:")
    for ddl in ALL_DDL:
        conn.execute(ddl)
    conn.execute("INSERT INTO schema_version VALUES (?)", (SCHEMA_VERSION + 1,))
    conn.commit()

    with pytest.raises(RuntimeError, match="newer than runtime"):
        _apply_schema(conn)

    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == SCHEMA_VERSION + 1


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
    row = db.execute("SELECT * FROM personality WHERE agent_id=?", ("a1",)).fetchone()
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


def test_insert_range_constraints(db: sqlite3.Connection) -> None:
    for agent_id in ("a1", "a2"):
        db.execute(
            "INSERT INTO agents(id, name, created_at, updated_at) VALUES (?,?,?,?)",
            (agent_id, agent_id, 1000, 1000),
        )
    db.commit()

    invalid_writes = [
        (
            "INSERT INTO agents(id, name, age, created_at, updated_at) VALUES (?,?,?,?,?)",
            ("bad-age", "Bad", -1, 1000, 1000),
        ),
        (
            "INSERT INTO personality(agent_id, openness) VALUES (?,?)",
            ("a1", 1.1),
        ),
        (
            "INSERT INTO relationships"
            "(id, agent_id, target_agent_id, relationship_type, strength, updated_at)"
            " VALUES (?,?,?,?,?,?)",
            ("bad-rel", "a1", "a2", "friend", -1.1, 1000),
        ),
        (
            "INSERT INTO emotional_states(agent_id, emotion, value, updated_at) VALUES (?,?,?,?)",
            ("a1", "joy", 1.1, 1000),
        ),
        (
            "INSERT INTO goals"
            "(id, agent_id, description, priority, status, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?)",
            ("bad-goal", "a1", "Goal", 0.5, "unknown", 1000, 1000),
        ),
        (
            "INSERT INTO voice_profiles(agent_id, speed, pitch) VALUES (?,?,?)",
            ("a1", 0.0, 1.0),
        ),
    ]

    for statement, values in invalid_writes:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(statement, values)
        db.rollback()


def test_update_range_constraints(db: sqlite3.Connection) -> None:
    db.execute(
        "INSERT INTO agents(id, name, created_at, updated_at) VALUES (?,?,?,?)",
        ("a1", "Alice", 1000, 1000),
    )
    db.execute("INSERT INTO personality(agent_id) VALUES (?)", ("a1",))
    db.commit()

    with pytest.raises(sqlite3.IntegrityError, match="personality values"):
        db.execute("UPDATE personality SET neuroticism=? WHERE agent_id=?", (-0.1, "a1"))

    assert db.execute("SELECT neuroticism FROM personality WHERE agent_id=?", ("a1",)).fetchone()[
        0
    ] == pytest.approx(0.5)
