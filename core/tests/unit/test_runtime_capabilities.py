import asyncio
import logging

import pytest

from empneon.core.contracts import (
    ActionResult,
    AgentStateSnapshot,
    CognitiveRequest,
    Decision,
    StateDelta,
    WorldEvent,
)
from empneon.core.runtime import ActionRecord, ActionRecordStore, CognitiveRuntime
from empneon.core.scheduler.resources import ResourceBudget, ResourceGovernor
from empneon.db.connection import open_db

SECRET_INTENT = "secret-intent-name"
SECRET_PATH = "secret-path-root.child"


class SpyAdapter:
    def __init__(self) -> None:
        self.executed: list[Decision] = []

    def observe(self) -> tuple[WorldEvent, ...]:
        return ()

    def execute(self, decision: Decision, /) -> ActionResult:
        self.executed.append(decision)
        return ActionResult(decision.id, "succeeded", decision.state_changes)


def run(
    capabilities: dict[str, object] | None,
    intent: str = "greet",
    *paths: str,
) -> tuple[ActionRecord, SpyAdapter, ActionRecordStore]:
    state = (
        AgentStateSnapshot(1, "game", "agent-a", capabilities=capabilities)
        if capabilities is not None
        else None
    )
    event = WorldEvent("encounter", ("agent-a",), agent_state=state)
    request = CognitiveRequest("agent-a", 3, event)
    actions = ActionRecordStore(open_db(":memory:"))
    runtime = CognitiveRuntime(ResourceGovernor(ResourceBudget(256, 0)), actions)
    adapter = SpyAdapter()

    async def resolve(_: CognitiveRequest) -> Decision:
        changes = tuple(StateDelta(path, "set", "x") for path in paths)
        return Decision("agent-a", intent, state_changes=changes)

    return asyncio.run(runtime.process(request, adapter, resolve)), adapter, actions


def test_permitted_decision_executes() -> None:
    capabilities: dict[str, object] = {"intents": ["greet"], "state_paths": ["dialogue"]}
    record, adapter, _ = run(capabilities, "greet", "dialogue")
    assert record.result.status == "succeeded"
    assert len(adapter.executed) == 1


def test_unpublished_capabilities_execute_normally() -> None:
    assert run(None, "anything", "any.path")[1].executed
    assert run({}, "anything", "any.path")[1].executed
    assert run({"actions": ["friendly_chat"]}, "anything")[1].executed


@pytest.mark.parametrize(
    ("capabilities", "paths", "reason"),
    [
        ({"intents": ["wave"]}, (), "intent not supported: greet"),
        (
            {"state_paths": ["dialogue"]},
            ("inventory.gold",),
            "state path not supported: inventory.gold",
        ),
    ],
)
def test_unsupported_decision_is_rejected_without_executing(
    capabilities: dict[str, object], paths: tuple[str, ...], reason: str
) -> None:
    record, adapter, actions = run(capabilities, "greet", *paths)

    assert adapter.executed == []
    assert record.result.status == "rejected"
    assert record.result.reason == reason
    assert record.result.applied_changes == ()
    assert actions.get(record.decision.id) == record
    assert actions.get_consequences(record.decision.id) == ()


def test_rejection_log_carries_no_identifiers(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="empneon"):
        run({"intents": ["wave"]}, SECRET_INTENT, SECRET_PATH)
    assert "capability" in caplog.text
    assert SECRET_INTENT not in caplog.text and SECRET_PATH not in caplog.text
