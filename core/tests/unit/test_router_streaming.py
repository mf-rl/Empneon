import pytest

from empneon.providers.llm import (
    ConfiguredProviderRouter,
    LMStudioProvider,
    OpenAICompatibleProvider,
    ResilientProvider,
)


def _router(
    task: dict[str, object] | None = None, name: str = "openai"
) -> ConfiguredProviderRouter:
    endpoint = "http://localhost:1234/api/v1" if name == "lmstudio" else "http://localhost:1234/v1"
    return ConfiguredProviderRouter(
        name, {name: {"endpoint": endpoint, "model": "m"}}, {"large": dict(task or {})}
    )


def test_stream_for_requires_the_streaming_opt_in() -> None:
    with pytest.raises(ValueError, match="streaming"):
        _router().stream_for("large")
    with pytest.raises(ValueError, match="streaming"):
        _router({"streaming": False}).stream_for("large")


@pytest.mark.parametrize("value", ["yes", 1, None, {}])
def test_stream_for_rejects_non_boolean_streaming(value: object) -> None:
    with pytest.raises(ValueError, match="streaming config must be a boolean"):
        _router({"streaming": value}).stream_for("large")


@pytest.mark.parametrize(
    ("name", "kind"), [("openai", OpenAICompatibleProvider), ("lmstudio", LMStudioProvider)]
)
def test_stream_for_returns_a_streaming_provider(name: str, kind: type) -> None:
    provider = _router({"streaming": True}, name).stream_for("large")
    assert isinstance(provider, kind)
    assert provider.capabilities.streaming


def test_stream_for_wraps_when_retry_or_breaker_is_configured() -> None:
    retried = _router({"streaming": True, "retry": {}}).stream_for("large")
    guarded = _router({"streaming": True, "circuit_breaker": {}}).stream_for("large")
    assert isinstance(retried, ResilientProvider)
    assert isinstance(guarded, ResilientProvider)


def test_provider_for_is_unchanged_by_the_streaming_key() -> None:
    assert isinstance(_router({"streaming": True}).provider_for("large"), OpenAICompatibleProvider)
    assert isinstance(_router().provider_for("large"), OpenAICompatibleProvider)


def test_streaming_key_is_validated_by_provider_for_only_when_streaming() -> None:
    # Default path never inspects the key, so existing configs cannot start failing.
    assert _router({"streaming": "yes"}).provider_for("large") is not None
