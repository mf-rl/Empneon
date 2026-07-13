import sqlite3

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


def test_agent_observations_are_separate_from_canonical_event() -> None:
    conn = open_db(":memory:")
    agents = AgentStore(conn)
    events = EpisodicMemoryStore(conn)
    observations = ObservationStore(conn)
    alice = agents.create(Agent.new("Alice"))
    bob = agents.create(Agent.new("Bob"))
    event = events.create(Event("A masked guest entered", [alice.id, bob.id], happened_at=10))

    alice_view = observations.create(
        Observation(event.id, alice.id, "Alice thought the guest was Charlie", observed_at=11)
    )
    bob_view = observations.create(
        Observation(event.id, bob.id, "Bob could not identify the guest", observed_at=12)
    )

    assert observations.get_for_event(event.id) == [alice_view, bob_view]
    assert observations.get_for_agent(alice.id) == [alice_view]
    canonical = events.get(event.id)
    assert canonical is not None
    assert canonical.description == event.description
    assert set(canonical.participant_ids) == {alice.id, bob.id}


def test_beliefs_are_separate_from_events_and_observations() -> None:
    conn = open_db(":memory:")
    agents = AgentStore(conn)
    events = EpisodicMemoryStore(conn)
    observations = ObservationStore(conn)
    beliefs = BeliefStore(conn)
    alice = agents.create(Agent.new("Alice"))
    event = events.create(Event("A masked guest entered", [alice.id], happened_at=10))
    observation = observations.create(
        Observation(event.id, alice.id, "Alice saw a red coat", observed_at=11)
    )
    belief = beliefs.create(
        Belief(
            alice.id,
            "The masked guest was Charlie",
            "observation",
            observation.id,
            0.7,
            "Alice associated the red coat with Charlie",
            created_at=12,
        )
    )

    assert beliefs.get_for_agent(alice.id) == [belief]
    assert observations.get_for_event(event.id) == [observation]
    assert events.get(event.id) == event


def test_belief_provenance_prevents_deleting_its_canonical_evidence() -> None:
    conn = open_db(":memory:")
    agents = AgentStore(conn)
    events = EpisodicMemoryStore(conn)
    observations = ObservationStore(conn)
    beliefs = BeliefStore(conn)
    alice = agents.create(Agent.new("Alice"))
    event = events.create(Event("A masked guest entered", [alice.id]))
    observations.create(Observation(event.id, alice.id, "Alice saw a red coat"))
    observation = observations.get_for_event(event.id)[0]
    belief = beliefs.create(
        Belief(
            alice.id,
            "The guest was Charlie",
            "observation",
            observation.id,
            0.7,
            "Alice recognized the coat",
        )
    )

    with pytest.raises(sqlite3.IntegrityError):
        events.delete(event.id)

    assert observations.get_for_event(event.id) == [observation]
    assert beliefs.get_for_agent(alice.id) == [belief]

    agents.delete(alice.id)
    assert beliefs.get_for_agent(alice.id) == []


def test_belief_records_source_confidence_interpretation_and_lineage() -> None:
    conn = open_db(":memory:")
    agents = AgentStore(conn)
    events = EpisodicMemoryStore(conn)
    observations = ObservationStore(conn)
    beliefs = BeliefStore(conn)
    alice = agents.create(Agent.new("Alice"))
    bob = agents.create(Agent.new("Bob"))
    carol = agents.create(Agent.new("Carol"))
    event = events.create(Event("A masked guest entered", [alice.id, bob.id, carol.id]))
    observation = observations.create(
        Observation(event.id, alice.id, "Alice saw Charlie remove the mask")
    )
    alice_belief = beliefs.create(
        Belief(
            alice.id,
            "The guest was Charlie",
            "observation",
            observation.id,
            0.95,
            "Alice recognized Charlie directly",
        )
    )
    bob_belief = beliefs.create(
        Belief(
            bob.id,
            "The guest was Charlie",
            "belief",
            alice_belief.id,
            0.75,
            "Bob trusted Alice's account",
        )
    )
    carol_belief = beliefs.create(
        Belief(
            carol.id,
            "The guest was Charlie",
            "belief",
            bob_belief.id,
            0.6,
            "Carol accepted Bob's retelling",
        )
    )

    assert beliefs.get(alice_belief.id) == alice_belief
    assert beliefs.get(bob_belief.id) == bob_belief
    assert bob_belief.lineage == (alice_belief.id,)
    assert carol_belief.lineage == (alice_belief.id, bob_belief.id)


def test_belief_rejects_missing_source_and_invalid_confidence() -> None:
    conn = open_db(":memory:")
    alice = AgentStore(conn).create(Agent.new("Alice"))
    beliefs = BeliefStore(conn)

    with pytest.raises(ValueError, match="source"):
        beliefs.create(
            Belief(alice.id, "Claim", "observation", "missing", 0.5, "Interpretation")
        )
    with pytest.raises(ValueError, match="confidence"):
        Belief(alice.id, "Claim", "observation", "missing", 1.1, "Interpretation")


def test_belief_contradiction_and_revision_preserve_history() -> None:
    conn = open_db(":memory:")
    agents = AgentStore(conn)
    events = EpisodicMemoryStore(conn)
    observations = ObservationStore(conn)
    beliefs = BeliefStore(conn)
    alice = agents.create(Agent.new("Alice"))
    event = events.create(Event("Charlie entered wearing a coat", [alice.id]))
    observation = observations.create(
        Observation(event.id, alice.id, "The coat looked red in dim light")
    )
    red = beliefs.create(
        Belief(alice.id, "The coat was red", "observation", observation.id, 0.6, "Dim light")
    )
    blue = beliefs.create(
        Belief(alice.id, "The coat was blue", "observation", observation.id, 0.8, "Closer look")
    )

    beliefs.record_contradiction(red.id, blue.id, "The coat cannot be both colors")
    revision = beliefs.revise(
        red.id,
        Belief(
            alice.id,
            "The coat was blue",
            "belief",
            blue.id,
            0.9,
            "Alice accepted the clearer account",
        ),
        "Better evidence corrected the color",
    )

    assert beliefs.get_contradictions(red.id) == [blue]
    assert beliefs.get_contradictions(blue.id) == [red]
    assert beliefs.get_revision(red.id) == revision
    assert {belief.id for belief in beliefs.get_for_agent(alice.id)} == {
        red.id,
        blue.id,
        revision.id,
    }
    assert {belief.id for belief in beliefs.get_current_for_agent(alice.id)} == {
        blue.id,
        revision.id,
    }


def test_belief_revision_is_single_and_atomic() -> None:
    conn = open_db(":memory:")
    agents = AgentStore(conn)
    events = EpisodicMemoryStore(conn)
    observations = ObservationStore(conn)
    beliefs = BeliefStore(conn)
    alice = agents.create(Agent.new("Alice"))
    event = events.create(Event("A coat changed color", [alice.id]))
    observation = observations.create(Observation(event.id, alice.id, "The coat looked blue"))
    original = beliefs.create(
        Belief(alice.id, "The coat was red", "observation", observation.id, 0.4, "First look")
    )
    first = beliefs.revise(
        original.id,
        Belief(alice.id, "The coat was blue", "observation", observation.id, 0.9, "Second look"),
        "Closer inspection",
    )
    rejected = Belief(
        alice.id, "The coat was green", "observation", observation.id, 0.2, "Guess"
    )

    with pytest.raises(ValueError, match="already been revised"):
        beliefs.revise(original.id, rejected, "Another guess")

    assert beliefs.get_revision(original.id) == first
    assert beliefs.get(rejected.id) is None


def test_trust_weighted_propagation_is_bounded_and_traceable() -> None:
    conn = open_db(":memory:")
    agents = AgentStore(conn)
    relationships = RelationshipStore(conn)
    events = EpisodicMemoryStore(conn)
    observations = ObservationStore(conn)
    beliefs = BeliefStore(conn)
    alice = agents.create(Agent("alice", "Alice"))
    bob = agents.create(Agent("bob", "Bob"))
    carol = agents.create(Agent("carol", "Carol"))
    dave = agents.create(Agent("dave", "Dave"))
    erin = agents.create(Agent("erin", "Erin"))
    relationships.set(Relationship(bob.id, alice.id, "friend", trust=0.8))
    relationships.set(Relationship(carol.id, bob.id, "friend", trust=0.5))
    relationships.set(Relationship(dave.id, carol.id, "friend", trust=0.9))
    relationships.set(Relationship(erin.id, alice.id, "friend", trust=0.1))
    relationships.set(Relationship(alice.id, carol.id, "friend", trust=1.0))
    event = events.create(Event("Alice found a blue key", [alice.id]))
    observation = observations.create(Observation(event.id, alice.id, "The key was blue"))
    source = beliefs.create(
        Belief(alice.id, "The key is blue", "observation", observation.id, 1.0, "Direct sight")
    )

    propagated = beliefs.propagate(
        source.id, max_hops=2, max_recipients=10, min_confidence=0.1, decay=0.5
    )

    assert [belief.agent_id for belief in propagated] == [bob.id, carol.id]
    assert propagated[0].confidence == pytest.approx(0.4)
    assert propagated[1].confidence == pytest.approx(0.1)
    assert propagated[1].lineage == (source.id, propagated[0].id)
    assert beliefs.get(propagated[1].id) == propagated[1]


def test_propagation_respects_total_recipient_bound() -> None:
    conn = open_db(":memory:")
    agents = AgentStore(conn)
    relationships = RelationshipStore(conn)
    events = EpisodicMemoryStore(conn)
    observations = ObservationStore(conn)
    beliefs = BeliefStore(conn)
    alice = agents.create(Agent("alice", "Alice"))
    bob = agents.create(Agent("bob", "Bob"))
    carol = agents.create(Agent("carol", "Carol"))
    relationships.set(Relationship(bob.id, alice.id, "friend", trust=1.0))
    relationships.set(Relationship(carol.id, alice.id, "friend", trust=1.0))
    event = events.create(Event("Alice found a key", [alice.id]))
    observation = observations.create(Observation(event.id, alice.id, "Alice saw the key"))
    source = beliefs.create(
        Belief(alice.id, "The key exists", "observation", observation.id, 1.0, "Direct sight")
    )

    propagated = beliefs.propagate(source.id, max_recipients=1)

    assert [belief.agent_id for belief in propagated] == [bob.id]
