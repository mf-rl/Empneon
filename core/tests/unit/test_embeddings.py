import asyncio
import io
import json
import logging
import math
import urllib.error
from collections.abc import Sequence
from email.message import Message
from unittest.mock import patch

import pytest

import empneon.providers.llm as llm
from empneon.providers.llm import (
    BreakerRegistry,
    CircuitBreaker,
    CircuitBreakerPolicy,
    CircuitOpenError,
    ConfiguredProviderRouter,
    EmbeddingProvider,
    EmbeddingResult,
    OpenAICompatibleEmbeddingProvider,
    ProviderError,
    ResilientEmbeddingProvider,
    RetryPolicy,
)

SECRET_TEXT = "super-secret-memory-text"
SECRET_KEY = "sk-secret-key-123"


class Response:
    def __init__(self, payload: object) -> None:
        self._body = json.dumps(payload).encode()

    def __enter__(self) -> "Response":
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def read(self) -> bytes:
        return self._body


def payload(vectors: Sequence[Sequence[float]], *, tokens: int | None = None) -> dict[str, object]:
    data: dict[str, object] = {
        "data": [{"index": i, "embedding": list(v)} for i, v in enumerate(vectors)]
    }
    if tokens is not None:
        data["usage"] = {"prompt_tokens": tokens}
    return data


def provider(
    *,
    api_key: str | None = None,
    normalize: bool = True,
    batch_size: int = 64,
    dimensions: int | None = None,
) -> OpenAICompatibleEmbeddingProvider:
    return OpenAICompatibleEmbeddingProvider(
        "http://x/v1",
        "embed-model",
        api_key=api_key,
        batch_size=batch_size,
        normalize=normalize,
        dimensions=dimensions,
    )


def embed(target: EmbeddingProvider, *texts: str) -> EmbeddingResult:
    return asyncio.run(target.embed(texts))


def http_error(status: int, headers: dict[str, str] | None = None) -> urllib.error.HTTPError:
    message = Message()
    for name, value in (headers or {}).items():
        message[name] = value
    return urllib.error.HTTPError(
        "http://x", status, "err", message, io.BytesIO(SECRET_TEXT.encode())
    )


def test_request_shape_and_result_fields() -> None:
    target = provider(api_key=SECRET_KEY, normalize=False)
    reply = Response(payload([[1, 2], [3, 4]], tokens=7))
    with patch("urllib.request.urlopen", return_value=reply) as urlopen:
        result = embed(target, "alpha", "beta")

    request = urlopen.call_args.args[0]
    assert request.full_url == "http://x/v1/embeddings"
    assert request.get_method() == "POST"
    assert request.get_header("Authorization") == f"Bearer {SECRET_KEY}"
    assert json.loads(request.data) == {"model": "embed-model", "input": ["alpha", "beta"]}
    assert result.vectors == ((1.0, 2.0), (3.0, 4.0))
    assert result.dimensions == 2
    assert result.prompt_tokens == 7
    assert result.latency_ms is not None and result.latency_ms >= 0


def test_vectors_follow_input_order_even_if_response_is_shuffled() -> None:
    shuffled = {"data": [{"index": 1, "embedding": [2.0]}, {"index": 0, "embedding": [1.0]}]}
    with patch("urllib.request.urlopen", return_value=Response(shuffled)):
        assert embed(provider(normalize=False), "a", "b").vectors == ((1.0,), (2.0,))


def test_vectors_are_l2_normalized_by_default_and_zero_is_unchanged() -> None:
    with patch("urllib.request.urlopen", return_value=Response(payload([[3, 4], [0, 0]]))):
        first, zero = embed(provider(), "a", "b").vectors
    assert first == pytest.approx((0.6, 0.8))
    assert math.isclose(sum(v * v for v in first), 1.0)
    assert zero == (0.0, 0.0)


def test_large_inputs_are_split_into_ordered_batches() -> None:
    def batch(start: int, count: int) -> Response:
        return Response(payload([[float(start + i), 1.0] for i in range(count)], tokens=count))

    responses = [batch(0, 64), batch(64, 64), batch(128, 2)]
    texts = [f"text-{i}" for i in range(130)]
    with patch("urllib.request.urlopen", side_effect=responses) as urlopen:
        result = embed(provider(batch_size=64, normalize=False), *texts)

    assert urlopen.call_count == 3
    assert [json.loads(call.args[0].data)["input"][0] for call in urlopen.call_args_list] == [
        "text-0",
        "text-64",
        "text-128",
    ]
    assert [v[0] for v in result.vectors] == [float(i) for i in range(130)]
    assert result.prompt_tokens == 130


def test_missing_usage_in_any_batch_makes_total_tokens_unknown() -> None:
    responses = [Response(payload([[1.0]], tokens=1)), Response(payload([[1.0]]))]
    with patch("urllib.request.urlopen", side_effect=responses):
        assert embed(provider(batch_size=1), "a", "b").prompt_tokens is None


@pytest.mark.parametrize(
    "body",
    [
        {"data": []},
        {"data": [{"index": 0, "embedding": [1.0]}]},
        {"data": [{"index": 0, "embedding": [1.0]}, {"index": 5, "embedding": [1.0]}]},
        {"data": [{"index": 0, "embedding": []}, {"index": 1, "embedding": []}]},
        {"data": [{"index": 0, "embedding": "no"}, {"index": 1, "embedding": [1.0]}]},
        {"data": [{"index": 0, "embedding": [True]}, {"index": 1, "embedding": [1.0]}]},
        {"data": [{"index": 0, "embedding": [1.0, 2.0]}, {"index": 1, "embedding": [1.0]}]},
        {"data": "nope"},
        {},
    ],
)
def test_invalid_responses_are_non_retryable_provider_errors(body: dict[str, object]) -> None:
    with (
        patch("urllib.request.urlopen", return_value=Response(body)),
        pytest.raises(ProviderError) as info,
    ):
        embed(provider(), "a", "b")
    assert (info.value.status, info.value.transport) == (None, False)


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_non_finite_values_are_rejected(bad: float) -> None:
    literal = "NaN" if math.isnan(bad) else "Infinity"
    raw = f'{{"data": [{{"index": 0, "embedding": [{literal}]}}]}}'

    class Raw(Response):
        def __init__(self) -> None:
            self._body = raw.encode()

    with patch("urllib.request.urlopen", return_value=Raw()), pytest.raises(ProviderError):
        embed(provider(), "a")


def test_configured_dimensions_must_match() -> None:
    with (
        patch("urllib.request.urlopen", return_value=Response(payload([[1.0, 2.0]]))),
        pytest.raises(ProviderError),
    ):
        embed(provider(dimensions=3), "a")
    with patch("urllib.request.urlopen", return_value=Response(payload([[1.0, 2.0]]))):
        assert embed(provider(dimensions=2), "a").dimensions == 2


@pytest.mark.parametrize("texts", [(), ("",), ("  ",), ("ok", "")])
def test_invalid_inputs_fail_before_any_network_call(texts: tuple[str, ...]) -> None:
    with patch("urllib.request.urlopen") as urlopen, pytest.raises(ValueError):
        asyncio.run(provider().embed(texts))
    urlopen.assert_not_called()


def test_invalid_options_are_rejected() -> None:
    with pytest.raises(ValueError, match="batch_size"):
        provider(batch_size=0)
    with pytest.raises(ValueError, match="dimensions"):
        provider(dimensions=0)


def test_http_errors_expose_status_and_retry_after_without_leaking(
    caplog: pytest.LogCaptureFixture,
) -> None:
    target = provider(api_key=SECRET_KEY)
    with (
        patch("urllib.request.urlopen", side_effect=http_error(429, {"Retry-After": "3"})),
        caplog.at_level(logging.DEBUG, logger="empneon"),
        pytest.raises(ProviderError) as info,
    ):
        embed(target, SECRET_TEXT)

    assert (info.value.status, info.value.retry_after) == (429, 3.0)
    assert "embedding failed" in str(info.value)
    assert SECRET_TEXT not in caplog.text and SECRET_KEY not in caplog.text
    assert SECRET_KEY not in repr(target)


def test_connection_failures_are_transport_errors_and_bad_schemes_are_rejected() -> None:
    with patch("urllib.request.urlopen", side_effect=OSError), pytest.raises(ProviderError) as info:
        embed(provider(), "a")
    assert info.value.transport is True

    bad = OpenAICompatibleEmbeddingProvider("file:///etc", "m")
    with patch("urllib.request.urlopen") as urlopen, pytest.raises(ProviderError):
        embed(bad, "a")
    urlopen.assert_not_called()


def test_health_check_probes_models_and_never_raises() -> None:
    with patch("urllib.request.urlopen", return_value=Response({})) as urlopen:
        assert asyncio.run(provider().health_check()) is True
    assert urlopen.call_args.args[0].full_url == "http://x/v1/models"
    with patch("urllib.request.urlopen", side_effect=OSError):
        assert asyncio.run(provider().health_check()) is False


# ---- resilience ----------------------------------------------------------------------------


class Scripted:
    def __init__(self, *outcomes: BaseException | EmbeddingResult) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0

    async def embed(self, texts: Sequence[str]) -> EmbeddingResult:
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    async def health_check(self) -> bool:
        return True


OK = EmbeddingResult(((1.0,),), 1, 1)


def resilient(
    inner: Scripted,
    delays: list[float],
    *,
    breaker: CircuitBreaker | None = None,
    max_attempts: int = 3,
) -> ResilientEmbeddingProvider:
    async def sleep(seconds: float) -> None:
        delays.append(seconds)

    return ResilientEmbeddingProvider(
        inner,
        RetryPolicy(max_attempts=max_attempts, jitter=0.0),
        sleep=sleep,
        random=lambda: 0.5,
        breaker=breaker,
    )


@pytest.mark.parametrize(
    "failure",
    [
        ProviderError("down", status=503),
        ProviderError("slow", status=429, retry_after=2.0),
        ProviderError("refused", transport=True),
    ],
)
def test_transient_failures_are_retried(failure: ProviderError) -> None:
    inner = Scripted(failure, OK)
    delays: list[float] = []
    assert embed(resilient(inner, delays), "a") is OK
    assert inner.calls == 2
    assert delays == [2.0 if failure.retry_after else 0.5]


@pytest.mark.parametrize(
    "failure", [ProviderError("bad", status=400), ProviderError("malformed payload")]
)
def test_client_errors_and_bad_payloads_are_not_retried(failure: ProviderError) -> None:
    inner = Scripted(failure)
    with pytest.raises(ProviderError):
        embed(resilient(inner, []), "a")
    assert inner.calls == 1


def test_circuit_breaker_fails_fast_for_embeddings() -> None:
    inner = Scripted(ProviderError("down", status=503), ProviderError("down", status=503))
    breaker = CircuitBreaker(CircuitBreakerPolicy(2, 30.0), clock=lambda: 0.0)
    target = resilient(inner, [], breaker=breaker, max_attempts=1)
    for _ in range(2):
        with pytest.raises(ProviderError):
            embed(target, "a")
    with pytest.raises(CircuitOpenError):
        embed(target, "a")
    assert inner.calls == 2


def test_cancelled_probe_releases_the_breaker_slot() -> None:
    clock = [0.0]
    breaker = CircuitBreaker(CircuitBreakerPolicy(1, 10.0), clock=lambda: clock[0])
    breaker.acquire()
    breaker.record_failure()
    clock[0] = 11.0

    class Hanging(Scripted):
        async def embed(self, texts: Sequence[str]) -> EmbeddingResult:
            await asyncio.sleep(60)
            return OK

    target = ResilientEmbeddingProvider(Hanging(), RetryPolicy(max_attempts=1), breaker=breaker)

    async def scenario() -> None:
        task = asyncio.create_task(target.embed(["a"]))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    breaker.acquire()  # a new probe is allowed


# ---- router --------------------------------------------------------------------------------


def router(
    embedding: dict[str, object] | None,
    *,
    default: str = "openai",
    endpoint: str = "http://localhost:1234/v1",
    registry: BreakerRegistry | None = None,
) -> ConfiguredProviderRouter:
    tasks: dict[str, dict[str, object]] = {"large": {"circuit_breaker": {}}}
    if embedding is not None:
        tasks["embedding"] = embedding
    return ConfiguredProviderRouter(
        default,
        {default: {"endpoint": endpoint, "model": "chat-model", "api_key": SECRET_KEY}},
        tasks,
        breakers=registry,
    )


def test_router_builds_an_embedding_provider_from_the_embedding_task() -> None:
    built = router({"model": "embed-model", "dimensions": 8, "batch_size": 16, "normalize": False})
    target = built.embedding_provider_for()
    assert isinstance(target, OpenAICompatibleEmbeddingProvider)
    assert (target.base_url, target.model) == ("http://localhost:1234/v1", "embed-model")
    assert (target.dimensions, target.batch_size, target.normalize) == (8, 16, False)
    assert target.api_key == SECRET_KEY and target.local is True


def test_router_requires_an_explicit_embedding_task_and_never_reuses_the_chat_model() -> None:
    with pytest.raises(ValueError, match="embedding"):
        router(None).embedding_provider_for()
    with pytest.raises(ValueError, match="embedding"):
        router({"dimensions": 8}).embedding_provider_for()


def test_router_rewrites_lmstudio_native_endpoint_to_the_openai_compatible_one() -> None:
    built = router(
        {"model": "nomic"}, default="lmstudio", endpoint="http://127.0.0.1:1234/api/v1"
    )
    target = built.embedding_provider_for()
    assert isinstance(target, OpenAICompatibleEmbeddingProvider)
    assert target.base_url == "http://127.0.0.1:1234/v1"


@pytest.mark.parametrize(
    "extra",
    [
        {"dimensions": 0},
        {"dimensions": "x"},
        {"dimensions": True},
        {"batch_size": 0},
        {"batch_size": 1.5},
        {"normalize": "yes"},
    ],
)
def test_router_rejects_invalid_embedding_options(extra: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="embedding"):
        router({"model": "embed-model", **extra}).embedding_provider_for()


def test_router_wraps_with_retry_and_a_breaker_separate_from_chat() -> None:
    registry = BreakerRegistry()
    built = router({"model": "embed-model", "retry": {}, "circuit_breaker": {}}, registry=registry)
    first = built.embedding_provider_for()
    again = router(
        {"model": "embed-model", "retry": {}, "circuit_breaker": {}}, registry=registry
    ).embedding_provider_for()
    chat = built.provider_for("large")

    assert isinstance(first, ResilientEmbeddingProvider)
    assert isinstance(again, ResilientEmbeddingProvider)
    assert first.breaker is again.breaker is not None
    assert first.breaker is not getattr(chat, "breaker", None)
    assert isinstance(first.inner, OpenAICompatibleEmbeddingProvider)


def test_router_returns_the_plain_provider_without_resilience_blocks() -> None:
    target = router({"model": "embed-model"}).embedding_provider_for()
    assert isinstance(target, OpenAICompatibleEmbeddingProvider)


def test_new_names_are_part_of_the_llm_namespace() -> None:
    for name in (
        "EmbeddingProvider",
        "EmbeddingResult",
        "OpenAICompatibleEmbeddingProvider",
        "ResilientEmbeddingProvider",
        "EmbeddingOutcome",
        "EmbeddingUsageSink",
        "UsageMeteredEmbeddingProvider",
    ):
        assert name in llm.__all__
