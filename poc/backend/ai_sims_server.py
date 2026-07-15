import ast
import asyncio
import contextlib
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import re
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

from empneon.adapters.sims4 import Sims4PocAdapter
from empneon.core.contracts import ActionResult, CognitiveRequest, Decision, StateDelta
from empneon.core.identity.models import Agent
from empneon.core.identity.relationships import Relationship, RelationshipStore
from empneon.core.identity.store import AgentStore
from empneon.core.runtime import ActionRecordStore, CognitiveRuntime
from empneon.core.scheduler.resources import ResourceBudget, ResourceEstimate, ResourceGovernor
from empneon.db.connection import open_db
from empneon.providers.llm import ProviderError

CONFIG_PATH = os.environ.get("AI_SIM_CONFIG", os.path.join(ROOT, "config", "config.json"))

DEFAULT_CONFIG = {
    "host": "127.0.0.1",
    "port": 8765,
    "debug": True,
    "database": "ai_sims_memory.sqlite3",
    "core_database": "empneon_core.sqlite3",
    "active_agent_limit": 5,
    "agent_wake_timeout_seconds": 60,
    "provider": "lmstudio",
    "providers": {
        "lmstudio": {"endpoint": "http://127.0.0.1:1234/api/v1", "model": "local-model"},
        "ollama": {"endpoint": "http://127.0.0.1:11434/v1", "model": "llama3"},
        "openai": {"endpoint": "https://api.openai.com/v1", "model": "gpt-4.1-mini"},
        "llamacpp": {"endpoint": "http://127.0.0.1:8080/v1", "model": "local-model"},
        "koboldcpp": {"endpoint": "http://127.0.0.1:5001/v1", "model": "local-model"},
        "textgenwebui": {"endpoint": "http://127.0.0.1:5000/v1", "model": "local-model"},
    },
    "models": {
        "small": {"temperature": 0.4, "max_tokens": 300},
        "large": {"temperature": 0.6, "max_tokens": 500},
    },
    "memory": {
        "recent_limit": 6,
        "summary_every": 10,
        "summary_limit": 30,
    },
    "tts": {
        "enabled": False,
        "provider": "piper",
        "endpoint": "",
    },
}


def deep_update(base, overrides):
    for key, value in (overrides or {}).items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_update(base[key], value)
        else:
            base[key] = value
    return base


def load_config():
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
            deep_update(config, json.load(handle))
    except FileNotFoundError:
        pass
    except Exception as exc:
        sys.stderr.write("Could not read config {}: {}\n".format(CONFIG_PATH, exc))

    if os.environ.get("AI_SIM_PROVIDER"):
        config["provider"] = os.environ["AI_SIM_PROVIDER"]
    if os.environ.get("AI_SIM_LLM_BASE_URL"):
        provider = config.get("provider") or "lmstudio"
        config.setdefault("providers", {}).setdefault(provider, {})["endpoint"] = os.environ["AI_SIM_LLM_BASE_URL"]
    if os.environ.get("AI_SIM_MODEL"):
        provider = config.get("provider") or "lmstudio"
        config.setdefault("providers", {}).setdefault(provider, {})["model"] = os.environ["AI_SIM_MODEL"]
        for task in ("small", "large"):
            config.setdefault("models", {}).setdefault(task, {})["model"] = os.environ["AI_SIM_MODEL"]
    if os.environ.get("AI_SIM_DB"):
        config["database"] = os.environ["AI_SIM_DB"]
    if os.environ.get("AI_SIM_PORT"):
        config["port"] = int(os.environ["AI_SIM_PORT"])
    if os.environ.get("AI_SIM_HOST"):
        config["host"] = os.environ["AI_SIM_HOST"]
    return config


CONFIG = load_config()
HOST = str(CONFIG.get("host") or "127.0.0.1")
PORT = int(CONFIG.get("port") or 8765)
DB_PATH = str(CONFIG.get("database") or "ai_sims_memory.sqlite3")
CORE_DB_PATH = str(CONFIG.get("core_database") or "empneon_core.sqlite3")
ACTIVE_AGENT_LIMIT = int(CONFIG.get("active_agent_limit") or 5)
AGENT_WAKE_TIMEOUT = int(CONFIG.get("agent_wake_timeout_seconds") or 60)
PRIMARY_PROVIDER = str(CONFIG.get("provider") or "lmstudio")
PRIMARY_PROVIDER_CONFIG = CONFIG.get("providers", {}).get(PRIMARY_PROVIDER, {})
LLM_BASE_URL = str(PRIMARY_PROVIDER_CONFIG.get("endpoint") or "http://127.0.0.1:1234/api/v1").rstrip("/")
LLM_MODEL = str(PRIMARY_PROVIDER_CONFIG.get("model") or "local-model")
ACTIVE_DB_PATH = None
CORE_GOVERNOR = ResourceGovernor(ResourceBudget(256, 0, ACTIVE_AGENT_LIMIT))


def setup_logging():
    log_dir = os.path.join(ROOT, "logs")
    try:
        os.makedirs(log_dir, exist_ok=True)
    except Exception:
        log_dir = tempfile.gettempdir()
    root_logger = logging.getLogger("ai_sims")
    root_logger.setLevel(logging.DEBUG if CONFIG.get("debug") else logging.INFO)
    if root_logger.handlers:
        return root_logger
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    for name in ("agent_manager", "ai_provider", "memory"):
        handler = RotatingFileHandler(os.path.join(log_dir, name + ".log"), maxBytes=512000, backupCount=3)
        handler.setFormatter(formatter)
        logging.getLogger("ai_sims." + name).addHandler(handler)
        logging.getLogger("ai_sims." + name).setLevel(root_logger.level)
    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(formatter)
    root_logger.addHandler(stream)
    return root_logger


LOG = setup_logging()
AGENT_LOG = logging.getLogger("ai_sims.agent_manager")
PROVIDER_LOG = logging.getLogger("ai_sims.ai_provider")
MEMORY_LOG = logging.getLogger("ai_sims.memory")


class ReasoningOnlyResponse(RuntimeError):
    pass


SYSTEM_PROMPT = """You roleplay one The Sims 4 character.
Stay grounded in the Sim profile, relationship, current mood, and memories.
Return one valid JSON object only. No markdown. No schema explanation. No placeholders.
Do not write a thinking process, analysis, reasoning, or chain-of-thought.
The first character of your response must be {.
Keep dialogue under 30 words.
Use this exact shape with concrete values:
{
  "dialogue": "short in-character line",
  "emotion": "tense",
  "intent": "deflect",
  "relationship": {
    "friendship_delta": 1,
    "romance_delta": 0,
    "trust_delta": -1
  },
  "memory": {
    "importance": 0.4,
    "summary": "One concrete event memory."
  },
  "animation": "awkward_chat"
}
"""

DIALOGUE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "dialogue": {"type": "string"},
        "emotion": {"type": "string"},
        "intent": {"type": "string"},
        "relationship": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "friendship_delta": {"type": "integer", "minimum": -10, "maximum": 10},
                "romance_delta": {"type": "integer", "minimum": -10, "maximum": 10},
                "trust_delta": {"type": "integer", "minimum": -10, "maximum": 10},
                "respect_delta": {"type": "integer", "minimum": -10, "maximum": 10},
                "admiration_delta": {"type": "integer", "minimum": -10, "maximum": 10},
                "jealousy_delta": {"type": "integer", "minimum": -10, "maximum": 10},
                "resentment_delta": {"type": "integer", "minimum": -10, "maximum": 10},
                "fear_delta": {"type": "integer", "minimum": -10, "maximum": 10},
            },
            "required": ["friendship_delta", "romance_delta", "trust_delta"],
        },
        "memory": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "importance": {"type": "number", "minimum": 0, "maximum": 1},
                "summary": {"type": "string"},
            },
            "required": ["importance", "summary"],
        },
        "animation": {
            "type": "string",
            "enum": [
                "friendly_chat",
                "funny_chat",
                "romantic_chat",
                "awkward_chat",
                "angry_chat",
                "sad_chat",
                "apologize",
                "argue",
                "flirt",
                "laugh",
            ],
        },
    },
    "required": ["dialogue", "emotion", "intent", "relationship", "memory", "animation"],
}

DIRECTOR_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "hook": {"type": "string"},
        "target": {"type": "string"},
        "suggested_action": {"type": "string"},
        "tone": {"type": "string"},
    },
    "required": ["hook", "target", "suggested_action", "tone"],
}


def connect_db():
    global ACTIVE_DB_PATH
    paths = [ACTIVE_DB_PATH] if ACTIVE_DB_PATH else [DB_PATH]
    if not os.environ.get("AI_SIM_DB"):
        paths.append(os.path.join(tempfile.gettempdir(), "ai_sims_memory.sqlite3"))

    last_error = None
    for path in paths:
        if not path:
            continue
        try:
            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
            init_db(conn)
            conn.commit()
            ACTIVE_DB_PATH = path
            return conn
        except sqlite3.Error as exc:
            last_error = exc
    raise last_error


def ensure_column(conn, table, name, definition):
    rows = conn.execute("pragma table_info({})".format(table)).fetchall()
    if name not in [row["name"] for row in rows]:
        conn.execute("alter table {} add column {} {}".format(table, name, definition))


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


def sim_name(sim):
    return str(sim.get("name") or sim.get("id") or "Unknown Sim")


def sim_id(sim):
    return str(sim.get("id") or sim_name(sim))


def dumps(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def loads(text, default):
    try:
        return json.loads(text or "")
    except Exception:
        return default


def now():
    return time.time()


def default_personality(traits):
    personality = {
        "introversion": 50,
        "empathy": 50,
        "ambition": 50,
        "humor": 50,
        "honesty": 50,
        "risk_taking": 50,
    }
    trait_text = " ".join(str(item).lower() for item in (traits or []))
    adjustments = {
        "loner": {"introversion": 80},
        "outgoing": {"introversion": 20},
        "good": {"empathy": 75, "honesty": 70},
        "evil": {"empathy": 25, "honesty": 35},
        "ambitious": {"ambition": 85},
        "goofball": {"humor": 80},
        "romantic": {"empathy": 65},
        "hot-headed": {"risk_taking": 65},
    }
    for trait, values in adjustments.items():
        if trait in trait_text:
            personality.update(values)
    return personality


def default_values(traits):
    values = ["Friendship", "Stability"]
    trait_text = " ".join(str(item).lower() for item in (traits or []))
    for word, value in (
        ("family", "Family"),
        ("romantic", "Romance"),
        ("ambitious", "Career"),
        ("materialistic", "Money"),
        ("famous", "Fame"),
    ):
        if word in trait_text and value not in values:
            values.append(value)
    return values


def default_rules(traits):
    rules = []
    trait_text = " ".join(str(item).lower() for item in (traits or []))
    if "good" in trait_text:
        rules.append("Forgives easily")
    if "romantic" in trait_text:
        rules.append("Romantic")
    if "hot-headed" in trait_text:
        rules.append("Can escalate conflict")
    if "family" in trait_text:
        rules.append("Protective")
    return rules or ["Keeps conversations believable for their mood and relationship"]


def row_profile(row):
    if not row:
        return None
    return {
        "id": row["sim_id"],
        "name": row["name"],
        "identity": loads(row["identity_json"], {}),
        "personality": loads(row["personality_json"], {}),
        "values": loads(row["values_json"], []),
        "behavioral_rules": loads(row["behavioral_rules_json"], []),
        "knowledge": loads(row["knowledge_json"], {}),
        "goals": loads(row["goals_json"], []),
        "voice": loads(row["voice_json"], {}),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def default_profile(sim):
    traits = sim.get("traits") or []
    sid = sim_id(sim)
    name = sim_name(sim)
    identity = {
        "name": name,
        "age": sim.get("age") or "unknown",
        "gender": sim.get("gender") or "unknown",
        "sim_id": sid,
        "traits": traits,
    }
    return {
        "id": sid,
        "name": name,
        "identity": identity,
        "personality": default_personality(traits),
        "values": default_values(traits),
        "behavioral_rules": default_rules(traits),
        "knowledge": {"career": sim.get("career") or "unknown", "skills": sim.get("skills") or {}},
        "goals": [],
        "voice": {"voice": "", "speed": 1.0, "pitch": 0.0},
    }


def save_profile(profile):
    timestamp = now()
    with connect_db() as conn:
        existing = conn.execute("select created_at from sim_profiles where sim_id = ?", (profile["id"],)).fetchone()
        conn.execute(
            """
            insert or replace into sim_profiles (
                sim_id, name, identity_json, personality_json, values_json,
                behavioral_rules_json, knowledge_json, goals_json, voice_json,
                created_at, updated_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                profile["id"],
                profile["name"],
                dumps(profile.get("identity") or {}),
                dumps(profile.get("personality") or {}),
                dumps(profile.get("values") or []),
                dumps(profile.get("behavioral_rules") or []),
                dumps(profile.get("knowledge") or {}),
                dumps(profile.get("goals") or []),
                dumps(profile.get("voice") or {}),
                existing["created_at"] if existing else timestamp,
                timestamp,
            ),
        )
        conn.commit()


def get_profile(sim_or_id):
    sid = sim_id(sim_or_id) if isinstance(sim_or_id, dict) else str(sim_or_id)
    with connect_db() as conn:
        row = conn.execute("select * from sim_profiles where sim_id = ?", (sid,)).fetchone()
        if not row:
            row = conn.execute("select * from sim_profiles where lower(name) = lower(?) order by updated_at desc limit 1", (sid,)).fetchone()
    return row_profile(row)


def get_profile_by_name(name):
    with connect_db() as conn:
        row = conn.execute(
            "select * from sim_profiles where lower(name) = lower(?) order by updated_at desc limit 1",
            (str(name or ""),),
        ).fetchone()
    return row_profile(row)


def migrate_agent_id(old_id, new_id):
    old_id = str(old_id or "")
    new_id = str(new_id or "")
    if not old_id or not new_id or old_id == new_id:
        return
    with connect_db() as conn:
        existing = conn.execute("select sim_id from sim_profiles where sim_id = ?", (new_id,)).fetchone()
        if existing:
            return
        conn.execute("update sim_profiles set sim_id = ? where sim_id = ?", (new_id, old_id))
        for table, columns in (
            ("memories", ("speaker_id", "listener_id", "sim_id", "target_id")),
            ("memory_summaries", ("sim_id", "target_id")),
            ("relationships", ("sim_id", "target_id")),
            ("emotions", ("sim_id",)),
            ("goals", ("sim_id",)),
            ("conversations", ("speaker_id", "listener_id")),
            ("voice_settings", ("sim_id",)),
        ):
            for column in columns:
                conn.execute("update {} set {} = ? where {} = ?".format(table, column, column), (new_id, old_id))
        conn.commit()
    AGENT_LOG.info("migrated agent id old=%s new=%s", old_id, new_id)


def list_profiles(limit=100):
    with connect_db() as conn:
        rows = conn.execute(
            "select * from sim_profiles order by updated_at desc limit ?",
            (int(limit),),
        ).fetchall()
    return [row_profile(row) for row in rows]


def upsert_profile(sim):
    profile = get_profile(sim)
    if not profile:
        named_profile = get_profile_by_name(sim_name(sim))
        new_id = sim_id(sim)
        if named_profile and named_profile["id"] != new_id:
            migrate_agent_id(named_profile["id"], new_id)
            profile = get_profile(new_id)
        else:
            profile = default_profile(sim)
    else:
        profile["name"] = sim_name(sim)
        profile["identity"].update(default_profile(sim)["identity"])
        profile["knowledge"].update({"career": sim.get("career") or profile["knowledge"].get("career", "unknown")})
        profile["knowledge"]["skills"] = sim.get("skills") or profile["knowledge"].get("skills") or {}
    save_profile(profile)
    return profile


def default_relationship():
    return {
        "friendship": 0,
        "romance": 0,
        "trust": 50,
        "respect": 50,
        "admiration": 0,
        "jealousy": 0,
        "resentment": 0,
        "fear": 0,
    }


def get_relationship(sim_id_value, target_id_value):
    with connect_db() as conn:
        row = conn.execute(
            "select * from relationships where sim_id = ? and target_id = ?",
            (sim_id_value, target_id_value),
        ).fetchone()
    if not row:
        return default_relationship()
    return {key: row[key] for key in default_relationship()}


def save_relationship(sim_id_value, target_id_value, relationship):
    values = default_relationship()
    for key, value in (relationship or {}).items():
        if key in values:
            values[key] = value
    for key in values:
        values[key] = clamp_int(values[key], 0, 100)
    with connect_db() as conn:
        conn.execute(
            """
            insert or replace into relationships (
                sim_id, target_id, friendship, romance, trust, respect,
                admiration, jealousy, resentment, fear, updated_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sim_id_value,
                target_id_value,
                values["friendship"],
                values["romance"],
                values["trust"],
                values["respect"],
                values["admiration"],
                values["jealousy"],
                values["resentment"],
                values["fear"],
                now(),
            ),
        )
        conn.commit()
    return values


def apply_relationship_delta(sim_id_value, target_id_value, deltas):
    relationship = get_relationship(sim_id_value, target_id_value)
    for key in default_relationship():
        delta = deltas.get(key + "_delta", 0) if isinstance(deltas, dict) else 0
        relationship[key] = clamp_int(relationship.get(key, 0) + delta, 0, 100)
    saved = save_relationship(sim_id_value, target_id_value, relationship)
    reverse = get_relationship(target_id_value, sim_id_value)
    for key in ("friendship", "romance", "trust", "respect"):
        reverse[key] = max(reverse.get(key, 0), saved[key])
    save_relationship(target_id_value, sim_id_value, reverse)
    return saved


def relationship_with_payload(sim_id_value, target_id_value, payload_relationship):
    relationship = get_relationship(sim_id_value, target_id_value)
    for key, value in (payload_relationship or {}).items():
        if key in relationship:
            relationship[key] = clamp_int(value, 0, 100)
    save_relationship(sim_id_value, target_id_value, relationship)
    return relationship


def default_emotion(mood="neutral"):
    return {
        "happiness": 50,
        "anger": 0,
        "sadness": 0,
        "stress": 20,
        "confidence": 50,
        "current_mood": str(mood or "neutral"),
    }


def get_emotion(sim_id_value):
    with connect_db() as conn:
        row = conn.execute("select * from emotions where sim_id = ?", (sim_id_value,)).fetchone()
    if not row:
        return default_emotion()
    emotion = {key: row[key] for key in ("happiness", "anger", "sadness", "stress", "confidence")}
    emotion["current_mood"] = row["current_mood"]
    return emotion


def save_emotion(sim_id_value, emotion):
    values = default_emotion((emotion or {}).get("current_mood"))
    values.update(emotion or {})
    for key in ("happiness", "anger", "sadness", "stress", "confidence"):
        values[key] = clamp_int(values[key], 0, 100)
    with connect_db() as conn:
        conn.execute(
            """
            insert or replace into emotions (
                sim_id, happiness, anger, sadness, stress, confidence, current_mood, updated_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sim_id_value,
                values["happiness"],
                values["anger"],
                values["sadness"],
                values["stress"],
                values["confidence"],
                str(values["current_mood"] or "neutral"),
                now(),
            ),
        )
        conn.commit()
    return values


def emotion_from_label(label):
    label = str(label or "").lower()
    deltas = {
        "happy": {"happiness": 8, "stress": -3},
        "joy": {"happiness": 8, "stress": -3},
        "angry": {"anger": 10, "stress": 4, "happiness": -4},
        "sad": {"sadness": 10, "happiness": -5},
        "tense": {"stress": 8},
        "confident": {"confidence": 8, "stress": -2},
        "romantic": {"happiness": 5, "confidence": 3},
        "embarrassed": {"confidence": -6, "stress": 5},
    }
    return deltas.get(label, {})


def update_emotion_from_response(sim_id_value, label):
    emotion = get_emotion(sim_id_value)
    for key, delta in emotion_from_label(label).items():
        emotion[key] = clamp_int(emotion.get(key, 0) + delta, 0, 100)
    emotion["current_mood"] = str(label or emotion.get("current_mood") or "neutral")
    return save_emotion(sim_id_value, emotion)


def recent_memories(speaker_id, listener_id, limit=None, topic="", emotion="", location=""):
    limit = int(limit or CONFIG.get("memory", {}).get("recent_limit", 6))
    topic_like = "%{}%".format(topic) if topic else "%"
    emotion_like = "%{}%".format(emotion) if emotion else "%"
    location_like = "%{}%".format(location) if location else "%"
    with connect_db() as conn:
        rows = conn.execute(
            """
            select id, summary, event, emotion, category, topic, location, importance, created_at
            from memories
            where (
                (speaker_id = ? and listener_id = ?)
                or (speaker_id = ? and listener_id = ?)
            )
              and coalesce(topic, '') like ?
              and coalesce(emotion, '') like ?
              and coalesce(location, '') like ?
            order by importance desc, created_at desc
            limit ?
            """,
            (speaker_id, listener_id, listener_id, speaker_id, topic_like, emotion_like, location_like, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def memories_for_sim(speaker_id, limit=10):
    with connect_db() as conn:
        rows = conn.execute(
            """
            select id, summary, event, emotion, category, topic, location, importance, created_at
            from memories
            where speaker_id = ? or listener_id = ? or sim_id = ?
            order by importance desc, created_at desc
            limit ?
            """,
            (speaker_id, speaker_id, speaker_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def add_memory(speaker_id, listener_id, summary, importance, emotion="", category="", topic="", location=""):
    summary = str(summary or "").strip()
    if not summary:
        return
    category = category or ("long_term" if clamp_float(importance) >= 0.75 else "short_term")
    with connect_db() as conn:
        conn.execute(
            """
            insert into memories (
                speaker_id, listener_id, sim_id, target_id, event, summary,
                emotion, category, topic, location, importance, created_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                speaker_id,
                listener_id,
                speaker_id,
                listener_id,
                summary,
                summary,
                str(emotion or ""),
                str(category or "short_term"),
                str(topic or ""),
                str(location or ""),
                clamp_float(importance),
                now(),
            ),
        )
        conn.commit()
    MEMORY_LOG.info("memory saved sim=%s target=%s importance=%s summary=%s", speaker_id, listener_id, importance, summary)


def memory_summary(sim_id_value, target_id_value):
    with connect_db() as conn:
        row = conn.execute(
            "select summary, updated_at from memory_summaries where sim_id = ? and target_id = ?",
            (sim_id_value, target_id_value),
        ).fetchone()
    return dict(row) if row else {"summary": "", "updated_at": 0}


def save_memory_summary(sim_id_value, target_id_value, summary):
    with connect_db() as conn:
        conn.execute(
            """
            insert or replace into memory_summaries (sim_id, target_id, summary, updated_at)
            values (?, ?, ?, ?)
            """,
            (sim_id_value, target_id_value, str(summary or "").strip(), now()),
        )
        conn.commit()


def maybe_summarize_memories(sim_id_value, target_id_value):
    every = int(CONFIG.get("memory", {}).get("summary_every", 10) or 10)
    limit = int(CONFIG.get("memory", {}).get("summary_limit", 30) or 30)
    with connect_db() as conn:
        count = conn.execute(
            """
            select count(*) as count
            from memories
            where (speaker_id = ? and listener_id = ?)
               or (speaker_id = ? and listener_id = ?)
            """,
            (sim_id_value, target_id_value, target_id_value, sim_id_value),
        ).fetchone()["count"]
    if count < every or count % every != 0:
        return memory_summary(sim_id_value, target_id_value)
    memories = memories_for_pair(sim_id_value, target_id_value, limit=limit)
    lines = "\n".join("- " + item["summary"] for item in memories)
    prompt = "Summarize these Sims memories in two concise sentences.\n\n{}".format(lines)
    try:
        summary = llm_chat(
            [
                {"role": "system", "content": "You compress Sims relationship memories. Return plain text only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            task="small",
        ).strip()
    except Exception as exc:
        MEMORY_LOG.warning("summary LLM failed: %s", exc)
        summary = "; ".join(item["summary"] for item in memories[:4])
    save_memory_summary(sim_id_value, target_id_value, summary[:1000])
    return memory_summary(sim_id_value, target_id_value)


def memories_for_pair(sim_id_value, target_id_value, limit=20):
    with connect_db() as conn:
        rows = conn.execute(
            """
            select id, summary, event, emotion, category, topic, location, importance, created_at
            from memories
            where (speaker_id = ? and listener_id = ?)
               or (speaker_id = ? and listener_id = ?)
            order by importance desc, created_at desc
            limit ?
            """,
            (sim_id_value, target_id_value, target_id_value, sim_id_value, int(limit)),
        ).fetchall()
    return [dict(row) for row in rows]


def clamp_int(value, low=-10, high=10):
    try:
        value = int(round(float(value)))
    except (TypeError, ValueError):
        value = 0
    return max(low, min(high, value))


def clamp_float(value, low=0.0, high=1.0):
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = 0.5
    return max(low, min(high, value))


def normalize_response(raw):
    if not isinstance(raw, dict):
        raw = {}

    relationship = raw.get("relationship")
    if not isinstance(relationship, dict):
        relationship = raw

    memory = raw.get("memory")
    if isinstance(memory, str):
        memory = {"summary": memory, "importance": 0.5}
    elif not isinstance(memory, dict):
        memory = {}

    dialogue = str(raw.get("dialogue") or "").strip() or "..."
    animation = str(raw.get("animation") or "friendly_chat").strip()
    if animation not in (
        "friendly_chat",
        "funny_chat",
        "romantic_chat",
        "awkward_chat",
        "angry_chat",
        "sad_chat",
        "apologize",
        "argue",
        "flirt",
        "laugh",
    ):
        animation = "friendly_chat"
    return {
        "dialogue": dialogue,
        "emotion": str(raw.get("emotion") or "neutral").strip().lower(),
        "intent": str(raw.get("intent") or "respond").strip(),
        "relationship": {
            "friendship_delta": clamp_int(relationship.get("friendship_delta")),
            "romance_delta": clamp_int(relationship.get("romance_delta")),
            "trust_delta": clamp_int(relationship.get("trust_delta")),
            "respect_delta": clamp_int(relationship.get("respect_delta")),
            "admiration_delta": clamp_int(relationship.get("admiration_delta")),
            "jealousy_delta": clamp_int(relationship.get("jealousy_delta")),
            "resentment_delta": clamp_int(relationship.get("resentment_delta")),
            "fear_delta": clamp_int(relationship.get("fear_delta")),
        },
        "memory": {
            "importance": clamp_float(memory.get("importance")),
            "summary": str(memory.get("summary") or "").strip(),
        },
        "animation": animation,
    }


def extract_json(text):
    text = str(text or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("model did not return a JSON object")
    candidate = text[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    try:
        parsed = ast.literal_eval(candidate)
        if isinstance(parsed, dict):
            return parsed
    except (SyntaxError, ValueError):
        pass
    # ponytail: handles common local-model JSON-ish output; replace with schema-constrained decoding if needed.
    quoted_keys = re.sub(r'([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*:)', r'\1"\2"\3', candidate)
    return json.loads(quoted_keys)


def fallback_response(text):
    text = str(text or "").strip()
    if text.startswith("```"):
        text = "\n".join(line for line in text.splitlines() if not line.startswith("```")).strip()
    return normalize_response(
        {
            "dialogue": text[:500] or "...",
            "emotion": "neutral",
            "intent": "respond",
            "relationship": {},
            "memory": {"importance": 0.0, "summary": ""},
            "animation": "friendly_chat",
        }
    )


class AgentManager:
    def __init__(self, limit):
        self.limit = max(1, int(limit or 1))
        self._semaphore = threading.BoundedSemaphore(self.limit)
        self._lock = threading.RLock()
        self._active = {}

    def wake_agent(self, sim, reason="request", priority=3, timeout=None):
        profile = upsert_profile(sim)
        sid = profile["id"]
        with self._lock:
            if sid in self._active:
                self._active[sid]["refs"] += 1
                self._active[sid]["last_reason"] = reason
                AGENT_LOG.info("agent reused sim=%s reason=%s refs=%s", sid, reason, self._active[sid]["refs"])
                return profile

        acquired = self._semaphore.acquire(timeout=AGENT_WAKE_TIMEOUT if timeout is None else timeout)
        if not acquired:
            raise RuntimeError("active agent limit reached; request timed out")
        with self._lock:
            self._active[sid] = {
                "sim_id": sid,
                "name": profile["name"],
                "state": "active",
                "priority": int(priority or 3),
                "refs": 1,
                "woke_at": now(),
                "last_reason": reason,
            }
        AGENT_LOG.info("agent woke sim=%s name=%s reason=%s priority=%s", sid, profile["name"], reason, priority)
        return profile

    def sleep_agent(self, sim_id_value, reason="complete"):
        release = False
        with self._lock:
            active = self._active.get(str(sim_id_value))
            if not active:
                return False
            active["refs"] -= 1
            if active["refs"] <= 0:
                self._active.pop(str(sim_id_value), None)
                release = True
        if release:
            self._semaphore.release()
            AGENT_LOG.info("agent slept sim=%s reason=%s", sim_id_value, reason)
        return True

    @contextlib.contextmanager
    def session(self, sim, reason="request", priority=3):
        profile = self.wake_agent(sim, reason=reason, priority=priority)
        try:
            yield profile
        finally:
            self.sleep_agent(profile["id"], reason="session complete")

    def get_active_agents(self):
        with self._lock:
            return [dict(value) for value in self._active.values()]


AGENTS = AgentManager(ACTIVE_AGENT_LIMIT)


def task_model_config(task="large"):
    task_cfg = dict((CONFIG.get("models") or {}).get(task or "large") or {})
    provider_name = str(task_cfg.get("provider") or PRIMARY_PROVIDER or "lmstudio")
    provider_cfg = dict((CONFIG.get("providers") or {}).get(provider_name) or {})
    provider_cfg["name"] = provider_name
    if task_cfg.get("endpoint"):
        provider_cfg["endpoint"] = task_cfg.get("endpoint")
    if task_cfg.get("model"):
        provider_cfg["model"] = task_cfg.get("model")
    provider_cfg["temperature"] = task_cfg.get("temperature", provider_cfg.get("temperature", 0.6))
    provider_cfg["max_tokens"] = task_cfg.get("max_tokens", provider_cfg.get("max_tokens", 350))
    provider_cfg["endpoint"] = str(provider_cfg.get("endpoint") or LLM_BASE_URL).rstrip("/")
    provider_cfg["model"] = str(provider_cfg.get("model") or LLM_MODEL)
    return provider_cfg


def api_root(base_url=None):
    base_url = str(base_url or LLM_BASE_URL).rstrip("/")
    if base_url.endswith("/api/v1"):
        return base_url[: -len("/api/v1")]
    if base_url.endswith("/v1"):
        return base_url[: -len("/v1")]
    return base_url


def native_models_url(task="large"):
    cfg = task_model_config(task)
    return api_root(cfg["endpoint"]) + "/api/v1/models"


def chat_base_urls(base_url=None):
    base_url = str(base_url or LLM_BASE_URL).rstrip("/")
    root = api_root(base_url)
    urls = [root + "/v1"]
    if base_url.endswith("/api/v1"):
        urls.append(base_url)
    elif not base_url.endswith("/v1"):
        urls.append(base_url + "/v1")
    else:
        urls.append(base_url)
    return list(dict.fromkeys(urls))


def loaded_model_id(task="large"):
    cfg = task_model_config(task)
    model = cfg.get("model") or LLM_MODEL
    if model != "local-model":
        return model
    if cfg.get("name") != "lmstudio":
        return model
    try:
        with urllib.request.urlopen(native_models_url(task), timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
        for model in data.get("models") or []:
            loaded = model.get("loaded_instances") or []
            if loaded:
                return loaded[0].get("id") or model.get("key") or cfg.get("model") or LLM_MODEL
    except Exception:
        pass
    return model


def request_bodies(messages, temperature, schema, schema_name, task="large"):
    cfg = task_model_config(task)
    base = {
        "model": loaded_model_id(task),
        "messages": messages,
        "temperature": temperature if temperature is not None else cfg.get("temperature", 0.6),
        "max_tokens": int(cfg.get("max_tokens") or 350),
    }
    if schema:
        with_schema = dict(base)
        with_schema["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "schema": schema,
            },
        }
        yield json.dumps(with_schema).encode("utf-8")
    yield json.dumps(base).encode("utf-8")


def llm_chat(messages, temperature=None, schema=None, schema_name="response", task="large"):
    cfg = task_model_config(task)
    last_error = None
    headers = {"Content-Type": "application/json"}
    api_key = cfg.get("api_key") or os.environ.get("AI_SIM_API_KEY")
    if api_key:
        headers["Authorization"] = "Bearer " + str(api_key)
    for body in request_bodies(messages, temperature, schema, schema_name, task=task):
        for base_url in chat_base_urls(cfg["endpoint"]):
            request = urllib.request.Request(
                base_url + "/chat/completions",
                data=body,
                headers=headers,
                method="POST",
            )
            try:
                PROVIDER_LOG.info("chat provider=%s model=%s url=%s task=%s", cfg.get("name"), loaded_model_id(task), base_url, task)
                with urllib.request.urlopen(request, timeout=90) as response:
                    data = json.loads(response.read().decode("utf-8"))
                choice = data["choices"][0]
                message = choice.get("message") or {}
                content = str(message.get("content") or "").strip()
                if content:
                    return content
                reasoning = str(message.get("reasoning_content") or "").strip()
                if reasoning:
                    raise ReasoningOnlyResponse(
                        "model returned only reasoning_content; finish_reason={}".format(choice.get("finish_reason"))
                    )
                raise RuntimeError("model returned empty content; finish_reason={}".format(choice.get("finish_reason")))
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")
                last_error = RuntimeError("LLM HTTP {} at {}: {}".format(exc.code, base_url, detail[:500]))
                if exc.code in (400, 404):
                    continue
                raise last_error
            except urllib.error.URLError as exc:
                last_error = RuntimeError("cannot reach {} at {}: {}".format(cfg.get("name"), base_url, exc.reason))
                break

    raise last_error


def build_context(payload, speaker_profile, listener_profile, relationship, emotions, memories, summary):
    speaker = payload.get("speaker") or {}
    listener = payload.get("listener") or {}
    return {
        "speaker": speaker_profile,
        "listener": listener_profile,
        "relationship": relationship,
        "emotions": emotions,
        "memories": memories,
        "summary": summary.get("summary", "") if isinstance(summary, dict) else "",
        "location": payload.get("location") or "unknown",
        "nearby_sims": payload.get("nearby_sims") or [],
        "message": payload.get("message") or "",
        "speaker_traits": speaker.get("traits") or speaker_profile.get("identity", {}).get("traits") or [],
        "listener_traits": listener.get("traits") or listener_profile.get("identity", {}).get("traits") or [],
    }


def build_chat_prompt(payload, context):
    speaker_profile = context["speaker"]
    listener_profile = context["listener"]
    relationship = context["relationship"]
    emotions = context["emotions"]
    memory_lines = "\n".join("- " + item["summary"] for item in context["memories"]) or "- None yet"
    nearby = ", ".join(sim_name(item) if isinstance(item, dict) else str(item) for item in context["nearby_sims"]) or "none"
    goals = speaker_profile.get("goals") or []

    return """Role assignment:
You are {speaker_name}, the Speaker.
{listener_name} is the Listener and wrote the message below.
Reply as {speaker_name} to {listener_name}.
Never address the Listener by the Speaker's name.
Do not include the Speaker's name in dialogue.

Speaker:
{speaker_name}
Identity: {identity}
Traits: {speaker_traits}
Personality: {personality}
Values: {values}
Behavior rules: {rules}
Knowledge: {knowledge}
Goals: {goals}

Listener:
{listener_name}
Traits: {listener_traits}

Relationship:
{relationship}

Current emotion:
{emotions}

Memory summary:
{summary}

Relevant memories:
{memories}

Location:
{location}

Nearby Sims:
{nearby}

Player says:
{message}
""".format(
        speaker_name=speaker_profile.get("name") or "Unknown Sim",
        identity=dumps(speaker_profile.get("identity") or {}),
        speaker_traits=", ".join(context["speaker_traits"]) or "unknown",
        personality=dumps(speaker_profile.get("personality") or {}),
        values=", ".join(speaker_profile.get("values") or []) or "unknown",
        rules=", ".join(speaker_profile.get("behavioral_rules") or []) or "none",
        knowledge=dumps(speaker_profile.get("knowledge") or {}),
        goals=", ".join(str(goal) for goal in goals) or "none",
        listener_name=listener_profile.get("name") or "Unknown Sim",
        listener_traits=", ".join(context["listener_traits"]) or "unknown",
        relationship=dumps(relationship),
        emotions=dumps(emotions),
        summary=context["summary"] or "None yet",
        memories=memory_lines,
        location=context["location"],
        nearby=nearby,
        message=payload.get("message") or "",
    )


def response_has_role_confusion(response, context):
    words = set(re.findall(r"\w+", str(response.get("dialogue") or "").casefold()))
    speaker = set(re.findall(r"\w+", str(context["speaker"].get("name") or "").casefold()))
    listener = set(re.findall(r"\w+", str(context["listener"].get("name") or "").casefold()))
    return bool({word for word in speaker - listener if len(word) > 1} & words)

def save_conversation(conversation_id, speaker_id, listener_id, message, response):
    with connect_db() as conn:
        conn.execute(
            """
            insert into conversations (conversation_id, speaker_id, listener_id, message, response_json, created_at)
            values (?, ?, ?, ?, ?, ?)
            """,
            (conversation_id, speaker_id, listener_id, str(message or ""), dumps(response), now()),
        )
        conn.commit()


def reasoning_fallback_response(payload, context):
    message = str(payload.get("message") or "").lower()
    if any(word in message for word in ("avoid", "avoiding", "ignored", "ignore")):
        dialogue = "I wasn't trying to avoid you. I just needed a little space to sort through my feelings."
        emotion = "tense"
        intent = "reassure"
        animation = "awkward_chat"
        trust_delta = 0
    elif any(word in message for word in ("sorry", "apologize", "forgive")):
        dialogue = "I appreciate you saying that. I need time, but I'm listening."
        emotion = "softened"
        intent = "accept_apology"
        animation = "apologize"
        trust_delta = 1
    elif any(word in message for word in ("date", "love", "romance", "kiss")):
        dialogue = "You certainly know how to surprise me. Let's see where the moment takes us."
        emotion = "romantic"
        intent = "flirt"
        animation = "flirt"
        trust_delta = 0
    elif any(word in message for word in ("sex", "woohoo")):
        dialogue = "Slow down. If there is something between us, I want it to feel right, not rushed."
        emotion = "awkward"
        intent = "set_boundary"
        animation = "awkward_chat"
        trust_delta = -1
    else:
        dialogue = "I hear you. Give me a moment to choose my words carefully."
        emotion = context.get("emotions", {}).get("current_mood", "neutral")
        intent = "respond"
        animation = "friendly_chat"
        trust_delta = 0
    return normalize_response(
        {
            "dialogue": dialogue,
            "emotion": emotion,
            "intent": intent,
            "relationship": {"friendship_delta": 0, "romance_delta": 0, "trust_delta": trust_delta},
            "memory": {"importance": 0.2, "summary": "The conversation needed a careful response."},
            "animation": animation,
        }
    )


class HermesRuntime:
    def dialogue(self, payload, context):
        prompt = build_chat_prompt(payload, context)
        for attempt in range(2):
            try:
                content = llm_chat(
                    [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    schema=DIALOGUE_SCHEMA,
                    schema_name="sims_dialogue",
                    task="large",
                )
            except ReasoningOnlyResponse as exc:
                PROVIDER_LOG.warning("%s", exc)
                return reasoning_fallback_response(payload, context)
            try:
                response = normalize_response(extract_json(content))
            except (ValueError, json.JSONDecodeError):
                response = fallback_response(content)
            if not response_has_role_confusion(response, context):
                return response
            PROVIDER_LOG.warning("model confused speaker and listener; retrying=%s", attempt == 0)
            prompt += (
                "\nCorrection: Dialogue must not contain the Speaker's name, '{}'. "
                "If using a name, use the Listener's name, '{}'."
            ).format(context["speaker"]["name"], context["listener"]["name"])
        return reasoning_fallback_response(payload, context)

    def story_beat(self, prompt):
        content = llm_chat(
            [
                {"role": "system", "content": "You are a Sims 4 AI Director. Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            schema=DIRECTOR_SCHEMA,
            schema_name="sims_director",
            task="small",
        )
        try:
            raw = extract_json(content)
        except (ValueError, json.JSONDecodeError):
            raw = {"hook": str(content).strip()[:500], "target": "", "suggested_action": "", "tone": "neutral"}
        return {
            "hook": str(raw.get("hook") or "").strip(),
            "target": str(raw.get("target") or "").strip(),
            "suggested_action": str(raw.get("suggested_action") or "").strip(),
            "tone": str(raw.get("tone") or "neutral").strip(),
        }


HERMES = HermesRuntime()


def chat(payload):
    speaker = payload.get("speaker") or {}
    listener = payload.get("listener") or {}
    speaker_id = sim_id(speaker)
    listener_id = sim_id(listener)
    conversation_id = str(payload.get("conversation_id") or "{}-{}".format(speaker_id, listener_id))
    with AGENTS.session(speaker, reason="player_interaction", priority=1) as speaker_profile:
        listener_profile = upsert_profile(listener)
        emotions = get_emotion(speaker_id)
        if emotions.get("current_mood") in ("neutral", "unknown") and speaker.get("current_mood"):
            emotions = save_emotion(speaker_id, default_emotion(speaker.get("current_mood")))
        relationship = relationship_with_payload(speaker_id, listener_id, payload.get("relationship") or {})
        memories = recent_memories(
            speaker_id,
            listener_id,
            topic=payload.get("topic") or "",
            emotion=payload.get("emotion") or "",
            location=payload.get("location") or "",
        )
        summary = memory_summary(speaker_id, listener_id)
        context = build_context(payload, speaker_profile, listener_profile, relationship, emotions, memories, summary)
        adapter = Sims4PocAdapter(payload)
        event = adapter.observe()[0]
        request = CognitiveRequest(
            speaker_id,
            3,
            event,
            max_tokens=int(task_model_config("large").get("max_tokens") or 350),
        )

        async def resolve_dialogue(_request):
            try:
                response = HERMES.dialogue(payload, context)
            except RuntimeError as exc:
                raise ProviderError("Sims dialogue provider failed") from exc
            return adapter.decision_from_response(response, event.id)

        prompt = build_chat_prompt(payload, context)
        estimate = ResourceEstimate(
            context_tokens=max(1, len(prompt) // 4),
            completion_tokens=request.max_tokens,
            latency_ms=request.deadline_ms,
        )
        with open_db(CORE_DB_PATH) as conn:
            runtime = CognitiveRuntime(CORE_GOVERNOR, ActionRecordStore(conn))
            record = asyncio.run(runtime.process(request, adapter, resolve_dialogue, estimate))
        result = adapter.response_for(record.decision, record.result)
    memory = result["memory"]
    if memory["summary"] and memory["importance"] >= 0.2:
        add_memory(
            speaker_id,
            listener_id,
            memory["summary"],
            memory["importance"],
            emotion=result.get("emotion", ""),
            topic=payload.get("topic") or "",
            location=payload.get("location") or "",
        )
    relationship_state = apply_relationship_delta(speaker_id, listener_id, result.get("relationship") or {})
    emotion_state = update_emotion_from_response(speaker_id, result.get("emotion"))
    summary = maybe_summarize_memories(speaker_id, listener_id)
    save_conversation(conversation_id, speaker_id, listener_id, payload.get("message") or "", result)
    result["relationship_state"] = relationship_state
    result["emotion_state"] = emotion_state
    result["memory_summary"] = summary
    result["agent"] = {"id": speaker_id, "state": "dormant"}
    result["decision_id"] = record.decision.id
    result["action_status"] = record.result.status
    return result


def director(payload):
    sim = payload.get("sim") or payload.get("speaker") or {}
    sid = sim_id(sim)
    profile = upsert_profile(sim)
    emotion = get_emotion(sid)
    memories = memories_for_sim(sid, limit=10)
    memory_lines = "\n".join("- " + item["summary"] for item in memories) or "- None yet"
    prompt = """Create one Sims 4 story beat for this Sim.

Sim:
{name}
Traits: {traits}
Profile: {profile}
Emotion: {emotion}

Recent memories:
{memories}

Return only JSON with: hook, target, suggested_action, tone.
""".format(
        name=sim_name(sim),
        traits=", ".join(sim.get("traits") or []) or "unknown",
        profile=dumps(profile),
        emotion=dumps(emotion),
        memories=memory_lines,
    )
    return HERMES.story_beat(prompt)


def autonomous_action(payload):
    adapter = Sims4PocAdapter(payload)
    event = adapter.observe()[0]
    request = CognitiveRequest(event.actor_ids[0], 1, event)

    async def unused_resolver(_request: CognitiveRequest) -> Decision:
        raise AssertionError("CLOD 1 must not call a provider")

    with open_db(CORE_DB_PATH) as conn:
        actions = ActionRecordStore(conn)
        runtime = CognitiveRuntime(CORE_GOVERNOR, actions)
        decision = asyncio.run(runtime.decide(request, unused_resolver))
        action = adapter.action_for(decision)
        if action is None:
            raise ValueError("no supported Sims action available")
        for key in ("speaker", "listener"):
            persist_core_agent(conn, payload.get(key) or {})
        actions.propose(event.id, decision, action)
    return {
        "hook": "Core proposed autonomous action",
        "target": decision.target_id or "",
        "suggested_action": action,
        "decision_id": decision.id,
        "status": "proposed",
        "activation": "empneon_core",
        "agent_state": "dormant",
    }


def persist_core_agent(conn, sim):
    agent_id = str(sim.get("id") or "").strip()
    if not agent_id:
        raise ValueError("observed Sim id is required")
    store = AgentStore(conn)
    agent = store.get(agent_id)
    name = str(sim.get("name") or agent_id)
    if agent is None:
        store.create(
            Agent(
                id=agent_id,
                name=name,
                game_id=agent_id,
                adapter="sims4",
            ),
            commit=False,
        )
    elif agent.name != name:
        agent.name = name
        store.update(agent, commit=False)


def confirm_action(payload):
    decision_id = str(payload.get("decision_id") or "").strip()
    action = str(payload.get("action") or "").strip()
    status = str(payload.get("status") or "failed")
    reason = str(payload.get("reason") or "").strip() or None
    if not decision_id or not action:
        raise ValueError("decision_id and action are required")
    if status not in ("succeeded", "failed", "rejected"):
        raise ValueError("invalid action result status")
    changes = []
    if status == "succeeded":
        changes.append(StateDelta("animation", "set", action))
        for change in payload.get("changes") or []:
            if not isinstance(change, dict):
                raise ValueError("invalid confirmed consequence")
            path = str(change.get("path") or "")
            operation = str(change.get("operation") or "")
            value = change.get("value")
            if path not in ("relationship.friendship", "relationship.romance"):
                raise ValueError("unsupported confirmed consequence")
            if (
                operation != "increment"
                or isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not -100 <= value <= 100
            ):
                raise ValueError("invalid confirmed consequence")
            changes.append(StateDelta(path, "increment", value))
    result = ActionResult(decision_id, status, tuple(changes), reason)
    with open_db(CORE_DB_PATH) as conn:
        actions = ActionRecordStore(conn)
        proposal = actions.get_proposal(decision_id)
        friendship_delta = sum(
            float(change.value)
            for change in changes
            if change.path == "relationship.friendship"
        )
        if proposal is not None and proposal.decision.target_id and friendship_delta:
            relationships = RelationshipStore(conn)
            relationship = relationships.get(
                proposal.decision.actor_id,
                proposal.decision.target_id,
            ) or Relationship(
                proposal.decision.actor_id,
                proposal.decision.target_id,
                "acquaintance",
            )
            relationship.strength = max(
                -1.0,
                min(1.0, relationship.strength + friendship_delta / 100.0),
            )
            relationships.set(relationship, commit=False)
        record = actions.confirm(result, action)
    return {
        "decision_id": record.decision.id,
        "status": record.result.status,
        "consequences": len(record.result.applied_changes),
    }


def voice_profile(sim_id_value):
    profile = get_profile(sim_id_value) or {"voice": {}}
    voice = dict(profile.get("voice") or {})
    with connect_db() as conn:
        row = conn.execute("select * from voice_settings where sim_id = ?", (str(sim_id_value),)).fetchone()
    if row:
        voice.update({"voice": row["voice"], "speed": row["speed"], "pitch": row["pitch"], "provider": row["provider"]})
    return voice


def save_voice_profile(sim_id_value, voice):
    voice = voice or {}
    with connect_db() as conn:
        conn.execute(
            """
            insert or replace into voice_settings (sim_id, voice, speed, pitch, provider, updated_at)
            values (?, ?, ?, ?, ?, ?)
            """,
            (
                str(sim_id_value),
                str(voice.get("voice") or ""),
                float(voice.get("speed") or 1.0),
                float(voice.get("pitch") or 0.0),
                str(voice.get("provider") or CONFIG.get("tts", {}).get("provider") or ""),
                now(),
            ),
        )
        conn.commit()
    profile = get_profile(sim_id_value)
    if profile:
        profile["voice"] = voice_profile(sim_id_value)
        save_profile(profile)
    return voice_profile(sim_id_value)


def tts_generate(payload):
    tts = CONFIG.get("tts") or {}
    sim_id_value = str(payload.get("sim_id") or payload.get("sim") or "")
    voice = voice_profile(sim_id_value) if sim_id_value else {}
    request_payload = {
        "text": str(payload.get("text") or ""),
        "emotion": str(payload.get("emotion") or "neutral"),
        "intensity": clamp_int(payload.get("intensity", 50), 0, 100),
        "voice": voice,
    }
    if not tts.get("enabled") or not tts.get("endpoint"):
        return {"enabled": False, "status": "disabled", "request": request_payload}
    request = urllib.request.Request(
        str(tts.get("endpoint")),
        data=dumps(request_payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        body = response.read().decode("utf-8", "replace")
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        data = {"raw": body}
    data["enabled"] = True
    return data


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def send_json(self, status, data):
        body = json.dumps(data, ensure_ascii=True, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length") or "0")
        if length > 65536:
            raise ValueError("request body too large")
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        if parsed.path == "/health":
            small = task_model_config("small")
            large = task_model_config("large")
            self.send_json(
                200,
                {
                    "status": "ok",
                    "model": loaded_model_id(),
                    "provider": PRIMARY_PROVIDER,
                    "llm_base_url": large.get("endpoint"),
                    "native_models_url": native_models_url("large"),
                    "chat_base_url_candidates": chat_base_urls(large.get("endpoint")),
                    "models": {
                        "small": {"provider": small.get("name"), "model": loaded_model_id("small")},
                        "large": {"provider": large.get("name"), "model": loaded_model_id("large")},
                    },
                    "memory_db": ACTIVE_DB_PATH or DB_PATH,
                    "active_agent_limit": ACTIVE_AGENT_LIMIT,
                    "active_agents": AGENTS.get_active_agents(),
                },
            )
            return
        if parsed.path == "/agents/active":
            self.send_json(200, {"active_agents": AGENTS.get_active_agents()})
            return
        if parsed.path == "/profiles":
            self.send_json(200, {"profiles": list_profiles(limit=int(query.get("limit", [100])[0]))})
            return
        if parsed.path == "/profile":
            sim_id_value = query.get("sim_id", [""])[0]
            self.send_json(200, {"profile": get_profile(sim_id_value)})
            return
        if parsed.path == "/memories":
            speaker_id = query.get("speaker_id", query.get("sim_id", [""]))[0]
            listener_id = query.get("listener_id", query.get("target_id", [speaker_id]))[0]
            if listener_id:
                memories = memories_for_pair(speaker_id, listener_id, limit=int(query.get("limit", [20])[0]))
                summary = memory_summary(speaker_id, listener_id)
            else:
                memories = memories_for_sim(speaker_id, limit=int(query.get("limit", [20])[0]))
                summary = {"summary": "", "updated_at": 0}
            self.send_json(200, {"memories": memories, "summary": summary})
            return
        if parsed.path == "/relationship":
            sim_id_value = query.get("sim_id", [""])[0]
            target_id_value = query.get("target_id", [""])[0]
            self.send_json(200, {"relationship": get_relationship(sim_id_value, target_id_value)})
            return
        if parsed.path == "/emotion":
            sim_id_value = query.get("sim_id", [""])[0]
            self.send_json(200, {"emotion": get_emotion(sim_id_value)})
            return
        if parsed.path == "/voice":
            sim_id_value = query.get("sim_id", [""])[0]
            self.send_json(200, {"voice": voice_profile(sim_id_value)})
            return
        self.send_json(404, {"error": "not found"})

    def do_POST(self):
        try:
            payload = self.read_json()
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path in ("/chat", "/conversation"):
                if not payload.get("message"):
                    self.send_json(400, {"error": "message is required"})
                    return
                self.send_json(200, chat(payload))
                return
            if parsed.path == "/director":
                self.send_json(200, director(payload))
                return
            if parsed.path == "/autonomous":
                self.send_json(200, autonomous_action(payload))
                return
            if parsed.path == "/action-result":
                try:
                    self.send_json(200, confirm_action(payload))
                except ValueError as exc:
                    self.send_json(400, {"error": str(exc)})
                return
            if parsed.path == "/agent/wake":
                sim = payload.get("sim") or payload.get("speaker") or payload
                profile = AGENTS.wake_agent(
                    sim,
                    reason=payload.get("reason") or "manual",
                    priority=payload.get("priority") or 3,
                )
                self.send_json(200, {"profile": profile, "active_agents": AGENTS.get_active_agents()})
                return
            if parsed.path == "/agent/sleep":
                sim_id_value = str(payload.get("sim_id") or payload.get("id") or "")
                self.send_json(200, {"slept": AGENTS.sleep_agent(sim_id_value), "active_agents": AGENTS.get_active_agents()})
                return
            if parsed.path == "/profile":
                sim = payload.get("sim") or payload
                self.send_json(200, {"profile": upsert_profile(sim)})
                return
            if parsed.path == "/memory":
                add_memory(
                    str(payload.get("sim_id") or payload.get("speaker_id") or ""),
                    str(payload.get("target_id") or payload.get("listener_id") or ""),
                    payload.get("summary") or payload.get("event") or "",
                    payload.get("importance", 0.5),
                    emotion=payload.get("emotion") or "",
                    category=payload.get("category") or "",
                    topic=payload.get("topic") or "",
                    location=payload.get("location") or "",
                )
                self.send_json(200, {"status": "ok"})
                return
            if parsed.path == "/relationship":
                sim_id_value = str(payload.get("sim_id") or "")
                target_id_value = str(payload.get("target_id") or "")
                self.send_json(200, {"relationship": save_relationship(sim_id_value, target_id_value, payload.get("relationship") or payload)})
                return
            if parsed.path == "/emotion":
                sim_id_value = str(payload.get("sim_id") or "")
                self.send_json(200, {"emotion": save_emotion(sim_id_value, payload.get("emotion") or payload)})
                return
            if parsed.path == "/voice":
                sim_id_value = str(payload.get("sim_id") or "")
                self.send_json(200, {"voice": save_voice_profile(sim_id_value, payload.get("voice") or payload)})
                return
            if parsed.path == "/tts":
                self.send_json(200, tts_generate(payload))
                return
            self.send_json(404, {"error": "not found"})
        except Exception as exc:
            LOG.exception("request failed")
            self.send_json(500, {"error": str(exc)})


def run():
    connect_db().close()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print("AI Sims server on http://{}:{}".format(HOST, PORT))
    print("Provider: {}".format(PRIMARY_PROVIDER))
    print("Endpoint: {}".format(task_model_config("large").get("endpoint")))
    print("Model: {}".format(loaded_model_id("large")))
    server.serve_forever()


def self_test():
    global DB_PATH, ACTIVE_DB_PATH
    parsed = extract_json('```json\n{"dialogue":"hi","relationship":{"friendship_delta":12},"memory":"met"}\n```')
    result = normalize_response(parsed)
    assert result["dialogue"] == "hi"
    assert result["relationship"]["friendship_delta"] == 10
    assert result["memory"]["summary"] == "met"
    assert result["animation"] == "friendly_chat"
    assert extract_json("{dialogue: \"ok\"}")["dialogue"] == "ok"
    assert fallback_response("plain text")["dialogue"] == "plain text"
    role_context = {
        "speaker": {"name": "Sri Bolton"},
        "listener": {"name": "Robin Casillas"},
    }
    assert response_has_role_confusion({"dialogue": "Sure, Sri."}, role_context)
    assert not response_has_role_confusion({"dialogue": "Sure, Robin."}, role_context)
    assert chat_base_urls("http://x/api/v1") == ["http://x/v1", "http://x/api/v1"]
    assert native_models_url().endswith("/api/v1/models")
    old_db = DB_PATH
    old_active = ACTIVE_DB_PATH
    fd, path = tempfile.mkstemp(prefix="ai_sims_self_test_", suffix=".sqlite3")
    os.close(fd)
    try:
        DB_PATH = path
        ACTIVE_DB_PATH = None
        sim = {"id": "bella-goth", "name": "Bella Goth", "traits": ["romantic", "family-oriented"]}
        target = {"id": "mauricio", "name": "Mauricio", "traits": ["loyal"]}
        profile = upsert_profile(sim)
        assert profile["personality"]["empathy"] >= 50
        upsert_profile(target)
        relationship = apply_relationship_delta("bella-goth", "mauricio", {"trust_delta": 5, "respect_delta": 2})
        assert relationship["trust"] == 55
        emotion = update_emotion_from_response("bella-goth", "angry")
        assert emotion["anger"] > 0
        add_memory("bella-goth", "mauricio", "Mauricio helped Bella", 0.9, emotion="grateful")
        assert memories_for_pair("bella-goth", "mauricio")[0]["category"] == "long_term"
        fallback = reasoning_fallback_response(
            {"message": "why have you been avoiding me?"},
            {"emotions": {"current_mood": "tense"}},
        )
        assert fallback["dialogue"] != "..."
        assert fallback["animation"] == "awkward_chat"
    finally:
        DB_PATH = old_db
        ACTIVE_DB_PATH = old_active
        try:
            os.unlink(path)
        except OSError:
            pass
    print("ok")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        run()
