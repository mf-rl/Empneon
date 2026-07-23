"""LM Studio native chat transport."""

import asyncio
import json
import time
import urllib.request
from dataclasses import dataclass

from empneon.providers.llm.base import (
    GenerationRequest,
    GenerationResult,
    ModelCapabilities,
    ProviderError,
)


@dataclass(frozen=True)
class LMStudioProvider:
    base_url: str
    model: str
    timeout_seconds: float = 90

    @property
    def capabilities(self) -> ModelCapabilities:
        return ModelCapabilities(local=True)

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        try:
            return await asyncio.to_thread(self._generate, request)
        except (MemoryError, OSError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError("LM Studio generation failed") from exc

    async def health_check(self) -> bool:
        try:
            await asyncio.to_thread(self._request, "/models")
        except (MemoryError, OSError, ValueError, KeyError, json.JSONDecodeError):
            return False
        return True

    def _generate(self, request: GenerationRequest) -> GenerationResult:
        prompt = "\n\n".join(
            f"{message.role.upper()}:\n{message.content}" for message in request.messages
        )
        started = time.perf_counter()
        data = self._request(
            "/chat",
            {
                "model": self._model_id(),
                "input": prompt,
                "temperature": request.temperature,
                "max_output_tokens": request.max_tokens,
                "reasoning": "off",
            },
        )
        output = data.get("output", [])
        if not isinstance(output, list):
            raise ValueError("LM Studio output must be a list")
        usage = data.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        prompt_tokens = usage.get("input_tokens", usage.get("prompt_tokens"))
        completion_tokens = usage.get(
            "output_tokens", usage.get("completion_tokens")
        )
        latency_ms = max(0, round((time.perf_counter() - started) * 1000))
        for item in reversed(output):
            if not isinstance(item, dict):
                continue
            if item.get("type") == "message" and str(item.get("content") or "").strip():
                return GenerationResult(
                    str(item["content"]).strip(),
                    int(prompt_tokens) if prompt_tokens is not None else None,
                    int(completion_tokens) if completion_tokens is not None else None,
                    latency_ms,
                )
        raise ValueError("LM Studio returned empty content")

    def _model_id(self) -> str:
        if self.model != "local-model":
            return self.model
        data = self._request("/models")
        models = data.get("models", [])
        if not isinstance(models, list):
            return self.model
        for model in models:
            if not isinstance(model, dict):
                continue
            loaded = model.get("loaded_instances", [])
            if isinstance(loaded, list) and loaded and isinstance(loaded[0], dict):
                return str(loaded[0].get("id") or model.get("key") or self.model)
        return self.model

    def _request(
        self, path: str, body: dict[str, object] | None = None
    ) -> dict[str, object]:
        root = self.base_url.rstrip("/")
        if root.endswith("/api/v1"):
            root = root[: -len("/api/v1")]
        request = urllib.request.Request(
            f"{root}/api/v1{path}",
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"},
            method="POST" if body is not None else "GET",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            value = json.loads(response.read())
        if not isinstance(value, dict):
            raise ValueError("LM Studio returned a non-object response")
        return value
