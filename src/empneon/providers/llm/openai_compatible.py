"""OpenAI-compatible chat provider for local and hosted endpoints."""

import asyncio
import json
import time
import urllib.request
from dataclasses import dataclass
from typing import Any, cast

from empneon.providers.llm.base import (
    GenerationRequest,
    GenerationResult,
    ModelCapabilities,
    ProviderError,
)


@dataclass(frozen=True)
class OpenAICompatibleProvider:
    base_url: str
    model: str
    api_key: str | None = None
    timeout_seconds: float = 90

    @property
    def capabilities(self) -> ModelCapabilities:
        return ModelCapabilities(structured_output=True, local=True)

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        try:
            return await asyncio.to_thread(self._generate, request)
        except (MemoryError, OSError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError("OpenAI-compatible generation failed") from exc

    async def health_check(self) -> bool:
        try:
            await asyncio.to_thread(self._request, "/models")
        except (MemoryError, OSError, ValueError, KeyError, json.JSONDecodeError):
            return False
        return True

    def _generate(self, request: GenerationRequest) -> GenerationResult:
        body: dict[str, object] = {
            "model": self.model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in request.messages
            ],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if request.schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "response", "schema": request.schema},
            }

        started = time.perf_counter()
        data = self._request("/chat/completions", body)
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return GenerationResult(
            content=content,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            latency_ms=round((time.perf_counter() - started) * 1000),
        )

    def _request(self, path: str, body: dict[str, object] | None = None) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}{path}",
            data=json.dumps(body).encode() if body is not None else None,
            headers=headers,
            method="POST" if body is not None else "GET",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            return cast(dict[str, Any], json.loads(response.read()))
