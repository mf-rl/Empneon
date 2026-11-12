"""Circuit breaker that stops calling a failing provider and probes for recovery."""

import logging
import threading
import time
from collections.abc import Callable, Hashable, Mapping
from dataclasses import dataclass
from typing import ClassVar, Literal

from empneon.providers.llm.base import ProviderError

_log = logging.getLogger(__name__)
_POLICY_KEYS = frozenset({"failure_threshold", "reset_timeout_s"})

BreakerState = Literal["closed", "open", "half_open"]


class CircuitOpenError(ProviderError):
    """Raised without calling the provider while its circuit is open."""


@dataclass(frozen=True)
class CircuitBreakerPolicy:
    """Open after `failure_threshold` consecutive failures; probe again after `reset_timeout_s`."""

    failure_threshold: int = 5
    reset_timeout_s: float = 30.0

    def __post_init__(self) -> None:
        if self.failure_threshold < 1:
            raise ValueError("failure_threshold must be at least 1")
        if self.reset_timeout_s <= 0:
            raise ValueError("reset_timeout_s must be positive")

    @classmethod
    def from_mapping(cls, value: object) -> "CircuitBreakerPolicy":
        """Build a policy from configuration, rejecting unknown keys and wrong types."""
        if not isinstance(value, Mapping):
            raise ValueError("circuit_breaker config must be a mapping")
        unknown = sorted(set(map(str, value)) - _POLICY_KEYS)
        if unknown:
            raise ValueError(f"circuit_breaker config has unknown keys: {', '.join(unknown)}")
        options: dict[str, object] = {}
        for key, raw in value.items():
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise ValueError(f"circuit_breaker config {key} must be a number")
            if key == "failure_threshold":
                if not isinstance(raw, int):
                    raise ValueError("circuit_breaker config failure_threshold must be an integer")
                options[key] = raw
            else:
                options[key] = float(raw)
        try:
            return cls(**options)  # type: ignore[arg-type]
        except ValueError as exc:
            raise ValueError(f"invalid circuit_breaker config: {exc}") from exc


class CircuitBreaker:
    """Thread-safe closed / open / half-open breaker with an injectable monotonic clock."""

    def __init__(
        self,
        policy: CircuitBreakerPolicy | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.policy = policy or CircuitBreakerPolicy()
        self._clock = clock
        self._lock = threading.Lock()
        self._state: BreakerState = "closed"
        self._failures = 0
        self._opened_at = 0.0
        self._probing = False

    @property
    def state(self) -> BreakerState:
        with self._lock:
            return self._state

    def acquire(self) -> None:
        """Permit a call or raise `CircuitOpenError`; permits one probe once the timeout passes."""
        with self._lock:
            if self._state == "closed":
                return
            if self._state == "open":
                if self._clock() - self._opened_at < self.policy.reset_timeout_s:
                    raise CircuitOpenError("provider circuit is open")
                self._state = "half_open"
            if self._probing:
                raise CircuitOpenError("provider circuit is open")
            self._probing = True

    def record_success(self) -> None:
        with self._lock:
            reopened = self._state != "closed"
            self._state = "closed"
            self._failures = 0
            self._probing = False
        if reopened:
            _log.info("provider circuit closed")

    def record_failure(self) -> None:
        with self._lock:
            self._probing = False
            self._failures += 1
            if self._state == "closed" and self._failures < self.policy.failure_threshold:
                return
            newly_opened = self._state != "open"
            self._state = "open"
            self._opened_at = self._clock()
            failures = self._failures
        if newly_opened:
            _log.warning("provider circuit opened after %d consecutive failures", failures)

    def release(self) -> None:
        """Free the probe slot when a permitted call was cancelled before it finished."""
        with self._lock:
            self._probing = False


class BreakerRegistry:
    """Shares one breaker per provider key so state outlives per-call routers."""

    _default: ClassVar["BreakerRegistry | None"] = None
    _default_lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._breakers: dict[tuple[Hashable, CircuitBreakerPolicy], CircuitBreaker] = {}

    @classmethod
    def default(cls) -> "BreakerRegistry":
        """The lazily created process-wide registry used when none is injected."""
        with cls._default_lock:
            if cls._default is None:
                cls._default = cls()
            return cls._default

    def get(self, key: Hashable, policy: CircuitBreakerPolicy) -> CircuitBreaker:
        with self._lock:
            return self._breakers.setdefault((key, policy), CircuitBreaker(policy))

    def reset(self) -> None:
        """Forget every breaker; intended for tests and explicit operator resets."""
        with self._lock:
            self._breakers.clear()
