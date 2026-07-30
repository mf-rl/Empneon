"""Conservative admission control for Empneon's reserved resources."""

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass


class ResourceLimitExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class ResourceBudget:
    """Resources available to Empneon after game usage and safety reserves."""

    max_ram_mb: int
    max_vram_mb: int
    max_concurrent_requests: int = 1
    max_context_tokens: int | None = None
    max_completion_tokens: int | None = None
    max_latency_ms: int | None = None

    def __post_init__(self) -> None:
        if self.max_ram_mb < 0 or self.max_vram_mb < 0:
            raise ValueError("resource budget values must not be negative")
        if self.max_concurrent_requests < 1:
            raise ValueError("max concurrent requests must be positive")
        optional_limits = (
            self.max_context_tokens,
            self.max_completion_tokens,
            self.max_latency_ms,
        )
        if any(limit is not None and limit < 0 for limit in optional_limits):
            raise ValueError("resource budget values must not be negative")


@dataclass(frozen=True)
class ResourceEstimate:
    ram_mb: int = 0
    vram_mb: int = 0
    context_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0

    def __post_init__(self) -> None:
        if min(
            self.ram_mb,
            self.vram_mb,
            self.context_tokens,
            self.completion_tokens,
            self.latency_ms,
        ) < 0:
            raise ValueError("resource estimates must not be negative")


@dataclass(frozen=True)
class ResourceSnapshot:
    reserved_ram_mb: int
    reserved_vram_mb: int
    active_requests: int


class ResourceGovernor:
    """Atomically reserves bounded RAM, VRAM, and request concurrency."""

    def __init__(self, budget: ResourceBudget) -> None:
        self._budget = budget
        self._ram_mb = 0
        self._vram_mb = 0
        self._active = 0
        self._lock = threading.Lock()

    @property
    def budget(self) -> ResourceBudget:
        return self._budget

    @property
    def snapshot(self) -> ResourceSnapshot:
        with self._lock:
            return ResourceSnapshot(self._ram_mb, self._vram_mb, self._active)

    def can_reserve(self, estimate: ResourceEstimate) -> bool:
        with self._lock:
            return self._can_reserve(estimate)

    @contextmanager
    def reserve(self, estimate: ResourceEstimate) -> Iterator[None]:
        with self._lock:
            if not self._can_reserve(estimate):
                raise ResourceLimitExceeded("cognitive request exceeds the resource budget")
            self._ram_mb += estimate.ram_mb
            self._vram_mb += estimate.vram_mb
            self._active += 1
        try:
            yield
        finally:
            with self._lock:
                self._ram_mb -= estimate.ram_mb
                self._vram_mb -= estimate.vram_mb
                self._active -= 1

    def _can_reserve(self, estimate: ResourceEstimate) -> bool:
        return not (
            self._active >= self._budget.max_concurrent_requests
            or self._ram_mb + estimate.ram_mb > self._budget.max_ram_mb
            or self._vram_mb + estimate.vram_mb > self._budget.max_vram_mb
            or _exceeds(estimate.context_tokens, self._budget.max_context_tokens)
            or _exceeds(estimate.completion_tokens, self._budget.max_completion_tokens)
            or _exceeds(estimate.latency_ms, self._budget.max_latency_ms)
        )


def _exceeds(value: int, limit: int | None) -> bool:
    return limit is not None and value > limit
