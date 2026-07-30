import contextlib
import dataclasses
import json
import re
import shutil
import sqlite3
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from empneon.core.identity.emotions import EmotionalState, EmotionalStateStore
from empneon.core.identity.goals import (
    GOAL_ACTIVE,
    GOAL_COMPLETED,
    Goal,
    GoalStore,
)
from empneon.core.identity.models import Agent
from empneon.core.identity.personality import Personality, PersonalityStore
from empneon.core.identity.relationships import Relationship, RelationshipStore
from empneon.core.identity.serialization import IdentityStores, export_agent, import_agent
from empneon.core.identity.store import AgentStore
from empneon.core.identity.voice import VoiceProfile, VoiceProfileStore
from empneon.core.memory.documents import DocumentMemoryStore
from empneon.core.memory.episodic import (
    Belief,
    BeliefStore,
    EpisodicMemoryStore,
    Event,
    Observation,
    ObservationStore,
)
from empneon.core.memory.recall import (
    analyze_recall_query,
    fact_supports_query,
)
from empneon.core.memory.vector import VectorMemoryStore
from empneon.core.contracts import ActionResult
from empneon.core.runtime import ActionProposal
from empneon.core.state import load_agent_state
from empneon.db.connection import db_session, open_db
from empneon_thesims4.adapter import feature_hash


@dataclass(frozen=True)
class MigrationStatus:
    active_path: str
    sources: tuple[str, ...] = ()
    backups: tuple[str, ...] = ()
    completed: bool = True
    error: str | None = None

    def as_dict(self) -> dict[str, object]:
        return dataclasses.asdict(self)


def prepare_database(target: str, legacy_core: str, legacy_adapter: str) -> MigrationStatus:
    destination = Path(target).resolve()
    legacy_paths = tuple(Path(value).resolve() for value in (legacy_core, legacy_adapter))
    sources = tuple(str(path) for path in legacy_paths if path.exists() and path != destination)
    backups: list[str] = []
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        core_source = legacy_paths[0]
        if not destination.exists() and core_source.exists() and core_source != destination:
            with contextlib.closing(
                sqlite3.connect(core_source.as_uri() + "?mode=ro", uri=True)
            ) as source, contextlib.closing(sqlite3.connect(destination)) as output:
                source.backup(output)
            backup = _backup(core_source)
            backups.append(str(backup))
        with db_session(destination) as conn:
            _hide_legacy_unconfirmed_observations(conn)
        return MigrationStatus(str(destination), sources, tuple(backups))
    except Exception as exc:
        return MigrationStatus(
            str(destination), sources, tuple(backups), completed=False, error=str(exc)
        )


def open_memory(target: str) -> sqlite3.Connection:
    return open_db(target)


def _hide_legacy_unconfirmed_observations(conn: sqlite3.Connection) -> None:
    pending = (
        "SELECT o.id FROM event_observations o "
        "JOIN events e ON e.id=o.event_id "
        "WHERE e.description LIKE '%\"kind\": \"observed_interaction\"%'"
    )
    conn.execute(
        "DELETE FROM beliefs WHERE id IN "
        "(SELECT belief_id FROM belief_provenance WHERE source_observation_id IN ("
        + pending
        + "))"
    )
    conn.execute("DELETE FROM event_observations WHERE id IN (" + pending + ")")
    conn.commit()


def identity_stores(conn: sqlite3.Connection) -> IdentityStores:
    return IdentityStores(
        AgentStore(conn),
        PersonalityStore(conn),
        RelationshipStore(conn),
        EmotionalStateStore(conn),
        GoalStore(conn),
        VoiceProfileStore(conn),
    )


def sync_sim(conn: sqlite3.Connection, sim: Mapping[str, object]) -> dict[str, object]:
    profile = _sync_sim(conn, sim)
    conn.commit()
    return profile


def profile_for(conn: sqlite3.Connection, agent_id: str) -> dict[str, object] | None:
    agent = AgentStore(conn).get(str(agent_id))
    return None if agent is None else _profile(conn, agent)


def profile_by_name(conn: sqlite3.Connection, name: str) -> dict[str, object] | None:
    expected = str(name).casefold()
    agent = next(
        (item for item in AgentStore(conn).list_by_adapter("sims4") if item.name.casefold() == expected),
        None,
    )
    return None if agent is None else _profile(conn, agent)


def profiles(conn: sqlite3.Connection, limit: int = 100) -> list[dict[str, object]]:
    return [
        _profile(conn, agent)
        for agent in AgentStore(conn).list_by_adapter("sims4")[: max(0, int(limit))]
    ]


def relationship_view(
    conn: sqlite3.Connection, agent_id: str, target_id: str
) -> dict[str, int]:
    relationship = RelationshipStore(conn).get(str(agent_id), str(target_id))
    if relationship is None:
        return _default_relationship()
    values = _default_relationship()
    values["friendship"] = round(_clamp(relationship.strength, -1.0, 1.0) * 100)
    values["trust"] = round(_clamp(relationship.trust) * 100)
    return values


def relationship_diagnostic(
    conn: sqlite3.Connection, agent_id: str, target_id: str
) -> dict[str, object]:
    source_id = str(agent_id)
    target_id = str(target_id)
    relationship = RelationshipStore(conn).get(source_id, target_id)
    snapshot = load_agent_state(conn, source_id)
    observed = snapshot.relationships.get(target_id, {}) if snapshot is not None else {}
    native: dict[str, object] = {
        "friendship": round(float(observed.get("affinity", 0)) * 100),
        "romance": round(float(observed.get("romance", 0)) * 100),
    }
    attraction = observed.get("attraction")
    native_relationships = (
        snapshot.native.get("relationships", {}) if snapshot is not None else {}
    )
    target_native = (
        native_relationships.get(target_id, {})
        if isinstance(native_relationships, Mapping)
        else {}
    )
    native_attraction = (
        target_native.get("attraction", {})
        if isinstance(target_native, Mapping)
        else {}
    )
    if isinstance(attraction, (int, float)) and not isinstance(attraction, bool):
        native["attraction"] = {
            "normalized": float(attraction),
            "source": native_attraction.get("source", "unknown"),
            "value": native_attraction.get("value"),
            "label": native_attraction.get("label", "unknown"),
        }
    return {
        "direction": {"source_id": source_id, "target_id": target_id},
        "native": native,
        "empneon": {"trust": round((relationship.trust if relationship else 0.5) * 100)},
    }


def save_relationship(
    conn: sqlite3.Connection,
    agent_id: str,
    target_id: str,
    values: Mapping[str, object],
) -> dict[str, int]:
    _ensure_agent(conn, str(agent_id))
    _ensure_agent(conn, str(target_id))
    current = relationship_view(conn, str(agent_id), str(target_id))
    for name in current:
        raw = values.get(name)
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            current[name] = round(max(-100 if name == "friendship" else 0, min(100, raw)))
    relationship = RelationshipStore(conn).get(str(agent_id), str(target_id)) or Relationship(
        str(agent_id), str(target_id), "acquaintance", id=_stable_id(str(agent_id), "relationship", str(target_id))
    )
    relationship.strength = current["friendship"] / 100
    relationship.trust = current["trust"] / 100
    if current["romance"] > 0:
        relationship.relationship_type = "romantic"
    RelationshipStore(conn).set(relationship)
    return current


def apply_relationship_deltas(
    conn: sqlite3.Connection,
    agent_id: str,
    target_id: str,
    deltas: Mapping[str, object],
) -> dict[str, int]:
    current = relationship_view(conn, agent_id, target_id)
    for name in current:
        raw = deltas.get(name + "_delta")
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            current[name] += round(raw)
    saved = save_relationship(conn, agent_id, target_id, current)
    reverse = relationship_view(conn, target_id, agent_id)
    for name in ("friendship", "romance", "trust", "respect"):
        reverse[name] = max(reverse[name], saved[name])
    save_relationship(conn, target_id, agent_id, reverse)
    return saved


def emotion_view(conn: sqlite3.Connection, agent_id: str) -> dict[str, object]:
    values: dict[str, object] = {
        "happiness": 50,
        "anger": 0,
        "sadness": 0,
        "stress": 20,
        "confidence": 50,
        "current_mood": "neutral",
    }
    states = EmotionalStateStore(conn).get_all(str(agent_id))
    for state in states:
        if state.emotion in values:
            values[state.emotion] = round(_clamp(state.value) * 100)
    if states:
        values["current_mood"] = max(states, key=lambda state: state.value).emotion
    return values


def save_emotion(
    conn: sqlite3.Connection, agent_id: str, values: Mapping[str, object]
) -> dict[str, object]:
    _ensure_agent(conn, str(agent_id))
    store = EmotionalStateStore(conn)
    for name in ("happiness", "anger", "sadness", "stress", "confidence"):
        raw = values.get(name)
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            store.set(EmotionalState(str(agent_id), name, _clamp(float(raw) / 100)), commit=False)
    mood = str(values.get("current_mood") or "").strip().casefold()
    if mood and mood != "neutral":
        canonical = {"happy": "happiness", "angry": "anger", "sad": "sadness", "tense": "stress"}.get(mood, mood)
        if store.get(str(agent_id), canonical) is None:
            store.set(EmotionalState(str(agent_id), canonical, 0.75), commit=False)
    conn.commit()
    return emotion_view(conn, str(agent_id))


def voice_view(conn: sqlite3.Connection, agent_id: str) -> dict[str, object]:
    voice = VoiceProfileStore(conn).get(str(agent_id))
    if voice is None:
        return {"voice": "", "speed": 1.0, "pitch": 1.0, "provider": ""}
    return {
        "voice": voice.voice_id or "",
        "speed": voice.speed,
        "pitch": voice.pitch,
        "provider": voice.provider or "",
        "settings": voice.settings,
    }


def save_voice(
    conn: sqlite3.Connection, agent_id: str, values: Mapping[str, object]
) -> dict[str, object]:
    _ensure_agent(conn, str(agent_id))
    VoiceProfileStore(conn).set(_voice_profile(str(agent_id), values))
    return voice_view(conn, str(agent_id))


def export_identity(conn: sqlite3.Connection, agent_id: str) -> dict[str, object]:
    return export_agent(str(agent_id), identity_stores(conn))


def import_identity(conn: sqlite3.Connection, data: dict[str, object]) -> Agent:
    agent = import_agent(data, identity_stores(conn))
    conn.commit()
    return agent


def sim_diagnostics(conn: sqlite3.Connection, agent_id: str) -> dict[str, object]:
    identity = export_identity(conn, agent_id)
    observations = ObservationStore(conn).get_for_agent(agent_id)
    events = EpisodicMemoryStore(conn)
    snapshot = load_agent_state(conn, agent_id)
    return {
        **identity,
        "agent_state": dataclasses.asdict(snapshot) if snapshot is not None else None,
        "observations": [dataclasses.asdict(item) for item in observations],
        "beliefs": [
            dataclasses.asdict(item) for item in BeliefStore(conn).get_for_agent(agent_id)
        ],
        "accessible_memories": [
            dataclasses.asdict(event)
            for observation in observations
            if (event := events.get(observation.event_id)) is not None
        ],
    }


def apply_confirmed_consequences(
    conn: sqlite3.Connection, proposal: ActionProposal, result: ActionResult
) -> None:
    if result.status != "succeeded":
        return
    actor_id = proposal.decision.actor_id
    target_id = proposal.decision.target_id
    relationships = RelationshipStore(conn)
    emotions = EmotionalStateStore(conn)
    goals = GoalStore(conn)
    for change in result.applied_changes:
        parts = change.path.split(".")
        if parts[0] == "relationship":
            if not target_id:
                raise ValueError("relationship consequence requires a target Sim")
            relationship = relationships.get(actor_id, target_id) or Relationship(
                actor_id,
                target_id,
                "acquaintance",
                id=_stable_id(actor_id, "relationship", target_id),
            )
            amount = float(change.value) / 100
            if parts[1] == "friendship":
                relationship.strength = _clamp(relationship.strength + amount, -1.0, 1.0)
            elif parts[1] == "trust":
                relationship.trust = _clamp(relationship.trust + amount)
            elif parts[1] == "romance" and amount > 0:
                relationship.relationship_type = "romantic"
            relationships.set(relationship, commit=False)
        elif parts[0] == "emotion":
            current = emotions.get(actor_id, parts[1])
            value = float(change.value) / 100
            if change.operation == "increment":
                value += current.value if current else 0.0
            emotions.set(
                EmotionalState(actor_id, parts[1], _clamp(value)), commit=False
            )
        elif parts[0] == "need":
            need = parts[1].casefold()
            goal_id = _stable_id(actor_id, "need", need)
            goal = goals.get(goal_id)
            value = float(change.value)
            if value <= 25:
                goal = goal or Goal(
                    actor_id,
                    "Restore " + need,
                    priority=_clamp((25 - value) / 25, 0.6, 1.0),
                    id=goal_id,
                )
                goal.status = GOAL_ACTIVE
                goals.set(goal, commit=False)
            elif goal is not None:
                goal.status = GOAL_COMPLETED
                goals.set(goal, commit=False)
        elif parts[0] == "goal":
            goal = goals.get(parts[1])
            if goal is None or goal.agent_id != actor_id:
                raise ValueError("confirmed goal does not belong to acting Sim")
            goal.status = str(change.value)
            goals.set(goal, commit=False)


def record_observed_event(
    conn: sqlite3.Connection,
    event: Event,
    perceptions: Mapping[str, str],
    factual_statement: str | None = None,
    *,
    commit: bool = True,
) -> Event:
    for agent_id in {*event.participant_ids, *map(str, perceptions)}:
        _ensure_agent(conn, agent_id)
    if commit:
        conn.commit()
    events = EpisodicMemoryStore(conn)
    if events.get(event.id) is None:
        events.create(event, commit=commit)
    observations = ObservationStore(conn)
    existing_agents = {item.agent_id for item in observations.get_for_event(event.id)}
    for agent_id, perception in perceptions.items():
        if agent_id in existing_agents or not str(perception).strip():
            continue
        observation = Observation(
            event.id,
            str(agent_id),
            str(perception),
            id=_stable_id(str(agent_id), "observation", event.id),
        )
        observations.create(observation, commit=commit)
        if factual_statement and str(factual_statement).strip():
            belief = Belief(
                str(agent_id),
                str(factual_statement).strip(),
                "observation",
                observation.id,
                0.9,
                "Directly observed in The Sims 4",
                id=_stable_id(str(agent_id), "belief", event.id),
            )
            if BeliefStore(conn).get(belief.id) is None:
                BeliefStore(conn).create(belief, commit=commit)
    try:
        VectorMemoryStore(conn, commit=commit).upsert(
            event.id, feature_hash(event.description), commit=commit
        )
    except (ImportError, OSError, RuntimeError, sqlite3.Error):
        pass
    return event


def record_pending_event(conn: sqlite3.Connection, event: Event) -> Event:
    for agent_id in event.participant_ids:
        _ensure_agent(conn, str(agent_id))
    conn.commit()
    events = EpisodicMemoryStore(conn)
    if events.get(event.id) is None:
        events.create(event)
    return event


def add_experience(
    conn: sqlite3.Connection,
    agent_id: str,
    target_id: str,
    summary: str,
    *,
    location: str = "",
    happened_at: int | None = None,
    event_id: str | None = None,
) -> Event:
    participants = [str(agent_id)]
    if target_id and str(target_id) != str(agent_id):
        participants.append(str(target_id))
    event = Event(
        json.dumps(
            {
                "kind": "memory",
                "speaker_id": str(agent_id),
                "listener_id": str(target_id),
                "summary": str(summary),
            },
            ensure_ascii=True,
            sort_keys=True,
        ),
        participants,
        location=location or None,
        happened_at=int(happened_at or time.time()),
        id=event_id or str(uuid.uuid4()),
    )
    return record_observed_event(
        conn, event, {participant: str(summary) for participant in participants}
    )


def recent_conversations(
    conn: sqlite3.Connection,
    speaker_id: str,
    listener_id: str,
    conversation_id: str,
    limit: int = 6,
) -> list[dict[str, object]]:
    pair = {str(speaker_id), str(listener_id)}
    limit = max(0, int(limit))
    if limit == 0:
        return []
    rows = []
    for event in EpisodicMemoryStore(conn).get_for_agent(str(speaker_id)):
        data = _event_data(event.description)
        if data.get("kind") != "confirmed_interaction":
            continue
        if str(data.get("conversation_id") or "") != str(conversation_id):
            continue
        if {str(data.get("speaker_id") or ""), str(data.get("listener_id") or "")} != pair:
            continue
        rows.append(
            {
                "conversation_id": str(conversation_id),
                "speaker_id": str(data.get("speaker_id") or ""),
                "listener_id": str(data.get("listener_id") or ""),
                "message": str(data.get("message") or ""),
                "dialogue": str(data.get("dialogue") or ""),
            }
        )
        if len(rows) >= int(limit):
            break
    rows.reverse()
    return rows


def relevant_memories(
    conn: sqlite3.Connection, agent_id: str, query: str, limit: int = 6
) -> list[dict[str, object]]:
    observed = {item.event_id for item in ObservationStore(conn).get_for_agent(str(agent_id))}
    if not observed:
        return []
    event_ids: list[str] = []
    try:
        # ponytail: linear candidate window suits bounded game worlds; index observation ownership
        # in the vector query if a single Sim can accumulate an unbounded memory corpus.
        matches = VectorMemoryStore(conn).search(feature_hash(query), len(observed))
        event_ids.extend(event_id for event_id, _distance in matches if event_id in observed)
    except (ImportError, OSError, RuntimeError, sqlite3.Error):
        pass
    if len(event_ids) < limit:
        event_ids.extend(
            event.id
            for event in EpisodicMemoryStore(conn).get_for_agent(str(agent_id))
            if event.id not in event_ids
        )
    memories = []
    events = EpisodicMemoryStore(conn)
    for event_id in event_ids[:limit]:
        event = events.get(event_id)
        if event is not None:
            memories.append(
                {
                    "id": event.id,
                    "summary": _event_summary(event.description),
                    "location": event.location or "",
                    "created_at": event.happened_at,
                    "participant_ids": list(event.participant_ids),
                }
            )
    return memories


_DURABLE_FACT_CUE = re.compile(
    r"\b(?:i am|i'm|i like|i love|i hate|i prefer|i want|i need|i promise|"
    r"my\s+[a-z][a-z -]{0,30}\s+is|we met|we are|we're)\b",
    re.IGNORECASE,
)
_IDENTIFIER_ASSIGNMENT = re.compile(
    r"\b(?=[A-Z0-9-]*\d)[A-Z0-9]+(?:-[A-Z0-9]+)+\s+(?:is|are)\b"
)
_POSSESSIVE_IDENTIFIER_ASSIGNMENT = re.compile(
    r"\b(?P<possessive>my|our|your)\s+[a-z][a-z -]{0,30}\s+"
    r"(?:is|are)\s+(?=[A-Z0-9-]*\d)[A-Z0-9]+(?:-[A-Z0-9]+)+\b",
    re.IGNORECASE,
)
_CODEWORD_OWNER_QUERY = re.compile(
    r"\b(?P<owner>your|our)\s+(?:secret\s+)?code\s*word\b",
    re.IGNORECASE,
)
_ATTRIBUTED_RECALL_FACT = re.compile(
    r"^(?P<cue>you told me|i remember saying):\s*"
    r'["“](?P<statement>.+)["”]$',
    re.IGNORECASE,
)
_RECALL_STOPWORDS = frozenset(
    "about again been conversation did does first from have interaction just know "
    "last like remember said tell that the them then they this time was were what "
    "when where which who will with would your".split()
)


def _durable_fact(
    actor_id: str,
    text: str,
    *,
    allow_identifier_assignment: bool = False,
) -> dict[str, str] | None:
    statement = " ".join(str(text or "").split())
    if (
        not statement
        or statement.endswith("?")
        or not (
            _DURABLE_FACT_CUE.search(statement)
            or (
                allow_identifier_assignment
                and _IDENTIFIER_ASSIGNMENT.search(statement)
            )
        )
    ):
        return None
    return {"actor_id": str(actor_id), "statement": statement}


def _is_recall_question(text: str) -> bool:
    return analyze_recall_query(text).explicit


def codeword_recall_owner_id(
    query: str,
    responding_id: str,
    message_author_id: str,
) -> str | None:
    match = _CODEWORD_OWNER_QUERY.search(str(query or ""))
    if match is None:
        return None
    return str(
        responding_id
        if match.group("owner").casefold() == "your"
        else message_author_id
    )


def _possessive_identifier_fact(
    data: dict[str, object],
) -> dict[str, str] | None:
    statement = " ".join(str(data.get("message") or "").split())
    match = _POSSESSIVE_IDENTIFIER_ASSIGNMENT.search(statement)
    if not statement or statement.endswith("?") or match is None:
        return None
    actor_id = (
        str(data.get("speaker_id") or "")
        if match.group("possessive").casefold() == "your"
        else str(data.get("listener_id") or "")
    )
    if not actor_id:
        return None
    return {"actor_id": actor_id, "statement": statement}


def _authoritative_facts(
    data: dict[str, object],
) -> list[dict[str, object]]:
    speaker_id = str(data.get("speaker_id") or "")
    listener_id = str(data.get("listener_id") or "")
    recall_answer = _is_recall_question(str(data.get("message") or ""))
    facts = []
    for stored in data.get("facts") or []:
        if not isinstance(stored, dict):
            continue
        fact = dict(stored)
        match = _ATTRIBUTED_RECALL_FACT.match(
            str(fact.get("statement") or "")
        )
        if match and str(fact.get("actor_id") or "") == speaker_id:
            fact["actor_id"] = (
                listener_id
                if match.group("cue").casefold() == "you told me"
                else speaker_id
            )
            fact["statement"] = match.group("statement")
        if recall_answer and str(fact.get("actor_id") or "") == speaker_id:
            continue
        facts.append(fact)
    possessive_fact = None if recall_answer else _possessive_identifier_fact(data)
    if possessive_fact is not None and possessive_fact not in facts:
        facts.append(possessive_fact)
    legacy_fact = (
        None
        if recall_answer
        else _durable_fact(
            str(data.get("listener_id") or ""),
            str(data.get("message") or ""),
            allow_identifier_assignment=True,
        )
    )
    if legacy_fact is not None and legacy_fact not in facts:
        facts.append(legacy_fact)
    return facts


def _recall_terms(text: str) -> set[str]:
    terms = set()
    for token in re.findall(
        r"[a-z0-9]+(?:-[a-z0-9]+)*", str(text).casefold()
    ):
        if (len(token) < 4 and token != "met") or token in _RECALL_STOPWORDS:
            continue
        terms.add(token)
        if token == "meet":
            terms.add("met")
        if token.endswith("ed") and len(token) > 5:
            terms.update((token[:-1], token[:-2]))
    return terms


def _recall_event_rows(
    conn: sqlite3.Connection,
    actor_id: str,
    other_id: str,
    terms: set[str],
    *,
    oldest_first: bool = False,
) -> list[sqlite3.Row]:
    # ponytail: returned rows are bounded; add FTS if pair-history scan latency matters.
    base_query = (
        "SELECT id, description, happened_at FROM events"
        " WHERE json_valid(description)"
        " AND json_extract(description, '$.kind')='confirmed_interaction'"
        " AND ((json_extract(description, '$.speaker_id')=?"
        " AND json_extract(description, '$.listener_id')=?)"
        " OR (json_extract(description, '$.speaker_id')=?"
        " AND json_extract(description, '$.listener_id')=?))"
    )
    pair_args: list[object] = [actor_id, other_id, other_id, actor_id]
    direction = "ASC" if oldest_first else "DESC"
    boundary_query = (
        f"{base_query} ORDER BY happened_at {direction}, id {direction} LIMIT 100"
    )
    boundary_rows = conn.execute(boundary_query, pair_args).fetchall()
    if not terms:
        return boundary_rows

    term_values = json.dumps(sorted(terms))
    term_match = (
        "SELECT 1 FROM json_each(?) AS term"
        " WHERE instr(lower(events.description), term.value) > 0"
    )
    query = f"{base_query} AND EXISTS ({term_match})"
    args = [*pair_args, term_values]
    if not oldest_first:
        query += (
            " ORDER BY (SELECT count(*) FROM json_each(?) AS term"
            " WHERE instr(lower(events.description), term.value) > 0) DESC,"
            " happened_at DESC, id DESC"
        )
        args.append(term_values)
    else:
        query += f" ORDER BY happened_at {direction}, id {direction}"
    query += " LIMIT 100"
    targeted_rows = conn.execute(query, args).fetchall()
    seen = {row["id"] for row in targeted_rows}
    return targeted_rows + [row for row in boundary_rows if row["id"] not in seen]


def recall_candidates(
    conn: sqlite3.Connection,
    actor_id: str,
    other_id: str,
    query: str,
    max_chars: int = 6000,
) -> list[dict[str, object]]:
    terms = _recall_terms(query)
    recall_query = analyze_recall_query(query)
    owner_id = codeword_recall_owner_id(query, actor_id, other_id)
    ranked = []
    for event in _recall_event_rows(conn, str(actor_id), str(other_id), terms):
        data = _event_data(event["description"])
        facts = _authoritative_facts(data)
        if owner_id is not None:
            facts = [
                fact
                for fact in facts
                if str(fact.get("actor_id") or "") == owner_id
            ]
            if not facts:
                continue
        supporting_facts = [
            fact
            for fact in facts
            if fact_supports_query(fact, recall_query)
        ]
        searchable = " ".join(
            (
                str(data.get("message") or ""),
                str(data.get("dialogue") or ""),
                *(str(fact.get("statement") or "") for fact in facts),
            )
        )
        candidate = {
            "event_id": event["id"],
            "created_at": event["happened_at"],
            "speaker_id": str(data.get("speaker_id") or ""),
            "listener_id": str(data.get("listener_id") or ""),
            "message": str(data.get("message") or ""),
            "dialogue": str(data.get("dialogue") or ""),
            "facts": facts,
        }
        ranked.append(
            (
                bool(supporting_facts),
                bool(terms & _recall_terms(searchable)),
                bool(facts),
                event["happened_at"],
                candidate,
            )
        )
    ranked.sort(
        key=lambda item: (item[0], item[1], item[2], item[3]),
        reverse=True,
    )
    selected = []
    for _supports, _overlap, _has_facts, _created_at, candidate in ranked:
        trial = json.dumps(
            selected + [candidate], ensure_ascii=True, sort_keys=True
        )
        if len(trial) <= max(2, int(max_chars)):
            selected.append(candidate)
    return selected


def recalled_memories(
    conn: sqlite3.Connection,
    actor_id: str,
    other_id: str,
    query: str,
    limit: int = 3,
) -> list[dict[str, object]]:
    terms = _recall_terms(query)
    recall_query = analyze_recall_query(query)
    explicit = recall_query.explicit
    owner_id = codeword_recall_owner_id(query, actor_id, other_id)
    matches = []
    first_time = bool(re.search(r"\bfirst time\b", str(query), re.IGNORECASE))
    for event in _recall_event_rows(
        conn,
        str(actor_id),
        str(other_id),
        terms,
        oldest_first=first_time,
    ):
        data = _event_data(event["description"])
        facts = _authoritative_facts(data)
        if owner_id is not None:
            facts = [
                fact
                for fact in facts
                if str(fact.get("actor_id") or "") == owner_id
            ]
            if not facts:
                continue
        supporting_facts = [
            fact
            for fact in facts
            if fact_supports_query(fact, recall_query)
        ]
        answers_requested = bool(supporting_facts)
        searchable = " ".join(
            [str(data.get("message") or ""), str(data.get("dialogue") or "")]
            if explicit
            else [str(fact.get("statement") or "") for fact in facts]
        )
        overlap = terms & _recall_terms(searchable)
        if explicit and not terms:
            overlap = {"history"}
        if not overlap and not answers_requested:
            continue
        selected = dict(data)
        selected["event_id"] = event["id"]
        selected["created_at"] = event["happened_at"]
        selected["explicit"] = explicit
        selected["facts"] = [
            fact
            for fact in facts
            if fact in supporting_facts
            or terms & _recall_terms(str(fact.get("statement") or ""))
        ]
        matches.append(
            (len(overlap), event["happened_at"], selected, answers_requested)
        )
    if any(item[3] for item in matches):
        matches = [item for item in matches if item[3]]
    if first_time:
        matches.sort(key=lambda item: item[1])
    elif re.search(r"\blast time\b", str(query), re.IGNORECASE):
        matches.sort(key=lambda item: item[1], reverse=True)
    else:
        matches.sort(key=lambda item: (item[0], item[1]), reverse=True)
    recalled = []
    seen_facts = set()
    for _score, _created_at, memory, _answers_when in matches:
        unique_facts = []
        for fact in memory["facts"]:
            key = (
                str(fact.get("actor_id") or ""),
                str(fact.get("statement") or "").casefold(),
            )
            if key in seen_facts:
                continue
            seen_facts.add(key)
            unique_facts.append(fact)
        memory["facts"] = unique_facts
        if explicit or unique_facts:
            recalled.append(memory)
        if len(recalled) >= max(0, min(3, int(limit))):
            break
    return recalled


def record_delivered_experience(
    conn: sqlite3.Connection, proposal: ActionProposal, *, commit: bool = True
) -> Event | None:
    values = {change.path: change.value for change in proposal.decision.state_changes}
    source_event = EpisodicMemoryStore(conn).get(proposal.event_id)
    source = _event_data(source_event.description) if source_event is not None else {}
    message = str(source.get("message") or "").strip()
    dialogue = str(values.get("dialogue") or "").strip()
    dialogue_fact = (
        None
        if _is_recall_question(message) or proposal.decision.intent == "recall"
        else _durable_fact(proposal.decision.actor_id, dialogue)
    )
    facts = [
        fact
        for fact in (
            _durable_fact(
                proposal.decision.target_id or "",
                message,
                allow_identifier_assignment=True,
            ),
            dialogue_fact,
        )
        if fact is not None
    ]
    payload = {
        "kind": "confirmed_interaction",
        "source_event_id": proposal.event_id,
        "source": str(source.get("source") or ""),
        "source_type": str(source.get("type") or ""),
        "conversation_id": str(source.get("conversation_id") or ""),
        "speaker_id": proposal.decision.actor_id,
        "listener_id": proposal.decision.target_id or "",
        "message": message,
        "dialogue": dialogue,
        "summary": " ".join(value for value in (message, dialogue) if value),
        "facts": list(
            {
                (fact["actor_id"], fact["statement"].casefold()): fact
                for fact in facts
            }.values()
        ),
    }
    participants = [proposal.decision.actor_id]
    if proposal.decision.target_id:
        participants.append(proposal.decision.target_id)
    event = Event(
        json.dumps(payload, ensure_ascii=True, sort_keys=True),
        participants,
        location=source_event.location if source_event is not None else None,
        id=proposal.decision.id + ":confirmed",
    )
    return record_observed_event(
        conn,
        event,
        {agent_id: payload["summary"] for agent_id in participants},
        commit=commit,
    )


def import_legacy_adapter(conn: sqlite3.Connection, source_path: str) -> bool:
    marker_namespace = "thesims4.migration"
    identity_marker = "legacy-adapter-identity-v1"
    memory_marker = "legacy-adapter-episodic-v1"
    documents = DocumentMemoryStore(conn)
    if (
        documents.get(marker_namespace, identity_marker) is not None
        and documents.get(marker_namespace, memory_marker) is not None
    ):
        return False
    source_file = Path(source_path).resolve()
    if not source_file.exists():
        return False
    _backup(source_file)
    savepoint = "legacy_adapter_identity"
    conn.execute("SAVEPOINT " + savepoint)
    try:
        with contextlib.closing(
            sqlite3.connect(source_file.as_uri() + "?mode=ro", uri=True)
        ) as source:
            source.row_factory = sqlite3.Row
            _import_profiles(conn, source)
            _import_goals(conn, source)
            _import_relationships(conn, source)
            _import_emotions(conn, source)
            _import_voices(conn, source)
        conn.execute("RELEASE " + savepoint)
        conn.commit()
        with contextlib.closing(
            sqlite3.connect(source_file.as_uri() + "?mode=ro", uri=True)
        ) as source:
            source.row_factory = sqlite3.Row
            _import_episodic(conn, source)
        marker_value = json.dumps({"source": str(source_file)})
        for marker_key in (identity_marker, memory_marker):
            conn.execute(
                "INSERT OR REPLACE INTO memory_documents(namespace,key,value,updated_at)"
                " VALUES (?,?,?,?)",
                (marker_namespace, marker_key, marker_value, time.time_ns()),
            )
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise
    else:
        conn.commit()
        return True


def _sync_sim(
    conn: sqlite3.Connection, sim: Mapping[str, object]
) -> dict[str, object]:
    agent_id = str(sim.get("id") or "").strip()
    if not agent_id:
        raise ValueError("observed Sim id is required")
    stores = identity_stores(conn)
    name = str(sim.get("name") or agent_id)
    career = str(sim.get("career") or "").strip()
    occupation = None if not career or career.casefold() == "unknown" else career
    raw_age = sim.get("age")
    age = raw_age if isinstance(raw_age, int) and not isinstance(raw_age, bool) and raw_age >= 0 else None
    agent = stores.agents.get(agent_id)
    if agent is None:
        agent = Agent(
            agent_id,
            name,
            age=age,
            occupation=occupation,
            game_id=agent_id,
            adapter="sims4",
        )
        stores.agents.create(agent, commit=False)
    else:
        agent.name = name
        agent.age = age if age is not None else agent.age
        agent.occupation = occupation or agent.occupation
        agent.game_id = agent_id
        agent.adapter = "sims4"
        stores.agents.update(agent, commit=False)

    documents = DocumentMemoryStore(conn)
    stored_profile = documents.get("thesims4.actor-profile", agent_id) or {}
    if "traits" in sim:
        traits = [
            str(value) for value in sim.get("traits", []) if str(value).strip()
        ]
        documents.set(
            "thesims4.actor-profile",
            agent_id,
            {"traits": traits},
            commit=False,
        )
    else:
        traits = [str(value) for value in stored_profile.get("traits", [])]
    if "traits" in sim or stores.personality.get(agent_id) is None:
        stores.personality.set(_personality(agent_id, traits), commit=False)
    _sync_goals(stores.goals, agent_id, sim)
    _sync_emotion(stores.emotions, agent_id, sim)
    voice = sim.get("voice")
    if isinstance(voice, Mapping):
        stores.voice.set(_voice_profile(agent_id, voice), commit=False)
    return _profile(conn, agent, traits)


def _personality(agent_id: str, traits: list[str]) -> Personality:
    values = {
        "openness": 0.5,
        "conscientiousness": 0.5,
        "extraversion": 0.5,
        "agreeableness": 0.5,
        "neuroticism": 0.5,
    }
    adjustments = {
        "creative": {"openness": 0.25},
        "genius": {"openness": 0.2, "conscientiousness": 0.15},
        "ambitious": {"conscientiousness": 0.3},
        "lazy": {"conscientiousness": -0.25},
        "outgoing": {"extraversion": 0.3},
        "loner": {"extraversion": -0.3},
        "good": {"agreeableness": 0.25},
        "evil": {"agreeableness": -0.25},
        "hot-headed": {"neuroticism": 0.3},
        "cheerful": {"neuroticism": -0.2},
    }
    text = " ".join(traits).casefold()
    for trait, changes in adjustments.items():
        if trait in text:
            for name, delta in changes.items():
                values[name] = _clamp(values[name] + delta)
    return Personality(agent_id, **values)


def _sync_goals(store: GoalStore, agent_id: str, sim: Mapping[str, object]) -> None:
    aspiration = str(sim.get("aspiration") or "").strip()
    if aspiration and aspiration.casefold() != "unknown":
        goal_id = _stable_id(agent_id, "aspiration", aspiration)
        for goal in store.get_all(agent_id, GOAL_ACTIVE):
            if goal.description.startswith("Aspiration: ") and goal.id != goal_id:
                goal.status = GOAL_COMPLETED
                goal.updated_at = int(time.time())
                store.set(goal, commit=False)
        existing = store.get(goal_id)
        store.set(
            existing
            or Goal(
                agent_id,
                "Aspiration: " + aspiration,
                priority=0.8,
                id=goal_id,
            ),
            commit=False,
        )
    needs = sim.get("needs")
    if isinstance(needs, Mapping):
        allowed = {"bladder", "energy", "fun", "hunger", "hygiene", "social"}
        current_ids: set[str] = set()
        for name, raw in needs.items():
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                continue
            need = str(name).strip().casefold()
            if need.startswith("motive_"):
                need = need[7:]
            if need not in allowed:
                continue
            goal_id = _stable_id(agent_id, "need", need)
            current_ids.add(goal_id)
            existing = store.get(goal_id)
            if float(raw) <= 25:
                goal = existing or Goal(
                    agent_id,
                    "Restore " + need,
                    priority=_clamp((25 - float(raw)) / 25, 0.6, 1.0),
                    id=goal_id,
                )
                if existing is not None and goal.status != GOAL_ACTIVE:
                    goal.updated_at = int(time.time())
                goal.status = GOAL_ACTIVE
                store.set(goal, commit=False)
            elif existing is not None and existing.status == GOAL_ACTIVE:
                existing.status = GOAL_COMPLETED
                existing.updated_at = int(time.time())
                store.set(existing, commit=False)
        for goal in store.get_all(agent_id, GOAL_ACTIVE):
            if goal.description.startswith("Restore ") and goal.id not in current_ids:
                goal.status = GOAL_COMPLETED
                goal.updated_at = int(time.time())
                store.set(goal, commit=False)


def _sync_emotion(
    store: EmotionalStateStore, agent_id: str, sim: Mapping[str, object]
) -> None:
    store._conn.execute(
        "DELETE FROM emotional_states WHERE agent_id=? AND emotion LIKE '<class %mood_%'",
        (agent_id,),
    )
    mood = str(sim.get("current_mood") or "").strip().casefold()
    if not mood or mood == "unknown":
        return
    emotion = {
        "happy": "happiness",
        "angry": "anger",
        "sad": "sadness",
        "tense": "stress",
        "stressed": "stress",
        "confident": "confidence",
    }.get(mood, mood)
    store.set(EmotionalState(agent_id, emotion, 0.75), commit=False)


def _voice_profile(agent_id: str, voice: Mapping[str, object]) -> VoiceProfile:
    return VoiceProfile(
        agent_id,
        provider=str(voice.get("provider") or "") or None,
        voice_id=str(voice.get("voice_id") or voice.get("voice") or "") or None,
        speed=float(voice.get("speed") or 1.0),
        pitch=float(voice.get("pitch") or 1.0),
        settings=dict(voice.get("settings") or {}),
    )


def _profile(
    conn: sqlite3.Connection, agent: Agent, traits: list[str] | None = None
) -> dict[str, object]:
    stores = identity_stores(conn)
    if traits is None:
        stored = DocumentMemoryStore(conn).get("thesims4.actor-profile", agent.id) or {}
        traits = [str(value) for value in stored.get("traits", [])]
    personality = stores.personality.get(agent.id)
    voice = stores.voice.get(agent.id)
    return {
        "id": agent.id,
        "name": agent.name,
        "identity": {"traits": traits, "career": agent.occupation or "unknown"},
        "personality": dataclasses.asdict(personality) if personality else {},
        "values": [],
        "behavioral_rules": [],
        "knowledge": {},
        "goals": [goal.description for goal in stores.goals.get_all(agent.id, GOAL_ACTIVE)],
        "voice": dataclasses.asdict(voice) if voice else {},
    }


def _import_profiles(conn: sqlite3.Connection, source: sqlite3.Connection) -> None:
    for row in _rows(source, "sim_profiles"):
        identity = _json(row, "identity_json", {})
        voice = _json(row, "voice_json", {})
        sim = {
            "id": row["sim_id"],
            "name": row["name"],
            "traits": identity.get("traits", []) if isinstance(identity, dict) else [],
            "career": identity.get("career", "unknown") if isinstance(identity, dict) else "unknown",
            "voice": voice,
        }
        _sync_sim(conn, sim)


def _import_goals(conn: sqlite3.Connection, source: sqlite3.Connection) -> None:
    store = GoalStore(conn)
    for row in _rows(source, "goals"):
        description = str(row["goal"] or "").strip()
        if not description:
            continue
        agent_id = str(row["sim_id"])
        _ensure_agent(conn, agent_id)
        status = str(row["status"] or GOAL_ACTIVE)
        if status not in (GOAL_ACTIVE, GOAL_COMPLETED, "abandoned"):
            status = GOAL_ACTIVE
        store.set(
            Goal(
                agent_id,
                description,
                priority=_clamp(float(row["importance"] or 0.5)),
                status=status,
                id=_stable_id(agent_id, "legacy-goal", description),
            ),
            commit=False,
        )


def _import_relationships(conn: sqlite3.Connection, source: sqlite3.Connection) -> None:
    store = RelationshipStore(conn)
    for row in _rows(source, "relationships"):
        agent_id, target_id = str(row["sim_id"]), str(row["target_id"])
        _ensure_agent(conn, agent_id)
        _ensure_agent(conn, target_id)
        store.set(
            Relationship(
                agent_id,
                target_id,
                "legacy",
                strength=_clamp(float(row["friendship"] or 0) / 100, -1.0, 1.0),
                trust=_clamp(float(row["trust"] or 50) / 100),
                id=_stable_id(agent_id, "relationship", target_id),
            ),
            commit=False,
        )


def _import_emotions(conn: sqlite3.Connection, source: sqlite3.Connection) -> None:
    store = EmotionalStateStore(conn)
    for row in _rows(source, "emotions"):
        agent_id = str(row["sim_id"])
        _ensure_agent(conn, agent_id)
        for legacy, canonical in (
            ("happiness", "happiness"),
            ("anger", "anger"),
            ("sadness", "sadness"),
            ("stress", "stress"),
            ("confidence", "confidence"),
        ):
            store.set(
                EmotionalState(agent_id, canonical, _clamp(float(row[legacy] or 0) / 100)),
                commit=False,
            )


def _import_voices(conn: sqlite3.Connection, source: sqlite3.Connection) -> None:
    store = VoiceProfileStore(conn)
    for row in _rows(source, "voice_settings"):
        agent_id = str(row["sim_id"])
        _ensure_agent(conn, agent_id)
        store.set(
            VoiceProfile(
                agent_id,
                provider=str(row["provider"] or "") or None,
                voice_id=str(row["voice"] or "") or None,
                speed=float(row["speed"] or 1.0),
                pitch=float(row["pitch"] or 1.0),
            ),
            commit=False,
        )


def _import_episodic(conn: sqlite3.Connection, source: sqlite3.Connection) -> None:
    for row in _rows(source, "memories"):
        agent_id = str(row["sim_id"] or row["speaker_id"] or "").strip()
        target_id = str(row["target_id"] or row["listener_id"] or "").strip()
        summary = str(row["summary"] or row["event"] or "").strip()
        if agent_id and summary:
            add_experience(
                conn,
                agent_id,
                target_id,
                summary,
                location=str(row["location"] or ""),
                happened_at=int(row["created_at"] or 0),
                event_id=_stable_id(agent_id, "legacy-memory", str(row["id"])),
            )
    for row in _rows(source, "memory_summaries"):
        agent_id = str(row["sim_id"] or "").strip()
        summary = str(row["summary"] or "").strip()
        if agent_id and summary:
            add_experience(
                conn,
                agent_id,
                str(row["target_id"] or ""),
                summary,
                happened_at=int(row["updated_at"] or 0),
                event_id=_stable_id(agent_id, "legacy-summary", str(row["target_id"])),
            )
    for row in _rows(source, "conversations"):
        agent_id = str(row["speaker_id"] or "").strip()
        target_id = str(row["listener_id"] or "").strip()
        response = _json(row, "response_json", {})
        dialogue = str(response.get("dialogue") or "") if isinstance(response, dict) else ""
        summary = "{} {}".format(str(row["message"] or ""), dialogue).strip()
        if agent_id and summary:
            add_experience(
                conn,
                agent_id,
                target_id,
                summary,
                happened_at=int(row["created_at"] or 0),
                event_id=_stable_id(agent_id, "legacy-conversation", str(row["id"])),
            )


def _ensure_agent(conn: sqlite3.Connection, agent_id: str) -> None:
    store = AgentStore(conn)
    if store.get(agent_id) is None:
        store.create(Agent(agent_id, agent_id, game_id=agent_id, adapter="sims4"), commit=False)


def _default_relationship() -> dict[str, int]:
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


_LEGACY_TABLES = frozenset(
    {
        "sim_profiles",
        "goals",
        "relationships",
        "emotions",
        "voice_settings",
        "memories",
        "memory_summaries",
        "conversations",
    }
)


def _rows(source: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    if table not in _LEGACY_TABLES:
        raise ValueError(f"unknown legacy table: {table!r}")
    exists = source.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return [] if exists is None else source.execute("SELECT * FROM " + table).fetchall()


def _json(row: sqlite3.Row, name: str, default: object) -> object:
    try:
        return json.loads(row[name] or "")
    except (KeyError, TypeError, json.JSONDecodeError):
        return default


def _stable_id(agent_id: str, kind: str, value: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"empneon:sims4:{agent_id}:{kind}:{value}"))


def _event_summary(description: str) -> str:
    value = _event_data(description)
    if not value:
        return description
    return str(value.get("summary") or value.get("message") or value.get("dialogue") or description)


def _event_data(description: str) -> dict[str, object]:
    try:
        value = json.loads(description)
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _backup(source: Path) -> Path:
    backup = source.with_suffix(source.suffix + ".pre-core-memory.bak")
    if not backup.exists():
        shutil.copy2(source, backup)
    return backup
