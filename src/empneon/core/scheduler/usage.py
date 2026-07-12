"""Persistent estimates and actual provider usage."""

import sqlite3
import time
import uuid
from dataclasses import dataclass, field

from empneon.core.contracts import CognitiveRequest
from empneon.core.scheduler.resources import ResourceEstimate
from empneon.providers.llm import GenerationResult


@dataclass(frozen=True)
class UsageRecord:
    request_id: str
    agent_id: str
    event_id: str
    provider: str
    model: str
    estimate: ResourceEstimate
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_ms: int | None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    recorded_at: int = field(default_factory=lambda: int(time.time()))


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
    ) -> UsageRecord:
        record = UsageRecord(
            request.id,
            request.agent_id,
            request.event.id,
            provider,
            model,
            estimate,
            result.prompt_tokens,
            result.completion_tokens,
            result.latency_ms,
        )
        self._conn.execute(
            "INSERT INTO cognition_usage VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
            ),
        )
        self._conn.commit()
        return record

    def get_for_request(self, request_id: str) -> list[UsageRecord]:
        rows = self._conn.execute(
            "SELECT * FROM cognition_usage WHERE request_id=? ORDER BY recorded_at, rowid",
            (request_id,),
        ).fetchall()
        return [_to_record(row) for row in rows]


def _to_record(row: sqlite3.Row) -> UsageRecord:
    return UsageRecord(
        id=row["id"],
        request_id=row["request_id"],
        agent_id=row["agent_id"],
        event_id=row["event_id"],
        provider=row["provider"],
        model=row["model"],
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
