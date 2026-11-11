"""LM Studio native chat transport."""

import time
from dataclasses import dataclass

from empneon.providers.llm._http import (
    chat_completion_body,
    guarded_generate,
    guarded_health,
    request_json,
)
from empneon.providers.llm.base import GenerationRequest, GenerationResult, ModelCapabilities

API_V1_PREFIX = "/api/v1"


def _extract_message_text(output: list[object]) -> str | None:
    for item in reversed(output):
        if not isinstance(item, dict):
            continue
        if item.get("type") == "message" and str(item.get("content") or "").strip():
            return str(item["content"]).strip()
    return None


@dataclass(frozen=True)
class LMStudioProvider:
    base_url: str
    model: str
    timeout_seconds: float = 90

    @property
    def capabilities(self) -> ModelCapabilities:
        return ModelCapabilities(structured_output=True, local=True)

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        return await guarded_generate("LM Studio", lambda: self._generate(request))

    async def health_check(self) -> bool:
        return await guarded_health("LM Studio", lambda: self._request("/models"))

    def _generate(self, request: GenerationRequest) -> GenerationResult:
        if request.schema is not None:
            return self._generate_structured(request)
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
        text = _extract_message_text(output)
        if text is None:
            raise ValueError("LM Studio returned empty content")
        return GenerationResult(
            text,
            int(prompt_tokens) if prompt_tokens is not None else None,
            int(completion_tokens) if completion_tokens is not None else None,
            latency_ms,
        )

    def _generate_structured(self, request: GenerationRequest) -> GenerationResult:
        started = time.perf_counter()
        data = self._request(
            "/chat/completions",
            chat_completion_body(self._model_id(), request),
            native=False,
        )
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError("LM Studio returned no structured choices")
        choice = choices[0]
        if not isinstance(choice, dict):
            raise ValueError("LM Studio returned an invalid structured choice")
        message = choice.get("message")
        if not isinstance(message, dict):
            raise ValueError("LM Studio returned an invalid structured message")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("LM Studio returned empty structured content")
        usage = data.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        return GenerationResult(
            content=str(content),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            latency_ms=max(0, round((time.perf_counter() - started) * 1000)),
        )

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
        self,
        path: str,
        body: dict[str, object] | None = None,
        *,
        native: bool = True,
    ) -> dict[str, object]:
        root = self.base_url.rstrip("/")
        if root.endswith(API_V1_PREFIX):
            root = root[: -len(API_V1_PREFIX)]
        prefix = API_V1_PREFIX if native else "/v1"
        value = request_json(
            f"{root}{prefix}{path}", body=body, timeout=self.timeout_seconds
        )
        if not isinstance(value, dict):
            raise ValueError("LM Studio returned a non-object response")
        return value
