"""Minimal event-to-action cognitive runtime."""

import asyncio
import dataclasses
import json
import logging
import sqlite3
from dataclasses import dataclass, replace
from typing import cast

from empneon.core.capabilities import validate_decision
from empneon.core.clod.fallback import Resolver, resolve_with_fallback
from empneon.core.clod.rules import resolve_clod1
from empneon.core.contracts import (
    ActionResult,
    CognitiveRequest,
    Decision,
    DegradationReason,
    StateDelta,
)
from empneon.core.ports import GameAdapter
from empneon.core.scheduler.resources import ResourceEstimate, ResourceGovernor
from empneon.core.scheduler.selection import CognitionRoute, select_cognition
from empneon.core.scheduler.usage import UsageStore
from empneon.db.query import validate_limit
from empneon.providers.llm import GenerationResult

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ActionRecord:
    event_id: str
    decision: Decision
    result: ActionResult


@dataclass(frozen=True)
class ActionProposal:
    event_id: str
    decision: Decision
    adapter_action: str


class ActionRecordStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def record(self, event_id: str, decision: Decision, result: ActionResult) -> ActionRecord:
        if result.decision_id != decision.id:
            raise ValueError("action result does not match its decision")
        with self._conn:
            self._insert_record(event_id, decision, result)
        return ActionRecord(event_id, decision, result)

    def propose(self, event_id: str, decision: Decision, adapter_action: str) -> ActionProposal:
        if not adapter_action.strip():
            raise ValueError("adapter action must not be empty")
        with self._conn:
            self._conn.execute(
                "INSERT INTO action_proposals VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    decision.id,
                    event_id,
                    decision.actor_id,
                    decision.intent,
                    decision.target_id,
                    json.dumps(decision.evidence_ids),
                    json.dumps([dataclasses.asdict(change) for change in decision.state_changes]),
                    decision.confidence,
                    adapter_action,
                ),
            )
        return ActionProposal(event_id, decision, adapter_action)

    def get_proposal(self, decision_id: str) -> ActionProposal | None:
        row = self._conn.execute(
            "SELECT * FROM action_proposals WHERE decision_id=?", (decision_id,)
        ).fetchone()
        if row is None:
            return None
        return ActionProposal(row["event_id"], _decision_from_row(row), row["adapter_action"])

    def confirm(
        self, result: ActionResult, adapter_action: str, *, commit: bool = True
    ) -> ActionRecord:
        proposal = self.get_proposal(result.decision_id)
        if proposal is None:
            raise ValueError("unknown or already confirmed action proposal")
        if proposal.adapter_action != adapter_action:
            raise ValueError("confirmed action does not match its proposal")
        if commit:
            with self._conn:
                self._insert_record(proposal.event_id, proposal.decision, result)
                self._conn.execute(
                    "DELETE FROM action_proposals WHERE decision_id=?", (result.decision_id,)
                )
        else:
            self._insert_record(proposal.event_id, proposal.decision, result)
            self._conn.execute(
                "DELETE FROM action_proposals WHERE decision_id=?", (result.decision_id,)
            )
        return ActionRecord(proposal.event_id, proposal.decision, result)

    def _insert_record(
        self, event_id: str, decision: Decision, result: ActionResult
    ) -> None:
        self._conn.execute(
            "INSERT INTO action_results VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                decision.id,
                event_id,
                decision.actor_id,
                decision.intent,
                decision.target_id,
                json.dumps(decision.evidence_ids),
                json.dumps([dataclasses.asdict(change) for change in decision.state_changes]),
                decision.confidence,
                result.status,
                json.dumps([dataclasses.asdict(change) for change in result.applied_changes]),
                result.reason,
                result.completed_at,
            ),
        )
        self._conn.executemany(
            "INSERT INTO action_consequences VALUES (?,?,?,?,?)",
            [
                (decision.id, position, change.path, change.operation, json.dumps(change.value))
                for position, change in enumerate(result.applied_changes)
            ],
        )

    def get_consequences(self, decision_id: str) -> tuple[StateDelta, ...]:
        rows = self._conn.execute(
            "SELECT path, operation, value FROM action_consequences"
            " WHERE decision_id=? ORDER BY position",
            (decision_id,),
        ).fetchall()
        return tuple(
            StateDelta(row["path"], row["operation"], json.loads(row["value"])) for row in rows
        )

    def get(self, decision_id: str) -> ActionRecord | None:
        row = self._conn.execute(
            "SELECT * FROM action_results WHERE decision_id=?", (decision_id,)
        ).fetchone()
        return None if row is None else _action_record_from_row(row)

    def get_for_agent(
        self, agent_id: str, limit: int | None = None
    ) -> list[ActionRecord]:
        validate_limit(limit)
        query = (
            "SELECT * FROM action_results WHERE actor_id=?"
            " ORDER BY completed_at DESC, decision_id DESC"
        )
        args: tuple[str | int, ...] = (agent_id,)
        if limit is not None:
            query += " LIMIT ?"
            args = (agent_id, limit)
        rows = self._conn.execute(query, args).fetchall()
        return [_action_record_from_row(row) for row in rows]


class CognitiveRuntime:
    """Runs the event -> decision -> action loop under resource admission.

    With `enforce_deadlines=True`, a resolver that has not finished within the request's
    `deadline_ms` is cancelled and cognition degrades to CLOD 1 (reason `timeout`). A provider
    running in a worker thread keeps running until its own transport timeout; its result is
    discarded. Enforcement is off by default so existing callers keep their behavior.

    With a `usage` store, each degradation to CLOD 1 is persisted as a `core-rules` usage row
    carrying its `DegradationReason`; recording failures are logged and never change the decision.
    """

    def __init__(
        self,
        governor: ResourceGovernor,
        actions: ActionRecordStore,
        *,
        enforce_deadlines: bool = False,
        usage: UsageStore | None = None,
    ) -> None:
        self._governor = governor
        self._actions = actions
        self._enforce_deadlines = enforce_deadlines
        self._usage = usage

    async def process(
        self,
        request: CognitiveRequest,
        adapter: GameAdapter,
        resolver: Resolver,
        estimate: ResourceEstimate = ResourceEstimate(),
    ) -> ActionRecord:
        decision = await self.decide(request, resolver, estimate)
        state = request.event.agent_state
        rejection = validate_decision(decision, state.capabilities if state else None)
        if rejection is not None:
            _log.warning("decision rejected by capability check")
            result = ActionResult(decision.id, "rejected", reason=rejection)
            return self._actions.record(request.event.id, decision, result)
        try:
            result = adapter.execute(decision)
        except Exception as exc:
            _log.error("adapter execute failed: %s", type(exc).__name__)
            result = ActionResult(
                decision.id, "failed", reason=f"adapter raised {type(exc).__name__}"
            )
        return self._actions.record(request.event.id, decision, result)

    async def decide(
        self,
        request: CognitiveRequest,
        resolver: Resolver,
        estimate: ResourceEstimate = ResourceEstimate(),
    ) -> Decision:
        async def admitted(current: CognitiveRequest) -> Decision:
            with self._governor.reserve(estimate):
                if not self._enforce_deadlines:
                    return await resolver(current)
                async with asyncio.timeout(current.deadline_ms / 1000):
                    return await resolver(current)

        def record_degradation(reason: DegradationReason) -> None:
            if self._usage is None:
                return
            try:
                self._usage.record(
                    request,
                    estimate,
                    "core-rules",
                    "clod1",
                    GenerationResult("", 0, 0, 0),
                    1,
                    degradation_reason=reason,
                )
            except Exception as exc:
                _log.error("recording degradation failed: %s", type(exc).__name__)

        return await resolve_with_fallback(request, admitted, on_degrade=record_degradation)

    async def decide_dynamic(
        self,
        request: CognitiveRequest,
        routes: tuple[CognitionRoute, ...],
        deeper_reasoning_value: float,
        minimum_value: float = 0.5,
    ) -> Decision:
        plan = select_cognition(
            request, routes, self._governor, deeper_reasoning_value, minimum_value
        )
        if plan.resolver is None:
            return resolve_clod1(request)
        selected = cast(
            CognitiveRequest,
            replace(
                request,
                preferred_clod=plan.clod,
                max_tokens=plan.completion_tokens,
                max_context_tokens=plan.context_tokens,
            ),
        )
        return await self.decide(selected, plan.resolver, plan.estimate)


def _action_record_from_row(row: sqlite3.Row) -> ActionRecord:
    decision = _decision_from_row(row)
    result = ActionResult(
        decision.id,
        row["status"],
        tuple(StateDelta(**change) for change in json.loads(row["applied_changes"])),
        row["reason"],
        row["completed_at"],
    )
    return ActionRecord(row["event_id"], decision, result)


def _decision_from_row(row: sqlite3.Row) -> Decision:
    return Decision(
        id=row["decision_id"],
        actor_id=row["actor_id"],
        intent=row["intent"],
        target_id=row["target_id"],
        evidence_ids=tuple(json.loads(row["evidence_ids"])),
        state_changes=tuple(
            StateDelta(**change) for change in json.loads(row["decision_changes"])
        ),
        confidence=row["confidence"],
    )
