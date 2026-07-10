import pytest

from empneon.core.identity.models import Agent
from empneon.core.identity.personality import Personality, PersonalityStore
from empneon.core.identity.store import AgentStore
from empneon.db.connection import open_db


@pytest.fixture()
def stores() -> tuple[AgentStore, PersonalityStore]:
    conn = open_db(":memory:")
    return AgentStore(conn), PersonalityStore(conn)


def _agent(stores: tuple[AgentStore, PersonalityStore]) -> Agent:
    agent = Agent.new("Alice")
    stores[0].create(agent)
    return agent


def test_set_and_get(stores: tuple[AgentStore, PersonalityStore]) -> None:
    agent = _agent(stores)
    p = Personality(agent_id=agent.id, openness=0.9, neuroticism=0.2)
    stores[1].set(p)
    fetched = stores[1].get(agent.id)
    assert fetched is not None
    assert fetched.openness == pytest.approx(0.9)
    assert fetched.neuroticism == pytest.approx(0.2)
    assert fetched.conscientiousness == pytest.approx(0.5)  # default


def test_get_missing_returns_none(stores: tuple[AgentStore, PersonalityStore]) -> None:
    assert stores[1].get("no-such-agent") is None


def test_upsert_updates_existing(stores: tuple[AgentStore, PersonalityStore]) -> None:
    agent = _agent(stores)
    stores[1].set(Personality(agent_id=agent.id, openness=0.3))
    stores[1].set(Personality(agent_id=agent.id, openness=0.8))
    fetched = stores[1].get(agent.id)
    assert fetched is not None
    assert fetched.openness == pytest.approx(0.8)


def test_defaults_are_0_5(stores: tuple[AgentStore, PersonalityStore]) -> None:
    agent = _agent(stores)
    stores[1].set(Personality(agent_id=agent.id))
    fetched = stores[1].get(agent.id)
    assert fetched is not None
    for value in (
        fetched.openness,
        fetched.conscientiousness,
        fetched.extraversion,
        fetched.agreeableness,
        fetched.neuroticism,
    ):
        assert value == pytest.approx(0.5)


def test_cascade_delete(stores: tuple[AgentStore, PersonalityStore]) -> None:
    agent = _agent(stores)
    stores[1].set(Personality(agent_id=agent.id))
    stores[0].delete(agent.id)
    assert stores[1].get(agent.id) is None
