import asyncio
import logging
import threading

import pytest

from empneon.providers.llm import (
    BreakerRegistry,
    CircuitBreaker,
    CircuitBreakerPolicy,
    CircuitOpenError,
    ConfiguredProviderRouter,
    GenerationRequest,
    GenerationResult,
    Message,
    ModelCapabilities,
    OpenAICompatibleProvider,
    ProviderError,
    ResilientProvider,
    RetryPolicy,
)

SECRET = "super-secret-player-message"
REQUEST = GenerationRequest((Message("user", SECRET),), max_tokens=8)
OK = GenerationResult("ok", 1, 1, 1)
NO_RETRY = RetryPolicy(max_attempts=1)


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class Scripted:
    capabilities = ModelCapabilities(structured_output=True)

    def __init__(self, *outcomes: BaseException | GenerationResult) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    async def health_check(self) -> bool:
        return True


def down() -> ProviderError:
    return ProviderError("down", status=503)


def unreachable() -> ProviderError:
    return ProviderError("refused", transport=True)


def make(
    inner: Scripted, threshold: int = 2, reset_s: float = 30.0
) -> tuple[ResilientProvider, CircuitBreaker, Clock]:
    clock = Clock()
    breaker = CircuitBreaker(CircuitBreakerPolicy(threshold, reset_s), clock=clock)
    return ResilientProvider(inner, NO_RETRY, breaker=breaker), breaker, clock


def call(provider: ResilientProvider) -> GenerationResult:
    return asyncio.run(provider.generate(REQUEST))


def trip(provider: ResilientProvider, count: int) -> None:
    for _ in range(count):
        with pytest.raises(ProviderError):
            call(provider)


def test_opens_after_threshold_and_fails_fast_without_calling_provider() -> None:
    inner = Scripted(down(), unreachable(), OK)
    provider, breaker, _ = make(inner)
    trip(provider, 2)
    assert breaker.state == "open"

    with pytest.raises(CircuitOpenError):
        call(provider)
    assert inner.calls == 2


def test_open_circuit_fails_fast_without_retrying_or_sleeping() -> None:
    sleeps: list[float] = []

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    inner = Scripted()
    breaker = CircuitBreaker(CircuitBreakerPolicy(1, 30.0), clock=Clock())
    breaker.acquire()
    breaker.record_failure()
    provider = ResilientProvider(
        inner, RetryPolicy(max_attempts=5, base_delay_s=1.0), breaker=breaker, sleep=sleep
    )

    with pytest.raises(CircuitOpenError):
        call(provider)
    assert inner.calls == 0 and sleeps == []
    assert issubclass(CircuitOpenError, ProviderError)


def test_failure_is_counted_once_per_retry_exhausted_call() -> None:
    async def no_sleep(_: float) -> None:
        return None

    inner = Scripted(down(), down(), down(), down())
    breaker = CircuitBreaker(CircuitBreakerPolicy(2, 30.0), clock=Clock())
    provider = ResilientProvider(
        inner, RetryPolicy(max_attempts=2, base_delay_s=0.0, max_delay_s=0.0),
        breaker=breaker, sleep=no_sleep,
    )
    trip(provider, 1)  # two attempts, one counted failure
    assert breaker.state == "closed"
    trip(provider, 1)
    assert breaker.state == "open"


def test_success_resets_the_failure_count() -> None:
    inner = Scripted(down(), OK, down(), OK)
    provider, breaker, _ = make(inner, threshold=2)
    trip(provider, 1)
    assert call(provider) is OK
    trip(provider, 1)
    assert call(provider) is OK
    assert breaker.state == "closed"


def test_client_errors_and_bad_payloads_never_trip_the_breaker() -> None:
    inner = Scripted(
        ProviderError("bad", status=400), ProviderError("malformed"), ProviderError("x", status=401)
    )
    provider, breaker, _ = make(inner, threshold=1)
    trip(provider, 3)
    assert breaker.state == "closed"


def test_half_open_probe_success_closes_the_circuit() -> None:
    inner = Scripted(down(), down(), OK, OK)
    provider, breaker, clock = make(inner)
    trip(provider, 2)
    clock.now = 31.0

    assert call(provider) is OK
    assert breaker.state == "closed"
    assert call(provider) is OK


def test_half_open_probe_failure_reopens_for_a_full_timeout() -> None:
    inner = Scripted(down(), down(), down(), OK)
    provider, breaker, clock = make(inner)
    trip(provider, 2)
    clock.now = 31.0
    trip(provider, 1)
    assert breaker.state == "open"

    clock.now = 40.0  # less than reset_timeout_s after the failed probe
    with pytest.raises(CircuitOpenError):
        call(provider)
    clock.now = 62.0
    assert call(provider) is OK


def test_only_one_probe_is_allowed_while_half_open() -> None:
    breaker = CircuitBreaker(CircuitBreakerPolicy(1, 10.0), clock=(clock := Clock()))
    breaker.acquire()
    breaker.record_failure()
    clock.now = 11.0
    breaker.acquire()  # the single probe
    with pytest.raises(CircuitOpenError):
        breaker.acquire()


def test_cancelled_probe_releases_the_probe_slot() -> None:
    clock = Clock()
    breaker = CircuitBreaker(CircuitBreakerPolicy(1, 10.0), clock=clock)
    breaker.acquire()
    breaker.record_failure()
    clock.now = 11.0

    class Hanging(Scripted):
        async def generate(self, request: GenerationRequest) -> GenerationResult:
            await asyncio.sleep(60)
            return OK

    provider = ResilientProvider(Hanging(), NO_RETRY, breaker=breaker)

    async def scenario() -> None:
        task = asyncio.create_task(provider.generate(REQUEST))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    breaker.acquire()  # a new probe is allowed; the slot was not leaked


def test_transitions_are_logged_without_content(caplog: pytest.LogCaptureFixture) -> None:
    inner = Scripted(down(), down(), OK)
    provider, _, clock = make(inner)
    with caplog.at_level(logging.INFO, logger="empneon"):
        trip(provider, 2)
        clock.now = 31.0
        call(provider)
    assert "circuit opened" in caplog.text and "circuit closed" in caplog.text
    assert SECRET not in caplog.text


def test_breaker_is_thread_safe() -> None:
    breaker = CircuitBreaker(CircuitBreakerPolicy(50, 30.0))

    def worker() -> None:
        for _ in range(100):
            try:
                breaker.acquire()
            except CircuitOpenError:
                continue
            breaker.record_failure()

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert breaker.state == "open"


@pytest.mark.parametrize(
    "options",
    [{"failure_threshold": 0}, {"reset_timeout_s": 0.0}, {"reset_timeout_s": -1.0}],
)
def test_invalid_policy_is_rejected(options: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        CircuitBreakerPolicy(**options)  # type: ignore[arg-type]


def test_policy_defaults_and_mapping() -> None:
    assert CircuitBreakerPolicy() == CircuitBreakerPolicy(5, 30.0)
    assert CircuitBreakerPolicy.from_mapping({}) == CircuitBreakerPolicy(5, 30.0)
    assert CircuitBreakerPolicy.from_mapping(
        {"failure_threshold": 3, "reset_timeout_s": 60}
    ) == CircuitBreakerPolicy(3, 60.0)


@pytest.mark.parametrize(
    "value", ["yes", {"unknown": 1}, {"failure_threshold": True}, {"reset_timeout_s": "x"}]
)
def test_invalid_policy_mapping_is_rejected(value: object) -> None:
    with pytest.raises(ValueError, match="circuit_breaker"):
        CircuitBreakerPolicy.from_mapping(value)


def test_registry_shares_one_breaker_per_key_and_resets() -> None:
    registry = BreakerRegistry()
    policy = CircuitBreakerPolicy()
    first = registry.get(("lmstudio", "http://x", "m"), policy)
    assert registry.get(("lmstudio", "http://x", "m"), policy) is first
    assert registry.get(("lmstudio", "http://x", "other"), policy) is not first
    registry.reset()
    assert registry.get(("lmstudio", "http://x", "m"), policy) is not first


def _router(
    task: dict[str, object], registry: BreakerRegistry | None = None
) -> ConfiguredProviderRouter:
    return ConfiguredProviderRouter(
        "openai",
        {"openai": {"endpoint": "http://localhost:1234/v1", "model": "m"}},
        {"large": task},
        breakers=registry,
    )


def test_router_shares_breaker_state_across_router_instances() -> None:
    registry = BreakerRegistry()
    config = {"circuit_breaker": {"failure_threshold": 1}}
    first = _router(config, registry).provider_for("large")
    second = _router(config, registry).provider_for("large")
    assert isinstance(first, ResilientProvider) and isinstance(second, ResilientProvider)
    assert first.breaker is second.breaker is not None


def test_router_default_registry_is_shared_and_resettable() -> None:
    config = {"circuit_breaker": {}}
    first = _router(config).provider_for("large")
    second = _router(config).provider_for("large")
    assert isinstance(first, ResilientProvider) and isinstance(second, ResilientProvider)
    assert first.breaker is second.breaker
    BreakerRegistry.default().reset()
    third = _router(config).provider_for("large")
    assert isinstance(third, ResilientProvider) and third.breaker is not first.breaker


def test_router_without_circuit_breaker_config_has_no_breaker() -> None:
    assert isinstance(_router({}).provider_for("large"), OpenAICompatibleProvider)
    retry_only = _router({"retry": {}}).provider_for("large")
    assert isinstance(retry_only, ResilientProvider) and retry_only.breaker is None


def test_breaker_only_config_does_not_retry() -> None:
    provider = _router({"circuit_breaker": {}}, BreakerRegistry()).provider_for("large")
    assert isinstance(provider, ResilientProvider)
    assert provider.policy.max_attempts == 1


def test_router_rejects_invalid_circuit_breaker_config() -> None:
    with pytest.raises(ValueError, match="circuit_breaker"):
        _router({"circuit_breaker": {"failure_threshold": 0}}).provider_for("large")
