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

    with pytest.raises(SchedulerFull):
        scheduler.submit(request("overflow"))
    assert scheduler.pop() is high
    assert scheduler.pop() is low

    with patch("empneon.core.scheduler.priority.time.monotonic", side_effect=[0.0, 0.011]):
        scheduler.submit(request("expired", deadline_ms=10))
        with pytest.raises(RequestDeadlineExceeded):
            scheduler.pop()
