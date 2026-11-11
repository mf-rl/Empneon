"""Bounded priority scheduling for cognitive requests."""

import heapq
import itertools
import logging
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
    """Orders requests by urgency, deadline, then submission order."""

    def __init__(self, max_queue_size: int) -> None:
        if max_queue_size <= 0:
            raise ValueError("max_queue_size must be positive")
        self._max_queue_size = max_queue_size
        self._queue: list[tuple[float, float, int, CognitiveRequest]] = []
        self._sequence = itertools.count()
        self._lock = threading.Lock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._queue)

    def submit(self, request: CognitiveRequest) -> None:
        deadline = time.monotonic() + request.deadline_ms / 1_000
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
                (-request.urgency, deadline, next(self._sequence), request),
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
