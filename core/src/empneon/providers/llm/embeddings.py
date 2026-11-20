"""Embedding providers: turn text into vectors for semantic memory search."""

import logging
import math
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol

from empneon.providers.llm._http import guarded_generate, guarded_health, request_json
from empneon.providers.llm.base import ProviderError

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmbeddingResult:
    """One vector per input text, in input order."""

    vectors: tuple[tuple[float, ...], ...]
    prompt_tokens: int | None = None
    latency_ms: int | None = None

    @property
    def dimensions(self) -> int:
        return len(self.vectors[0]) if self.vectors else 0


class EmbeddingProvider(Protocol):
    """Minimal interface for turning texts into vectors."""

    async def embed(self, texts: Sequence[str]) -> EmbeddingResult: ...

    async def health_check(self) -> bool: ...


@dataclass(frozen=True)
class EmbeddingOutcome:
    """What one `embed` call cost and how it ended; never carries texts or vectors.

    `failure` uses the `DegradationReason` values (`provider_error`, `timeout`, `memory`,
    `invalid_output`), mirroring how failed generation degrades.
    """

    provider: str
    model: str
    input_count: int
    prompt_tokens: int | None
    latency_ms: int
    status: Literal["succeeded", "failed"]
    http_status: int | None
    failure: str | None


class EmbeddingUsageSink(Protocol):
    """Receives one outcome per metered `embed` call (for example `UsageStore.embedding_sink()`)."""

    def __call__(self, outcome: EmbeddingOutcome, /) -> None: ...


_FAILURE_REASONS: dict[type[BaseException], str] = {
    ProviderError: "provider_error",
    TimeoutError: "timeout",
    MemoryError: "memory",
    ValueError: "invalid_output",
}


def _failure_reason(error: BaseException) -> str | None:
    for kind, reason in _FAILURE_REASONS.items():
        if isinstance(error, kind):
            return reason
    return None


@dataclass(frozen=True)
class UsageMeteredEmbeddingProvider:
    """Reports one `EmbeddingOutcome` per `embed` call to a sink, outermost around any retries.

    Latency is wall-clock for the whole call, including retries and backoff. Results and errors
    pass through unchanged. Unmapped exceptions and cancellation report nothing. A sink that raises
    is ignored (only its exception type is logged), so metering can never fail an embedding.
    """

    inner: EmbeddingProvider
    provider: str
    model: str
    sink: EmbeddingUsageSink
    clock: Callable[[], float] = time.perf_counter

    async def embed(self, texts: Sequence[str]) -> EmbeddingResult:
        started = self.clock()
        try:
            result = await self.inner.embed(texts)
        except Exception as error:
            reason = _failure_reason(error)
            if reason is not None:
                self._report(texts, started, "failed", None, getattr(error, "status", None), reason)
            raise
        self._report(texts, started, "succeeded", result.prompt_tokens, None, None)
        return result

    async def health_check(self) -> bool:
        return await self.inner.health_check()

    def _report(
        self,
        texts: Sequence[str],
        started: float,
        status: Literal["succeeded", "failed"],
        prompt_tokens: int | None,
        http_status: int | None,
        failure: str | None,
    ) -> None:
        latency_ms = max(0, round((self.clock() - started) * 1000))
        outcome = EmbeddingOutcome(
            self.provider,
            self.model,
            max(1, len(texts)),
            prompt_tokens,
            latency_ms,
            status,
            http_status,
            failure,
        )
        try:
            self.sink(outcome)
        except Exception as exc:
            _log.warning("embedding usage sink failed: %s", type(exc).__name__)


@dataclass(frozen=True)
class OpenAICompatibleEmbeddingProvider:
    """Calls an OpenAI-style `/embeddings` endpoint (also LM Studio's `/v1` API).

    Vectors are L2-normalized by default so the vector store's Euclidean distance orders like
    cosine similarity. Inputs are split into `batch_size` requests. Invalid responses raise a
    non-transport `ProviderError`, which retry and circuit-breaker wrappers never count or retry.
    """

    base_url: str
    model: str
    api_key: str | None = field(default=None, repr=False)
    timeout_seconds: float = 90
    local: bool = False
    batch_size: int = 64
    normalize: bool = True
    dimensions: int | None = None

    def __post_init__(self) -> None:
        if self.batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        if self.dimensions is not None and self.dimensions < 1:
            raise ValueError("dimensions must be at least 1")

    async def embed(self, texts: Sequence[str]) -> EmbeddingResult:
        if not texts:
            raise ValueError("at least one text is required")
        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError("texts must be non-empty strings")
        batch = tuple(texts)
        return await guarded_generate(
            "OpenAI-compatible", lambda: self._embed(batch), operation="embedding"
        )

    async def health_check(self) -> bool:
        return await guarded_health("OpenAI-compatible", lambda: self._request("/models"))

    def _embed(self, texts: tuple[str, ...]) -> EmbeddingResult:
        started = time.perf_counter()
        vectors: list[tuple[float, ...]] = []
        tokens: int | None = 0
        for start in range(0, len(texts), self.batch_size):
            chunk = texts[start : start + self.batch_size]
            data = self._request("/embeddings", {"model": self.model, "input": list(chunk)})
            vectors.extend(_parse_vectors(data, len(chunk)))
            used = _prompt_tokens(data)
            tokens = None if tokens is None or used is None else tokens + used
        width = len(vectors[0])
        if any(len(vector) != width for vector in vectors):
            raise ValueError("embedding dimensions differ across batches")
        if self.dimensions is not None and width != self.dimensions:
            raise ValueError("embedding dimensions do not match the configured dimensions")
        if self.normalize:
            vectors = [_normalized(vector) for vector in vectors]
        latency_ms = max(0, round((time.perf_counter() - started) * 1000))
        return EmbeddingResult(tuple(vectors), tokens, latency_ms)

    def _request(self, path: str, body: dict[str, object] | None = None) -> dict[str, object]:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else None
        value = request_json(
            f"{self.base_url.rstrip('/')}{path}",
            body=body,
            headers=headers,
            timeout=self.timeout_seconds,
        )
        if not isinstance(value, dict):
            raise ValueError("embeddings endpoint returned a non-object response")
        return value


def _parse_vectors(data: dict[str, object], expected: int) -> list[tuple[float, ...]]:
    items = data.get("data")
    if not isinstance(items, list) or len(items) != expected:
        raise ValueError("embeddings response must hold one item per input")
    indexed: dict[int, tuple[float, ...]] = {}
    for position, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError("embeddings item must be an object")
        index = item.get("index", position)
        if isinstance(index, bool) or not isinstance(index, int) or index in indexed:
            raise ValueError("embeddings item has an invalid index")
        indexed[index] = _vector(item.get("embedding"))
    if set(indexed) != set(range(expected)):
        raise ValueError("embeddings indexes must cover every input")
    vectors = [indexed[index] for index in range(expected)]
    if any(len(vector) != len(vectors[0]) for vector in vectors):
        raise ValueError("embedding dimensions differ within a batch")
    return vectors


def _vector(value: object) -> tuple[float, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError("embedding must be a non-empty list")
    numbers: list[float] = []
    for number in value:
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            raise ValueError("embedding values must be numbers")
        if not math.isfinite(number):
            raise ValueError("embedding values must be finite")
        numbers.append(float(number))
    return tuple(numbers)


def _prompt_tokens(data: dict[str, object]) -> int | None:
    usage = data.get("usage")
    tokens = usage.get("prompt_tokens") if isinstance(usage, dict) else None
    return tokens if isinstance(tokens, int) and not isinstance(tokens, bool) else None


def _normalized(vector: tuple[float, ...]) -> tuple[float, ...]:
    norm = math.sqrt(sum(value * value for value in vector))
    return tuple(value / norm for value in vector) if norm else vector
