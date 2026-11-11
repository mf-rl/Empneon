import pytest

import empneon
from empneon import Clod
from empneon.core import ports
from empneon.core.clod import fallback
from empneon.core.contracts import AgentStateSnapshot, CognitiveRequest, WorldEvent
from empneon.core.identity.models import Agent
from empneon.core.identity.store import AgentStore
from empneon.core.memory.episodic import BeliefStore, EpisodicMemoryStore
from empneon.core.runtime import ActionRecordStore
from empneon.core.scheduler import selection
from empneon.core.scheduler.resources import ResourceEstimate
from empneon.core.scheduler.usage import UsageRecord
from empneon.db.connection import open_db

EVENT = WorldEvent("e", id="event-1")


def test_clod_levels_match_documented_numbers() -> None:
    assert [int(level) for level in Clod] == [0, 1, 2, 3, 4]
    assert Clod.RULES == 1 and Clod.INTERACTIVE == 3
    assert empneon.Clod is Clod


def test_enum_is_accepted_wherever_an_int_is() -> None:
    request = CognitiveRequest("alice", Clod.INTERACTIVE, EVENT)
    assert request.preferred_clod == 3
    record = UsageRecord("r", "a", "e", "p", "m", Clod.SMALL_MODEL, ResourceEstimate(), 1, 1, 1)
    assert record.clod == 2


@pytest.mark.parametrize("level", [-1, 5])
def test_invalid_clod_is_rejected_with_one_message(level: int) -> None:
    with pytest.raises(ValueError, match="must be between 0 and 4"):
        CognitiveRequest("alice", level, EVENT)
    with pytest.raises(ValueError, match="must be between 0 and 4"):
        UsageRecord("r", "a", "e", "p", "m", level, ResourceEstimate(), 1, 1, 1)


def test_resolver_alias_is_defined_once() -> None:
    assert selection.Resolver is ports.Resolver
    assert fallback.Resolver is ports.Resolver


@pytest.mark.parametrize("limit", [0, -1])
def test_store_limits_must_be_positive(limit: int) -> None:
    conn = open_db(":memory:")
    AgentStore(conn).create(Agent("a", "Alice"))
    for read in (
        EpisodicMemoryStore(conn).get_for_agent,
        BeliefStore(conn).get_for_agent,
        ActionRecordStore(conn).get_for_agent,
    ):
        with pytest.raises(ValueError, match="limit must be positive"):
            read("a", limit)
        assert read("a", 1) == []


def _state(schema_version: object) -> dict[str, object]:
    return {"schema_version": schema_version, "adapter": "game", "agent_id": "alice"}


@pytest.mark.parametrize("value", ["abc", True, 1.5, [], {}])
def test_malformed_schema_version_is_a_clear_value_error(value: object) -> None:
    with pytest.raises(ValueError, match="schema_version must be an integer"):
        AgentStateSnapshot.from_mapping(_state(value))


@pytest.mark.parametrize("value", [None, 2, "2"])
def test_unsupported_schema_version_is_rejected(value: object) -> None:
    with pytest.raises(ValueError, match="unsupported agent state schema_version"):
        AgentStateSnapshot.from_mapping(_state(value))


@pytest.mark.parametrize("value", [1, "1", 1.0])
def test_supported_schema_version_forms_still_load(value: object) -> None:
    assert AgentStateSnapshot.from_mapping(_state(value)).schema_version == 1
