import contextlib
import json
import os
import re
import sqlite3

from empneon.db.connection import open_db


def connect_db(path, connect, initialize):
    conn = None
    try:
        conn = connect(path)
        conn.row_factory = sqlite3.Row
        initialize(conn)
        conn.commit()
        return conn
    except sqlite3.Error as exc:
        if conn is not None:
            conn.close()
        raise RuntimeError(f"Cannot open legacy database at {path}: {exc}") from exc


def memory_checkpoint_path(database, save_slot_id):
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", save_slot_id):
        raise ValueError("valid save slot id is required")
    return database + ".empneon-saved.slot-" + save_slot_id


def backup_memory_database(source, destination):
    temporary = destination + ".tmp"
    try:
        os.remove(temporary)
    except FileNotFoundError:
        pass
    with (
        contextlib.closing(sqlite3.connect(source)) as source_db,
        contextlib.closing(sqlite3.connect(temporary)) as destination_db,
    ):
        source_db.backup(destination_db)
    os.replace(temporary, destination)


def restore_memory_database(source, destination):
    with (
        contextlib.closing(sqlite3.connect(source)) as source_db,
        contextlib.closing(sqlite3.connect(destination)) as destination_db,
    ):
        source_db.backup(destination_db)


def create_empty_memory_checkpoint(destination):
    temporary = destination + ".tmp"
    try:
        os.remove(temporary)
    except FileNotFoundError:
        pass
    open_db(temporary).close()
    os.replace(temporary, destination)


def read_memory_session(path):
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
            return value if isinstance(value, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def write_memory_session(path, session_id, save_slot_id):
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(
            {"session_id": session_id, "save_slot_id": save_slot_id},
            handle,
        )
    os.replace(temporary, path)


def validate_game_session_id(session_id):
    value = str(session_id or "").strip()
    if not value or len(value) > 128:
        raise ValueError("valid game session id is required")
    return value


_LEGACY_COLUMNS = frozenset(
    {
        ("memories", "sim_id", "text"),
        ("memories", "target_id", "text"),
        ("memories", "event", "text"),
        ("memories", "emotion", "text"),
        ("memories", "category", "text not null default 'short_term'"),
        ("memories", "topic", "text"),
        ("memories", "location", "text"),
    }
)


def ensure_column(conn, table, name, definition):
    if (table, name, definition.casefold()) not in _LEGACY_COLUMNS:
        raise ValueError("unknown legacy schema column")
    rows = conn.execute(f"pragma table_info({table})").fetchall()
    if name not in [row["name"] for row in rows]:
        conn.execute(f"alter table {table} add column {name} {definition}")


def init_db(conn):
    conn.execute(
        """
        create table if not exists sim_profiles (
            sim_id text primary key,
            name text not null,
            identity_json text not null,
            personality_json text not null,
            values_json text not null,
            behavioral_rules_json text not null,
            knowledge_json text not null,
            goals_json text not null,
            voice_json text not null,
            created_at real not null,
            updated_at real not null
        )
        """
    )
    conn.execute(
        """
        create table if not exists memories (
            id integer primary key autoincrement,
            speaker_id text not null,
            listener_id text not null,
            summary text not null,
            importance real not null default 0.5,
            created_at real not null
        )
        """
    )
    for name, definition in (
        ("sim_id", "text"),
        ("target_id", "text"),
        ("event", "text"),
        ("emotion", "text"),
        ("category", "text not null default 'short_term'"),
        ("topic", "text"),
        ("location", "text"),
    ):
        ensure_column(conn, "memories", name, definition)

    conn.execute(
        """
        create table if not exists memory_summaries (
            sim_id text not null,
            target_id text not null,
            summary text not null,
            updated_at real not null,
            primary key (sim_id, target_id)
        )
        """
    )
    conn.execute(
        """
        create table if not exists relationships (
            sim_id text not null,
            target_id text not null,
            friendship integer not null default 0,
            romance integer not null default 0,
            trust integer not null default 50,
            respect integer not null default 50,
            admiration integer not null default 0,
            jealousy integer not null default 0,
            resentment integer not null default 0,
            fear integer not null default 0,
            updated_at real not null,
            primary key (sim_id, target_id)
        )
        """
    )
    conn.execute(
        """
        create table if not exists emotions (
            sim_id text primary key,
            happiness integer not null default 50,
            anger integer not null default 0,
            sadness integer not null default 0,
            stress integer not null default 20,
            confidence integer not null default 50,
            current_mood text not null default 'neutral',
            updated_at real not null
        )
        """
    )
    conn.execute(
        """
        create table if not exists goals (
            id integer primary key autoincrement,
            sim_id text not null,
            goal text not null,
            status text not null default 'active',
            importance real not null default 0.5,
            updated_at real not null
        )
        """
    )
    conn.execute(
        """
        create table if not exists conversations (
            id integer primary key autoincrement,
            conversation_id text not null,
            speaker_id text not null,
            listener_id text not null,
            message text not null,
            response_json text not null,
            created_at real not null
        )
        """
    )
    conn.execute(
        """
        create table if not exists voice_settings (
            sim_id text primary key,
            voice text not null default '',
            speed real not null default 1.0,
            pitch real not null default 0.0,
            provider text not null default '',
            updated_at real not null
        )
        """
    )
