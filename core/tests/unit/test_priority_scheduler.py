from unittest.mock import patch

import pytest

from empneon.core.contracts import CognitiveRequest, WorldEvent
from empneon.core.scheduler import PriorityScheduler, RequestDeadlineExceeded, SchedulerFull


def request(agent_id: str, urgency: float = 0.5, deadline_ms: int = 1_000) -> CognitiveRequest:
    return CognitiveRequest(agent_id, 1, WorldEvent("event"), urgency, deadline_ms=deadline_ms)


def test_scheduler_enforces_priority_deadlines_and_backpressure() -> None:
    scheduler = PriorityScheduler(2)
    low = request("low", urgency=0.1)
    high = request("high", urgency=0.9)
    scheduler.submit(low)
    scheduler.submit(high)

    overflow = request("overflow")
    with pytest.raises(SchedulerFull):
        scheduler.submit(overflow)
    assert scheduler.pop() is high
    assert scheduler.pop() is low

    with patch("empneon.core.scheduler.priority.time.monotonic", side_effect=[0.0, 0.011]):
        scheduler.submit(request("expired", deadline_ms=10))
        with pytest.raises(RequestDeadlineExceeded):
            scheduler.pop()


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    fake = Clock()
    with patch("empneon.core.scheduler.priority.time.monotonic", fake):
        yield fake


def test_expired_requests_do_not_block_new_submissions(clock: Clock) -> None:
    scheduler = PriorityScheduler(2)
    scheduler.submit(request("stale-1", deadline_ms=10))
    scheduler.submit(request("stale-2", deadline_ms=10))
    clock.now = 1.0

    fresh = request("fresh")
    scheduler.submit(fresh)

    assert len(scheduler) == 1
    assert scheduler.pop() is fresh


def test_live_requests_still_apply_backpressure(clock: Clock) -> None:
    scheduler = PriorityScheduler(1)
    scheduler.submit(request("live"))
    with pytest.raises(SchedulerFull):
        scheduler.submit(request("overflow"))
    assert len(scheduler) == 1


def test_expire_removes_and_returns_only_expired_requests(clock: Clock) -> None:
    scheduler = PriorityScheduler(4)
    stale = request("stale", urgency=0.9, deadline_ms=10)
    low = request("low", urgency=0.1)
    high = request("high", urgency=0.8)
    for item in (stale, low, high):
        scheduler.submit(item)
    clock.now = 0.5

    assert scheduler.expire() == [stale]
    assert len(scheduler) == 2
    assert scheduler.pop() is high
    assert scheduler.pop() is low
    assert scheduler.expire() == []


def test_deadline_error_identifies_the_expired_request(clock: Clock) -> None:
    scheduler = PriorityScheduler(1)
    stale = request("stale", deadline_ms=10)
    scheduler.submit(stale)
    clock.now = 1.0

    with pytest.raises(RequestDeadlineExceeded) as info:
        scheduler.pop()

    assert info.value.request is stale
    assert len(scheduler) == 0
