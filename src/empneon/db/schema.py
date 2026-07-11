"""SQLite DDL for Empneon identity and agent state."""

SCHEMA_VERSION = 1

_CREATE_SCHEMA_VERSION = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
)
"""

_CREATE_AGENTS = """
CREATE TABLE IF NOT EXISTS agents (
    id          TEXT    PRIMARY KEY,
    name        TEXT    NOT NULL,
    age         INTEGER,
    occupation  TEXT,
    game_id     TEXT,
    adapter     TEXT,
    created_at  INTEGER NOT NULL,
    updated_at  INTEGER NOT NULL
)
"""

_CREATE_PERSONALITY = """
CREATE TABLE IF NOT EXISTS personality (
    agent_id          TEXT PRIMARY KEY
                           REFERENCES agents(id) ON DELETE CASCADE,
    openness          REAL NOT NULL DEFAULT 0.5,
    conscientiousness REAL NOT NULL DEFAULT 0.5,
    extraversion      REAL NOT NULL DEFAULT 0.5,
    agreeableness     REAL NOT NULL DEFAULT 0.5,
    neuroticism       REAL NOT NULL DEFAULT 0.5
)
"""

_CREATE_RELATIONSHIPS = """
CREATE TABLE IF NOT EXISTS relationships (
    id                TEXT    PRIMARY KEY,
    agent_id          TEXT    NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    target_agent_id   TEXT    NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    relationship_type TEXT    NOT NULL,
    strength          REAL    NOT NULL DEFAULT 0.0,
    trust             REAL    NOT NULL DEFAULT 0.5,
    updated_at        INTEGER NOT NULL,
    UNIQUE(agent_id, target_agent_id)
)
"""

_CREATE_EMOTIONAL_STATES = """
CREATE TABLE IF NOT EXISTS emotional_states (
    agent_id     TEXT    NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    emotion      TEXT    NOT NULL,
    value        REAL    NOT NULL DEFAULT 0.0,
    velocity     REAL    NOT NULL DEFAULT 0.0,
    acceleration REAL    NOT NULL DEFAULT 0.0,
    updated_at   INTEGER NOT NULL,
    PRIMARY KEY (agent_id, emotion)
)
"""

_CREATE_GOALS = """
CREATE TABLE IF NOT EXISTS goals (
    id          TEXT    PRIMARY KEY,
    agent_id    TEXT    NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    description TEXT    NOT NULL,
    priority    REAL    NOT NULL DEFAULT 0.5,
    status      TEXT    NOT NULL DEFAULT 'active',
    created_at  INTEGER NOT NULL,
    updated_at  INTEGER NOT NULL
)
"""

_CREATE_VOICE_PROFILES = """
CREATE TABLE IF NOT EXISTS voice_profiles (
    agent_id TEXT PRIMARY KEY
                  REFERENCES agents(id) ON DELETE CASCADE,
    provider TEXT,
    voice_id TEXT,
    speed    REAL NOT NULL DEFAULT 1.0,
    pitch    REAL NOT NULL DEFAULT 1.0,
    settings TEXT
)
"""

_CREATE_EVENTS = """
CREATE TABLE IF NOT EXISTS events (
    id          TEXT    PRIMARY KEY,
    description TEXT    NOT NULL,
    location    TEXT,
    happened_at INTEGER NOT NULL,
    created_at  INTEGER NOT NULL
)
"""

_CREATE_EVENT_PARTICIPANTS = """
CREATE TABLE IF NOT EXISTS event_participants (
    event_id TEXT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    PRIMARY KEY (event_id, agent_id)
)
"""

_CREATE_AGENT_METADATA = """
CREATE TABLE IF NOT EXISTS agent_metadata (
    agent_id TEXT    NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    key      TEXT    NOT NULL,
    value    TEXT    NOT NULL,
    PRIMARY KEY (agent_id, key)
)
"""

_CREATE_IDX_RELATIONSHIPS_AGENT = """
CREATE INDEX IF NOT EXISTS idx_relationships_agent
    ON relationships(agent_id)
"""

_CREATE_IDX_RELATIONSHIPS_TARGET = """
CREATE INDEX IF NOT EXISTS idx_relationships_target
    ON relationships(target_agent_id)
"""

_CREATE_IDX_GOALS_AGENT_STATUS = """
CREATE INDEX IF NOT EXISTS idx_goals_agent_status
    ON goals(agent_id, status)
"""

_CREATE_IDX_EMOTIONAL_STATES_AGENT = """
CREATE INDEX IF NOT EXISTS idx_emotional_states_agent
    ON emotional_states(agent_id)
"""

_CREATE_IDX_EVENT_PARTICIPANTS_AGENT = """
CREATE INDEX IF NOT EXISTS idx_event_participants_agent
    ON event_participants(agent_id)
"""

_CREATE_IDX_EVENTS_HAPPENED_AT = """
CREATE INDEX IF NOT EXISTS idx_events_happened_at
    ON events(happened_at)
"""

ALL_DDL: list[str] = [
    _CREATE_SCHEMA_VERSION,
    _CREATE_AGENTS,
    _CREATE_PERSONALITY,
    _CREATE_RELATIONSHIPS,
    _CREATE_EMOTIONAL_STATES,
    _CREATE_GOALS,
    _CREATE_VOICE_PROFILES,
    _CREATE_AGENT_METADATA,
    _CREATE_IDX_RELATIONSHIPS_AGENT,
    _CREATE_IDX_RELATIONSHIPS_TARGET,
    _CREATE_IDX_GOALS_AGENT_STATUS,
    _CREATE_IDX_EMOTIONAL_STATES_AGENT,
    _CREATE_EVENTS,
    _CREATE_EVENT_PARTICIPANTS,
    _CREATE_IDX_EVENT_PARTICIPANTS_AGENT,
    _CREATE_IDX_EVENTS_HAPPENED_AT,
]
