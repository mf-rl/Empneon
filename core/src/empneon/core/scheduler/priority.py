"""Bounded priority scheduling for cognitive requests."""

import heapq
import itertools
import threading
import time

from empneon.core.contracts import CognitiveRequest


class SchedulerFull(RuntimeError):
    pass


class RequestDeadlineExceeded(RuntimeError):
    pass


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
            raise RequestDeadlineExceeded("cognitive request deadline exceeded")
        return request
