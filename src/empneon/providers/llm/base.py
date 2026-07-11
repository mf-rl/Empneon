"""Provider-independent LLM request and capability contracts."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ModelCapabilities:
    structured_output: bool = False
    streaming: bool = False
    batching: bool = False
    prefix_caching: bool = False
    embeddings: bool = False
    local: bool = False
    context_window: int = 0


@dataclass(frozen=True)
class Message:
    role: str
    content: str


@dataclass(frozen=True)
class GenerationRequest:
    messages: tuple[Message, ...]
    max_tokens: int
    temperature: float = 0.7
    schema: dict[str, object] | None = None


@dataclass(frozen=True)
class GenerationResult:
    content: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: int | None = None


class LLMProvider(Protocol):
    """Minimal interface implemented by local, hosted, and custom providers."""

    @property
    def capabilities(self) -> ModelCapabilities: ...

    async def generate(self, request: GenerationRequest) -> GenerationResult: ...

    async def health_check(self) -> bool: ...
