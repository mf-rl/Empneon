import pytest

from empneon.core.identity.models import Agent
from empneon.core.identity.store import AgentStore
from empneon.core.memory.episodic import EpisodicMemoryStore, Event
from empneon.db.connection import open_db


@pytest.fixture()
def stores() -> tuple[AgentStore, EpisodicMemoryStore]:
    conn = open_db(":memory:")
    return AgentStore(conn), EpisodicMemoryStore(conn)


def _agents(stores: tuple[AgentStore, EpisodicMemoryStore]) -> tuple[Agent, Agent]:
    a = Agent.new("Alice")
    b = Agent.new("Bob")
    stores[0].create(a)
    stores[0].create(b)
    return a, b


def test_create_and_get(stores: tuple[AgentStore, EpisodicMemoryStore]) -> None:
    a, b = _agents(stores)
    event = Event(
        description="Alice and Bob met at the market",
        participant_ids=[a.id, b.id],
        location="Market Square",
        happened_at=1000,
    )
    stores[1].create(event)
    fetched = stores[1].get(event.id)
    assert fetched is not None
    assert fetched.description == "Alice and Bob met at the market"
    assert fetched.location == "Market Square"
    assert fetched.happened_at == 1000
    assert set(fetched.participant_ids) == {a.id, b.id}


def test_get_missing_returns_none(stores: tuple[AgentStore, EpisodicMemoryStore]) -> None:
    assert stores[1].get("nonexistent") is None


def test_get_for_agent_returns_events(stores: tuple[AgentStore, EpisodicMemoryStore]) -> None:
    a, b = _agents(stores)
    stores[1].create(Event("Event A", [a.id, b.id], happened_at=100))
    stores[1].create(Event("Event B", [a.id], happened_at=200))
    stores[1].create(Event("Event C", [b.id], happened_at=300))
    result = stores[1].get_for_agent(a.id)
    assert len(result) == 2
    assert {e.description for e in result} == {"Event A", "Event B"}


def test_get_for_agent_ordered_newest_first(stores: tuple[AgentStore, EpisodicMemoryStore]) -> None:
    a, _ = _agents(stores)
    stores[1].create(Event("Old", [a.id], happened_at=100))
    stores[1].create(Event("New", [a.id], happened_at=900))
    stores[1].create(Event("Mid", [a.id], happened_at=500))
    result = stores[1].get_for_agent(a.id)
    assert result[0].description == "New"
    assert result[-1].description == "Old"


def test_get_for_agent_with_limit(stores: tuple[AgentStore, EpisodicMemoryStore]) -> None:
    a, _ = _agents(stores)
    for i in range(5):
        stores[1].create(Event(f"Event {i}", [a.id], happened_at=i * 100))
    result = stores[1].get_for_agent(a.id, limit=2)
    assert len(result) == 2


def test_get_for_agent_empty(stores: tuple[AgentStore, EpisodicMemoryStore]) -> None:
    a, _ = _agents(stores)
    assert stores[1].get_for_agent(a.id) == []


def test_delete_event(stores: tuple[AgentStore, EpisodicMemoryStore]) -> None:
    a, _ = _agents(stores)
    event = Event("Gone", [a.id], happened_at=1)
    stores[1].create(event)
    stores[1].delete(event.id)
    assert stores[1].get(event.id) is None
    assert stores[1].get_for_agent(a.id) == []


def test_delete_event_removes_participants(stores: tuple[AgentStore, EpisodicMemoryStore]) -> None:
    a, b = _agents(stores)
    event = Event("Together", [a.id, b.id], happened_at=1)
    stores[1].create(event)
    stores[1].delete(event.id)
    assert stores[1].get_for_agent(a.id) == []
    assert stores[1].get_for_agent(b.id) == []


def test_cascade_delete_agent_removes_participation(
    stores: tuple[AgentStore, EpisodicMemoryStore],
) -> None:
    a, b = _agents(stores)
    event = Event("Together", [a.id, b.id], happened_at=1)
    stores[1].create(event)
    stores[0].delete(a.id)
    # Event still exists; Alice no longer listed as participant
    fetched = stores[1].get(event.id)
    assert fetched is not None
    assert a.id not in fetched.participant_ids
    assert b.id in fetched.participant_ids


def test_null_location(stores: tuple[AgentStore, EpisodicMemoryStore]) -> None:
    a, _ = _agents(stores)
    event = Event("Solo thought", [a.id], happened_at=1)
    stores[1].create(event)
    fetched = stores[1].get(event.id)
    assert fetched is not None
    assert fetched.location is None
