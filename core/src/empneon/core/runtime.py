"""Minimal event-to-action cognitive runtime."""

import dataclasses
import json
import sqlite3
from dataclasses import dataclass, replace
from typing import cast

from empneon.core.clod.fallback import Resolver, resolve_with_fallback
from empneon.core.clod.rules import resolve_clod1
from empneon.core.contracts import ActionResult, CognitiveRequest, Decision, StateDelta
from empneon.core.ports import GameAdapter
from empneon.core.scheduler.resources import ResourceEstimate, ResourceGovernor
from empneon.core.scheduler.selection import CognitionRoute, select_cognition
from empneon.db.query import validate_limit


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
    def __init__(self, governor: ResourceGovernor, actions: ActionRecordStore) -> None:
        self._governor = governor
        self._actions = actions

    async def process(
        self,
        request: CognitiveRequest,
        adapter: GameAdapter,
        resolver: Resolver,
        estimate: ResourceEstimate = ResourceEstimate(),
    ) -> ActionRecord:
        decision = await self.decide(request, resolver, estimate)
        result = adapter.execute(decision)
        return self._actions.record(request.event.id, decision, result)

    async def decide(
        self,
        request: CognitiveRequest,
        resolver: Resolver,
        estimate: ResourceEstimate = ResourceEstimate(),
    ) -> Decision:
        async def admitted(current: CognitiveRequest) -> Decision:
            with self._governor.reserve(estimate):
                return await resolver(current)

        return await resolve_with_fallback(request, admitted)

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
