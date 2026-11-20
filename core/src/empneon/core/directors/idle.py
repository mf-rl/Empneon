"""Reference director: ask an agent that has gone quiet to check in."""

from dataclasses import dataclass

from empneon.core.directors.protocol import DirectorView, Opportunity


@dataclass(frozen=True)
class IdleCheckInDirector:
    """Propose an `idle` opportunity for each agent whose latest event is old enough.

    Uses only generic state: `DirectorView.recent_events` and `happened_at`. An agent with no
    event in the view is skipped, since there is no evidence of how long it has been quiet.
    Throwaway by design: it exists to exercise the protocol, not to prescribe behavior.
    """

    idle_after_s: int
    urgency: float = 0.2
    deadline_ms: int = 3_000
    max_urgency: float = 0.3
    max_opportunities: int = 8
    id: str = "core.idle-check-in"

    def __post_init__(self) -> None:
        if self.idle_after_s <= 0:
            raise ValueError("idle_after_s must be positive")
        if not 0 <= self.urgency <= 1 or not 0 <= self.max_urgency <= 1:
            raise ValueError("urgency values must be between 0 and 1")
        if self.deadline_ms <= 0:
            raise ValueError("deadline_ms must be positive")
        if self.max_opportunities < 0:
            raise ValueError("max_opportunities must not be negative")

    def propose(self, view: DirectorView) -> tuple[Opportunity, ...]:
        latest: dict[str, int] = {}
        for event in view.recent_events:
            for actor in event.actor_ids:
                if event.happened_at > latest.get(actor, -1):
                    latest[actor] = event.happened_at
        found = []
        for agent in view.agents:
            last = latest.get(agent.agent_id)
            if last is None or view.now - last < self.idle_after_s:
                continue
            found.append(
                Opportunity(
                    self.id,
                    "idle",
                    agent.agent_id,
                    min(self.urgency, self.max_urgency),
                    self.deadline_ms,
                    {"idle_seconds": view.now - last},
                )
            )
        return tuple(found)
