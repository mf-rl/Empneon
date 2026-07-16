"""Integration test: identity survives game restart, process restart, and model change.

Uses a real SQLite file (not :memory:) to prove data actually persists on disk.
"""

import pytest

from empneon.core.identity.emotions import EmotionalState, EmotionalStateStore
from empneon.core.identity.goals import Goal, GoalStore
from empneon.core.identity.models import Agent
from empneon.core.identity.personality import Personality, PersonalityStore
from empneon.core.identity.relationships import Relationship, RelationshipStore
from empneon.core.identity.serialization import IdentityStores, export_agent, import_agent
from empneon.core.identity.store import AgentStore
from empneon.core.identity.voice import VoiceProfile, VoiceProfileStore
from empneon.db.connection import open_db


def _make_stores(path: str) -> IdentityStores:
    conn = open_db(path)
    return IdentityStores(
        agents=AgentStore(conn),
        personality=PersonalityStore(conn),
        relationships=RelationshipStore(conn),
        emotions=EmotionalStateStore(conn),
        goals=GoalStore(conn),
        voice=VoiceProfileStore(conn),
    )


def test_identity_survives_connection_close_and_reopen(tmp_path: pytest.TempPathFactory) -> None:
    """Simulates game restart: close DB connection, reopen same file, data intact."""
    db_file = str(tmp_path / "empneon.db")

    # Session 1 — write
    s1 = _make_stores(db_file)
    alice = Agent.new("Alice", age=30, occupation="Chef")
    bob = Agent.new("Bob")
    s1.agents.create(alice)
    s1.agents.create(bob)
    s1.personality.set(Personality(alice.id, openness=0.9, neuroticism=0.2))
    s1.relationships.set(Relationship(alice.id, bob.id, "friend", strength=0.8, trust=0.9))
    s1.emotions.set(EmotionalState(alice.id, "joy", value=0.7, velocity=0.01))
    s1.goals.create(Goal(agent_id=alice.id, description="Open a restaurant", priority=0.9))
    s1.voice.set(VoiceProfile(alice.id, provider="xtts", voice_id="alice_01"))
    s1.agents._conn.close()

    # Session 2 — reopen same file, verify all data intact
    s2 = _make_stores(db_file)

    agent = s2.agents.get(alice.id)
    assert agent is not None
    assert agent.name == "Alice"
    assert agent.age == 30
    assert agent.occupation == "Chef"

    p = s2.personality.get(alice.id)
    assert p is not None
    assert p.openness == pytest.approx(0.9)
    assert p.neuroticism == pytest.approx(0.2)

    rels = s2.relationships.get_all(alice.id)
    assert len(rels) == 1
    assert rels[0].trust == pytest.approx(0.9)

    emos = s2.emotions.get_all(alice.id)
    assert len(emos) == 1
    assert emos[0].value == pytest.approx(0.7)

    goals = s2.goals.get_all(alice.id)
    assert len(goals) == 1
    assert goals[0].description == "Open a restaurant"

    v = s2.voice.get(alice.id)
    assert v is not None
    assert v.provider == "xtts"


def test_identity_survives_export_import_across_databases(tmp_path: pytest.TempPathFactory) -> None:
    """Simulates model change: export identity, import into fresh DB, data intact."""
    db1 = str(tmp_path / "original.db")
    db2 = str(tmp_path / "new_model.db")

    # Original DB — one LLM model in use
    s1 = _make_stores(db1)
    alice = Agent.new("Alice", age=30, adapter="lm_studio")
    bob = Agent.new("Bob", adapter="lm_studio")
    s1.agents.create(alice)
    s1.agents.create(bob)
    s1.personality.set(Personality(alice.id, conscientiousness=0.8))
    s1.goals.create(Goal(agent_id=alice.id, description="Learn piano", priority=0.7))
    s1.voice.set(VoiceProfile(alice.id, provider="kokoro", settings={"lang": "en"}))

    snapshot = export_agent(alice.id, s1)

    # New DB — different model/adapter, import same identity
    s2 = _make_stores(db2)
    s2.agents.create(bob)  # Bob needed for FK if relationships exist

    imported = import_agent(snapshot, s2)

    assert imported.id == alice.id
    assert imported.name == "Alice"

    p = s2.personality.get(alice.id)
    assert p is not None
    assert p.conscientiousness == pytest.approx(0.8)

    goals = s2.goals.get_all(alice.id)
    assert len(goals) == 1
    assert goals[0].description == "Learn piano"

    v = s2.voice.get(alice.id)
    assert v is not None
    assert v.provider == "kokoro"
    assert v.settings == {"lang": "en"}


def test_identity_has_no_model_specific_fields() -> None:
    """Model independence: Agent schema contains no LLM model reference fields."""
    agent = Agent.new("Test")
    agent_fields = {f.name for f in agent.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    model_fields = {"model", "model_id", "llm", "llm_provider", "engine"}
    assert agent_fields.isdisjoint(model_fields), (
        f"Agent has model-specific fields: {agent_fields & model_fields}"
    )
