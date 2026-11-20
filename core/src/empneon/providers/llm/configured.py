"""Configuration-driven provider routing owned by Empneon Core."""

import os
from collections.abc import Mapping
from typing import TypedDict, cast
from urllib.parse import urlsplit

from empneon.providers.llm.base import (
    GenerationRequest,
    GenerationResult,
    LLMProvider,
    Message,
    ProviderError,
    StreamingLLMProvider,
)
from empneon.providers.llm.breaker import BreakerRegistry, CircuitBreaker, CircuitBreakerPolicy
from empneon.providers.llm.embeddings import EmbeddingProvider, OpenAICompatibleEmbeddingProvider
from empneon.providers.llm.lmstudio import API_V1_PREFIX, LMStudioProvider
from empneon.providers.llm.openai_compatible import OpenAICompatibleProvider
from empneon.providers.llm.resilience import (
    ResilientEmbeddingProvider,
    ResilientProvider,
    RetryPolicy,
)


class ConfiguredProviderRouter:
    def __init__(
        self,
        default_provider: str,
        providers: Mapping[str, Mapping[str, object]],
        tasks: Mapping[str, Mapping[str, object]],
        *,
        api_key_env: str | None = None,
        breakers: BreakerRegistry | None = None,
    ) -> None:
        self._breakers = breakers
        self._default = default_provider
        self._providers = providers
        self._tasks = tasks
        self._api_key_env = api_key_env

    def config_for(self, task: str) -> dict[str, object]:
        task_config = dict(self._tasks.get(task, {}))
        name = str(task_config.get("provider") or self._default)
        config = dict(self._providers.get(name, {}))
        config.update(task_config)
        config["name"] = name
        if not str(config.get("endpoint") or "").strip():
            raise ValueError(f"provider {name!r} requires an endpoint")
        if not str(config.get("model") or "").strip():
            raise ValueError(f"provider {name!r} requires a model")
        return config

    def provider_for(self, task: str) -> LLMProvider:
        return self._wrapped(self.config_for(task))

    def stream_for(self, task: str) -> StreamingLLMProvider:
        """Build a streaming provider for `task`; opt-in through `streaming: true` in its config.

        Uses the same retry and circuit-breaker wrapping as `provider_for`. Raises `ValueError`
        when `streaming` is absent or not `true`, or when the configured provider cannot stream.
        """
        config = self.config_for(task)
        enabled = config.get("streaming")
        if "streaming" in config and not isinstance(enabled, bool):
            raise ValueError("streaming config must be a boolean")
        if enabled is not True:
            raise ValueError(f"task {task!r} must set streaming: true to use stream_for")
        provider = self._wrapped(config)
        if not provider.capabilities.streaming or not hasattr(provider, "stream"):
            raise ValueError(f"provider {config['name']!r} does not support streaming")
        return cast(StreamingLLMProvider, provider)

    def _wrapped(self, config: Mapping[str, object]) -> LLMProvider:
        provider = self._build_provider(config)
        resilience = self._resilience(config)
        if resilience is None:
            return provider
        policy, breaker = resilience
        return ResilientProvider(provider, policy, breaker=breaker)

    def embedding_provider_for(self, task: str = "embedding") -> EmbeddingProvider:
        """Build the embedding provider configured under the explicit `task` entry.

        The task must name its own `model`, so a missing entry can never reuse the chat model.
        Optional keys: `dimensions`, `batch_size`, `normalize`, `retry`, `circuit_breaker`.
        """
        if not str((self._tasks.get(task) or {}).get("model") or "").strip():
            raise ValueError(f"embedding task {task!r} requires its own model")
        config = self.config_for(task)
        endpoint = str(config["endpoint"]).rstrip("/")
        if config["name"] == "lmstudio" and endpoint.endswith(API_V1_PREFIX):
            endpoint = endpoint[: -len(API_V1_PREFIX)] + "/v1"
        provider = OpenAICompatibleEmbeddingProvider(
            endpoint,
            str(config["model"]),
            api_key=self._api_key(config),
            local=self._is_local(endpoint, config),
            **_embedding_options(config),
        )
        resilience = self._resilience(config)
        if resilience is None:
            return provider
        policy, breaker = resilience
        return ResilientEmbeddingProvider(provider, policy, breaker=breaker)

    def _resilience(
        self, config: Mapping[str, object]
    ) -> tuple[RetryPolicy, CircuitBreaker | None] | None:
        retry, breaker_config = config.get("retry"), config.get("circuit_breaker")
        if retry is None and breaker_config is None:
            return None
        policy = (
            RetryPolicy.from_mapping(retry) if retry is not None else RetryPolicy(max_attempts=1)
        )
        breaker = None
        if breaker_config is not None:
            registry = self._breakers or BreakerRegistry.default()
            key = (config["name"], config["endpoint"], config["model"])
            breaker = registry.get(key, CircuitBreakerPolicy.from_mapping(breaker_config))
        return policy, breaker

    def _api_key(self, config: Mapping[str, object]) -> str | None:
        return str(config.get("api_key") or "") or (
            os.environ.get(self._api_key_env) if self._api_key_env else None
        )

    @staticmethod
    def _is_local(endpoint: str, config: Mapping[str, object]) -> bool:
        host = (urlsplit(endpoint).hostname or "").casefold()
        return bool(config.get("local", host in {"localhost", "127.0.0.1", "::1"}))

    def _build_provider(self, config: Mapping[str, object]) -> LLMProvider:
        provider_type = str(config["name"])
        args = (
            str(config["endpoint"]),
            str(config["model"]),
        )
        if provider_type == "lmstudio":
            return LMStudioProvider(*args)
        return OpenAICompatibleProvider(
            *args, api_key=self._api_key(config), local=self._is_local(args[0], config)
        )

    def generation_request(
        self,
        task: str,
        messages: tuple[Message, ...],
        *,
        schema: dict[str, object] | None = None,
        temperature: float | None = None,
    ) -> GenerationRequest:
        config = self.config_for(task)
        return GenerationRequest(
            messages,
            max_tokens=int(str(config.get("max_tokens") or 350)),
            temperature=float(
                str(config.get("temperature", 0.7) if temperature is None else temperature)
            ),
            schema=schema,
        )

    async def generate(
        self,
        task: str,
        messages: tuple[Message, ...],
        *,
        schema: dict[str, object] | None = None,
        temperature: float | None = None,
    ) -> str:
        return (
            await self.generate_result(
                task, messages, schema=schema, temperature=temperature
            )
        ).content

    async def generate_result(
        self,
        task: str,
        messages: tuple[Message, ...],
        *,
        schema: dict[str, object] | None = None,
        temperature: float | None = None,
    ) -> GenerationResult:
        provider = self.provider_for(task)
        if schema is not None and not provider.capabilities.structured_output:
            raise ProviderError("provider does not support structured output")
        request = self.generation_request(
            task, messages, schema=schema, temperature=temperature
        )
        return await provider.generate(request)


class _EmbeddingOptions(TypedDict, total=False):
    dimensions: int
    batch_size: int
    normalize: bool


def _positive_integer(config: Mapping[str, object], key: str) -> int:
    value = config[key]
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"embedding config {key} must be a positive integer")
    return value


def _embedding_options(config: Mapping[str, object]) -> _EmbeddingOptions:
    """Validate the optional embedding keys, rejecting wrong types with a clear message."""
    options = _EmbeddingOptions()
    if "dimensions" in config:
        options["dimensions"] = _positive_integer(config, "dimensions")
    if "batch_size" in config:
        options["batch_size"] = _positive_integer(config, "batch_size")
    if "normalize" in config:
        normalize = config["normalize"]
        if not isinstance(normalize, bool):
            raise ValueError("embedding config normalize must be a boolean")
        options["normalize"] = normalize
    return options
