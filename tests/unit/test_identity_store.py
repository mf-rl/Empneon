import pytest

from empneon.core.identity.models import Agent
from empneon.core.identity.store import AgentStore
from empneon.db.connection import open_db


@pytest.fixture()
def store() -> AgentStore:
    return AgentStore(open_db(":memory:"))


def test_create_and_get(store: AgentStore) -> None:
    agent = Agent.new("Alice", occupation="Doctor")
    store.create(agent)
    fetched = store.get(agent.id)
    assert fetched is not None
    assert fetched.name == "Alice"
    assert fetched.occupation == "Doctor"


def test_get_missing_returns_none(store: AgentStore) -> None:
    assert store.get("does-not-exist") is None


def test_update(store: AgentStore) -> None:
    agent = Agent.new("Bob")
    store.create(agent)
    agent.name = "Robert"
    store.update(agent)
    fetched = store.get(agent.id)
    assert fetched is not None
    assert fetched.name == "Robert"


def test_delete(store: AgentStore) -> None:
    agent = Agent.new("Carol")
    store.create(agent)
    store.delete(agent.id)
    assert store.get(agent.id) is None


def test_list_all(store: AgentStore) -> None:
    store.create(Agent.new("Alice"))
    store.create(Agent.new("Bob"))
    agents = store.list_all()
    assert len(agents) == 2
    assert {a.name for a in agents} == {"Alice", "Bob"}


def test_list_by_adapter(store: AgentStore) -> None:
    store.create(Agent.new("Alice", adapter="sims4"))
    store.create(Agent.new("Bob", adapter="inzoi"))
    result = store.list_by_adapter("sims4")
    assert len(result) == 1
    assert result[0].name == "Alice"


def test_new_agents_have_unique_ids(store: AgentStore) -> None:
    a1 = Agent.new("Alice")
    a2 = Agent.new("Alice")
    assert a1.id != a2.id


def test_update_bumps_updated_at(store: AgentStore) -> None:
    agent = Agent.new("Dave")
    store.create(agent)
    original_ts = agent.updated_at
    agent.name = "David"
    store.update(agent)
    assert agent.updated_at >= original_ts
