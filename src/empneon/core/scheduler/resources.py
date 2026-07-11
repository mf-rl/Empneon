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

    def __post_init__(self) -> None:
        if min(self.max_ram_mb, self.max_vram_mb, self.max_concurrent_requests) < 0:
            raise ValueError("resource budget values must not be negative")


@dataclass(frozen=True)
class ResourceEstimate:
    ram_mb: int = 0
    vram_mb: int = 0

    def __post_init__(self) -> None:
        if self.ram_mb < 0 or self.vram_mb < 0:
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
    def snapshot(self) -> ResourceSnapshot:
        with self._lock:
            return ResourceSnapshot(self._ram_mb, self._vram_mb, self._active)

    @contextmanager
    def reserve(self, estimate: ResourceEstimate) -> Iterator[None]:
        with self._lock:
            if (
                self._active >= self._budget.max_concurrent_requests
                or self._ram_mb + estimate.ram_mb > self._budget.max_ram_mb
                or self._vram_mb + estimate.vram_mb > self._budget.max_vram_mb
            ):
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
