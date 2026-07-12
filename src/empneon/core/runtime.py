"""Minimal event-to-action cognitive runtime."""

import dataclasses
import json
import sqlite3
from dataclasses import dataclass

from empneon.adapters import GameAdapter
from empneon.core.clod.fallback import Resolver, resolve_with_fallback
from empneon.core.contracts import ActionResult, CognitiveRequest, Decision, StateDelta
from empneon.core.scheduler.resources import ResourceEstimate, ResourceGovernor


@dataclass(frozen=True)
class ActionRecord:
    event_id: str
    decision: Decision
    result: ActionResult


class ActionRecordStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def record(self, event_id: str, decision: Decision, result: ActionResult) -> ActionRecord:
        if result.decision_id != decision.id:
            raise ValueError("action result does not match its decision")
        with self._conn:
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
        return ActionRecord(event_id, decision, result)

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
        if row is None:
            return None
        decision = Decision(
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
        result = ActionResult(
            decision.id,
            row["status"],
            tuple(StateDelta(**change) for change in json.loads(row["applied_changes"])),
            row["reason"],
            row["completed_at"],
        )
        return ActionRecord(row["event_id"], decision, result)


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
        async def admitted(current: CognitiveRequest) -> Decision:
            with self._governor.reserve(estimate):
                return await resolver(current)

        decision = await resolve_with_fallback(request, admitted)
        result = adapter.execute(decision)
        return self._actions.record(request.event.id, decision, result)
