"""Persistent secret, rumor, testimony, and correction scenarios."""

import sqlite3
from pathlib import Path

import pytest

from empneon.core.identity.models import Agent
from empneon.core.identity.relationships import Relationship, RelationshipStore
from empneon.core.identity.store import AgentStore
from empneon.core.memory.episodic import (
    Belief,
    BeliefStore,
    EpisodicMemoryStore,
    Event,
    Observation,
    ObservationStore,
)
from empneon.db.connection import open_db

ScenarioStores = tuple[
    sqlite3.Connection,
    AgentStore,
    RelationshipStore,
    EpisodicMemoryStore,
    ObservationStore,
    BeliefStore,
]


def _stores(path: str) -> ScenarioStores:
    conn = open_db(path)
    return (
        conn,
        AgentStore(conn),
        RelationshipStore(conn),
        EpisodicMemoryStore(conn),
        ObservationStore(conn),
        BeliefStore(conn),
    )


def _agent(store: AgentStore, agent_id: str) -> Agent:
    return store.create(Agent(agent_id, agent_id.title()))


def test_secret_remains_with_its_only_observer_after_restart(tmp_path: Path) -> None:
    path = str(tmp_path / "secret.db")
    conn, agents, _, events, observations, beliefs = _stores(path)
    alice = _agent(agents, "alice")
    bob = _agent(agents, "bob")
    event = events.create(Event("Alice found a hidden key", [alice.id]))
    observation = observations.create(
        Observation(event.id, alice.id, "The key is beneath the fountain")
    )
    secret = beliefs.create(
        Belief(
            alice.id,
            "The key is beneath the fountain",
            "observation",
            observation.id,
            1.0,
            "Alice saw the hiding place",
        )
    )

    assert beliefs.propagate(secret.id) == []
    conn.close()

    conn, _, _, _, _, beliefs = _stores(path)
    assert beliefs.get(secret.id) == secret
    assert beliefs.get_for_agent(bob.id) == []
    conn.close()


def test_rumor_retains_trust_decay_and_lineage_after_restart(tmp_path: Path) -> None:
    path = str(tmp_path / "rumor.db")
    conn, agents, relationships, events, observations, beliefs = _stores(path)
    alice = _agent(agents, "alice")
    bob = _agent(agents, "bob")
    carol = _agent(agents, "carol")
    relationships.set(Relationship(bob.id, alice.id, "friend", trust=0.8))
    relationships.set(Relationship(carol.id, bob.id, "friend", trust=0.5))
    event = events.create(Event("Alice heard the mayor may resign", [alice.id]))
    observation = observations.create(
        Observation(event.id, alice.id, "The mayor discussed resignation")
    )
    source = beliefs.create(
        Belief(
            alice.id,
            "The mayor may resign",
            "observation",
            observation.id,
            1.0,
            "Alice heard the private discussion",
        )
    )
    rumor = beliefs.propagate(source.id, max_hops=2, decay=0.5)
    conn.close()

    conn, _, _, _, _, beliefs = _stores(path)
    assert [belief.agent_id for belief in rumor] == [bob.id, carol.id]
    persisted = beliefs.get(rumor[1].id)
    assert persisted is not None
    assert persisted.confidence == pytest.approx(0.1)
    assert persisted.lineage == (source.id, rumor[0].id)
    conn.close()


def test_conflicting_testimony_remains_linked_after_restart(tmp_path: Path) -> None:
    path = str(tmp_path / "testimony.db")
    conn, agents, relationships, events, observations, beliefs = _stores(path)
    alice = _agent(agents, "alice")
    bob = _agent(agents, "bob")
    carol = _agent(agents, "carol")
    relationships.set(Relationship(carol.id, alice.id, "witness", trust=0.9))
    relationships.set(Relationship(carol.id, bob.id, "witness", trust=0.9))
    event = events.create(Event("A masked guest left the hall", [alice.id, bob.id]))
    alice_view = observations.create(
        Observation(event.id, alice.id, "Alice saw the guest leave north")
    )
    bob_view = observations.create(Observation(event.id, bob.id, "Bob saw the guest leave south"))
    north = beliefs.create(
        Belief(alice.id, "The guest went north", "observation", alice_view.id, 0.9, "Clear view")
    )
    south = beliefs.create(
        Belief(bob.id, "The guest went south", "observation", bob_view.id, 0.9, "Clear view")
    )
    carol_north = beliefs.propagate(north.id, max_hops=1)[0]
    carol_south = beliefs.propagate(south.id, max_hops=1)[0]
    beliefs.record_contradiction(
        carol_north.id, carol_south.id, "The guest could not leave in both directions"
    )
    conn.close()

    conn, _, _, _, _, beliefs = _stores(path)
    assert beliefs.get_contradictions(carol_north.id) == [carol_south]
    assert beliefs.get_contradictions(carol_south.id) == [carol_north]
    conn.close()


def test_correction_revises_rumor_and_survives_restart(tmp_path: Path) -> None:
    path = str(tmp_path / "correction.db")
    conn, agents, relationships, events, observations, beliefs = _stores(path)
    alice = _agent(agents, "alice")
    bob = _agent(agents, "bob")
    relationships.set(Relationship(bob.id, alice.id, "friend", trust=0.8))
    rumor_event = events.create(Event("Alice misread the train board", [alice.id]))
    rumor_observation = observations.create(
        Observation(rumor_event.id, alice.id, "The train appears to leave at eight")
    )
    source = beliefs.create(
        Belief(
            alice.id,
            "The train leaves at eight",
            "observation",
            rumor_observation.id,
            0.7,
            "Alice read the distant board",
        )
    )
    rumor = beliefs.propagate(source.id, max_hops=1)[0]
    correction_event = events.create(Event("Bob checked the printed schedule", [bob.id]))
    correction_observation = observations.create(
        Observation(correction_event.id, bob.id, "The train leaves at nine")
    )
    correction = beliefs.revise(
        rumor.id,
        Belief(
            bob.id,
            "The train leaves at nine",
            "observation",
            correction_observation.id,
            1.0,
            "Bob verified the printed schedule",
        ),
        "Primary evidence corrected the rumor",
    )
    beliefs.record_contradiction(rumor.id, correction.id, "The departure times conflict")
    conn.close()

    conn, _, _, _, _, beliefs = _stores(path)
    assert beliefs.get_revision(rumor.id) == correction
    assert beliefs.get_contradictions(rumor.id) == [correction]
    assert [belief.id for belief in beliefs.get_current_for_agent(bob.id)] == [correction.id]
    assert {belief.id for belief in beliefs.get_for_agent(bob.id)} == {rumor.id, correction.id}
    conn.close()
