import asyncio
import json
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
    generate_requests,
    prepare_generation_requests,
)


class Response:
    def __init__(self, data: dict[str, object]) -> None:
        self.data = data

    def __enter__(self) -> "Response":
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def read(self) -> bytes:
        return json.dumps(self.data).encode()


def test_generates_with_openai_compatible_chat_endpoint() -> None:
    provider = OpenAICompatibleProvider("http://localhost:1234/v1", "local-model", "key")
    result_data: dict[str, object] = {
        "choices": [{"message": {"content": "hello"}}],
        "usage": {"prompt_tokens": 4, "completion_tokens": 1},
    }

    with patch("urllib.request.urlopen", return_value=Response(result_data)) as urlopen:
        result = asyncio.run(
            provider.generate(GenerationRequest((Message("user", "Hi"),), max_tokens=20))
        )

    request = urlopen.call_args.args[0]
    assert request.full_url == "http://localhost:1234/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer key"
    assert json.loads(request.data)["model"] == "local-model"
    assert result.content == "hello"
    assert result.prompt_tokens == 4
    assert result.completion_tokens == 1


def test_health_check_returns_false_when_endpoint_is_unavailable() -> None:
    provider = OpenAICompatibleProvider("http://localhost:1234/v1", "local-model")

    with patch("urllib.request.urlopen", side_effect=OSError):
        assert asyncio.run(provider.health_check()) is False


@pytest.mark.parametrize("failure", [OSError(), TimeoutError(), MemoryError()])
def test_generation_normalizes_provider_failures(failure: Exception) -> None:
    provider = OpenAICompatibleProvider("http://localhost:1234/v1", "local-model")

    with patch("urllib.request.urlopen", side_effect=failure):
        with pytest.raises(ProviderError):
            asyncio.run(
                provider.generate(GenerationRequest((Message("user", "Hi"),), max_tokens=20))
            )


class OptimizedProvider:
    capabilities = ModelCapabilities(batching=True, prefix_caching=True)

    def __init__(self) -> None:
        self.prepared: list[tuple[Message, ...]] = []
        self.batches: list[tuple[GenerationRequest, ...]] = []

    async def generate(self, _: GenerationRequest) -> GenerationResult:
        raise AssertionError("optimized requests must use native batching")

    async def generate_batch(
        self,
        requests: tuple[GenerationRequest, ...],
        _: tuple[Message, ...],
    ) -> tuple[GenerationResult, ...]:
        self.batches.append(requests)
        return tuple(GenerationResult(f"result-{index}") for index, _ in enumerate(requests))

    async def prepare_prefix_cache(self, prefix: tuple[Message, ...]) -> None:
        self.prepared.append(prefix)

    async def health_check(self) -> bool:
        return True


class OrdinaryProvider:
    capabilities = ModelCapabilities()

    def __init__(self) -> None:
        self.requests: list[GenerationRequest] = []

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        self.requests.append(request)
        return GenerationResult(request.messages[-1].content)

    async def health_check(self) -> bool:
        return True


class MisconfiguredProvider(OrdinaryProvider):
    capabilities = ModelCapabilities(batching=True)


def test_prepares_and_executes_declared_shared_prefix_optimizations() -> None:
    shared = Message("system", "shared society context")
    trailing = Message("assistant", "same text after divergence")
    requests = (
        GenerationRequest((shared, Message("user", "agent A"), trailing), 20),
        GenerationRequest((shared, Message("user", "agent B"), trailing), 20),
    )
    provider = OptimizedProvider()

    preparation = prepare_generation_requests(requests, provider.capabilities)
    results = asyncio.run(generate_requests(provider, requests))

    assert preparation.shared_prefix == (shared,)
    assert preparation.use_batch is True
    assert preparation.prepare_cache is True
    assert provider.prepared == [(shared,)]
    assert provider.batches == [requests]
    assert tuple(result.content for result in results) == ("result-0", "result-1")


def test_preserves_ordinary_generation_without_declared_capabilities() -> None:
    shared = Message("system", "shared society context")
    requests = (
        GenerationRequest((shared, Message("user", "agent A")), 20),
        GenerationRequest((shared, Message("user", "agent B")), 20),
    )
    provider = OrdinaryProvider()

    preparation = prepare_generation_requests(requests, provider.capabilities)
    results = asyncio.run(generate_requests(provider, requests))

    assert preparation.use_batch is False
    assert preparation.prepare_cache is False
    assert provider.requests == list(requests)
    assert tuple(result.content for result in results) == ("agent A", "agent B")


def test_rejects_declared_batching_without_native_method() -> None:
    shared = Message("system", "shared society context")
    requests = (
        GenerationRequest((shared, Message("user", "agent A")), 20),
        GenerationRequest((shared, Message("user", "agent B")), 20),
    )

    with pytest.raises(ProviderError, match="without generate_batch"):
        asyncio.run(generate_requests(MisconfiguredProvider(), requests))


def test_configured_router_selects_provider_without_adapter_logic(monkeypatch) -> None:
    monkeypatch.setenv("AI_SIM_API_KEY", "secret")
    router = ConfiguredProviderRouter(
        "openrouter",
        {
            "openrouter": {
                "endpoint": "https://openrouter.ai/api/v1",
                "model": "openai/gpt-4.1-mini",
            }
        },
        {"large": {"max_tokens": 120, "temperature": 0.3}},
        api_key_env="AI_SIM_API_KEY",
    )
    provider = router.provider_for("large")

    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.base_url == "https://openrouter.ai/api/v1"
    assert provider.model == "openai/gpt-4.1-mini"
    assert provider.api_key == "secret"
    assert provider.capabilities.local is False
    assert router.generation_request(
        "large", (Message("user", "hello"),)
    ) == GenerationRequest(
        (Message("user", "hello"),), max_tokens=120, temperature=0.3
    )


def test_configured_router_exposes_generation_result_without_breaking_generate(
    monkeypatch,
) -> None:
    expected = GenerationResult("hello", 10, 3, 25)

    class Provider:
        async def generate(self, _request):
            return expected

    router = ConfiguredProviderRouter(
        "test",
        {"test": {"endpoint": "http://localhost", "model": "stub"}},
        {"large": {}},
    )
    monkeypatch.setattr(router, "provider_for", lambda _task: Provider())

    assert hasattr(router, "generate_result")
    assert asyncio.run(
        router.generate_result("large", (Message("user", "hi"),))
    ) == expected
    assert asyncio.run(router.generate("large", (Message("user", "hi"),))) == "hello"


def test_lmstudio_native_provider_resolves_loaded_model_and_disables_reasoning() -> None:
    models = {"models": [{"key": "gemma", "loaded_instances": [{"id": "gemma-loaded"}]}]}
    chat = {
        "output": [{"type": "message", "content": "Hello Robin"}],
        "usage": {"input_tokens": 17, "output_tokens": 4},
    }

    with patch(
        "urllib.request.urlopen", side_effect=[Response(models), Response(chat)]
    ) as urlopen:
        result = asyncio.run(
            LMStudioProvider("http://localhost:1234/api/v1", "local-model").generate(
                GenerationRequest((Message("user", "Hello"),), 120, 0.4)
            )
        )

    chat_request = urlopen.call_args_list[1].args[0]
    assert chat_request.full_url == "http://localhost:1234/api/v1/chat"
    assert json.loads(chat_request.data) == {
        "model": "gemma-loaded",
        "input": "USER:\nHello",
        "temperature": 0.4,
        "max_output_tokens": 120,
        "reasoning": "off",
    }
    assert result.content == "Hello Robin"
    assert result.prompt_tokens == 17
    assert result.completion_tokens == 4
    assert result.latency_ms >= 0
