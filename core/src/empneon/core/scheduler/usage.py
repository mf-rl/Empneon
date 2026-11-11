"""Persistent estimates and actual provider usage."""

import sqlite3
import time
import uuid
from dataclasses import dataclass, field

from empneon.core.contracts import CognitiveRequest, validate_clod
from empneon.core.scheduler.resources import ResourceEstimate
from empneon.providers.llm import GenerationResult


@dataclass(frozen=True)
class UsageRecord:
    request_id: str
    agent_id: str
    event_id: str
    provider: str
    model: str
    clod: int | None
    estimate: ResourceEstimate
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_ms: int | None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    recorded_at: int = field(default_factory=lambda: int(time.time()))

    def __post_init__(self) -> None:
        if self.clod is not None:
            validate_clod(self.clod, "selected CLOD")


class UsageStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def record(
        self,
        request: CognitiveRequest,
        estimate: ResourceEstimate,
        provider: str,
        model: str,
        result: GenerationResult,
        clod: int,
        *,
        commit: bool = True,
    ) -> UsageRecord:
        record = UsageRecord(
            request.id,
            request.agent_id,
            request.event.id,
            provider,
            model,
            clod,
            estimate,
            result.prompt_tokens,
            result.completion_tokens,
            result.latency_ms,
        )
        self._conn.execute(
            "INSERT INTO cognition_usage ("
            "id, request_id, agent_id, event_id, provider, model,"
            "estimated_ram_mb, estimated_vram_mb, estimated_context_tokens,"
            "estimated_completion_tokens, estimated_latency_ms, actual_prompt_tokens,"
            "actual_completion_tokens, actual_latency_ms, recorded_at, selected_clod"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                record.id,
                record.request_id,
                record.agent_id,
                record.event_id,
                record.provider,
                record.model,
                estimate.ram_mb,
                estimate.vram_mb,
                estimate.context_tokens,
                estimate.completion_tokens,
                estimate.latency_ms,
                record.prompt_tokens,
                record.completion_tokens,
                record.latency_ms,
                record.recorded_at,
                record.clod,
            ),
        )
        if commit:
            self._conn.commit()
        return record

    def get_for_request(self, request_id: str) -> list[UsageRecord]:
        rows = self._conn.execute(
            "SELECT * FROM cognition_usage WHERE request_id=? ORDER BY recorded_at, rowid",
            (request_id,),
        ).fetchall()
        return [_to_record(row) for row in rows]

    def telemetry(self, agent_id: str | None = None) -> dict[str, object]:
        query = "SELECT * FROM cognition_usage"
        args: tuple[str, ...] = ()
        if agent_id is not None:
            query += " WHERE agent_id=?"
            args = (agent_id,)
        rows = self._conn.execute(query + " ORDER BY recorded_at, rowid", args).fetchall()
        records = [_to_record(row) for row in rows]
        clods: dict[str, int] = {}
        providers: dict[str, int] = {}
        for record in records:
            clod = "unknown" if record.clod is None else str(record.clod)
            clods[clod] = clods.get(clod, 0) + 1
            providers[record.provider] = providers.get(record.provider, 0) + 1
        return {
            "attempts": len(records),
            "requests": len({record.request_id for record in records}),
            "by_clod": clods,
            "by_provider": providers,
            "estimated": {
                "peak_ram_mb": max((record.estimate.ram_mb for record in records), default=0),
                "peak_vram_mb": max((record.estimate.vram_mb for record in records), default=0),
                "context_tokens": sum(record.estimate.context_tokens for record in records),
                "completion_tokens": sum(
                    record.estimate.completion_tokens for record in records
                ),
                "latency_ms": sum(record.estimate.latency_ms for record in records),
            },
            "actual": {
                "prompt_tokens": sum(record.prompt_tokens or 0 for record in records),
                "completion_tokens": sum(record.completion_tokens or 0 for record in records),
                "latency_ms": sum(record.latency_ms or 0 for record in records),
            },
        }


def _to_record(row: sqlite3.Row) -> UsageRecord:
    return UsageRecord(
        id=row["id"],
        request_id=row["request_id"],
        agent_id=row["agent_id"],
        event_id=row["event_id"],
        provider=row["provider"],
        model=row["model"],
        clod=row["selected_clod"],
        estimate=ResourceEstimate(
            ram_mb=row["estimated_ram_mb"],
            vram_mb=row["estimated_vram_mb"],
            context_tokens=row["estimated_context_tokens"],
            completion_tokens=row["estimated_completion_tokens"],
            latency_ms=row["estimated_latency_ms"],
        ),
        prompt_tokens=row["actual_prompt_tokens"],
        completion_tokens=row["actual_completion_tokens"],
        latency_ms=row["actual_latency_ms"],
        recorded_at=row["recorded_at"],
    )
