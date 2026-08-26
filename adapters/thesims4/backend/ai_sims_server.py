# ruff: noqa: E402, F401

import asyncio
import dataclasses
import json
import logging
import os
import re
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.request
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

from empneon.core.contracts import (
    SOCIAL_CATEGORIES,
    ActionResult,
    CognitiveRequest,
    Decision,
    StateDelta,
    WorldEvent,
)
from empneon.core.identity.relationships import Relationship, RelationshipStore
from empneon.core.identity.store import AgentStore
from empneon.core.memory.documents import DocumentMemoryStore
from empneon.core.memory.episodic import Event
from empneon.core.memory.recall import (
    analyze_recall_query,
    fact_supports_query,
    validate_recall_response,
)
from empneon.core.replay import replay_action_record
from empneon.core.runtime import ActionRecordStore, CognitiveRuntime
from empneon.core.scheduler.resources import ResourceBudget, ResourceEstimate, ResourceGovernor
from empneon.core.scheduler.selection import CognitionRoute
from empneon.core.scheduler.usage import UsageStore
from empneon.core.state import save_agent_state
from empneon.core.timeline import agent_timeline
from empneon.db.connection import db_session, open_db
from empneon.providers.llm import (
    ConfiguredProviderRouter,
    GenerationResult,
    Message,
    ProviderError,
)

from backend import (
    cognition as backend_cognition,
)
from backend import (
    config as backend_config,
)
from backend import (
    db as backend_db,
)
from backend import (
    empneon_state,
)
from backend.agent_manager import AgentManager as _AgentManager
from backend.agent_manager import CognitionQueue as _CognitionQueue
from backend.agent_manager import Test10QueueGate as _Test10QueueGate
from empneon_thesims4 import Sims4Adapter, cognition_priority

CONFIG_PATH = os.environ.get("AI_SIM_CONFIG", os.path.join(ROOT, "config", "config.json"))

DEFAULT_CONFIG = backend_config.DEFAULT_CONFIG


def deep_update(base, overrides):
    return backend_config.deep_update(base, overrides)


def load_config():
    return backend_config.load_config(CONFIG_PATH, os.environ, sys.stderr)


CONFIG = load_config()
if not isinstance(CONFIG.get("preserve_memory_only_on_game_save"), bool):
    raise ValueError("preserve_memory_only_on_game_save must be true or false")
if not isinstance(CONFIG.get("response_rejection_enabled"), bool):
    raise ValueError("response_rejection_enabled must be true or false")
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
RESPONSE_REJECTION_ENABLED = CONFIG["response_rejection_enabled"]
API_TOKEN = str(os.environ.get("AI_SIM_API_TOKEN") or "")
PRIMARY_PROVIDER = str(CONFIG.get("provider") or "lmstudio")
ACTIVE_DB_PATH = None
MEMORY_SESSION_LOCK = threading.RLock()
CORE_GOVERNOR = ResourceGovernor(ResourceBudget(256, 0, ACTIVE_AGENT_LIMIT))
GENERATION_CONTEXT = threading.local()
ASYNC_LOOP = threading.local()
MIGRATION_STATUS = empneon_state.MigrationStatus(
    os.path.abspath(MEMORY_DB_PATH), completed=False, error="not started"
)


def setup_logging():
    return backend_config.setup_logging(ROOT, CONFIG, sys.stderr)


LOG = logging.getLogger("ai_sims")
LOG.setLevel(logging.DEBUG if CONFIG.get("debug") else logging.INFO)
AGENT_LOG = logging.getLogger("ai_sims.agent_manager")
PROVIDER_LOG = logging.getLogger("ai_sims.ai_provider")
MEMORY_LOG = logging.getLogger("ai_sims.memory")
for logger in (AGENT_LOG, PROVIDER_LOG, MEMORY_LOG):
    logger.setLevel(LOG.level)


SYSTEM_PROMPT = backend_cognition.SYSTEM_PROMPT
SOCIAL_ACTIONS = backend_cognition.SOCIAL_ACTIONS
RELATIONSHIP_OUTCOMES = backend_cognition.RELATIONSHIP_OUTCOMES
ROMANTIC_RECIPROCATION = backend_cognition.ROMANTIC_RECIPROCATION
ROMANTIC_REJECTION = backend_cognition.ROMANTIC_REJECTION
DIALOGUE_SCHEMA = backend_cognition.DIALOGUE_SCHEMA
MEMORY_SELECTOR_SCHEMA = backend_cognition.MEMORY_SELECTOR_SCHEMA
available_actions = backend_cognition.available_actions
available_response_categories = backend_cognition.available_response_categories
dialogue_schema = backend_cognition.dialogue_schema
DIRECTOR_SCHEMA = backend_cognition.DIRECTOR_SCHEMA


def connect_db():
    global ACTIVE_DB_PATH
    path = ACTIVE_DB_PATH or DB_PATH
    conn = backend_db.connect_db(path, sqlite3.connect, init_db)
    ACTIVE_DB_PATH = path
    return conn


def memory_session_paths():
    database = os.path.abspath(CORE_DB_PATH)
    return (
        database,
        os.path.abspath(ACTIVE_DB_PATH or DB_PATH) + ".empneon-saved",
        database + ".empneon-session",
    )


memory_checkpoint_path = backend_db.memory_checkpoint_path
backup_memory_database = backend_db.backup_memory_database
restore_memory_database = backend_db.restore_memory_database
create_empty_memory_checkpoint = backend_db.create_empty_memory_checkpoint
read_memory_session = backend_db.read_memory_session
write_memory_session = backend_db.write_memory_session
validate_game_session_id = backend_db.validate_game_session_id


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
                with db_session(database) as conn:
                    empneon_state.import_legacy_adapter(conn, legacy_saved)
                backup_memory_database(database, saved)
            elif not previous:
                backup_memory_database(database, saved)
            else:
                create_empty_memory_checkpoint(saved)
        changed = previous.get("session_id") != session_id
        slot_changed = bool(
            previous.get("save_slot_id") and previous.get("save_slot_id") != save_slot_id
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


_LEGACY_COLUMNS = backend_db._LEGACY_COLUMNS
ensure_column = backend_db.ensure_column
init_db = backend_db.init_db


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
    with db_session(CORE_DB_PATH) as conn:
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
    with db_session(CORE_DB_PATH) as conn:
        return empneon_state.profile_for(conn, sid) or empneon_state.profile_by_name(conn, sid)


def get_profile_by_name(name):
    with db_session(CORE_DB_PATH) as conn:
        return empneon_state.profile_by_name(conn, str(name or ""))


def list_profiles(limit=100):
    with db_session(CORE_DB_PATH) as conn:
        return empneon_state.profiles(conn, int(limit))


def upsert_profile(sim):
    with db_session(CORE_DB_PATH) as conn:
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
    with db_session(CORE_DB_PATH) as conn:
        return empneon_state.relationship_view(conn, sim_id_value, target_id_value)


def get_relationship_diagnostic(sim_id_value, target_id_value):
    with db_session(CORE_DB_PATH) as conn:
        return empneon_state.relationship_diagnostic(conn, sim_id_value, target_id_value)


def save_relationship(sim_id_value, target_id_value, relationship):
    with db_session(CORE_DB_PATH) as conn:
        return empneon_state.save_relationship(
            conn, sim_id_value, target_id_value, relationship or {}
        )


def apply_relationship_delta(sim_id_value, target_id_value, deltas):
    with db_session(CORE_DB_PATH) as conn:
        return empneon_state.apply_relationship_deltas(
            conn, sim_id_value, target_id_value, deltas or {}
        )


def relationship_with_payload(sim_id_value, target_id_value, payload_relationship):
    with db_session(CORE_DB_PATH) as conn:
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
    with db_session(CORE_DB_PATH) as conn:
        return empneon_state.emotion_view(conn, sim_id_value)


def save_emotion(sim_id_value, emotion):
    with db_session(CORE_DB_PATH) as conn:
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
    with db_session(CORE_DB_PATH) as conn:
        return empneon_state.relevant_memories(conn, speaker_id, "", int(limit))


def add_memory(
    speaker_id, listener_id, summary, importance, location=""
):
    summary = str(summary or "").strip()
    if not summary:
        return
    with db_session(CORE_DB_PATH) as conn:
        empneon_state.add_experience(
            conn, speaker_id, listener_id, summary, location=str(location or "")
        )
    MEMORY_LOG.info(
        "memory saved sim=%s target=%s importance=%s summary=%s",
        speaker_id,
        listener_id,
        importance,
        summary,
    )


def memory_summary(sim_id_value, target_id_value):
    memories = memories_for_pair(sim_id_value, target_id_value, limit=4)
    return {
        "summary": "; ".join(item["summary"] for item in memories),
        "updated_at": max((item.get("created_at", 0) for item in memories), default=0),
    }


def memories_for_pair(sim_id_value, target_id_value, limit=20, query=""):
    pair = {str(sim_id_value), str(target_id_value)}
    with db_session(CORE_DB_PATH) as conn:
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


clamp_int = backend_cognition.clamp_int
clamp_float = backend_cognition.clamp_float
sanitize_action_proposal = backend_cognition.sanitize_action_proposal
validated_relationship_outcome = backend_cognition.validated_relationship_outcome
normalize_response = backend_cognition.normalize_response
extract_json = backend_cognition.extract_json
fallback_response = backend_cognition.fallback_response


class AgentManager(_AgentManager):
    def __init__(self, limit):
        super().__init__(
            limit,
            profile_lookup=lambda sim: upsert_profile(sim),
            clock=lambda: now(),
            log_info=lambda *args: AGENT_LOG.info(*args),
        )


class CognitionQueue(_CognitionQueue):
    def __init__(self, workers, max_queue_size):
        super().__init__(
            workers,
            max_queue_size,
            clock=lambda: time.time(),
            log_info=lambda *args: AGENT_LOG.info(*args),
        )


class Test10QueueGate(_Test10QueueGate):
    def __init__(self, queue, timeout_seconds=60):
        super().__init__(
            queue,
            timeout_seconds,
            monotonic=lambda: time.monotonic(),
            sleep=lambda seconds: time.sleep(seconds),
            log_exception=lambda *args: AGENT_LOG.exception(*args),
        )


AGENTS = AgentManager(ACTIVE_AGENT_LIMIT)
COGNITION_QUEUE = CognitionQueue(
    ACTIVE_AGENT_LIMIT,
    max(8, ACTIVE_AGENT_LIMIT * 4),
)
TEST10_QUEUE_GATE = Test10QueueGate(COGNITION_QUEUE)


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


def run_async(awaitable):
    loop = getattr(ASYNC_LOOP, "loop", None)
    if loop is None or loop.is_closed():
        loop = asyncio.new_event_loop()
        ASYNC_LOOP.loop = loop
    return loop.run_until_complete(awaitable)


def llm_chat(messages, temperature=None, schema=None, schema_name="response", task="large"):
    del schema_name  # Core providers use the schema itself, not an adapter label.
    task = str(getattr(GENERATION_CONTEXT, "task", task) or task)
    core_messages = tuple(
        Message(str(message.get("role") or "user"), str(message.get("content") or ""))
        for message in messages
    )
    router = provider_router()
    if hasattr(router, "generate_result"):
        result = run_async(
            router.generate_result(
                task,
                core_messages,
                schema=schema,
                temperature=temperature,
            )
        )
    else:
        result = GenerationResult(
            run_async(
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


_FULL_EXCHANGE_QUERY = backend_cognition._FULL_EXCHANGE_QUERY


def select_recalled_memories(query, candidates):
    return backend_cognition.select_recalled_memories(
        query,
        candidates,
        lambda *args, **kwargs: llm_chat(*args, **kwargs),
    )


def semantic_recalled_memories(query, candidates, fallback):
    return backend_cognition.semantic_recalled_memories(
        query,
        candidates,
        fallback,
        select_recalled_memories,
        lambda *args, **kwargs: PROVIDER_LOG.warning(*args, **kwargs),
    )


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


_actor_snapshot = backend_cognition._actor_snapshot
build_context = backend_cognition.build_context
_exchange_text = backend_cognition._exchange_text
_recalled_memory_text = backend_cognition._recalled_memory_text
build_chat_prompt = backend_cognition.build_chat_prompt


_identity_gender = backend_cognition._identity_gender
_mask_quoted_dialogue = backend_cognition._mask_quoted_dialogue
_direct_partner_terms = backend_cognition._direct_partner_terms
_direct_partner_prefix = backend_cognition._direct_partner_prefix
response_has_role_confusion = backend_cognition.response_has_role_confusion
_dialogue_words = backend_cognition._dialogue_words
_dialogue_similarity = backend_cognition._dialogue_similarity
explicit_social_category = backend_cognition.explicit_social_category
classify_social_category = backend_cognition.classify_social_category
response_category_issue = backend_cognition.response_category_issue
classify_player_interaction = backend_cognition.classify_player_interaction
_is_romantic_request = backend_cognition._is_romantic_request
response_grounding_issue = backend_cognition.response_grounding_issue


_supported_recall_facts = backend_cognition._supported_recall_facts
_CODEWORD_FACT = backend_cognition._CODEWORD_FACT
_codeword_fact_parts = backend_cognition._codeword_fact_parts
_attributed_fact_text = backend_cognition._attributed_fact_text
_recalled_fact_dialogue = backend_cognition._recalled_fact_dialogue
_PREFERENCE_FACT = backend_cognition._PREFERENCE_FACT
_PROMISE_FACT = backend_cognition._PROMISE_FACT
_preference_issue = backend_cognition._preference_issue
_promise_issue = backend_cognition._promise_issue
_supported_recall_issue = backend_cognition._supported_recall_issue
_memory_supports_question = backend_cognition._memory_supports_question


def reasoning_fallback_response(payload, context):
    return backend_cognition.reasoning_fallback_response(
        payload,
        context,
        lambda *args, **kwargs: response_grounding_issue(*args, **kwargs),
        lambda *args, **kwargs: response_has_role_confusion(*args, **kwargs),
    )


_response_rejection_diagnostics = backend_cognition._response_rejection_diagnostics


class CognitionRuntime(backend_cognition.CognitionRuntime):
    def __init__(self):
        super().__init__(
            lambda *args, **kwargs: llm_chat(*args, **kwargs),
            lambda: RESPONSE_REJECTION_ENABLED,
            lambda *args, **kwargs: PROVIDER_LOG.warning(*args, **kwargs),
            grounding_issue=lambda *args, **kwargs: response_grounding_issue(*args, **kwargs),
            role_confusion=lambda *args, **kwargs: response_has_role_confusion(*args, **kwargs),
            reasoning_fallback=lambda *args, **kwargs: reasoning_fallback_response(*args, **kwargs),
        )


COGNITION_RUNTIME = CognitionRuntime()


def chat(payload):
    payload = dict(payload)
    payload["incoming_category"] = classify_social_category(payload.get("message"))
    speaker = payload.get("speaker") or {}
    listener = payload.get("listener") or {}
    speaker_id = str(speaker.get("id") or "").strip()
    listener_id = str(listener.get("id") or "").strip()
    conversation_id = str(payload.get("conversation_id") or "").strip()
    if not speaker_id:
        raise ValueError("speaker id is required")
    if not listener_id:
        raise ValueError("listener id is required")
    if not conversation_id:
        raise ValueError("conversation id is required")
    payload["conversation_id"] = conversation_id
    with AGENTS.session(speaker, reason="player_interaction", priority=1) as speaker_profile:
        listener_profile = upsert_profile(listener)
        emotions = get_emotion(speaker_id)
        if emotions.get("current_mood") in ("neutral", "unknown") and speaker.get("current_mood"):
            emotions = save_emotion(speaker_id, default_emotion(speaker.get("current_mood")))
        relationship = relationship_with_payload(
            speaker_id, listener_id, payload.get("relationship") or {}
        )
        query = str(payload.get("message") or "")
        with db_session(CORE_DB_PATH) as conn:
            deterministic_recalled = empneon_state.recalled_memories(
                conn,
                speaker_id,
                listener_id,
                query,
                limit=3,
            )
            candidates = empneon_state.recall_candidates(
                conn,
                speaker_id,
                listener_id,
                query,
            )
            conversation = empneon_state.recent_conversations(
                conn, speaker_id, listener_id, conversation_id, limit=6
            )
        GENERATION_CONTEXT.attempts = []
        try:
            recalled = semantic_recalled_memories(
                query,
                candidates,
                deterministic_recalled,
            )
        finally:
            generations = list(GENERATION_CONTEXT.attempts)
            GENERATION_CONTEXT.attempts = None
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
        context["max_context_tokens"] = int(model_config.get("context_tokens") or 4096)
        context["max_completion_tokens"] = int(model_config.get("max_tokens") or 350)
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
        selected = {"clod": 1, "task": "core-rules"}
        response_rejections = []

        def resolver(task):
            async def resolve_dialogue(current):
                def invoke():
                    GENERATION_CONTEXT.task = task
                    GENERATION_CONTEXT.attempts = []
                    try:
                        return COGNITION_RUNTIME.dialogue(payload, context)
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
                response_rejections.extend(
                    _response_rejection_diagnostics(response.pop("_response_rejections", []))
                )
                return adapter.decision_from_response(response, event.id)

            return resolve_dialogue

        resolvers = {task: resolver(task) for task in ("small", "large", "deep")}
        with db_session(CORE_DB_PATH) as conn:
            actions = ActionRecordStore(conn)
            runtime = CognitiveRuntime(CORE_GOVERNOR, actions)
            decision = COGNITION_QUEUE.run(
                request,
                lambda: run_async(
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
            if response_rejections:
                DocumentMemoryStore(conn).set(
                    "thesims4.response-rejections",
                    decision.id,
                    {"response_rejections": response_rejections},
                )
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
                        {
                            "small": 2,
                            "large": 3,
                            "deep": 4,
                        }.get(task, int(selected["clod"])),
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
    return COGNITION_RUNTIME.story_beat(prompt)


def autonomous_action(payload):
    adapter = Sims4Adapter(payload)
    event = adapter.observe()[0]
    request = CognitiveRequest(event.actor_ids[0], 1, event)

    async def unused_resolver(_request: CognitiveRequest) -> Decision:
        raise AssertionError("CLOD 1 must not call a provider")

    with db_session(CORE_DB_PATH) as conn:
        actions = ActionRecordStore(conn)
        runtime = CognitiveRuntime(CORE_GOVERNOR, actions)
        decision = COGNITION_QUEUE.run(
            request, lambda: run_async(runtime.decide(request, unused_resolver))
        )
        action = adapter.action_for(decision)
        if action is None:
            raise ValueError("no supported Sims action available")
        actor = payload.get("speaker") or payload.get("sim") or {}
        persist_core_agent(conn, actor)
        listener = payload.get("listener")
        if isinstance(listener, dict) and listener.get("id"):
            persist_core_agent(conn, listener)
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
                dataclasses.asdict(event.agent_state) if event.agent_state is not None else None
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
            elif (
                len(parts) == 2
                and parts[0] == "emotion"
                and re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", parts[1])
            ):
                valid = (
                    operation in ("set", "increment")
                    and numeric
                    and (-100 <= value <= 100 if operation == "increment" else 0 <= value <= 100)
                )
            elif (
                len(parts) == 2
                and parts[0] == "need"
                and re.fullmatch(r"[a-zA-Z0-9 _-]{1,64}", parts[1])
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
    with db_session(CORE_DB_PATH) as conn:
        actions = ActionRecordStore(conn)
        proposal = actions.get_proposal(decision_id)
        if proposal is None:
            existing = actions.get(decision_id)
            receipt = DocumentMemoryStore(conn).get("thesims4.action-result", decision_id)
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
    with db_session(CORE_DB_PATH) as conn:
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
                actions.confirm(ActionResult(decision_id, "succeeded"), "none", commit=False)
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
    with db_session(CORE_DB_PATH) as conn:
        return empneon_state.voice_view(conn, sim_id_value)


def save_voice_profile(sim_id_value, voice):
    values = dict(voice or {})
    values.setdefault("provider", CONFIG.get("tts", {}).get("provider") or "")
    with db_session(CORE_DB_PATH) as conn:
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
        raise DiagnosticInputError(f"{name} is required")
    if len(value) > 128:
        raise DiagnosticInputError(f"{name} is too long")
    return value


def sims_timeline(conn, agent_id):
    timeline = agent_timeline(conn, agent_id, limit=100)
    documents = DocumentMemoryStore(conn)
    for entry in timeline["entries"]:
        if entry["type"] != "decision":
            continue
        try:
            stored = documents.get("thesims4.response-rejections", entry["id"])
        except json.JSONDecodeError:
            continue
        if not isinstance(stored, dict):
            continue
        rejections = _response_rejection_diagnostics(stored.get("response_rejections"))
        if not rejections:
            continue
        entry["data"]["diagnostics"] = {"response_rejections": rejections}
    return timeline


from backend import server as backend_server

backend_server.Handler.resolve = staticmethod(globals().__getitem__)
EmpneonHTTPServer = backend_server.EmpneonHTTPServer
Handler = backend_server.Handler


def run():
    global MIGRATION_STATUS
    setup_logging()
    MIGRATION_STATUS = empneon_state.prepare_database(
        MEMORY_DB_PATH, LEGACY_CORE_DB_PATH, LEGACY_ADAPTER_DB_PATH
    )
    if not MIGRATION_STATUS.completed:
        raise RuntimeError(f"Empneon memory migration failed: {MIGRATION_STATUS.error}")
    with db_session(MEMORY_DB_PATH) as conn:
        empneon_state.import_legacy_adapter(conn, LEGACY_ADAPTER_DB_PATH)
    open_db(CORE_DB_PATH).close()
    server = EmpneonHTTPServer((HOST, PORT), Handler)
    print(f"Empneon for The Sims 4 on http://{HOST}:{PORT}")
    print(f"Provider: {PRIMARY_PROVIDER}")
    print("Endpoint: {}".format(task_model_config("large").get("endpoint")))
    print("Model: {}".format(configured_model("large")))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Empneon backend stopped by keyboard interrupt.")
    finally:
        server.server_close()


def self_test():
    _SELF_TEST_SIM_NAME = "Bella Goth"
    parsed = extract_json(
        '```json\n{"dialogue":"hi","relationship":{"friendship_delta":12},"memory":"met"}\n```'
    )
    result = normalize_response(parsed)
    assert result["dialogue"] == "hi"
    assert result["relationship_outcome"] == "none"
    assert result["memory"]["summary"] == "met"
    assert result["animation"] == "social.friendly"
    assert extract_json('{dialogue: "ok"}')["dialogue"] == "ok"
    assert fallback_response("plain text")["dialogue"] == "plain text"
    role_context = {
        "speaker": {"name": "Sri Bolton"},
        "listener": {"name": "Robin Casillas"},
    }
    assert response_has_role_confusion({"dialogue": "Sure, Sri."}, role_context)
    assert not response_has_role_confusion({"dialogue": "Sure, Robin."}, role_context)
    fd, path = tempfile.mkstemp(prefix="ai_sims_self_test_", suffix=".sqlite3")
    os.close(fd)
    try:
        with db_session(path) as conn:
            sim = {
                "id": "bella-goth",
                "name": _SELF_TEST_SIM_NAME,
                "traits": ["romantic", "family-oriented"],
            }
            target = {"id": "mauricio", "name": "Mauricio", "traits": ["loyal"]}
            profile = empneon_state.sync_sim(conn, sim)
            assert profile["name"] == _SELF_TEST_SIM_NAME
            empneon_state.sync_sim(conn, target)
            relationship = empneon_state.apply_relationship_deltas(
                conn,
                "bella-goth",
                "mauricio",
                {"trust_delta": 5, "respect_delta": 2},
            )
            assert relationship["trust"] == 55
            emotion = empneon_state.emotion_view(conn, "bella-goth")
            for key, delta in emotion_from_label("angry").items():
                emotion[key] = clamp_int(emotion.get(key, 0) + delta, 0, 100)
            emotion["current_mood"] = "angry"
            emotion = empneon_state.save_emotion(conn, "bella-goth", emotion)
            assert emotion["anger"] > 0
            empneon_state.add_experience(
                conn,
                "bella-goth",
                "mauricio",
                "Mauricio helped Bella",
            )
            memories = empneon_state.relevant_memories(conn, "bella-goth", "Mauricio", 20)
            assert memories[0]["summary"] == "Mauricio helped Bella"
        fallback = reasoning_fallback_response(
            {"message": "why have you been avoiding me?"},
            {
                "emotions": {"current_mood": "tense"},
                "speaker": {"name": _SELF_TEST_SIM_NAME},
                "listener": {"name": "Mauricio"},
                "speaker_id": "bella-goth",
                "listener_id": "mauricio",
                "recalled_memories": [],
            },
        )
        assert fallback["dialogue"] != "..."
        assert fallback["animation"] == "none"
    finally:
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(path + suffix)
            except OSError:
                pass
    print("ok")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        run()
