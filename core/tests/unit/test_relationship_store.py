import pytest

from empneon.core.identity.models import Agent
from empneon.core.identity.relationships import Relationship, RelationshipStore
from empneon.core.identity.store import AgentStore
from empneon.db.connection import open_db


@pytest.fixture()
def stores() -> tuple[AgentStore, RelationshipStore]:
    conn = open_db(":memory:")
    return AgentStore(conn), RelationshipStore(conn)


def _make_agents(stores: tuple[AgentStore, RelationshipStore]) -> tuple[Agent, Agent]:
    a = Agent.new("Alice")
    b = Agent.new("Bob")
    stores[0].create(a)
    stores[0].create(b)
    return a, b


def test_set_and_get(stores: tuple[AgentStore, RelationshipStore]) -> None:
    a, b = _make_agents(stores)
    rel = Relationship(a.id, b.id, "friend", strength=0.8, trust=0.9)
    stores[1].set(rel)
    fetched = stores[1].get(a.id, b.id)
    assert fetched is not None
    assert fetched.relationship_type == "friend"
    assert fetched.strength == pytest.approx(0.8)
    assert fetched.trust == pytest.approx(0.9)


def test_get_missing_returns_none(stores: tuple[AgentStore, RelationshipStore]) -> None:
    a, b = _make_agents(stores)
    assert stores[1].get(a.id, b.id) is None


def test_directed_edges_are_independent(
    stores: tuple[AgentStore, RelationshipStore],
) -> None:
    a, b = _make_agents(stores)
    stores[1].set(Relationship(a.id, b.id, "friend", strength=0.8))
    stores[1].set(Relationship(b.id, a.id, "rival", strength=-0.3))
    ab = stores[1].get(a.id, b.id)
    ba = stores[1].get(b.id, a.id)
    assert ab is not None and ab.relationship_type == "friend"
    assert ba is not None and ba.relationship_type == "rival"


def test_upsert_updates_existing(stores: tuple[AgentStore, RelationshipStore]) -> None:
    a, b = _make_agents(stores)
    stores[1].set(Relationship(a.id, b.id, "acquaintance", strength=0.2))
    stores[1].set(Relationship(a.id, b.id, "friend", strength=0.8))
    fetched = stores[1].get(a.id, b.id)
    assert fetched is not None
    assert fetched.relationship_type == "friend"
    assert fetched.strength == pytest.approx(0.8)


def test_get_all_returns_outgoing_edges(
    stores: tuple[AgentStore, RelationshipStore],
) -> None:
    a, b = _make_agents(stores)
    c = Agent.new("Carol")
    stores[0].create(c)
    stores[1].set(Relationship(a.id, b.id, "friend"))
    stores[1].set(Relationship(a.id, c.id, "colleague"))
    stores[1].set(Relationship(b.id, a.id, "rival"))  # should NOT appear
    result = stores[1].get_all(a.id)
    assert len(result) == 2
    targets = {r.target_agent_id for r in result}
    assert targets == {b.id, c.id}


def test_delete_edge(stores: tuple[AgentStore, RelationshipStore]) -> None:
    a, b = _make_agents(stores)
    stores[1].set(Relationship(a.id, b.id, "friend"))
    stores[1].delete(a.id, b.id)
    assert stores[1].get(a.id, b.id) is None


def test_cascade_delete_agent(stores: tuple[AgentStore, RelationshipStore]) -> None:
    a, b = _make_agents(stores)
    stores[1].set(Relationship(a.id, b.id, "friend"))
    stores[0].delete(a.id)
    assert stores[1].get(a.id, b.id) is None
