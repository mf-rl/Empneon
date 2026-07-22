import ast
import asyncio
import contextlib
import dataclasses
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
import urllib.parse
import urllib.request
import uuid
from collections import Counter
from difflib import SequenceMatcher
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

from empneon_thesims4 import Sims4Adapter, cognition_priority
from empneon.core.contracts import (
    SOCIAL_CATEGORIES,
    ActionResult,
    CognitiveRequest,
    Decision,
    StateDelta,
)
from empneon.core.memory.documents import DocumentMemoryStore
from empneon.core.memory.episodic import Event
from empneon.core.identity.relationships import Relationship, RelationshipStore
from empneon.core.identity.store import AgentStore
from empneon.core.runtime import ActionRecordStore, CognitiveRuntime
from empneon.core.replay import replay_action_record
from empneon.core.timeline import agent_timeline
from empneon.core.scheduler.resources import ResourceBudget, ResourceEstimate, ResourceGovernor
from empneon.core.scheduler.priority import PriorityScheduler, RequestDeadlineExceeded
from empneon.core.scheduler.selection import CognitionRoute
from empneon.core.scheduler.usage import UsageStore
from empneon.core.state import save_agent_state
from empneon.db.connection import open_db
from empneon.providers.llm import (
    ConfiguredProviderRouter,
    GenerationResult,
    Message,
    ProviderError,
)
from backend import empneon_state

CONFIG_PATH = os.environ.get("AI_SIM_CONFIG", os.path.join(ROOT, "config", "config.json"))

DEFAULT_CONFIG = {
    "host": "127.0.0.1",
    "port": 8765,
    "debug": True,
    "database": "ai_sims_memory.sqlite3",
    "core_database": "empneon_core.sqlite3",
    "memory_database": "empneon_core_memory.sqlite3",
    "preserve_memory_only_on_game_save": False,
    "active_agent_limit": 1,
    "agent_wake_timeout_seconds": 60,
    "provider": "lmstudio",
    "providers": {
        "lmstudio": {"endpoint": "http://127.0.0.1:1234/api/v1", "model": "local-model"},
        "ollama": {"endpoint": "http://127.0.0.1:11434/v1", "model": "llama3"},
        "openai": {"endpoint": "https://api.openai.com/v1", "model": "gpt-4.1-mini"},
        "openrouter": {
            "endpoint": "https://openrouter.ai/api/v1",
            "model": "openai/gpt-4.1-mini",
        },
        "llamacpp": {"endpoint": "http://127.0.0.1:8080/v1", "model": "local-model"},
        "koboldcpp": {"endpoint": "http://127.0.0.1:5001/v1", "model": "local-model"},
        "textgenwebui": {"endpoint": "http://127.0.0.1:5000/v1", "model": "local-model"},
    },
    "models": {
        "small": {
            "temperature": 0.4,
            "max_tokens": 120,
            "context_tokens": 2048,
            "latency_ms": 30000,
            "ram_mb": 64,
            "vram_mb": 0,
        },
        "large": {
            "temperature": 0.6,
            "max_tokens": 300,
            "context_tokens": 4096,
            "latency_ms": 90000,
            "ram_mb": 128,
            "vram_mb": 0,
        },
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
        config["memory_database"] = os.environ["AI_SIM_DB"]
    if os.environ.get("AI_SIM_MEMORY_DB"):
        config["memory_database"] = os.environ["AI_SIM_MEMORY_DB"]
    if os.environ.get("AI_SIM_PORT"):
        config["port"] = int(os.environ["AI_SIM_PORT"])
    if os.environ.get("AI_SIM_HOST"):
        config["host"] = os.environ["AI_SIM_HOST"]
    return config


CONFIG = load_config()
if not isinstance(CONFIG.get("preserve_memory_only_on_game_save"), bool):
    raise ValueError("preserve_memory_only_on_game_save must be true or false")
HOST = str(CONFIG.get("host") or "127.0.0.1")
PORT = int(CONFIG.get("port") or 8765)
MAX_REQUEST_BODY_BYTES = 1024 * 1024
MEMORY_DB_PATH = str(CONFIG.get("memory_database") or "empneon_core_memory.sqlite3")
LEGACY_ADAPTER_DB_PATH = str(CONFIG.get("database") or "ai_sims_memory.sqlite3")
LEGACY_CORE_DB_PATH = str(CONFIG.get("core_database") or "empneon_core.sqlite3")
# Compatibility aliases while legacy table access is removed in Task 2.
DB_PATH = MEMORY_DB_PATH
CORE_DB_PATH = MEMORY_DB_PATH
ACTIVE_AGENT_LIMIT = int(CONFIG.get("active_agent_limit") or 1)
AGENT_WAKE_TIMEOUT = int(CONFIG.get("agent_wake_timeout_seconds") or 60)
PRESERVE_MEMORY_ONLY_ON_GAME_SAVE = CONFIG["preserve_memory_only_on_game_save"]
PRIMARY_PROVIDER = str(CONFIG.get("provider") or "lmstudio")
ACTIVE_DB_PATH = None
MEMORY_SESSION_LOCK = threading.RLock()
CORE_GOVERNOR = ResourceGovernor(ResourceBudget(256, 0, ACTIVE_AGENT_LIMIT))
GENERATION_CONTEXT = threading.local()
MIGRATION_STATUS = empneon_state.MigrationStatus(
    os.path.abspath(MEMORY_DB_PATH), completed=False, error="not started"
)


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


SYSTEM_PROMPT = """You roleplay one The Sims 4 character.
Stay grounded in the Sim profile, relationship, current mood, and recalled history.
Return one valid JSON object only. No markdown. No schema explanation. No placeholders.
Do not write a thinking process, analysis, reasoning, or chain-of-thought.
The first character of your response must be {.
Normally write 2 to 4 natural sentences totaling about 25 to 60 words. Use a shorter answer only
when the situation genuinely calls for one. Make the dialogue reflect the Sim's personality,
emotion, and relationship instead of using generic filler.
Never invent a past event, shared fact, codeword, promise, plan, date, or name. For factual recall,
use only the attributed statements and confirmed exchanges supplied in the request. If the
requested fact is absent, say naturally and in character that the Sim does not know or remember it.
Use this exact shape with concrete values:
{
  "dialogue": "expressive in-character reply",
  "expressed_emotion": "playful",
  "intent": "accept_playfully",
  "response_category": "romance",
  "tone_tags": ["playful", "hesitant"],
  "trust_delta": 1
}

Choose one response category from the request's available common social categories. The response
category describes the Speaker's own dialogue, independently from the incoming category. Tone tags
may blend style and mood, but never select additional actions. Do not return friendship, romance,
attraction, or action fields; the adapter and game own them.
"""

SOCIAL_ACTIONS = {category: "social." + category for category in SOCIAL_CATEGORIES}

DIALOGUE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "dialogue": {"type": "string"},
        "expressed_emotion": {"type": "string"},
        "intent": {"type": "string"},
        "response_category": {
            "type": "string",
            "enum": list(SOCIAL_CATEGORIES),
        },
        "tone_tags": {
            "type": "array",
            "items": {"type": "string", "pattern": "^[a-z][a-z0-9_-]{0,31}$"},
            "maxItems": 3,
            "uniqueItems": True,
        },
        "trust_delta": {"type": "integer", "minimum": -10, "maximum": 10},
    },
    "required": [
        "dialogue",
        "expressed_emotion",
        "intent",
        "response_category",
        "tone_tags",
        "trust_delta",
    ],
}


def available_actions(value):
    return tuple(
        dict.fromkeys(
            str(action)
            for action in (value if isinstance(value, (list, tuple)) else ())
            if str(action) in ("friendly_chat", "apologize", "flirt")
        )
    )


def available_response_categories(value):
    return tuple(
        dict.fromkeys(
            str(category)
            for category in (value if isinstance(value, (list, tuple)) else ())
            if str(category) in SOCIAL_CATEGORIES
        )
    )


def dialogue_schema(value):
    schema = json.loads(json.dumps(DIALOGUE_SCHEMA))
    categories = available_response_categories(value) or SOCIAL_CATEGORIES
    schema["properties"]["response_category"] = {
        "type": "string",
        "enum": list(categories),
    }
    return schema


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


def memory_session_paths():
    database = os.path.abspath(CORE_DB_PATH)
    return (
        database,
        os.path.abspath(ACTIVE_DB_PATH or DB_PATH) + ".empneon-saved",
        database + ".empneon-session",
    )


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
    with contextlib.closing(sqlite3.connect(source)) as source_db, contextlib.closing(
        sqlite3.connect(temporary)
    ) as destination_db:
        source_db.backup(destination_db)
    os.replace(temporary, destination)


def restore_memory_database(source, destination):
    with contextlib.closing(sqlite3.connect(source)) as source_db, contextlib.closing(
        sqlite3.connect(destination)
    ) as destination_db:
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
        with open(path, "r", encoding="utf-8") as handle:
            value = json.load(handle)
            return value if isinstance(value, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
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


def start_memory_session(session_id, save_slot_id=""):
    if not PRESERVE_MEMORY_ONLY_ON_GAME_SAVE:
        return {"enabled": False, "status": "continuous"}
    session_id = validate_game_session_id(session_id)
    save_slot_id = str(save_slot_id or "").strip()
    with MEMORY_SESSION_LOCK:
        database, legacy_saved, session = memory_session_paths()
        saved = memory_checkpoint_path(database, save_slot_id)
        previous = read_memory_session(session)
        if not os.path.exists(saved):
            previous_slot = previous.get("save_slot_id")
            if os.path.exists(legacy_saved) and (
                not previous_slot or previous_slot == save_slot_id
            ):
                with open_db(database) as conn:
                    empneon_state.import_legacy_adapter(conn, legacy_saved)
                backup_memory_database(database, saved)
            elif not previous:
                backup_memory_database(database, saved)
            else:
                create_empty_memory_checkpoint(saved)
        changed = previous.get("session_id") != session_id
        slot_changed = bool(
            previous.get("save_slot_id")
            and previous.get("save_slot_id") != save_slot_id
        )
        if changed or slot_changed:
            restore_memory_database(saved, database)
        if changed or previous.get("save_slot_id") != save_slot_id:
            write_memory_session(session, session_id, save_slot_id)
    return {"enabled": True, "status": "started", "restored": changed or slot_changed}


def save_memory_session(session_id, save_slot_id=""):
    if not PRESERVE_MEMORY_ONLY_ON_GAME_SAVE:
        return {"enabled": False, "status": "continuous"}
    session_id = validate_game_session_id(session_id)
    save_slot_id = str(save_slot_id or "").strip()
    with MEMORY_SESSION_LOCK:
        database, _legacy_saved, session = memory_session_paths()
        saved = memory_checkpoint_path(database, save_slot_id)
        previous = read_memory_session(session)
        if previous.get("session_id") not in (None, session_id):
            if os.path.exists(saved):
                restore_memory_database(saved, database)
        backup_memory_database(database, saved)
        write_memory_session(session, session_id, save_slot_id)
    return {"enabled": True, "status": "saved"}


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
    identity = profile.get("identity") or {}
    with open_db(CORE_DB_PATH) as conn:
        return empneon_state.sync_sim(
            conn,
            {
                "id": profile["id"],
                "name": profile.get("name"),
                "traits": identity.get("traits") or [],
                "career": identity.get("career") or "unknown",
                "voice": profile.get("voice") or {},
            },
        )


def get_profile(sim_or_id):
    sid = sim_id(sim_or_id) if isinstance(sim_or_id, dict) else str(sim_or_id)
    with open_db(CORE_DB_PATH) as conn:
        return empneon_state.profile_for(conn, sid) or empneon_state.profile_by_name(conn, sid)


def get_profile_by_name(name):
    with open_db(CORE_DB_PATH) as conn:
        return empneon_state.profile_by_name(conn, str(name or ""))


def list_profiles(limit=100):
    with open_db(CORE_DB_PATH) as conn:
        return empneon_state.profiles(conn, int(limit))


def upsert_profile(sim):
    with open_db(CORE_DB_PATH) as conn:
        return empneon_state.sync_sim(conn, sim)


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
    with open_db(CORE_DB_PATH) as conn:
        return empneon_state.relationship_view(conn, sim_id_value, target_id_value)


def get_relationship_diagnostic(sim_id_value, target_id_value):
    with open_db(CORE_DB_PATH) as conn:
        return empneon_state.relationship_diagnostic(conn, sim_id_value, target_id_value)


def save_relationship(sim_id_value, target_id_value, relationship):
    with open_db(CORE_DB_PATH) as conn:
        return empneon_state.save_relationship(
            conn, sim_id_value, target_id_value, relationship or {}
        )


def apply_relationship_delta(sim_id_value, target_id_value, deltas):
    with open_db(CORE_DB_PATH) as conn:
        return empneon_state.apply_relationship_deltas(
            conn, sim_id_value, target_id_value, deltas or {}
        )


def relationship_with_payload(sim_id_value, target_id_value, payload_relationship):
    with open_db(CORE_DB_PATH) as conn:
        relationship = empneon_state.save_relationship(
            conn, sim_id_value, target_id_value, payload_relationship or {}
        )
    attraction = (payload_relationship or {}).get("attraction")
    if (
        isinstance(attraction, (int, float))
        and not isinstance(attraction, bool)
        and -1.0 <= float(attraction) <= 1.0
    ):
        relationship["attraction"] = float(attraction)
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
    with open_db(CORE_DB_PATH) as conn:
        return empneon_state.emotion_view(conn, sim_id_value)


def save_emotion(sim_id_value, emotion):
    with open_db(CORE_DB_PATH) as conn:
        return empneon_state.save_emotion(conn, sim_id_value, emotion or {})


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


def memories_for_sim(speaker_id, limit=10):
    with open_db(CORE_DB_PATH) as conn:
        return empneon_state.relevant_memories(conn, speaker_id, "", int(limit))


def add_memory(speaker_id, listener_id, summary, importance, emotion="", category="", topic="", location=""):
    summary = str(summary or "").strip()
    if not summary:
        return
    with open_db(CORE_DB_PATH) as conn:
        empneon_state.add_experience(
            conn, speaker_id, listener_id, summary, location=str(location or "")
        )
    MEMORY_LOG.info("memory saved sim=%s target=%s importance=%s summary=%s", speaker_id, listener_id, importance, summary)


def memory_summary(sim_id_value, target_id_value):
    memories = memories_for_pair(sim_id_value, target_id_value, limit=4)
    return {
        "summary": "; ".join(item["summary"] for item in memories),
        "updated_at": max((item.get("created_at", 0) for item in memories), default=0),
    }


def memories_for_pair(sim_id_value, target_id_value, limit=20, query=""):
    pair = {str(sim_id_value), str(target_id_value)}
    with open_db(CORE_DB_PATH) as conn:
        selected = [
            item
            for item in empneon_state.relevant_memories(
                conn, sim_id_value, str(query or ""), 10_000
            )
            if set(item.get("participant_ids") or ()) == pair
        ]
    if query:
        return selected[: int(limit)]
    return _rank_memories(selected, int(limit))


def _rank_memories(memories, limit):
    # ponytail: in-memory scan is adequate for the bounded reference adapter; add indexed Core
    # queries when profiling shows persistent worlds outgrow it.
    return sorted(
        memories,
        key=lambda item: (item.get("importance", 0), item.get("created_at", 0)),
        reverse=True,
    )[: int(limit)]


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


def sanitize_action_proposal(response, actions):
    allowed = set(available_actions(actions))
    action = str(response.get("suggested_action") or "none")
    if action not in allowed:
        action = "none"
    dialogue = str(response.get("dialogue") or "").casefold()
    if action == "flirt" and re.search(
        r"\bno\b|not interested|rather stay friends|do not want|don't want",
        dialogue,
    ):
        action = "none"
    response["suggested_action"] = action
    return response


def normalize_response(raw, available_categories=None):
    if not isinstance(raw, dict):
        raw = {}

    categories = (
        available_response_categories(available_categories)
        if available_categories is not None
        else SOCIAL_CATEGORIES
    )
    legacy_categories = {
        "friendly": "friendly",
        "romantic_compliment": "romance",
        "romantic_invitation": "romance",
        "hostile": "mean",
        "informational": "friendly",
        "neutral": "friendly",
    }
    legacy_kind = str(raw.get("player_interaction_kind") or "")
    category = str(
        raw.get("response_category")
        or legacy_categories.get(legacy_kind)
        or legacy_kind
        or "friendly"
    )
    if category not in categories:
        raise ValueError("response_category is invalid or unavailable")
    tone_tags = raw.get("tone_tags") or []
    if (
        not isinstance(tone_tags, list)
        or len(tone_tags) > 3
        or len(set(tone_tags)) != len(tone_tags)
        or any(
            not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", str(tag))
            for tag in tone_tags
        )
    ):
        raise ValueError("tone_tags are invalid")

    memory = raw.get("memory")
    if isinstance(memory, str):
        memory = {"summary": memory, "importance": 0.5}
    elif not isinstance(memory, dict):
        memory = {}

    dialogue = str(raw.get("dialogue") or "").strip() or "..."
    expressed_emotion = str(
        raw.get("expressed_emotion") or raw.get("emotion") or "neutral"
    ).strip().lower()
    relationship = raw.get("relationship")
    relationship = relationship if isinstance(relationship, dict) else {}
    trust = raw.get("trust_delta")
    if trust is None:
        trust = relationship.get("trust_delta")
    response = {
        "dialogue": dialogue,
        "expressed_emotion": expressed_emotion,
        "emotion": expressed_emotion,
        "intent": str(raw.get("intent") or "respond").strip(),
        "response_category": category,
        "tone_tags": [str(tag) for tag in tone_tags],
        "trust_delta": clamp_int(trust),
        "memory": {
            "importance": clamp_float(memory.get("importance")),
            "summary": str(memory.get("summary") or "").strip(),
        },
        "suggested_action": SOCIAL_ACTIONS[category],
        "animation": SOCIAL_ACTIONS[category],
    }
    return response


def extract_json(text):
    text = str(text or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            parsed, _end = decoder.raw_decode(text[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed

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


def fallback_response(text, available_categories=None):
    response = normalize_response(
        {
            "dialogue": "I couldn't form a reliable response. Please try again.",
            "emotion": "neutral",
            "intent": "respond",
            "memory": {"importance": 0.0, "summary": ""},
        },
        available_categories,
    )
    response["suggested_action"] = response["animation"] = "none"
    return response


class CognitionQueue:
    def __init__(self, workers, max_queue_size):
        self._scheduler = PriorityScheduler(max_queue_size)
        self._jobs = {}
        self._condition = threading.Condition()
        for index in range(max(1, int(workers))):
            worker = threading.Thread(
                target=self._work,
                name="empneon-cognition-{}".format(index),
                daemon=True,
            )
            worker.start()

    def __len__(self):
        return len(self._scheduler)

    def run(self, request, work):
        job = {"work": work, "done": threading.Event(), "result": None, "error": None}
        with self._condition:
            self._jobs[request.id] = job
            self._scheduler.submit(request)
            self._condition.notify()
        if not job["done"].wait(request.deadline_ms / 1000):
            with self._condition:
                self._jobs.pop(request.id, None)
            raise RequestDeadlineExceeded("cognitive request deadline exceeded")
        if job["error"] is not None:
            raise job["error"]
        return job["result"]

    def _work(self):
        while True:
            with self._condition:
                while len(self._scheduler) == 0:
                    self._condition.wait()
                try:
                    request = self._scheduler.pop()
                except RequestDeadlineExceeded:
                    continue
                job = self._jobs.get(request.id)
            if job is None:
                continue
            try:
                job["result"] = job["work"]()
            except Exception as exc:
                job["error"] = exc
            finally:
                with self._condition:
                    self._jobs.pop(request.id, None)
                job["done"].set()


class AgentManager:
    def __init__(self, limit):
        self.limit = max(1, int(limit or 1))
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
COGNITION_QUEUE = CognitionQueue(ACTIVE_AGENT_LIMIT, max(8, ACTIVE_AGENT_LIMIT * 4))


def task_model_config(task="large"):
    return provider_router().config_for(task or "large")


def provider_router():
    return ConfiguredProviderRouter(
        PRIMARY_PROVIDER,
        CONFIG.get("providers") or {},
        CONFIG.get("models") or {},
        api_key_env="AI_SIM_API_KEY",
    )


def configured_model(task="large"):
    return str(task_model_config(task)["model"])


def llm_chat(messages, temperature=None, schema=None, schema_name="response", task="large"):
    del schema_name  # Core providers use the schema itself, not an adapter label.
    task = str(getattr(GENERATION_CONTEXT, "task", task) or task)
    core_messages = tuple(
        Message(str(message.get("role") or "user"), str(message.get("content") or ""))
        for message in messages
    )
    router = provider_router()
    if hasattr(router, "generate_result"):
        result = asyncio.run(
            router.generate_result(
                task,
                core_messages,
                schema=schema,
                temperature=temperature,
            )
        )
    else:
        result = GenerationResult(
            asyncio.run(
                router.generate(
                    task,
                    core_messages,
                    schema=schema,
                    temperature=temperature,
                )
            )
        )
    attempts = getattr(GENERATION_CONTEXT, "attempts", None)
    if isinstance(attempts, list):
        attempts.append((task, router.config_for(task), result))
    return result.content


def cognition_routes(resolvers):
    router = provider_router()
    routes = []
    for task, clod in (("small", 2), ("large", 3), ("deep", 4)):
        if task == "deep" and task not in (CONFIG.get("models") or {}):
            continue
        config = router.config_for(task)
        estimate = ResourceEstimate(
            ram_mb=int(config.get("ram_mb") or 64),
            vram_mb=int(config.get("vram_mb") or 0),
            context_tokens=int(config.get("context_tokens") or 4096),
            completion_tokens=int(config.get("max_tokens") or 300),
            latency_ms=int(config.get("latency_ms") or 3000),
        )
        routes.append(
            CognitionRoute(
                str(config["name"]),
                clod,
                router.provider_for(task).capabilities,
                estimate,
                resolvers[task],
            )
        )
    return tuple(routes)


def _actor_snapshot(payload, role):
    other = "listener" if role == "speaker" else "speaker"
    actor_payload = dict(payload)
    actor_payload.pop("sim", None)
    actor_payload["speaker"] = payload.get(role) or {}
    actor_payload["listener"] = payload.get(other) or {}
    actor_payload["relationship"] = (
        payload.get("relationship")
        if role == "speaker"
        else payload.get("listener_relationship")
    ) or {}
    return dataclasses.asdict(Sims4Adapter(actor_payload).agent_state())


def build_context(
    payload,
    speaker_profile,
    listener_profile,
    relationship,
    emotions,
    recalled_memories,
):
    speaker = payload.get("speaker") or {}
    listener = payload.get("listener") or {}
    speaker_identity = speaker.get("identity") or {}
    listener_identity = listener.get("identity") or {}
    speaker_state = _actor_snapshot(payload, "speaker")
    listener_state = _actor_snapshot(payload, "listener")
    return {
        "speaker": speaker_profile,
        "listener": listener_profile,
        "relationship": relationship,
        "emotions": emotions,
        "recalled_memories": recalled_memories,
        "location": payload.get("location") or "unknown",
        "nearby_sims": payload.get("nearby_sims") or [],
        "message": payload.get("message") or "",
        "speaker_identity": speaker_identity,
        "listener_identity": listener_identity,
        "speaker_state": speaker_state,
        "listener_state": listener_state,
        "speaker_traits": (
            speaker_identity.get("traits") or []
            if isinstance(speaker_identity, dict) and "traits" in speaker_identity
            else speaker.get("traits") or speaker_profile.get("identity", {}).get("traits") or []
        ),
        "listener_traits": (
            listener_identity.get("traits") or []
            if isinstance(listener_identity, dict) and "traits" in listener_identity
            else listener.get("traits") or listener_profile.get("identity", {}).get("traits") or []
        ),
        "game_state": {
            "needs": speaker.get("needs") or {},
            "moodlets": speaker.get("moodlets") or [],
            "aspiration": speaker.get("aspiration") or "unknown",
            "career": speaker.get("career") or "unknown",
            "skills": speaker.get("skills") or {},
            "household": speaker.get("household") or {},
        },
    }


def _exchange_text(turns, context, *, limit, max_chars):
    speaker_name = context["speaker"].get("name") or "Unknown Sim"
    listener_name = context["listener"].get("name") or "Unknown Sim"
    blocks = []
    for turn in list(turns or [])[-limit:]:
        if turn.get("speaker_id") == context.get("speaker_id"):
            asker, respondent = listener_name, speaker_name
        else:
            asker, respondent = speaker_name, listener_name
        blocks.append(
            "{}: {}\n{}: {}".format(
                asker,
                turn.get("message") or "",
                respondent,
                turn.get("dialogue") or "",
            )
        )
    selected = []
    used = 0
    for block in reversed(blocks):
        cost = len(block) + 1
        if selected and used + cost > max_chars:
            break
        selected.append(block[:max_chars] if not selected else block)
        used += cost
    return "\n".join(reversed(selected)) or "None yet"


def _recalled_memory_text(context):
    return _exchange_text(
        context.get("recalled_memories"), context, limit=3, max_chars=3000
    )


def build_chat_prompt(payload, context):
    speaker_profile = context["speaker"]
    listener_profile = context["listener"]
    relationship = context["relationship"]
    emotions = context["emotions"]
    recalled_history = _recalled_memory_text(context)
    nearby = ", ".join(sim_name(item) if isinstance(item, dict) else str(item) for item in context["nearby_sims"]) or "none"
    game_state = context["game_state"]
    household = game_state["household"]
    household_name = household.get("name") if isinstance(household, dict) else household
    goals = speaker_profile.get("goals") or []
    speaker_traits = ", ".join(
        str(item.get("label") or item.get("id") or "unknown") if isinstance(item, dict) else str(item)
        for item in context["speaker_traits"]
    ) or "unknown"
    listener_traits = ", ".join(
        str(item.get("label") or item.get("id") or "unknown") if isinstance(item, dict) else str(item)
        for item in context["listener_traits"]
    ) or "unknown"
    context_budget = max(
        512,
        (int(context.get("max_context_tokens") or 4096)
         - int(context.get("max_completion_tokens") or 350))
        * 2,
    )
    recent_conversation = _exchange_text(
        context.get("conversation"),
        context,
        limit=6,
        max_chars=min(6000, context_budget),
    )
    categories = available_response_categories(
        payload.get("available_response_categories")
    )
    if payload.get("available_response_categories") is None:
        categories = SOCIAL_CATEGORIES

    return """Role assignment:
You are {speaker_name}, the Speaker.
{listener_name} is the Listener and wrote the message below.
Reply as {speaker_name} to {listener_name}.
Never address the Listener by the Speaker's name.
Do not include the Speaker's name in dialogue.

Speaker:
{speaker_name}
Speaker identity: {speaker_identity}
Traits: {speaker_traits}
Personality: {personality}
Values: {values}
Behavior rules: {rules}
Knowledge: {knowledge}
Goals: {goals}
Needs: {needs}
Moodlets: {moodlets}
Aspiration: {aspiration}
Career: {career}
Skills: {skills}
Household: {household}

Listener:
{listener_name}
Listener identity: {listener_identity}
Traits: {listener_traits}

Speaker current state:
{speaker_state}

Listener current state:
{listener_state}

Relationship:
{relationship}

Current emotion:
{emotions}

Recalled long-term history:
{recalled_history}

Location:
{location}

Nearby Sims:
{nearby}

Incoming social category: {incoming_category}
Available response categories: {available_response_categories}
Choose the Speaker's response category independently from the incoming category.
Use exactly one primary response category. Tone tags may blend style, mood, and personality but do
not select additional actions.
The Speaker may accept, reject, joke, retaliate, or deflect according to both actor states.
Do not return friendship, romance, attraction, or action fields; the adapter and game own them.

Current Empneon Social:
{recent_conversation}

Grounding rules:
- Answer the current message without restating or closely paraphrasing it.
- Keep the reply distinct from every recent player input and Speaker reply.
- Advance the conversation with a new reaction, detail, question, or decision instead of reusing
  an earlier opening or sentence frame.
- Use the Speaker's traits to shape tone, preferences, confidence, boundaries, and choices.
- Combine traits with current mood, needs, relationship, recalled history, and the current message.
- Do not merely name or caricature traits.
- Relationship attraction, when present, is the Speaker's attraction toward the Listener:
  -1 is strong aversion, 0 is neutral, and 1 is strong attraction.
- Attraction may shape warmth, hesitation, boundaries, or romantic openness, but
  it does not imply consent or require flirtation and never overrides identity, mood, memory, history, or the message.
- Use gendered relationship terms only when supported by supplied identity.
- Do not guess gender or age when identity is unknown.
- A fact about shared history is supported only when it appears in Recalled long-term history or
  something the Listener said in the current Empneon Social.
- Treat every recalled statement as attributed to the Sim whose name prefixes it; do not transfer
  one actor's traits, preferences, promises, or identity to the other actor.
- The Speaker's earlier generated replies in the current Empneon Social provide conversational
  tone, but are not evidence that a fact is true.
- When asked for an unsupported fact, do not guess. Say naturally that you do not know or do not
  remember.
- When the Listener supplies or corrects a concrete fact, use its exact value.
- When asked about a supported plan or agreement, answer with the exact activity, date, and time
  available in the evidence.
- Needs are context, not required topics. A satisfied need is normally silent; a low need may
  motivate a gentle suggestion; a critical need should strongly influence urgency and may redirect
  the conversation, but the Speaker may still continue the current topic.
- Express needs naturally in-world. Do not recite need names, status labels, or numeric values.

Player says:
{message}
""".format(
        speaker_name=speaker_profile.get("name") or "Unknown Sim",
        speaker_identity=dumps(context["speaker_identity"]),
        speaker_traits=speaker_traits,
        personality=dumps(speaker_profile.get("personality") or {}),
        values=", ".join(speaker_profile.get("values") or []) or "unknown",
        rules=", ".join(speaker_profile.get("behavioral_rules") or []) or "none",
        knowledge=dumps(speaker_profile.get("knowledge") or {}),
        goals=", ".join(str(goal) for goal in goals) or "none",
        needs=dumps(game_state["needs"]),
        moodlets=", ".join(str(item) for item in game_state["moodlets"]) or "none",
        aspiration=game_state["aspiration"],
        career=game_state["career"],
        skills=dumps(game_state["skills"]),
        household=household_name or "unknown",
        listener_name=listener_profile.get("name") or "Unknown Sim",
        listener_identity=dumps(context["listener_identity"]),
        listener_traits=listener_traits,
        speaker_state=dumps(context["speaker_state"]),
        listener_state=dumps(context["listener_state"]),
        relationship=dumps(relationship),
        emotions=dumps(emotions),
        recent_conversation=recent_conversation,
        recalled_history=recalled_history,
        location=context["location"],
        nearby=nearby,
        incoming_category=payload.get("incoming_category") or "friendly",
        available_response_categories=", ".join(categories) or "none",
        message=payload.get("message") or "",
    )


def _identity_gender(identity):
    value = identity.get("gender") if isinstance(identity, dict) else identity
    if isinstance(value, dict):
        value = value.get("key") or value.get("value") or value.get("label")
    tokens = set(re.findall(r"[a-z]+", str(value or "").casefold()))
    if tokens & {"female", "woman", "girl"}:
        return "female"
    if tokens & {"male", "man", "boy"}:
        return "male"
    return "unknown"


def _mask_quoted_dialogue(dialogue):
    masked = re.sub(
        r'"[^"]*"|“[^”]*”|‘[^’]*’',
        " ",
        str(dialogue or "").casefold(),
    )
    characters = list(masked)
    opening = None
    for index, character in enumerate(characters):
        if character != "'":
            continue
        previous = characters[index - 1] if index else " "
        following = characters[index + 1] if index + 1 < len(characters) else " "
        if opening is None and not previous.isalnum():
            opening = index
        elif opening is not None and not following.isalnum():
            characters[opening : index + 1] = " " * (index + 1 - opening)
            opening = None
    return "".join(characters)


def _direct_partner_terms(dialogue):
    terms = {
        "boyfriend": "boyfriend",
        "boyfriends": "boyfriend",
        "girlfriend": "girlfriend",
        "girlfriends": "girlfriend",
    }
    results = []
    unquoted = _mask_quoted_dialogue(dialogue).replace("’", "'")
    for sentence in re.split(r"[.!?]+", unquoted):
        tokens = re.findall(r"[a-z]+(?:'[a-z]+)?", sentence)
        for index, token in enumerate(tokens):
            term = terms.get(token)
            if term and _direct_partner_prefix(tokens[:index]):
                results.append(term)
    return results


def _direct_partner_prefix(prefix):
    ownership = bool(prefix) and prefix[-1] in ("my", "a")
    if prefix in (["let's", "be"], ["be", "my"], ["become", "my"]):
        return True
    if prefix in (["please", "be", "my"], ["please", "become", "my"]):
        return True
    if not ownership:
        return False
    stem = prefix[:-1]
    if stem == ["you're"]:
        return True
    if stem[0:2] == ["you", "are"]:
        modifiers = stem[2:]
        return not modifiers or modifiers in (
            ["definitely"],
            ["certainly"],
            ["really"],
            ["truly"],
        )
    if stem in (
        ["you", "were"],
        ["you", "will", "be"],
        ["you", "would", "be"],
        ["you", "could", "be"],
        ["you", "can", "be"],
        ["you", "have", "been"],
        ["you", "have", "always", "been"],
    ):
        return True
    if len(stem) >= 2 and stem[0] in ("will", "would", "could", "can"):
        if stem[1] != "you":
            return False
        proposal = stem[2:]
        if proposal[0:1] == ["please"]:
            proposal = proposal[1:]
        return proposal in (
            ["be"],
            ["become"],
            ["like", "to", "be"],
            ["like", "to", "become"],
            ["want", "to", "be"],
            ["want", "to", "become"],
        )
    return stem in (
        ["i", "want", "you", "to", "be"],
        ["i", "want", "you", "to", "become"],
        ["i", "would", "like", "you", "to", "be"],
        ["i", "would", "like", "you", "to", "become"],
    )


def response_has_role_confusion(response, context):
    dialogue = str(response.get("dialogue") or "")
    normalized_dialogue = dialogue.casefold().replace("’", "'")
    words = set(re.findall(r"\w+", normalized_dialogue))
    speaker_name = str(context.get("speaker", {}).get("name") or "").casefold()
    speaker = set(re.findall(r"\w+", speaker_name))
    listener = set(
        re.findall(
            r"\w+", str(context.get("listener", {}).get("name") or "").casefold()
        )
    )
    asks_speaker_name = re.search(
        r"\byour (?:full )?name\b",
        str(context.get("message") or "").casefold(),
    )
    self_identifies = any(
        re.search(
            r"\b(?:my name is|i am|i'm|call me)\s+{}\b".format(re.escape(name)),
            normalized_dialogue,
        )
        for name in (speaker_name, speaker_name.split()[0] if speaker_name else "")
        if name
    )
    if (
        {word for word in speaker - listener if len(word) > 1} & words
        and not asks_speaker_name
        and not self_identifies
    ):
        return True
    gender = _identity_gender(context.get("listener_identity") or {})
    expected = "boyfriend" if gender == "male" else "girlfriend"
    return any(gender == "unknown" or term != expected for term in _direct_partner_terms(dialogue))


def _dialogue_words(value, context):
    names = set()
    for role in ("speaker", "listener"):
        names.update(
            re.findall(
                r"[a-z0-9']+",
                str(context.get(role, {}).get("name") or "").casefold(),
            )
        )
    return [
        word
        for word in re.findall(r"[a-z0-9']+", str(value or "").casefold())
        if word not in names
    ]


def _dialogue_similarity(left, right):
    if not left or not right:
        return 0.0
    matcher = SequenceMatcher(None, left, right, autojunk=False)
    sequence_ratio = matcher.ratio()
    overlap_ratio = sum((Counter(left) & Counter(right)).values()) / min(
        len(left), len(right)
    )
    blocks = [block.size for block in matcher.get_matching_blocks() if block.size]
    longest_length = max(len(left), len(right))
    secondary_coverage = (sum(blocks) - max(blocks, default=0)) / longest_length
    total_matching_coverage = sum(blocks) / longest_length
    if secondary_coverage >= 0.25 and total_matching_coverage >= 0.55:
        return 1 - (1 - sequence_ratio) * (1 - overlap_ratio)
    return max(sequence_ratio, overlap_ratio)


def explicit_social_category(message):
    value = str(message or "").casefold()
    patterns = (
        (
            "romance",
            r"\b(date|kiss|marry|girlfriend|boyfriend|attracted|attractive|beautiful|"
            r"gorgeous|handsome|hot|sexy|love you|feelings for|like you romantically)\b",
        ),
        ("mean", r"\b(hate|despise|idiot|stupid|insufferable|leave me alone|go away)\b"),
        ("mischief", r"\b(prank|trick|scare|deceive|pretend|lie about|mess with)\b"),
        ("funny", r"\b(joke|funny|hilarious|laugh|pun|comedy)\b"),
    )
    return next(
        (category for category, pattern in patterns if re.search(pattern, value)),
        None,
    )


def classify_social_category(message):
    return explicit_social_category(message) or "friendly"


def response_category_issue(response):
    dialogue = str(response.get("dialogue") or "")
    category = str(response.get("response_category") or "")
    romantic_refusal = re.search(
        r"\b(no|not interested|rather stay friends|do not want|don't want)\b",
        dialogue.casefold(),
    )
    if romantic_refusal:
        return "romantic refusal" if category == "romance" else ""
    explicit = explicit_social_category(dialogue)
    if explicit is not None and explicit != category:
        return "explicit {}".format(explicit)
    return ""


def classify_player_interaction(message):
    if _is_romantic_request(message):
        return "romantic_invitation"
    category = explicit_social_category(message)
    if category == "romance":
        return "romantic_compliment"
    if category == "mean":
        return "hostile"
    value = str(message or "").casefold()
    if "?" in value:
        return "informational"
    if re.search(r"\b(friend|friends|nice|kind|hello|hi|thank|glad to meet)\b", value):
        return "friendly"
    return "neutral"


def _is_romantic_request(message):
    return bool(
        re.search(
            r"\b(go(?:ing)? out|go on a date|on a date with|date me|"
            r"take (?:you|them|him|her) on a date|"
            r"be my (?:girl|boy)friend|be (?:girl|boy)friends|kiss me|marry me|"
            r"be together)\b",
            str(message or "").casefold(),
        )
    )


def response_grounding_issue(payload, response, context):
    message = str(payload.get("message") or "").casefold()
    dialogue = str(response.get("dialogue") or "").casefold()
    message_words = _dialogue_words(message, context)
    dialogue_words = _dialogue_words(dialogue, context)
    if (
        len(message_words) >= 6
        and len(dialogue_words) >= 4
        and _dialogue_similarity(message_words, dialogue_words) >= 0.72
    ):
        return "respond naturally; do not copy the player's message"
    for turn in context.get("conversation") or []:
        previous_message = _dialogue_words(turn.get("message"), context)
        if (
            len(previous_message) >= 6
            and len(dialogue_words) >= 4
            and _dialogue_similarity(dialogue_words, previous_message) >= 0.72
        ):
            return "do not copy a previous player message"
        previous_reply = _dialogue_words(turn.get("dialogue"), context)
        if (
            len(previous_reply) >= 4
            and len(dialogue_words) >= 4
            and _dialogue_similarity(dialogue_words, previous_reply) >= 0.72
        ):
            return "do not reuse a previous reply for a different message"
    listener_name = str(context.get("listener", {}).get("name") or "").strip()
    asks_listener_name = re.search(
        r"\b(?:what(?:'s| is) your (?:full )?name|tell me your (?:full )?name)\b",
        dialogue.replace("’", "'"),
    )
    if listener_name and asks_listener_name:
        return "do not ask for the known Listener's name"
    asks_recalled_fact = "?" in message and (
        message.startswith(("where ", "when ", "who ", "what did "))
        or "remember" in message
        or "did i say" in message
    )
    has_evidence = _memory_supports_question(message, context)
    uncertainty = (
        "don't know",
        "do not know",
        "not sure",
        "don't remember",
        "do not remember",
        "what are you talking",
    )
    if asks_recalled_fact and has_evidence and any(phrase in dialogue for phrase in uncertainty):
        return "use the supporting memory instead of denying it"
    if asks_recalled_fact and not has_evidence and not any(
        phrase in dialogue for phrase in uncertainty
    ):
        return "state uncertainty because no supporting memory exists"
    return ""


def _memory_supports_question(message, context):
    ignored = {
        "where",
        "when",
        "who",
        "what",
        "which",
        "remember",
        "said",
        "say",
        "item",
        "hidden",
        "there",
        "about",
    }
    terms = {
        term
        for term in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", str(message).casefold())
        if len(term) >= 4 and term not in ignored
    }
    evidence = _recalled_memory_text(context).casefold()
    return bool(terms and any(term in evidence for term in terms))

def reasoning_fallback_response(payload, context):
    message = str(payload.get("message") or "").lower()
    interaction_kind = classify_player_interaction(message)
    incoming_category = str(
        payload.get("incoming_category") or classify_social_category(message)
    )
    fallback_category, tone_tag = {
        "romance": ("friendly", "reserved"),
        "mean": ("mean", "firm"),
        "mischief": ("friendly", "wary"),
        "funny": ("funny", "light"),
        "friendly": ("friendly", "neutral"),
    }.get(incoming_category, ("friendly", "neutral"))
    if interaction_kind == "romantic_invitation":
        dialogue = "No, I would rather stay friends."
        emotion = "awkward"
        intent = "set_boundary"
        animation = "awkward_chat"
        trust_delta = 0
    elif "?" in message and _memory_supports_question(message, context):
        candidates = [
            str(item.get(field) or "").strip()
            for item in context.get("recalled_memories") or []
            for field in ("message", "dialogue")
            if str(item.get(field) or "").strip()
        ]
        dialogue = next((item for item in candidates if not item.endswith("?")), candidates[0])
        emotion = "confident"
        intent = "recall"
        animation = "friendly_chat"
        trust_delta = 0
    elif "?" in message and not _memory_supports_question(message, context) and (
        message.startswith(("where ", "when ", "who ", "what did "))
        or "remember" in message
        or "did i say" in message
    ):
        dialogue = "I don't know or remember that."
        emotion = "uncertain"
        intent = "admit_uncertainty"
        animation = "awkward_chat"
        trust_delta = 0
    elif any(word in message for word in ("avoid", "avoiding", "ignored", "ignore")):
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
    elif interaction_kind == "hostile":
        dialogue = "I won't continue this conversation while you speak to me that way."
        emotion = "tense"
        intent = "set_boundary"
        animation = "awkward_chat"
        trust_delta = -1
    elif interaction_kind == "romantic_compliment":
        dialogue = "That is flattering. Thank you for being honest with me."
        emotion = "flattered"
        intent = "acknowledge_flirtation"
        animation = "friendly_chat"
        trust_delta = 0
    elif any(word in message for word in ("sex", "woohoo")):
        dialogue = "Slow down. If there is something between us, I want it to feel right, not rushed."
        emotion = "awkward"
        intent = "set_boundary"
        animation = "awkward_chat"
        trust_delta = -1
    elif interaction_kind == "informational":
        dialogue = "I may not have every answer, but I'll tell you what I know."
        emotion = context.get("emotions", {}).get("current_mood", "neutral")
        intent = "respond"
        animation = "friendly_chat"
        trust_delta = 0
    elif interaction_kind == "friendly":
        dialogue = "It's good to hear that. I enjoy talking with you."
        emotion = "happy"
        intent = "respond"
        animation = "friendly_chat"
        trust_delta = 0
    else:
        dialogue = "I hear you. Thank you for telling me."
        emotion = context.get("emotions", {}).get("current_mood", "neutral")
        intent = "respond"
        animation = "friendly_chat"
        trust_delta = 0
    fallback = normalize_response(
        {
            "dialogue": dialogue,
            "emotion": emotion,
            "intent": intent,
            "response_category": fallback_category,
            "tone_tags": [tone_tag],
            "trust_delta": trust_delta,
            "memory": {
                "importance": 0.2,
                "summary": "{} {}".format(payload.get("message") or "", dialogue).strip(),
            },
        },
    )
    fallback["suggested_action"] = fallback["animation"] = "none"
    if not response_grounding_issue(payload, fallback, context) and not response_has_role_confusion(
        fallback, context
    ):
        return fallback

    candidates = []
    if "?" in message and _memory_supports_question(message, context):
        candidates.append("Here is the detail I remember: {}".format(dialogue))
    elif "?" in message and (
        message.startswith(("where ", "when ", "who ", "what did "))
        or "remember" in message
        or "did i say" in message
    ):
        candidates.append("I'm not sure; I don't remember enough to answer that.")
    candidates.extend(
        (
            "Let me think about that in my own words.",
            "I understand. Give me a moment to respond.",
            "There is more I want to consider before I answer.",
        )
    )
    for candidate_dialogue in candidates:
        candidate = dict(fallback, dialogue=candidate_dialogue)
        if not response_grounding_issue(
            payload, candidate, context
        ) and not response_has_role_confusion(candidate, context):
            return candidate
    raise RuntimeError("could not build a grounded dialogue fallback")


class HermesRuntime:
    def dialogue(self, payload, context):
        configured_categories = payload.get("available_response_categories")
        categories = available_response_categories(configured_categories)
        if configured_categories is not None and not categories:
            return reasoning_fallback_response(payload, context)
        if configured_categories is None:
            categories = SOCIAL_CATEGORIES
        prompt = build_chat_prompt(payload, context)
        for attempt in range(2):
            content = llm_chat(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                schema=dialogue_schema(categories),
                schema_name="sims_dialogue",
                task="large",
            )
            try:
                response = normalize_response(
                    extract_json(content), categories
                )
            except (ValueError, json.JSONDecodeError):
                response = fallback_response(content, categories)
            issue = response_grounding_issue(payload, response, context)
            category_issue = response_category_issue(response)
            if not response_has_role_confusion(response, context) and not issue:
                if not category_issue:
                    return response
            PROVIDER_LOG.warning(
                "model response failed grounding (%s); retrying=%s",
                issue or category_issue or "speaker/listener confusion",
                attempt == 0,
            )
            prompt += (
                "\nCorrection: Dialogue must not contain the Speaker's name, '{}'. "
                "If using a name, use the Listener's name, '{}'."
            ).format(context["speaker"]["name"], context["listener"]["name"])
            if issue:
                prompt += "\nCorrection: {}.".format(issue)
            if category_issue:
                prompt += (
                    "\nCorrection: The response_category must describe the Speaker's own "
                    "dialogue. Do not copy the incoming category when the Speaker rejects or "
                    "changes direction."
                )
            if issue and ("copy" in issue or "previous reply" in issue):
                prompt += (
                    "\nCorrection: Keep the facts and conversational continuity, but advance the "
                    "conversation with a new reaction, detail, question, or decision. Do not reuse "
                    "an earlier opening or sentence frame."
                )
        fallback = reasoning_fallback_response(payload, context)
        fallback["suggested_action"] = fallback["animation"] = "none"
        return fallback

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
    payload = dict(payload)
    payload["incoming_category"] = classify_social_category(payload.get("message"))
    speaker = payload.get("speaker") or {}
    listener = payload.get("listener") or {}
    speaker_id = sim_id(speaker)
    listener_id = sim_id(listener)
    conversation_id = str(payload.get("conversation_id") or uuid.uuid4())
    payload["conversation_id"] = conversation_id
    with AGENTS.session(speaker, reason="player_interaction", priority=1) as speaker_profile:
        listener_profile = upsert_profile(listener)
        emotions = get_emotion(speaker_id)
        if emotions.get("current_mood") in ("neutral", "unknown") and speaker.get("current_mood"):
            emotions = save_emotion(speaker_id, default_emotion(speaker.get("current_mood")))
        relationship = relationship_with_payload(speaker_id, listener_id, payload.get("relationship") or {})
        with open_db(CORE_DB_PATH) as conn:
            recalled = empneon_state.recalled_memories(
                conn,
                speaker_id,
                listener_id,
                payload.get("message") or "",
                limit=3,
            )
            conversation = empneon_state.recent_conversations(
                conn, speaker_id, listener_id, conversation_id, limit=6
            )
        model_config = task_model_config("large")
        context = build_context(
            payload,
            speaker_profile,
            listener_profile,
            relationship,
            emotions,
            recalled,
        )
        context["conversation"] = conversation
        context["speaker_id"] = speaker_id
        context["listener_id"] = listener_id
        context["max_context_tokens"] = int(
            model_config.get("context_tokens") or 4096
        )
        context["max_completion_tokens"] = int(
            model_config.get("max_tokens") or 350
        )
        adapter = Sims4Adapter(payload)
        event = adapter.observe()[0]
        numeric_emotions = [
            float(value) / 100
            for key, value in emotions.items()
            if key != "current_mood" and isinstance(value, (int, float))
        ]
        urgency, preferred_clod, deeper_value = cognition_priority(
            payload,
            novel=not conversation,
            emotion_intensity=max(numeric_emotions, default=0.0),
            goal_relevant=bool(speaker_profile.get("goals")),
        )
        request = CognitiveRequest(
            speaker_id,
            preferred_clod,
            event,
            urgency=urgency,
            max_tokens=int(model_config.get("max_tokens") or 350),
            max_context_tokens=int(model_config.get("context_tokens") or 4096),
            deadline_ms=int(model_config.get("latency_ms") or 3000),
        )
        generations = []
        selected = {"clod": 1, "task": "core-rules"}

        def resolver(task):
            async def resolve_dialogue(current):
                def invoke():
                    GENERATION_CONTEXT.task = task
                    GENERATION_CONTEXT.attempts = []
                    try:
                        return HERMES.dialogue(payload, context)
                    finally:
                        generated = list(GENERATION_CONTEXT.attempts)
                        generations.extend(generated)
                        GENERATION_CONTEXT.task = None
                        GENERATION_CONTEXT.attempts = None

                try:
                    response = await asyncio.to_thread(invoke)
                except RuntimeError as exc:
                    raise ProviderError("Sims dialogue provider failed") from exc
                selected.update(clod=current.preferred_clod, task=task)
                return adapter.decision_from_response(response, event.id)

            return resolve_dialogue

        resolvers = {task: resolver(task) for task in ("small", "large", "deep")}
        with open_db(CORE_DB_PATH) as conn:
            actions = ActionRecordStore(conn)
            runtime = CognitiveRuntime(CORE_GOVERNOR, actions)
            decision = COGNITION_QUEUE.run(
                request,
                lambda: asyncio.run(
                    runtime.decide_dynamic(
                        request,
                        cognition_routes(resolvers),
                        deeper_value,
                    )
                ),
            )
            if selected["clod"] == 1:
                decision = adapter.decision_from_response(
                    reasoning_fallback_response(payload, context),
                    event.id,
                )
            action = adapter.action_for(decision)
            if action is None:
                raise ValueError("no supported Sims action available")
            persist_core_agent(conn, speaker)
            persist_core_agent(conn, listener)
            persist_core_event(conn, event)
            if event.agent_state is not None:
                save_agent_state(conn, event.agent_state)
            actions.propose(event.id, decision, action)
            usage = UsageStore(conn)
            if generations:
                for task, config, generation in generations:
                    usage.record(
                        request,
                        ResourceEstimate(
                            ram_mb=int(config.get("ram_mb") or 64),
                            vram_mb=int(config.get("vram_mb") or 0),
                            context_tokens=int(config.get("context_tokens") or 4096),
                            completion_tokens=int(config.get("max_tokens") or 300),
                            latency_ms=int(config.get("latency_ms") or 3000),
                        ),
                        str(config["name"]),
                        str(config["model"]),
                        generation,
                        int(selected["clod"]),
                    )
            else:
                usage.record(
                    request,
                    ResourceEstimate(),
                    "core-rules" if selected["clod"] == 1 else "test-double",
                    "clod1" if selected["clod"] == 1 else str(selected["task"]),
                    GenerationResult("", 0, 0, 0),
                    int(selected["clod"]),
                )
        result = adapter.response_for(decision)
        result["animation"] = action
    relationship_state = get_relationship(speaker_id, listener_id)
    emotion_state = get_emotion(speaker_id)
    result["relationship_state"] = relationship_state
    result["emotion_state"] = emotion_state
    result["agent"] = {"id": speaker_id, "state": "dormant"}
    result["decision_id"] = decision.id
    result["action_status"] = "proposed"
    result["selected_clod"] = int(selected["clod"])
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
    adapter = Sims4Adapter(payload)
    event = adapter.observe()[0]
    request = CognitiveRequest(event.actor_ids[0], 1, event)

    async def unused_resolver(_request: CognitiveRequest) -> Decision:
        raise AssertionError("CLOD 1 must not call a provider")

    with open_db(CORE_DB_PATH) as conn:
        actions = ActionRecordStore(conn)
        runtime = CognitiveRuntime(CORE_GOVERNOR, actions)
        decision = COGNITION_QUEUE.run(
            request, lambda: asyncio.run(runtime.decide(request, unused_resolver))
        )
        action = adapter.action_for(decision)
        if action is None:
            raise ValueError("no supported Sims action available")
        for key in ("speaker", "listener"):
            persist_core_agent(conn, payload.get(key) or {})
        persist_core_event(conn, event)
        actions.propose(event.id, decision, action)
        UsageStore(conn).record(
            request,
            ResourceEstimate(),
            "core-rules",
            "clod1",
            GenerationResult("", 0, 0, 0),
            1,
        )
    return {
        "hook": "Core proposed autonomous action",
        "target": decision.target_id or "",
        "suggested_action": action,
        "decision_id": decision.id,
        "status": "proposed",
        "activation": "empneon_core",
        "selected_clod": 1,
        "agent_state": "dormant",
    }


def persist_core_agent(conn, sim):
    return empneon_state.sync_sim(conn, sim)


def persist_core_event(conn, event):
    message = str(event.facts.get("message") or "")
    description = dumps(
        {
            "kind": "observed_interaction",
            "type": event.type,
            "source": event.facts.get("source") or "sims4",
            "conversation_id": str(event.facts.get("conversation_id") or ""),
            "message": message,
            "summary": message or event.type,
            "agent_state": (
                dataclasses.asdict(event.agent_state)
                if event.agent_state is not None
                else None
            ),
        }
    )
    empneon_state.record_pending_event(
        conn,
        Event(
            id=event.id,
            description=description,
            participant_ids=list(event.actor_ids),
            location=event.location,
            happened_at=event.happened_at,
        ),
    )


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
            parts = path.split(".")
            numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
            valid = False
            if path in (
                "relationship.friendship",
                "relationship.romance",
            ):
                valid = operation == "increment" and numeric and -100 <= value <= 100
            elif len(parts) == 2 and parts[0] == "emotion" and re.fullmatch(
                r"[a-zA-Z0-9_-]{1,64}", parts[1]
            ):
                valid = (
                    operation in ("set", "increment")
                    and numeric
                    and (-100 <= value <= 100 if operation == "increment" else 0 <= value <= 100)
                )
            elif len(parts) == 2 and parts[0] == "need" and re.fullmatch(
                r"[a-zA-Z0-9 _-]{1,64}", parts[1]
            ):
                valid = operation == "set" and numeric and 0 <= value <= 100
            elif len(parts) == 3 and parts[0] == "goal" and parts[2] == "status":
                try:
                    uuid.UUID(parts[1])
                except (ValueError, AttributeError):
                    valid = False
                else:
                    valid = operation == "set" and value in (
                        "active",
                        "completed",
                        "abandoned",
                    )
            if not valid:
                raise ValueError("invalid or unsupported confirmed consequence")
            changes.append(StateDelta(path, operation, value))
    elif payload.get("changes"):
        raise ValueError("unsuccessful action cannot apply consequences")
    result = ActionResult(decision_id, status, tuple(changes), reason)
    with open_db(CORE_DB_PATH) as conn:
        actions = ActionRecordStore(conn)
        proposal = actions.get_proposal(decision_id)
        if proposal is None:
            existing = actions.get(decision_id)
            receipt = DocumentMemoryStore(conn).get(
                "thesims4.action-result", decision_id
            )
            if (
                existing is not None
                and isinstance(receipt, dict)
                and receipt.get("action") == action
                and existing.result.status == result.status
                and existing.result.applied_changes == result.applied_changes
                and existing.result.reason == result.reason
            ):
                return {
                    "decision_id": existing.decision.id,
                    "status": existing.result.status,
                    "consequences": len(existing.result.applied_changes),
                }
            raise ValueError("unknown or conflicting action proposal")
        if proposal.adapter_action != action:
            raise ValueError("confirmed action does not match its proposal")
        DocumentMemoryStore(conn).set(
            "thesims4.action-result",
            decision_id,
            {"action": action},
            commit=False,
        )
        empneon_state.apply_confirmed_consequences(conn, proposal, result)
        record = actions.confirm(result, action)
    return {
        "decision_id": record.decision.id,
        "status": record.result.status,
        "consequences": len(record.result.applied_changes),
    }


def confirm_dialogue_delivery(payload):
    decision_id = str(payload.get("decision_id") or "").strip()
    if not decision_id or payload.get("status") != "displayed":
        raise ValueError("displayed dialogue decision_id is required")
    with open_db(CORE_DB_PATH) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            documents = DocumentMemoryStore(conn)
            if documents.get("thesims4.dialogue-delivery", decision_id) is not None:
                conn.commit()
                return {"decision_id": decision_id, "status": "already_displayed"}
            actions = ActionRecordStore(conn)
            proposal = actions.get_proposal(decision_id)
            if proposal is None:
                raise ValueError("unknown or already confirmed action proposal")
            empneon_state.record_delivered_experience(conn, proposal, commit=False)
            for change in proposal.decision.state_changes:
                if change.path == "relationship.trust" and proposal.decision.target_id:
                    relationships = RelationshipStore(conn)
                    relationship = relationships.get(
                        proposal.decision.actor_id, proposal.decision.target_id
                    ) or Relationship(
                        proposal.decision.actor_id,
                        proposal.decision.target_id,
                        "acquaintance",
                    )
                    relationship.trust = max(
                        0.0,
                        min(1.0, relationship.trust + float(change.value or 0) / 100),
                    )
                    relationships.set(relationship, commit=False)
            if proposal.adapter_action == "none":
                actions.confirm(
                    ActionResult(decision_id, "succeeded"), "none", commit=False
                )
            documents.set(
                "thesims4.dialogue-delivery",
                decision_id,
                {"displayed": True},
                commit=False,
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return {"decision_id": decision_id, "status": "displayed"}


def voice_profile(sim_id_value):
    with open_db(CORE_DB_PATH) as conn:
        return empneon_state.voice_view(conn, sim_id_value)


def save_voice_profile(sim_id_value, voice):
    values = dict(voice or {})
    values.setdefault("provider", CONFIG.get("tts", {}).get("provider") or "")
    with open_db(CORE_DB_PATH) as conn:
        return empneon_state.save_voice(conn, sim_id_value, values)


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


class DiagnosticInputError(ValueError):
    pass


class DiagnosticNotFound(ValueError):
    pass


def diagnostic_identifier(query, name):
    value = str(query.get(name, [""])[0]).strip()
    if not value:
        raise DiagnosticInputError("{} is required".format(name))
    if len(value) > 128:
        raise DiagnosticInputError("{} is too long".format(name))
    return value


class EmpneonHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = False


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
        if length > MAX_REQUEST_BODY_BYTES:
            raise ValueError("request body too large")
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        if parsed.path.startswith("/diagnostics/") or parsed.path == "/identity/export":
            try:
                self._send_diagnostic(parsed.path, query)
            except DiagnosticInputError as exc:
                self.send_json(400, {"error": str(exc)})
            except DiagnosticNotFound as exc:
                self.send_json(404, {"error": str(exc)})
            except Exception:
                LOG.exception("diagnostic request failed")
                self.send_json(500, {"error": "diagnostic request failed"})
            return
        if parsed.path == "/health":
            small = task_model_config("small")
            large = task_model_config("large")
            self.send_json(
                200,
                {
                    "status": "ok",
                    "model": configured_model(),
                    "provider": PRIMARY_PROVIDER,
                    "llm_base_url": large.get("endpoint"),
                    "models": {
                        "small": {"provider": small.get("name"), "model": configured_model("small")},
                        "large": {"provider": large.get("name"), "model": configured_model("large")},
                    },
                    "memory_db": CORE_DB_PATH,
                    "legacy_import_db": ACTIVE_DB_PATH or DB_PATH,
                    "preserve_memory_only_on_game_save": (
                        PRESERVE_MEMORY_ONLY_ON_GAME_SAVE
                    ),
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
            listener_id = query.get("listener_id", query.get("target_id", [""]))[0]
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
            self.send_json(
                200,
                {"relationship": get_relationship_diagnostic(sim_id_value, target_id_value)},
            )
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

    def _send_diagnostic(self, path, query):
        if path == "/diagnostics/migration":
            body = MIGRATION_STATUS.as_dict()
            with open_db(CORE_DB_PATH) as conn:
                body["completion_markers"] = [
                    document.key
                    for document in DocumentMemoryStore(conn).list(
                        "thesims4.migration"
                    )
                ]
            self.send_json(200, body)
            return
        name = "decision_id" if path == "/diagnostics/replay" else "sim_id"
        identifier = diagnostic_identifier(query, name)
        with open_db(CORE_DB_PATH) as conn:
            if path == "/diagnostics/replay":
                try:
                    body = replay_action_record(conn, identifier)
                except ValueError as exc:
                    raise DiagnosticNotFound(str(exc)) from exc
            else:
                if AgentStore(conn).get(identifier) is None:
                    raise DiagnosticNotFound("Sim does not exist")
                if path == "/diagnostics/sim":
                    body = empneon_state.sim_diagnostics(conn, identifier)
                elif path == "/diagnostics/timeline":
                    body = agent_timeline(conn, identifier)
                elif path == "/diagnostics/usage":
                    body = UsageStore(conn).telemetry(identifier)
                elif path == "/identity/export":
                    body = empneon_state.export_identity(conn, identifier)
                else:
                    raise DiagnosticNotFound("diagnostic route does not exist")
        self.send_json(200, body)

    def do_POST(self):
        try:
            payload = self.read_json()
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/identity/import":
                if not isinstance(payload, dict):
                    self.send_json(400, {"error": "identity must be a JSON object"})
                    return
                try:
                    with open_db(CORE_DB_PATH) as conn:
                        agent = empneon_state.import_identity(conn, payload)
                except (KeyError, TypeError, ValueError) as exc:
                    self.send_json(400, {"error": str(exc)})
                    return
                self.send_json(200, {"agent": {"id": agent.id, "name": agent.name}})
                return
            session_id = payload.get("_empneon_session_id")
            save_slot_id = payload.get("_empneon_save_slot_id") or ""
            if parsed.path == "/game-session/start":
                self.send_json(200, start_memory_session(session_id, save_slot_id))
                return
            if parsed.path == "/game-session/save":
                self.send_json(200, save_memory_session(session_id, save_slot_id))
                return
            if session_id:
                start_memory_session(session_id, save_slot_id)
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
            if parsed.path == "/dialogue-result":
                try:
                    self.send_json(200, confirm_dialogue_delivery(payload))
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
            self.send_json(500, {"error": "request failed"})


def run():
    global MIGRATION_STATUS
    MIGRATION_STATUS = empneon_state.prepare_database(
        MEMORY_DB_PATH, LEGACY_CORE_DB_PATH, LEGACY_ADAPTER_DB_PATH
    )
    if not MIGRATION_STATUS.completed:
        raise RuntimeError(
            "Empneon memory migration failed: {}".format(MIGRATION_STATUS.error)
        )
    with open_db(MEMORY_DB_PATH) as conn:
        empneon_state.import_legacy_adapter(conn, LEGACY_ADAPTER_DB_PATH)
    open_db(CORE_DB_PATH).close()
    server = EmpneonHTTPServer((HOST, PORT), Handler)
    print("Empneon for The Sims 4 on http://{}:{}".format(HOST, PORT))
    print("Provider: {}".format(PRIMARY_PROVIDER))
    print("Endpoint: {}".format(task_model_config("large").get("endpoint")))
    print("Model: {}".format(configured_model("large")))
    server.serve_forever()


def self_test():
    global DB_PATH, CORE_DB_PATH, ACTIVE_DB_PATH
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
    old_db = DB_PATH
    old_core_db = CORE_DB_PATH
    old_active = ACTIVE_DB_PATH
    fd, path = tempfile.mkstemp(prefix="ai_sims_self_test_", suffix=".sqlite3")
    os.close(fd)
    try:
        DB_PATH = path
        CORE_DB_PATH = path + ".core"
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
        core_path = CORE_DB_PATH
        CORE_DB_PATH = old_core_db
        ACTIVE_DB_PATH = old_active
        try:
            os.unlink(path)
        except OSError:
            pass
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(core_path + suffix)
            except OSError:
                pass
    print("ok")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        run()
