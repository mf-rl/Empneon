"""Configuration-driven provider routing owned by Empneon Core."""

import os
from collections.abc import Mapping
from urllib.parse import urlsplit

from empneon.providers.llm.base import GenerationRequest, GenerationResult, LLMProvider, Message
from empneon.providers.llm.lmstudio import LMStudioProvider
from empneon.providers.llm.openai_compatible import OpenAICompatibleProvider


class ConfiguredProviderRouter:
    def __init__(
        self,
        default_provider: str,
        providers: Mapping[str, Mapping[str, object]],
        tasks: Mapping[str, Mapping[str, object]],
        *,
        api_key_env: str | None = None,
    ) -> None:
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
        config = self.config_for(task)
        provider_type = str(config["name"])
        args = (
            str(config["endpoint"]),
            str(config["model"]),
        )
        if provider_type == "lmstudio":
            return LMStudioProvider(*args)
        api_key = str(config.get("api_key") or "") or (
            os.environ.get(self._api_key_env) if self._api_key_env else None
        )
        host = (urlsplit(args[0]).hostname or "").casefold()
        local = bool(config.get("local", host in {"localhost", "127.0.0.1", "::1"}))
        return OpenAICompatibleProvider(*args, api_key=api_key, local=local)

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
        request = self.generation_request(
            task, messages, schema=schema, temperature=temperature
        )
        return await self.provider_for(task).generate(request)
