"""Bounded priority scheduling for cognitive requests."""

import heapq
import itertools
import logging
import math
import threading
import time

from empneon.core.contracts import CognitiveRequest

_log = logging.getLogger(__name__)


class SchedulerFull(RuntimeError):
    pass


class RequestDeadlineExceeded(RuntimeError):
    """A request's deadline passed before it was dequeued; `request` is that request, if known."""

    def __init__(self, message: str = "", *, request: CognitiveRequest | None = None) -> None:
        super().__init__(message)
        self.request = request


class PriorityScheduler:
    """Orders requests by urgency, deadline, then submission order.

    With `aging_per_second > 0`, a queued request's effective urgency grows by that amount for each
    second it waits, so a low-urgency request eventually outranks a steady stream of newer urgent
    ones. Aging only affects ordering: deadlines are never extended. The default (0.0) is strict
    urgency ordering.
    """

    def __init__(self, max_queue_size: int, *, aging_per_second: float = 0.0) -> None:
        if max_queue_size <= 0:
            raise ValueError("max_queue_size must be positive")
        if not math.isfinite(aging_per_second) or aging_per_second < 0:
            raise ValueError("aging_per_second must be finite and non-negative")
        self._aging_per_second = aging_per_second
        self._max_queue_size = max_queue_size
        # (priority key, deadline, sequence, request); a smaller key is served first
        self._queue: list[tuple[float, float, int, CognitiveRequest]] = []
        self._sequence = itertools.count()
        self._lock = threading.Lock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._queue)

    def submit(self, request: CognitiveRequest) -> None:
        now = time.monotonic()
        deadline = now + request.deadline_ms / 1_000
        # urgency + rate * (t - submitted) ranks the same as rate * submitted - urgency at any t,
        # so the key is fixed at submission and the heap stays valid as time passes.
        key = self._aging_per_second * now - request.urgency
        with self._lock:
            if len(self._queue) >= self._max_queue_size:
                dropped = self._remove_expired()
                if dropped:
                    _log.warning(
                        "dropped %d expired cognitive requests to admit new work", len(dropped)
                    )
            if len(self._queue) >= self._max_queue_size:
                raise SchedulerFull("cognitive request queue is full")
            heapq.heappush(
                self._queue,
                (key, deadline, next(self._sequence), request),
            )

    def pop(self) -> CognitiveRequest:
        with self._lock:
            if not self._queue:
                raise IndexError("cognitive request queue is empty")
            _, deadline, _, request = heapq.heappop(self._queue)
        if time.monotonic() > deadline:
            raise RequestDeadlineExceeded("cognitive request deadline exceeded", request=request)
        return request

    def expire(self) -> list[CognitiveRequest]:
        """Remove and return queued requests whose deadline has passed."""
        with self._lock:
            return self._remove_expired()

    def _remove_expired(self) -> list[CognitiveRequest]:
        now = time.monotonic()
        expired = [entry for entry in self._queue if entry[1] < now]
        if expired:
            self._queue = [entry for entry in self._queue if entry[1] >= now]
            heapq.heapify(self._queue)
        return [entry[3] for entry in sorted(expired)]
