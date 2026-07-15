"""SQLite DDL for Empneon identity and agent state."""

SCHEMA_VERSION = 10

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

_CREATE_EVENT_OBSERVATIONS = """
CREATE TABLE IF NOT EXISTS event_observations (
    id          TEXT    PRIMARY KEY,
    event_id    TEXT    NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    agent_id    TEXT    NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    perception  TEXT    NOT NULL,
    observed_at INTEGER NOT NULL,
    UNIQUE(event_id, agent_id)
)
"""

_CREATE_BELIEFS = """
CREATE TABLE IF NOT EXISTS beliefs (
    id         TEXT    PRIMARY KEY,
    agent_id   TEXT    NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    statement  TEXT    NOT NULL,
    created_at INTEGER NOT NULL
)
"""

_CREATE_BELIEF_PROVENANCE = """
CREATE TABLE IF NOT EXISTS belief_provenance (
    belief_id            TEXT PRIMARY KEY REFERENCES beliefs(id) ON DELETE CASCADE,
    source_observation_id TEXT REFERENCES event_observations(id) ON DELETE NO ACTION,
    source_belief_id      TEXT REFERENCES beliefs(id) ON DELETE NO ACTION,
    confidence           REAL NOT NULL CHECK(confidence BETWEEN 0.0 AND 1.0),
    interpretation       TEXT NOT NULL,
    lineage              TEXT NOT NULL,
    CHECK((source_observation_id IS NULL) != (source_belief_id IS NULL))
)
"""

_CREATE_BELIEF_RELATIONS = """
CREATE TABLE IF NOT EXISTS belief_relations (
    belief_id         TEXT    NOT NULL REFERENCES beliefs(id) ON DELETE CASCADE,
    related_belief_id TEXT    NOT NULL REFERENCES beliefs(id) ON DELETE CASCADE,
    relation          TEXT    NOT NULL CHECK(relation IN ('contradicts', 'revises')),
    reason            TEXT    NOT NULL,
    created_at        INTEGER NOT NULL,
    PRIMARY KEY (belief_id, related_belief_id, relation),
    CHECK(belief_id != related_belief_id)
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

_CREATE_COGNITION_USAGE = """
CREATE TABLE IF NOT EXISTS cognition_usage (
    id                          TEXT    PRIMARY KEY,
    request_id                  TEXT    NOT NULL,
    agent_id                    TEXT    NOT NULL,
    event_id                    TEXT    NOT NULL,
    provider                    TEXT    NOT NULL,
    model                       TEXT    NOT NULL,
    estimated_ram_mb            INTEGER NOT NULL,
    estimated_vram_mb           INTEGER NOT NULL,
    estimated_context_tokens    INTEGER NOT NULL,
    estimated_completion_tokens INTEGER NOT NULL,
    estimated_latency_ms        INTEGER NOT NULL,
    actual_prompt_tokens        INTEGER,
    actual_completion_tokens    INTEGER,
    actual_latency_ms           INTEGER,
    recorded_at                 INTEGER NOT NULL
)
"""

_ADD_COGNITION_USAGE_SELECTED_CLOD = """
ALTER TABLE cognition_usage
ADD COLUMN selected_clod INTEGER CHECK(selected_clod BETWEEN 0 AND 4)
"""

_CREATE_ACTION_RESULTS = """
CREATE TABLE IF NOT EXISTS action_results (
    decision_id    TEXT    PRIMARY KEY,
    event_id       TEXT    NOT NULL,
    actor_id       TEXT    NOT NULL,
    intent         TEXT    NOT NULL,
    target_id      TEXT,
    evidence_ids   TEXT    NOT NULL,
    decision_changes TEXT  NOT NULL,
    confidence     REAL    NOT NULL,
    status         TEXT    NOT NULL,
    applied_changes TEXT   NOT NULL,
    reason         TEXT,
    completed_at   INTEGER NOT NULL
)
"""

_CREATE_ACTION_CONSEQUENCES = """
CREATE TABLE IF NOT EXISTS action_consequences (
    decision_id TEXT    NOT NULL REFERENCES action_results(decision_id) ON DELETE CASCADE,
    position    INTEGER NOT NULL,
    path        TEXT    NOT NULL,
    operation   TEXT    NOT NULL,
    value       TEXT,
    PRIMARY KEY (decision_id, position)
)
"""

_CREATE_ACTION_PROPOSALS = """
CREATE TABLE IF NOT EXISTS action_proposals (
    decision_id      TEXT PRIMARY KEY,
    event_id         TEXT NOT NULL,
    actor_id         TEXT NOT NULL,
    intent           TEXT NOT NULL,
    target_id        TEXT,
    evidence_ids     TEXT NOT NULL,
    decision_changes TEXT NOT NULL,
    confidence       REAL NOT NULL,
    adapter_action   TEXT NOT NULL
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

_CREATE_IDX_EVENT_OBSERVATIONS_AGENT = """
CREATE INDEX IF NOT EXISTS idx_event_observations_agent
    ON event_observations(agent_id, observed_at)
"""

_CREATE_IDX_BELIEFS_AGENT = """
CREATE INDEX IF NOT EXISTS idx_beliefs_agent
    ON beliefs(agent_id, created_at)
"""

_CREATE_IDX_BELIEF_SINGLE_REVISION = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_belief_single_revision
    ON belief_relations(related_belief_id) WHERE relation = 'revises'
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
    _CREATE_COGNITION_USAGE,
    _CREATE_ACTION_RESULTS,
    _CREATE_ACTION_CONSEQUENCES,
    _CREATE_ACTION_PROPOSALS,
    _CREATE_IDX_RELATIONSHIPS_AGENT,
    _CREATE_IDX_RELATIONSHIPS_TARGET,
    _CREATE_IDX_GOALS_AGENT_STATUS,
    _CREATE_IDX_EMOTIONAL_STATES_AGENT,
    _CREATE_EVENTS,
    _CREATE_EVENT_PARTICIPANTS,
    _CREATE_IDX_EVENT_PARTICIPANTS_AGENT,
    _CREATE_IDX_EVENTS_HAPPENED_AT,
    _CREATE_EVENT_OBSERVATIONS,
    _CREATE_BELIEFS,
    _CREATE_BELIEF_PROVENANCE,
    _CREATE_BELIEF_RELATIONS,
    _CREATE_IDX_EVENT_OBSERVATIONS_AGENT,
    _CREATE_IDX_BELIEFS_AGENT,
    _CREATE_IDX_BELIEF_SINGLE_REVISION,
]

_VALIDATE_AGENTS_INSERT = """
CREATE TRIGGER validate_agents_insert
BEFORE INSERT ON agents
WHEN NEW.age IS NOT NULL AND NEW.age < 0
BEGIN
    SELECT RAISE(ABORT, 'agent age must not be negative');
END
"""

_VALIDATE_AGENTS_UPDATE = _VALIDATE_AGENTS_INSERT.replace(
    "validate_agents_insert\nBEFORE INSERT", "validate_agents_update\nBEFORE UPDATE"
)

_VALIDATE_PERSONALITY_INSERT = """
CREATE TRIGGER validate_personality_insert
BEFORE INSERT ON personality
WHEN NEW.openness NOT BETWEEN 0.0 AND 1.0
  OR NEW.conscientiousness NOT BETWEEN 0.0 AND 1.0
  OR NEW.extraversion NOT BETWEEN 0.0 AND 1.0
  OR NEW.agreeableness NOT BETWEEN 0.0 AND 1.0
  OR NEW.neuroticism NOT BETWEEN 0.0 AND 1.0
BEGIN
    SELECT RAISE(ABORT, 'personality values must be between 0 and 1');
END
"""

_VALIDATE_PERSONALITY_UPDATE = _VALIDATE_PERSONALITY_INSERT.replace(
    "validate_personality_insert\nBEFORE INSERT",
    "validate_personality_update\nBEFORE UPDATE",
)

_VALIDATE_RELATIONSHIPS_INSERT = """
CREATE TRIGGER validate_relationships_insert
BEFORE INSERT ON relationships
WHEN NEW.strength NOT BETWEEN -1.0 AND 1.0
  OR NEW.trust NOT BETWEEN 0.0 AND 1.0
BEGIN
    SELECT RAISE(ABORT, 'relationship strength or trust is out of range');
END
"""

_VALIDATE_RELATIONSHIPS_UPDATE = _VALIDATE_RELATIONSHIPS_INSERT.replace(
    "validate_relationships_insert\nBEFORE INSERT",
    "validate_relationships_update\nBEFORE UPDATE",
)

_VALIDATE_EMOTIONS_INSERT = """
CREATE TRIGGER validate_emotions_insert
BEFORE INSERT ON emotional_states
WHEN NEW.value NOT BETWEEN 0.0 AND 1.0
BEGIN
    SELECT RAISE(ABORT, 'emotion value must be between 0 and 1');
END
"""

_VALIDATE_EMOTIONS_UPDATE = _VALIDATE_EMOTIONS_INSERT.replace(
    "validate_emotions_insert\nBEFORE INSERT", "validate_emotions_update\nBEFORE UPDATE"
)

_VALIDATE_GOALS_INSERT = """
CREATE TRIGGER validate_goals_insert
BEFORE INSERT ON goals
WHEN NEW.priority NOT BETWEEN 0.0 AND 1.0
  OR NEW.status NOT IN ('active', 'completed', 'abandoned')
BEGIN
    SELECT RAISE(ABORT, 'goal priority or status is invalid');
END
"""

_VALIDATE_GOALS_UPDATE = _VALIDATE_GOALS_INSERT.replace(
    "validate_goals_insert\nBEFORE INSERT", "validate_goals_update\nBEFORE UPDATE"
)

_VALIDATE_VOICE_INSERT = """
CREATE TRIGGER validate_voice_insert
BEFORE INSERT ON voice_profiles
WHEN NEW.speed <= 0.0 OR NEW.pitch <= 0.0
BEGIN
    SELECT RAISE(ABORT, 'voice speed and pitch must be positive');
END
"""

_VALIDATE_VOICE_UPDATE = _VALIDATE_VOICE_INSERT.replace(
    "validate_voice_insert\nBEFORE INSERT", "validate_voice_update\nBEFORE UPDATE"
)

MIGRATIONS: dict[int, tuple[str, ...]] = {
    2: (
        _VALIDATE_AGENTS_INSERT,
        _VALIDATE_AGENTS_UPDATE,
        _VALIDATE_PERSONALITY_INSERT,
        _VALIDATE_PERSONALITY_UPDATE,
        _VALIDATE_RELATIONSHIPS_INSERT,
        _VALIDATE_RELATIONSHIPS_UPDATE,
        _VALIDATE_EMOTIONS_INSERT,
        _VALIDATE_EMOTIONS_UPDATE,
        _VALIDATE_GOALS_INSERT,
        _VALIDATE_GOALS_UPDATE,
        _VALIDATE_VOICE_INSERT,
        _VALIDATE_VOICE_UPDATE,
    ),
    3: (_CREATE_COGNITION_USAGE,),
    4: (_CREATE_ACTION_RESULTS,),
    5: (_CREATE_ACTION_CONSEQUENCES,),
    6: (_CREATE_ACTION_PROPOSALS,),
    7: (
        _CREATE_EVENT_OBSERVATIONS,
        _CREATE_BELIEFS,
        _CREATE_IDX_EVENT_OBSERVATIONS_AGENT,
        _CREATE_IDX_BELIEFS_AGENT,
    ),
    8: (_CREATE_BELIEF_PROVENANCE,),
    9: (_CREATE_BELIEF_RELATIONS, _CREATE_IDX_BELIEF_SINGLE_REVISION),
    10: (_ADD_COGNITION_USAGE_SELECTED_CLOD,),
}
