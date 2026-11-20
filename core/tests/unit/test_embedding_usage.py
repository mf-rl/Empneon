import asyncio
import logging
import sqlite3
from collections.abc import Sequence

import pytest

from empneon.core.contracts import CognitiveRequest, DegradationReason, WorldEvent
from empneon.core.identity.models import Agent
from empneon.core.identity.store import AgentStore
from empneon.core.memory.episodic import EpisodicMemoryStore, Event
from empneon.core.memory.semantic import SemanticMemoryIndex
from empneon.core.scheduler.resources import ResourceEstimate
from empneon.core.scheduler.usage import UsageStore
from empneon.db.connection import open_db
from empneon.providers.llm import (
    CircuitOpenError,
    ConfiguredProviderRouter,
    EmbeddingOutcome,
    EmbeddingResult,
    GenerationResult,
    OpenAICompatibleEmbeddingProvider,
    ProviderError,
    ResilientEmbeddingProvider,
    RetryPolicy,
    UsageMeteredEmbeddingProvider,
)
from empneon.providers.llm.embeddings import _FAILURE_REASONS

SECRET = "super-secret-embedded-text"


class Inner:
    def __init__(self, *outcomes: BaseException | EmbeddingResult) -> None:
        self._outcomes = list(outcomes)

    async def embed(self, texts: Sequence[str]) -> EmbeddingResult:
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    async def health_check(self) -> bool:
        return True


class Clock:
    def __init__(self, *ticks: float) -> None:
        self._ticks = list(ticks)

    def __call__(self) -> float:
        return self._ticks.pop(0)


OK = EmbeddingResult(((1.0,), (2.0,)), 7, 3)


def metered(
    inner: Inner, sink: list[EmbeddingOutcome], clock: Clock | None = None
) -> UsageMeteredEmbeddingProvider:
    return UsageMeteredEmbeddingProvider(
        inner, provider="prov", model="mod", sink=sink.append, clock=clock or Clock(0.0, 0.25)
    )


def embed(provider: UsageMeteredEmbeddingProvider, *texts: str) -> EmbeddingResult:
    return asyncio.run(provider.embed(texts or ("a", "b")))


def test_success_is_reported_once_and_the_result_is_unchanged() -> None:
    sink: list[EmbeddingOutcome] = []

    result = embed(metered(Inner(OK), sink))

    assert result is OK
    assert sink == [
        EmbeddingOutcome("prov", "mod", 2, 7, 250, "succeeded", None, None)
    ]


@pytest.mark.parametrize(
    ("error", "reason", "status"),
    [
        (ProviderError("x", status=503), "provider_error", 503),
        (ProviderError("x", transport=True), "provider_error", None),
        (CircuitOpenError("open"), "provider_error", None),
        (TimeoutError(), "timeout", None),
        (MemoryError(), "memory", None),
        (ValueError(SECRET), "invalid_output", None),
    ],
)
def test_failures_map_to_a_degradation_reason(
    error: BaseException, reason: str, status: int | None
) -> None:
    sink: list[EmbeddingOutcome] = []

    with pytest.raises(type(error)):
        embed(metered(Inner(error), sink))

    (outcome,) = sink
    assert (outcome.status, outcome.failure, outcome.http_status) == ("failed", reason, status)
    assert outcome.prompt_tokens is None and outcome.latency_ms == 250


def test_failure_reasons_match_the_degradation_enum() -> None:
    assert set(_FAILURE_REASONS.values()) <= {reason.value for reason in DegradationReason}


@pytest.mark.parametrize("error", [RuntimeError("bug"), asyncio.CancelledError()])
def test_unmapped_errors_and_cancellation_report_nothing(error: BaseException) -> None:
    sink: list[EmbeddingOutcome] = []

    with pytest.raises(type(error)):
        embed(metered(Inner(error), sink))

    assert sink == []


def test_a_raising_sink_never_changes_the_result_or_leaks(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broken(_: EmbeddingOutcome) -> None:
        raise RuntimeError(SECRET)

    caplog.set_level(logging.DEBUG)
    provider = UsageMeteredEmbeddingProvider(
        Inner(OK), provider="p", model="m", sink=broken, clock=Clock(0.0, 1.0)
    )

    assert asyncio.run(provider.embed([SECRET])) is OK
    assert "RuntimeError" in caplog.text
    assert SECRET not in caplog.text


def test_inputs_and_vectors_are_never_logged(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    sink: list[EmbeddingOutcome] = []
    with pytest.raises(ValueError):
        embed(metered(Inner(ValueError(SECRET)), sink), SECRET)
    embed(metered(Inner(OK), sink), SECRET)
    assert SECRET not in caplog.text and "1.0" not in caplog.text


def test_retries_are_one_row_with_wall_clock_latency() -> None:
    sink: list[EmbeddingOutcome] = []
    resilient = ResilientEmbeddingProvider(
        Inner(ProviderError("x", status=503), OK),
        _policy(),
        sleep=_no_sleep,
        random=lambda: 0.5,
    )
    provider = UsageMeteredEmbeddingProvider(
        resilient, provider="p", model="m", sink=sink.append, clock=Clock(0.0, 2.0)
    )

    assert asyncio.run(provider.embed(["a", "b"])) is OK
    assert [(o.status, o.latency_ms) for o in sink] == [("succeeded", 2000)]


def _policy() -> RetryPolicy:
    return RetryPolicy(max_attempts=3, jitter=0.0)


async def _no_sleep(_: float) -> None:
    return None


def test_health_check_delegates() -> None:
    assert asyncio.run(metered(Inner(), []).health_check()) is True


# ---- store -------------------------------------------------------------------------------


def outcome(**overrides: object) -> EmbeddingOutcome:
    values: dict[str, object] = {
        "provider": "p",
        "model": "m",
        "input_count": 2,
        "prompt_tokens": 7,
        "latency_ms": 40,
        "status": "succeeded",
        "http_status": None,
        "failure": None,
    }
    values.update(overrides)
    return EmbeddingOutcome(**values)  # type: ignore[arg-type]


def test_record_embedding_round_trips_into_telemetry() -> None:
    conn = open_db(":memory:")
    store = UsageStore(conn)
    store.record_embedding(outcome())
    store.record_embedding(outcome(prompt_tokens=None, latency_ms=10))
    store.record_embedding(
        outcome(status="failed", failure="provider_error", http_status=503, latency_ms=5)
    )
    store.record_embedding(outcome(status="failed", failure="timeout", prompt_tokens=None))

    assert store.telemetry()["embeddings"] == {
        "calls": 4,
        "by_status": {"succeeded": 2, "failed": 2},
        "by_degradation": {"provider_error": 1, "timeout": 1},
        "prompt_tokens": 14,
        "latency_ms": 40 + 10 + 5 + 40,
    }


def test_embeddings_telemetry_is_empty_and_not_agent_scoped() -> None:
    store = UsageStore(open_db(":memory:"))
    assert store.telemetry()["embeddings"] == {
        "calls": 0,
        "by_status": {},
        "by_degradation": {},
        "prompt_tokens": 0,
        "latency_ms": 0,
    }
    assert "embeddings" not in store.telemetry("agent-a")


def test_embedding_rows_do_not_change_generation_aggregates() -> None:
    store = UsageStore(open_db(":memory:"))
    request = CognitiveRequest("alice", 3, WorldEvent("conversation", id="event-1"))
    store.record(request, ResourceEstimate(), "prov", "mod", GenerationResult("x", 3, 4, 50), 3)
    before = {k: v for k, v in store.telemetry().items() if k != "embeddings"}

    store.record_embedding(outcome())
    store.record_embedding(outcome(status="failed", failure="timeout"))

    assert {k: v for k, v in store.telemetry().items() if k != "embeddings"} == before


def test_record_embedding_rejects_inconsistent_outcomes() -> None:
    store = UsageStore(open_db(":memory:"))
    with pytest.raises(ValueError):
        store.record_embedding(outcome(status="failed", failure=None))
    with pytest.raises(ValueError):
        store.record_embedding(outcome(failure="timeout"))
    with pytest.raises(ValueError):
        store.record_embedding(outcome(status="failed", failure="because"))


def test_sink_writes_and_commits_when_no_transaction_is_open() -> None:
    conn = open_db(":memory:")
    UsageStore(conn).embedding_sink()(outcome())
    assert not conn.in_transaction
    assert conn.execute("SELECT count(*) FROM embedding_usage").fetchone()[0] == 1


def test_sink_never_commits_a_callers_open_transaction() -> None:
    conn = open_db(":memory:")
    conn.execute("INSERT INTO schema_version VALUES (99)")  # opens a caller transaction
    assert conn.in_transaction

    UsageStore(conn).embedding_sink()(outcome())

    assert conn.in_transaction
    conn.rollback()
    assert conn.execute("SELECT count(*) FROM embedding_usage").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM schema_version WHERE version=99").fetchone()[0] == 0


# ---- router and semantic index ------------------------------------------------------------


def router(task: dict[str, object]) -> ConfiguredProviderRouter:
    return ConfiguredProviderRouter(
        "openai",
        {"openai": {"endpoint": "http://localhost:1234/v1", "model": "chat"}},
        {"embedding": {"model": "embed-model", **task}},
    )


def test_router_wraps_only_when_a_sink_is_supplied() -> None:
    assert isinstance(router({}).embedding_provider_for(), OpenAICompatibleEmbeddingProvider)

    sink: list[EmbeddingOutcome] = []
    plain = router({}).embedding_provider_for(usage=sink.append)
    assert isinstance(plain, UsageMeteredEmbeddingProvider)
    assert isinstance(plain.inner, OpenAICompatibleEmbeddingProvider)
    assert (plain.provider, plain.model) == ("openai", "embed-model")

    retried = router({"retry": {}}).embedding_provider_for(usage=sink.append)
    assert isinstance(retried, UsageMeteredEmbeddingProvider)
    assert isinstance(retried.inner, ResilientEmbeddingProvider)


class FakeEmbedder:
    def __init__(self, failure: BaseException | None = None) -> None:
        self.failure = failure

    async def embed(self, texts: Sequence[str]) -> EmbeddingResult:
        if self.failure is not None:
            raise self.failure
        return EmbeddingResult(tuple((float(len(t)), 1.0) for t in texts), len(texts), 1)

    async def health_check(self) -> bool:
        return True


def _index(
    failure: BaseException | None = None,
) -> tuple[sqlite3.Connection, SemanticMemoryIndex]:
    conn = open_db(":memory:")
    AgentStore(conn).create(Agent("alice", "Alice"))
    EpisodicMemoryStore(conn).create(Event("Alice met Bob", ["alice"], happened_at=1, id="e1"))
    embedder = UsageMeteredEmbeddingProvider(
        FakeEmbedder(failure),
        provider="p",
        model="m",
        sink=UsageStore(conn).embedding_sink(),
    )
    return conn, SemanticMemoryIndex(conn, embedder)


def _calls(conn: sqlite3.Connection) -> list[tuple[object, ...]]:
    rows = conn.execute(
        "SELECT status, input_count, degradation_reason FROM embedding_usage ORDER BY rowid"
    )
    return [tuple(row) for row in rows]


def test_semantic_index_and_search_each_write_one_usage_row() -> None:
    conn, index = _index()

    asyncio.run(index.index_unindexed())
    asyncio.run(index.search("alice", "met"))

    assert _calls(conn) == [("succeeded", 1, None), ("succeeded", 1, None)]


def test_a_failed_embed_writes_a_failed_row_and_no_vectors() -> None:
    conn, index = _index(ProviderError("down", status=503))

    with pytest.raises(ProviderError):
        asyncio.run(index.index_unindexed())

    assert _calls(conn) == [("failed", 1, "provider_error")]
    vectors = conn.execute("SELECT name FROM sqlite_master WHERE name='vec_memory_index'")
    assert vectors.fetchone() is None


def test_usage_rows_survive_a_callers_rollback_only_when_no_transaction_was_open() -> None:
    conn, index = _index()
    conn.execute("INSERT INTO schema_version VALUES (99)")  # caller owns an open transaction

    asyncio.run(index.index_unindexed(commit=False))
    assert conn.in_transaction
    conn.rollback()

    assert _calls(conn) == []
