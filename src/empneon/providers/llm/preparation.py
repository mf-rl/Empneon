"""Capability-gated shared-prefix generation preparation."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import cast

from empneon.providers.llm.base import (
    GenerationRequest,
    GenerationResult,
    LLMProvider,
    Message,
    ModelCapabilities,
    ProviderError,
)

BatchGenerator = Callable[
    [tuple[GenerationRequest, ...], tuple[Message, ...]],
    Awaitable[tuple[GenerationResult, ...]],
]
PrefixPreparer = Callable[[tuple[Message, ...]], Awaitable[None]]


@dataclass(frozen=True)
class GenerationPreparation:
    requests: tuple[GenerationRequest, ...]
    shared_prefix: tuple[Message, ...]
    use_batch: bool
    prepare_cache: bool


def prepare_generation_requests(
    requests: tuple[GenerationRequest, ...],
    capabilities: ModelCapabilities,
) -> GenerationPreparation:
    """Detect a reusable prefix and enable only declared optimizations."""
    if not requests:
        raise ValueError("at least one generation request is required")
    shared_prefix = _shared_prefix(tuple(request.messages for request in requests))
    multiple_with_prefix = len(requests) > 1 and bool(shared_prefix)
    first = requests[0]
    compatible = all(
        request.temperature == first.temperature and request.schema == first.schema
        for request in requests[1:]
    )
    return GenerationPreparation(
        requests,
        shared_prefix,
        multiple_with_prefix and capabilities.batching and compatible,
        multiple_with_prefix and capabilities.prefix_caching,
    )


async def generate_requests(
    provider: LLMProvider,
    requests: tuple[GenerationRequest, ...],
) -> tuple[GenerationResult, ...]:
    """Run native optional optimizations or preserve ordinary generation."""
    preparation = prepare_generation_requests(requests, provider.capabilities)
    batch = getattr(provider, "generate_batch", None) if preparation.use_batch else None
    cache = (
        getattr(provider, "prepare_prefix_cache", None)
        if preparation.prepare_cache
        else None
    )
    if preparation.use_batch and not callable(batch):
        raise ProviderError("provider declares batching without generate_batch")
    if preparation.prepare_cache and not callable(cache):
        raise ProviderError(
            "provider declares prefix caching without prepare_prefix_cache"
        )
    if cache is not None:
        await cast(PrefixPreparer, cache)(preparation.shared_prefix)
    if batch is not None:
        results = tuple(
            await cast(BatchGenerator, batch)(requests, preparation.shared_prefix)
        )
        if len(results) != len(requests):
            raise ProviderError("batch result count does not match request count")
        return results
    return tuple([await provider.generate(request) for request in requests])


def _shared_prefix(message_sets: tuple[tuple[Message, ...], ...]) -> tuple[Message, ...]:
    prefix = []
    for messages in zip(*message_sets, strict=False):
        if any(message != messages[0] for message in messages[1:]):
            break
        prefix.append(messages[0])
    return tuple(prefix)
