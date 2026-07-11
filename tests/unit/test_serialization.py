import json
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


@pytest.fixture()
def stores() -> IdentityStores:
    conn = open_db(":memory:")
    return IdentityStores(
        agents=AgentStore(conn),
        personality=PersonalityStore(conn),
        relationships=RelationshipStore(conn),
        emotions=EmotionalStateStore(conn),
        goals=GoalStore(conn),
        voice=VoiceProfileStore(conn),
    )


def _populate(stores: IdentityStores) -> Agent:
    a = Agent.new("Alice", age=30, occupation="Chef")
    b = Agent.new("Bob")
    stores.agents.create(a)
    stores.agents.create(b)

    stores.personality.set(Personality(a.id, openness=0.9, neuroticism=0.2))
    stores.relationships.set(Relationship(a.id, b.id, "friend", strength=0.8, trust=0.9))
    stores.emotions.set(EmotionalState(a.id, "joy", value=0.7, velocity=0.01))
    stores.goals.create(Goal(agent_id=a.id, description="Open a restaurant", priority=0.9))
    stores.voice.set(VoiceProfile(a.id, provider="xtts", voice_id="alice_01", speed=1.1,
                                  settings={"language": "en"}))
    return a


def test_export_contains_all_layers(stores: IdentityStores) -> None:
    a = _populate(stores)
    data = export_agent(a.id, stores)
    assert data["version"] == 1
    assert data["agent"]["id"] == a.id
    assert data["personality"]["openness"] == pytest.approx(0.9)
    assert len(data["relationships"]) == 1
    assert len(data["emotions"]) == 1
    assert len(data["goals"]) == 1
    assert data["voice_profile"]["provider"] == "xtts"


def test_export_is_json_serializable(stores: IdentityStores) -> None:
    a = _populate(stores)
    data = export_agent(a.id, stores)
    dumped = json.dumps(data)
    assert isinstance(dumped, str)


def test_export_missing_agent_raises(stores: IdentityStores) -> None:
    with pytest.raises(ValueError, match="not found"):
        export_agent("nonexistent", stores)


def test_export_optional_layers_are_none_when_absent(stores: IdentityStores) -> None:
    a = Agent.new("Sparse")
    stores.agents.create(a)
    data = export_agent(a.id, stores)
    assert data["personality"] is None
    assert data["voice_profile"] is None
    assert data["relationships"] == []
    assert data["emotions"] == []
    assert data["goals"] == []


def test_roundtrip_full_identity(stores: IdentityStores) -> None:
    a = _populate(stores)
    snapshot = export_agent(a.id, stores)

    # Import into a fresh DB
    conn2 = open_db(":memory:")
    # Bob must exist in target DB for FK on relationships
    b_data = stores.agents.get_all() if hasattr(stores.agents, "get_all") else None
    stores2 = IdentityStores(
        agents=AgentStore(conn2),
        personality=PersonalityStore(conn2),
        relationships=RelationshipStore(conn2),
        emotions=EmotionalStateStore(conn2),
        goals=GoalStore(conn2),
        voice=VoiceProfileStore(conn2),
    )
    # Pre-create Bob so FK on relationships resolves
    bob = stores.agents.list_all()[1]
    stores2.agents.create(bob)

    imported = import_agent(snapshot, stores2)

    assert imported.id == a.id
    assert imported.name == "Alice"

    p = stores2.personality.get(a.id)
    assert p is not None
    assert p.openness == pytest.approx(0.9)

    rels = stores2.relationships.get_all(a.id)
    assert len(rels) == 1
    assert rels[0].trust == pytest.approx(0.9)

    emos = stores2.emotions.get_all(a.id)
    assert len(emos) == 1
    assert emos[0].value == pytest.approx(0.7)

    goals = stores2.goals.get_all(a.id)
    assert len(goals) == 1
    assert goals[0].description == "Open a restaurant"

    v = stores2.voice.get(a.id)
    assert v is not None
    assert v.provider == "xtts"
    assert v.settings == {"language": "en"}


def test_reimport_is_idempotent(stores: IdentityStores) -> None:
    a = _populate(stores)
    snapshot = export_agent(a.id, stores)
    import_agent(snapshot, stores)  # second import into same DB — must not raise
    assert stores.agents.get(a.id) is not None
    assert len(stores.goals.get_all(a.id)) == 1  # no duplicates
