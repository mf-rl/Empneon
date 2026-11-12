"""Opt-in retry with exponential backoff for transient provider failures."""

import asyncio
import logging
import random as _random
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field

from empneon.providers.llm.base import (
    GenerationRequest,
    GenerationResult,
    LLMProvider,
    ModelCapabilities,
    ProviderError,
)

_log = logging.getLogger(__name__)

DEFAULT_RETRY_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
_POLICY_KEYS = frozenset(
    {
        "max_attempts",
        "base_delay_s",
        "max_delay_s",
        "jitter",
        "respect_retry_after",
        "retry_statuses",
    }
)


@dataclass(frozen=True)
class RetryPolicy:
    """How many times and how long to retry transient failures.

    Retried: HTTP statuses in `retry_statuses` and connection-level failures. Never retried:
    other HTTP statuses (for example 400, 401, 404) and malformed or invalid payloads.
    """

    max_attempts: int = 3
    base_delay_s: float = 0.5
    max_delay_s: float = 8.0
    jitter: float = 0.2
    respect_retry_after: bool = True
    retry_statuses: frozenset[int] = field(default=DEFAULT_RETRY_STATUSES)

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.base_delay_s < 0 or self.max_delay_s < 0:
            raise ValueError("retry delays must not be negative")
        if self.base_delay_s > self.max_delay_s:
            raise ValueError("base_delay_s must not exceed max_delay_s")
        if not 0.0 <= self.jitter <= 1.0:
            raise ValueError("jitter must be between 0 and 1")

    @classmethod
    def from_mapping(cls, value: object) -> "RetryPolicy":
        """Build a policy from configuration, rejecting unknown keys and wrong types."""
        if not isinstance(value, Mapping):
            raise ValueError("retry config must be a mapping")
        unknown = sorted(set(map(str, value)) - _POLICY_KEYS)
        if unknown:
            raise ValueError(f"retry config has unknown keys: {', '.join(unknown)}")
        options: dict[str, object] = {}
        for key, raw in value.items():
            if key == "max_attempts":
                options[key] = _integer(key, raw)
            elif key == "respect_retry_after":
                if not isinstance(raw, bool):
                    raise ValueError("retry config respect_retry_after must be a boolean")
                options[key] = raw
            elif key == "retry_statuses":
                if not isinstance(raw, (list, tuple, set, frozenset)):
                    raise ValueError("retry config retry_statuses must be a list of integers")
                options[key] = frozenset(_integer(key, item) for item in raw)
            else:
                options[key] = _number(key, raw)
        try:
            return cls(**options)  # type: ignore[arg-type]
        except ValueError as exc:
            raise ValueError(f"invalid retry config: {exc}") from exc


def _integer(key: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"retry config {key} must be an integer")
    return value


def _number(key: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"retry config {key} must be a number")
    return float(value)


def is_retryable(error: ProviderError, policy: RetryPolicy) -> bool:
    """Whether `error` is a transient failure that `policy` allows retrying."""
    if error.status is not None:
        return error.status in policy.retry_statuses
    return error.transport


class ResilientProvider:
    """Wraps an `LLMProvider`, retrying transient `generate` failures per a `RetryPolicy`.

    `health_check` is a single probe and is never retried. `sleep` and `random` are injectable
    so tests need not wait.
    """

    def __init__(
        self,
        inner: LLMProvider,
        policy: RetryPolicy,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        random: Callable[[], float] = _random.random,
    ) -> None:
        self.inner = inner
        self.policy = policy
        self._sleep = sleep
        self._random = random

    @property
    def capabilities(self) -> ModelCapabilities:
        return self.inner.capabilities

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        attempt = 1
        while True:
            try:
                return await self.inner.generate(request)
            except ProviderError as error:
                if attempt >= self.policy.max_attempts or not is_retryable(error, self.policy):
                    raise
                delay = self._delay(attempt, error)
                _log.warning(
                    "provider call failed (status=%s); retrying in %.2fs (attempt %d/%d)",
                    error.status,
                    delay,
                    attempt,
                    self.policy.max_attempts,
                )
                await self._sleep(delay)
                attempt += 1

    async def health_check(self) -> bool:
        return await self.inner.health_check()

    def _delay(self, attempt: int, error: ProviderError) -> float:
        policy = self.policy
        if policy.respect_retry_after and error.retry_after is not None:
            return min(error.retry_after, policy.max_delay_s)
        delay = policy.base_delay_s * 2 ** (attempt - 1)
        delay *= 1 + policy.jitter * (2 * self._random() - 1)
        return min(delay, policy.max_delay_s)
