import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable

import pytest

from empneon.providers.llm import (
    CircuitBreaker,
    CircuitBreakerPolicy,
    CircuitOpenError,
    GenerationRequest,
    GenerationResult,
    Message,
    ModelCapabilities,
    ProviderError,
    ResilientProvider,
    RetryPolicy,
)

REQUEST = GenerationRequest((Message("user", "hi"),), max_tokens=8)
NO_RETRY = RetryPolicy(max_attempts=1)


def down() -> ProviderError:
    return ProviderError("down", status=503)


class ScriptedStream:
    """Fake streaming provider: each attempt yields its strings and raises its exceptions."""

    capabilities = ModelCapabilities(streaming=True)

    def __init__(self, *attempts: list[str | BaseException]) -> None:
        self._attempts = list(attempts)
        self.calls = 0
        self.finished = 0

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        raise AssertionError("generate must not be used")

    async def health_check(self) -> bool:
        return True

    async def stream(self, request: GenerationRequest) -> AsyncIterator[str]:
        self.calls += 1
        try:
            for item in self._attempts.pop(0):
                if isinstance(item, BaseException):
                    raise item
                yield item
        finally:
            self.finished += 1


def provider(
    inner: ScriptedStream,
    delays: list[float] | None = None,
    policy: RetryPolicy | None = None,
    breaker: CircuitBreaker | None = None,
) -> ResilientProvider:
    async def sleep(seconds: float) -> None:
        if delays is not None:
            delays.append(seconds)

    return ResilientProvider(
        inner, policy or RetryPolicy(jitter=0.0), sleep=sleep, random=lambda: 0.5, breaker=breaker
    )


async def drain(
    wrapped: ResilientProvider, received: list[str] | None = None
) -> list[str]:
    received = [] if received is None else received
    async for chunk in wrapped.stream(REQUEST):  # type: ignore[attr-defined]
        received.append(chunk)
    return received


def run(coro: Awaitable[list[str]]) -> list[str]:
    return asyncio.run(coro)  # type: ignore[arg-type]


def test_retries_failure_before_the_first_chunk() -> None:
    inner = ScriptedStream([down()], [down()], ["a", "b"])
    delays: list[float] = []
    assert run(drain(provider(inner, delays))) == ["a", "b"]
    assert inner.calls == 3
    assert delays == [0.5, 1.0]


def test_exhausted_retries_before_first_chunk_reraise_last_error() -> None:
    last = ProviderError("last", status=502)
    inner = ScriptedStream([down()], [down()], [last])
    with pytest.raises(ProviderError) as info:
        run(drain(provider(inner)))
    assert info.value is last
    assert inner.calls == 3


def test_non_retryable_failure_before_first_chunk_is_not_retried() -> None:
    inner = ScriptedStream([ProviderError("bad", status=400)], ["never"])
    with pytest.raises(ProviderError):
        run(drain(provider(inner)))
    assert inner.calls == 1


def test_mid_stream_failure_is_never_retried() -> None:
    inner = ScriptedStream(["a", down()], ["a", "b"])
    delays: list[float] = []
    received: list[str] = []
    with pytest.raises(ProviderError):
        run(drain(provider(inner, delays), received))
    assert received == ["a"]
    assert inner.calls == 1
    assert delays == []


def test_empty_stream_succeeds() -> None:
    assert run(drain(provider(ScriptedStream([])))) == []


def test_inner_without_streaming_is_rejected() -> None:
    class NoStream:
        capabilities = ModelCapabilities()

        async def generate(self, request: GenerationRequest) -> GenerationResult:
            raise AssertionError

        async def health_check(self) -> bool:
            return True

    wrapped = ResilientProvider(NoStream(), NO_RETRY)
    with pytest.raises(TypeError):
        run(drain(wrapped))


def test_abandoned_stream_closes_the_inner_stream() -> None:
    inner = ScriptedStream(["a", "b"])

    async def scenario() -> None:
        stream = provider(inner).stream(REQUEST)  # type: ignore[attr-defined]
        assert await anext(stream) == "a"
        await stream.aclose()

    asyncio.run(scenario())
    assert inner.finished == 1


# --- circuit breaker interaction ---


def breaker(threshold: int = 2, clock: Callable[[], float] | None = None) -> CircuitBreaker:
    if clock is None:
        return CircuitBreaker(CircuitBreakerPolicy(threshold, 30.0))
    return CircuitBreaker(CircuitBreakerPolicy(threshold, 30.0), clock=clock)


def test_mid_stream_failures_open_the_circuit_then_fail_fast() -> None:
    inner = ScriptedStream(["a", down()], ["a", down()], ["never"])
    guard = breaker()
    wrapped = provider(inner, policy=NO_RETRY, breaker=guard)
    for _ in range(2):
        with pytest.raises(ProviderError):
            run(drain(wrapped))
    assert guard.state == "open"
    with pytest.raises(CircuitOpenError):
        run(drain(wrapped))
    assert inner.calls == 2


def test_retry_exhausted_stream_counts_one_breaker_failure() -> None:
    inner = ScriptedStream([down()], [down()], [down()], ["ok"])
    guard = breaker(threshold=2)
    wrapped = provider(inner, policy=RetryPolicy(jitter=0.0), breaker=guard)
    with pytest.raises(ProviderError):
        run(drain(wrapped))
    assert guard.state == "closed"
    assert inner.calls == 3


def test_completed_stream_resets_failure_count() -> None:
    inner = ScriptedStream([down()], ["a"], [down()])
    guard = breaker(threshold=2)
    wrapped = provider(inner, policy=NO_RETRY, breaker=guard)
    with pytest.raises(ProviderError):
        run(drain(wrapped))
    assert run(drain(wrapped)) == ["a"]
    with pytest.raises(ProviderError):
        run(drain(wrapped))
    assert guard.state == "closed"


def test_malformed_stream_payload_does_not_trip_the_breaker() -> None:
    inner = ScriptedStream(["a", ProviderError("bad payload")], ["b", ProviderError("bad")])
    guard = breaker(threshold=1)
    wrapped = provider(inner, policy=NO_RETRY, breaker=guard)
    for _ in range(2):
        with pytest.raises(ProviderError):
            run(drain(wrapped))
    assert guard.state == "closed"


def test_half_open_probe_stream_success_closes_the_circuit() -> None:
    now = [0.0]
    guard = breaker(threshold=1, clock=lambda: now[0])
    guard.acquire()
    guard.record_failure()
    now[0] = 31.0
    assert run(drain(provider(ScriptedStream(["a"]), policy=NO_RETRY, breaker=guard))) == ["a"]
    assert guard.state == "closed"


def test_abandoned_probe_stream_releases_the_probe_slot() -> None:
    now = [0.0]
    guard = breaker(threshold=1, clock=lambda: now[0])
    guard.acquire()
    guard.record_failure()
    now[0] = 31.0
    wrapped = provider(ScriptedStream(["a", "b"]), policy=NO_RETRY, breaker=guard)

    async def scenario() -> None:
        stream = wrapped.stream(REQUEST)  # type: ignore[attr-defined]
        assert await anext(stream) == "a"
        await stream.aclose()

    asyncio.run(scenario())
    guard.acquire()  # slot was not leaked
