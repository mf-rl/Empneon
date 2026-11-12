import asyncio
import io
import logging
import urllib.error
from collections.abc import Callable
from unittest.mock import patch

import pytest

from empneon.providers.llm import (
    ConfiguredProviderRouter,
    GenerationRequest,
    GenerationResult,
    LMStudioProvider,
    Message,
    ModelCapabilities,
    OpenAICompatibleProvider,
    ProviderError,
    ResilientProvider,
    RetryPolicy,
)
from empneon.providers.llm._http import guarded_generate

SECRET = "super-secret-player-message"
REQUEST = GenerationRequest((Message("user", SECRET),), max_tokens=8)
OK = GenerationResult("ok", 1, 1, 1)


class Scripted:
    """Fake provider that raises or returns each scripted outcome in order."""

    capabilities = ModelCapabilities(structured_output=True, local=True)

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


def transient(status: int | None = 503, **extra: object) -> ProviderError:
    return ProviderError("failed", status=status, transport=status is None, **extra)  # type: ignore[arg-type]


def resilient(
    inner: Scripted, delays: list[float], **policy: object
) -> ResilientProvider:
    async def sleep(seconds: float) -> None:
        delays.append(seconds)

    options: dict[str, object] = {"jitter": 0.0, **policy}
    return ResilientProvider(inner, RetryPolicy(**options), sleep=sleep, random=lambda: 0.5)  # type: ignore[arg-type]


def run(provider: ResilientProvider) -> GenerationResult:
    return asyncio.run(provider.generate(REQUEST))


@pytest.mark.parametrize("failure", [transient(503), transient(429), transient(None)])
def test_succeeds_after_transient_failures(failure: ProviderError) -> None:
    inner = Scripted(failure, failure, OK)
    delays: list[float] = []
    assert run(resilient(inner, delays)) is OK
    assert inner.calls == 3
    assert delays == [0.5, 1.0]


def test_exhaustion_reraises_last_error() -> None:
    last = transient(502)
    inner = Scripted(transient(503), transient(503), last)
    with pytest.raises(ProviderError) as info:
        run(resilient(inner, []))
    assert info.value is last
    assert inner.calls == 3


@pytest.mark.parametrize(
    "failure",
    [
        ProviderError("bad", status=400),
        ProviderError("auth", status=401),
        ProviderError("missing", status=404),
        ProviderError("malformed payload"),
    ],
)
def test_non_transient_errors_are_not_retried(failure: ProviderError) -> None:
    inner = Scripted(failure)
    with pytest.raises(ProviderError):
        run(resilient(inner, []))
    assert inner.calls == 1


def test_backoff_is_exponential_and_capped() -> None:
    inner = Scripted(*[transient(503)] * 5, OK)
    delays: list[float] = []
    run(resilient(inner, delays, max_attempts=6, base_delay_s=1.0, max_delay_s=5.0))
    assert delays == [1.0, 2.0, 4.0, 5.0, 5.0]


def test_jitter_is_bounded() -> None:
    inner = Scripted(transient(503), OK)
    delays: list[float] = []
    provider = ResilientProvider(
        inner,
        RetryPolicy(base_delay_s=1.0, jitter=0.2),
        sleep=lambda seconds: _record(delays, seconds),
        random=lambda: 1.0,
    )
    asyncio.run(provider.generate(REQUEST))
    assert delays == [pytest.approx(1.2)]


async def _record(delays: list[float], seconds: float) -> None:
    delays.append(seconds)


def test_retry_after_is_honored_and_capped() -> None:
    inner = Scripted(transient(429, retry_after=3.0), transient(429, retry_after=99.0), OK)
    delays: list[float] = []
    run(resilient(inner, delays, max_delay_s=10.0))
    assert delays == [3.0, 10.0]


def test_retry_after_can_be_ignored() -> None:
    inner = Scripted(transient(429, retry_after=3.0), OK)
    delays: list[float] = []
    run(resilient(inner, delays, respect_retry_after=False))
    assert delays == [0.5]


def test_single_attempt_behaves_like_the_inner_provider() -> None:
    inner = Scripted(transient(503))
    with pytest.raises(ProviderError):
        run(resilient(inner, [], max_attempts=1))
    assert inner.calls == 1


def test_cancellation_during_backoff_stops_retrying() -> None:
    inner = Scripted(transient(503), OK)

    async def scenario() -> None:
        gate = asyncio.Event()

        async def blocked_sleep(_: float) -> None:
            gate.set()
            await asyncio.sleep(60)

        provider = ResilientProvider(inner, RetryPolicy(), sleep=blocked_sleep)
        task = asyncio.create_task(provider.generate(REQUEST))
        await gate.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    assert inner.calls == 1


def test_retries_are_logged_without_content(caplog: pytest.LogCaptureFixture) -> None:
    inner = Scripted(transient(503), OK)
    with caplog.at_level(logging.WARNING, logger="empneon"):
        run(resilient(inner, []))
    assert "retrying" in caplog.text and "503" in caplog.text
    assert SECRET not in caplog.text


def test_capabilities_and_health_delegate() -> None:
    inner = Scripted()
    provider = resilient(inner, [])
    assert provider.capabilities is inner.capabilities
    assert asyncio.run(provider.health_check()) is True


@pytest.mark.parametrize(
    "options",
    [
        {"max_attempts": 0},
        {"base_delay_s": -1.0},
        {"max_delay_s": -1.0},
        {"jitter": 1.5},
        {"base_delay_s": 5.0, "max_delay_s": 1.0},
    ],
)
def test_invalid_policy_is_rejected(options: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        RetryPolicy(**options)  # type: ignore[arg-type]


def _http_error(status: int, headers: dict[str, str] | None = None) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("http://x", status, "err", headers or {}, io.BytesIO(b""))  # type: ignore[arg-type]


def _classify(failure: BaseException) -> ProviderError:
    def call() -> object:
        raise failure

    with pytest.raises(ProviderError) as info:
        asyncio.run(guarded_generate("Test", call))
    return info.value


def test_http_error_carries_status_and_retry_after() -> None:
    error = _classify(_http_error(503, {"Retry-After": "2"}))
    assert (error.status, error.retry_after, error.transport) == (503, 2.0, False)


@pytest.mark.parametrize("value", ["soon", "Wed, 21 Oct 2026 07:28:00 GMT", "-3", ""])
def test_unusable_retry_after_is_ignored(value: str) -> None:
    assert _classify(_http_error(429, {"Retry-After": value})).retry_after is None


def test_connection_failures_are_transport_errors() -> None:
    error = _classify(urllib.error.URLError("refused"))
    assert (error.status, error.transport) == (None, True)
    assert _classify(TimeoutError()).transport is True


def test_malformed_payload_is_not_a_transport_error() -> None:
    assert _classify(ValueError("bad json")).transport is False


def _router(extra: dict[str, object] | None = None) -> ConfiguredProviderRouter:
    config: dict[str, object] = {"endpoint": "http://localhost:1234/v1", "model": "m"}
    task: dict[str, object] = dict(extra or {})
    return ConfiguredProviderRouter("openai", {"openai": config}, {"large": task})


def test_router_wraps_only_when_retry_is_configured() -> None:
    assert isinstance(_router().provider_for("large"), OpenAICompatibleProvider)
    wrapped = _router({"retry": {"max_attempts": 4, "base_delay_s": 0.1}}).provider_for("large")
    assert isinstance(wrapped, ResilientProvider)
    assert wrapped.capabilities.local is True


def test_router_wraps_lmstudio_too() -> None:
    router = ConfiguredProviderRouter(
        "lmstudio",
        {"lmstudio": {"endpoint": "http://127.0.0.1:1234/api/v1", "model": "m"}},
        {"large": {"retry": {}}},
    )
    provider = router.provider_for("large")
    assert isinstance(provider, ResilientProvider)
    assert isinstance(provider.inner, LMStudioProvider)


@pytest.mark.parametrize(
    "retry",
    [{"max_attempts": 0}, {"unknown_key": 1}, {"jitter": "x"}, "yes", {"max_attempts": True}],
)
def test_router_rejects_invalid_retry_config(retry: object) -> None:
    with pytest.raises(ValueError, match="retry"):
        _router({"retry": retry}).provider_for("large")


def test_end_to_end_retry_over_http_errors() -> None:
    provider = ResilientProvider(
        OpenAICompatibleProvider("http://x/v1", "m"),
        RetryPolicy(base_delay_s=0.0, max_delay_s=0.0, jitter=0.0),
    )

    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def read(self) -> bytes:
            return b'{"choices":[{"message":{"content":"hi"}}]}'

    outcomes: list[Callable[[], object]] = [
        lambda: (_ for _ in ()).throw(_http_error(503)),
        lambda: Response(),
    ]

    def fake_urlopen(*args: object, **kwargs: object) -> object:
        return outcomes.pop(0)()

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        assert asyncio.run(provider.generate(REQUEST)).content == "hi"
