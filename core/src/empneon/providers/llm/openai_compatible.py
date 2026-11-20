"""OpenAI-compatible chat provider for local and hosted endpoints."""

import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, cast

from empneon.providers.llm._http import (
    chat_completion_body,
    delta_text,
    guarded_generate,
    guarded_health,
    guarded_stream,
    open_stream,
    request_json,
)
from empneon.providers.llm.base import GenerationRequest, GenerationResult, ModelCapabilities


@dataclass(frozen=True)
class OpenAICompatibleProvider:
    base_url: str
    model: str
    api_key: str | None = field(default=None, repr=False)
    timeout_seconds: float = 90
    local: bool = False

    @property
    def capabilities(self) -> ModelCapabilities:
        return ModelCapabilities(structured_output=True, streaming=True, local=self.local)

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        return await guarded_generate("OpenAI-compatible", lambda: self._generate(request))

    def stream(self, request: GenerationRequest) -> AsyncIterator[str]:
        """Yield text deltas from a streamed chat completion (opt-in; `generate` is unchanged)."""
        body = {**chat_completion_body(self.model, request), "stream": True}
        return guarded_stream(
            "OpenAI-compatible",
            lambda: open_stream(
                f"{self.base_url.rstrip('/')}/chat/completions",
                body=body,
                headers=self._headers(),
                timeout=self.timeout_seconds,
            ),
            delta_text,
        )

    async def health_check(self) -> bool:
        return await guarded_health("OpenAI-compatible", lambda: self._request("/models"))

    def _generate(self, request: GenerationRequest) -> GenerationResult:
        started = time.perf_counter()
        data = self._request("/chat/completions", chat_completion_body(self.model, request))
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return GenerationResult(
            content=content,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            latency_ms=round((time.perf_counter() - started) * 1000),
        )

    def _headers(self) -> dict[str, str] | None:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else None

    def _request(self, path: str, body: dict[str, object] | None = None) -> dict[str, Any]:
        value = request_json(
            f"{self.base_url.rstrip('/')}{path}",
            body=body,
            headers=self._headers(),
            timeout=self.timeout_seconds,
        )
        return cast(dict[str, Any], value)
