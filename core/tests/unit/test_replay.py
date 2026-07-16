import json

import pytest

from empneon.core.contracts import ActionResult, Decision, StateDelta
from empneon.core.identity.models import Agent
from empneon.core.identity.store import AgentStore
from empneon.core.memory.episodic import EpisodicMemoryStore, Event
from empneon.core.replay import replay_action_record
from empneon.core.runtime import ActionRecordStore
from empneon.db.connection import open_db


def test_replay_inspects_confirmed_delta_divergence_without_mutation() -> None:
    conn = open_db(":memory:")
    AgentStore(conn).create(Agent("alice", "Alice"))
    event = EpisodicMemoryStore(conn).create(
        Event("Alice greeted Bob", ["alice"], happened_at=10, id="event-1")
    )
    matched = StateDelta("relationship.friendship", "increment", 5)
    omitted = StateDelta("emotion", "set", "happy")
    additional = StateDelta("animation", "set", "friendly_chat")
    decision = Decision(
        "alice",
        "greet",
        evidence_ids=(event.id,),
        state_changes=(matched, omitted),
        id="decision-1",
    )
    actions = ActionRecordStore(conn)
    original = actions.record(
        event.id,
        decision,
        ActionResult(decision.id, "succeeded", (matched, additional), completed_at=20),
    )

    replay = replay_action_record(conn, decision.id)

    assert replay["event"]["description"] == "Alice greeted Bob"
    assert replay["deltas"] == {
        "matched": [{"path": matched.path, "operation": matched.operation, "value": 5}],
        "not_applied": [{"path": omitted.path, "operation": omitted.operation, "value": "happy"}],
        "additional": [
            {"path": additional.path, "operation": additional.operation, "value": "friendly_chat"}
        ],
    }
    assert replay["consequence_integrity"] is True
    assert json.loads(json.dumps(replay))["decision"]["id"] == decision.id
    assert actions.get(decision.id) == original
    with pytest.raises(ValueError, match="does not exist"):
        replay_action_record(conn, "unknown")
