import pytest

from empneon.core.identity.goals import (
    GOAL_ABANDONED,
    GOAL_ACTIVE,
    GOAL_COMPLETED,
    Goal,
    GoalStore,
)
from empneon.core.identity.models import Agent
from empneon.core.identity.store import AgentStore
from empneon.db.connection import open_db


@pytest.fixture
def stores() -> tuple[AgentStore, GoalStore]:
    conn = open_db(":memory:")
    return AgentStore(conn), GoalStore(conn)


def _agent(stores: tuple[AgentStore, GoalStore]) -> Agent:
    a = Agent.new("Alice")
    stores[0].create(a)
    return a


def test_create_and_get(stores: tuple[AgentStore, GoalStore]) -> None:
    a = _agent(stores)
    goal = Goal(agent_id=a.id, description="Become a chef", priority=0.8)
    stores[1].create(goal)
    fetched = stores[1].get(goal.id)
    assert fetched is not None
    assert fetched.description == "Become a chef"
    assert fetched.priority == pytest.approx(0.8)
    assert fetched.status == GOAL_ACTIVE


def test_get_missing_returns_none(stores: tuple[AgentStore, GoalStore]) -> None:
    assert stores[1].get("nonexistent-id") is None


def test_get_all_returns_all_goals(stores: tuple[AgentStore, GoalStore]) -> None:
    a = _agent(stores)
    stores[1].create(Goal(agent_id=a.id, description="Goal A", priority=0.9))
    stores[1].create(Goal(agent_id=a.id, description="Goal B", priority=0.3))
    stores[1].create(Goal(agent_id=a.id, description="Goal C", priority=0.6))
    result = stores[1].get_all(a.id)
    assert len(result) == 3
    assert {g.description for g in result} == {"Goal A", "Goal B", "Goal C"}


def test_get_all_sorted_by_priority_desc(stores: tuple[AgentStore, GoalStore]) -> None:
    a = _agent(stores)
    stores[1].create(Goal(agent_id=a.id, description="Low", priority=0.1))
    stores[1].create(Goal(agent_id=a.id, description="High", priority=0.9))
    stores[1].create(Goal(agent_id=a.id, description="Mid", priority=0.5))
    result = stores[1].get_all(a.id)
    assert result[0].description == "High"
    assert result[-1].description == "Low"


def test_get_all_filtered_by_status(stores: tuple[AgentStore, GoalStore]) -> None:
    a = _agent(stores)
    g1 = Goal(agent_id=a.id, description="Active goal", priority=0.8)
    g2 = Goal(agent_id=a.id, description="Done goal", priority=0.5)
    stores[1].create(g1)
    stores[1].create(g2)
    stores[1].update_status(g2.id, GOAL_COMPLETED)
    active = stores[1].get_all(a.id, status=GOAL_ACTIVE)
    done = stores[1].get_all(a.id, status=GOAL_COMPLETED)
    assert len(active) == 1
    assert active[0].description == "Active goal"
    assert len(done) == 1
    assert done[0].description == "Done goal"


def test_get_all_empty(stores: tuple[AgentStore, GoalStore]) -> None:
    a = _agent(stores)
    assert stores[1].get_all(a.id) == []


def test_update_status_to_completed(stores: tuple[AgentStore, GoalStore]) -> None:
    a = _agent(stores)
    goal = Goal(agent_id=a.id, description="Finish the novel")
    stores[1].create(goal)
    stores[1].update_status(goal.id, GOAL_COMPLETED)
    fetched = stores[1].get(goal.id)
    assert fetched is not None
    assert fetched.status == GOAL_COMPLETED


def test_update_status_to_abandoned(stores: tuple[AgentStore, GoalStore]) -> None:
    a = _agent(stores)
    goal = Goal(agent_id=a.id, description="Learn piano")
    stores[1].create(goal)
    stores[1].update_status(goal.id, GOAL_ABANDONED)
    fetched = stores[1].get(goal.id)
    assert fetched is not None
    assert fetched.status == GOAL_ABANDONED


def test_delete_goal(stores: tuple[AgentStore, GoalStore]) -> None:
    a = _agent(stores)
    goal = Goal(agent_id=a.id, description="Temporary goal")
    stores[1].create(goal)
    stores[1].delete(goal.id)
    assert stores[1].get(goal.id) is None


def test_cascade_delete_agent(stores: tuple[AgentStore, GoalStore]) -> None:
    a = _agent(stores)
    goal = Goal(agent_id=a.id, description="Will be orphaned")
    stores[1].create(goal)
    stores[0].delete(a.id)
    assert stores[1].get(goal.id) is None


def test_goals_are_per_agent(stores: tuple[AgentStore, GoalStore]) -> None:
    a = _agent(stores)
    b = Agent.new("Bob")
    stores[0].create(b)
    stores[1].create(Goal(agent_id=a.id, description="Alice's goal"))
    stores[1].create(Goal(agent_id=b.id, description="Bob's goal"))
    assert len(stores[1].get_all(a.id)) == 1
    assert stores[1].get_all(a.id)[0].description == "Alice's goal"
    assert len(stores[1].get_all(b.id)) == 1
    assert stores[1].get_all(b.id)[0].description == "Bob's goal"
