import pytest

from empneon.core.identity.emotions import EmotionalState, EmotionalStateStore
from empneon.core.identity.models import Agent
from empneon.core.identity.store import AgentStore
from empneon.db.connection import open_db


@pytest.fixture()
def stores() -> tuple[AgentStore, EmotionalStateStore]:
    conn = open_db(":memory:")
    return AgentStore(conn), EmotionalStateStore(conn)


def _agent(stores: tuple[AgentStore, EmotionalStateStore]) -> Agent:
    a = Agent.new("Alice")
    stores[0].create(a)
    return a


def test_set_and_get(stores: tuple[AgentStore, EmotionalStateStore]) -> None:
    a = _agent(stores)
    state = EmotionalState(a.id, "sadness", value=0.7, velocity=-0.02, acceleration=0.001)
    stores[1].set(state)
    fetched = stores[1].get(a.id, "sadness")
    assert fetched is not None
    assert fetched.value == pytest.approx(0.7)
    assert fetched.velocity == pytest.approx(-0.02)
    assert fetched.acceleration == pytest.approx(0.001)


def test_get_missing_returns_none(stores: tuple[AgentStore, EmotionalStateStore]) -> None:
    a = _agent(stores)
    assert stores[1].get(a.id, "joy") is None


def test_upsert_updates_existing(stores: tuple[AgentStore, EmotionalStateStore]) -> None:
    a = _agent(stores)
    stores[1].set(EmotionalState(a.id, "anger", value=0.3))
    stores[1].set(EmotionalState(a.id, "anger", value=0.9, velocity=0.05))
    fetched = stores[1].get(a.id, "anger")
    assert fetched is not None
    assert fetched.value == pytest.approx(0.9)
    assert fetched.velocity == pytest.approx(0.05)


def test_get_all_returns_all_emotions(stores: tuple[AgentStore, EmotionalStateStore]) -> None:
    a = _agent(stores)
    stores[1].set(EmotionalState(a.id, "joy", value=0.8))
    stores[1].set(EmotionalState(a.id, "fear", value=0.4))
    stores[1].set(EmotionalState(a.id, "disgust", value=0.1))
    result = stores[1].get_all(a.id)
    assert len(result) == 3
    assert {s.emotion for s in result} == {"joy", "fear", "disgust"}


def test_get_all_empty(stores: tuple[AgentStore, EmotionalStateStore]) -> None:
    a = _agent(stores)
    assert stores[1].get_all(a.id) == []


def test_delete_emotion(stores: tuple[AgentStore, EmotionalStateStore]) -> None:
    a = _agent(stores)
    stores[1].set(EmotionalState(a.id, "joy", value=0.8))
    stores[1].delete(a.id, "joy")
    assert stores[1].get(a.id, "joy") is None


def test_cascade_delete_agent(stores: tuple[AgentStore, EmotionalStateStore]) -> None:
    a = _agent(stores)
    stores[1].set(EmotionalState(a.id, "sadness", value=0.5))
    stores[0].delete(a.id)
    assert stores[1].get(a.id, "sadness") is None


def test_emotions_are_per_agent(stores: tuple[AgentStore, EmotionalStateStore]) -> None:
    a = _agent(stores)
    b = Agent.new("Bob")
    stores[0].create(b)
    stores[1].set(EmotionalState(a.id, "joy", value=0.9))
    stores[1].set(EmotionalState(b.id, "joy", value=0.1))
    assert stores[1].get_all(a.id)[0].value == pytest.approx(0.9)
    assert stores[1].get_all(b.id)[0].value == pytest.approx(0.1)
