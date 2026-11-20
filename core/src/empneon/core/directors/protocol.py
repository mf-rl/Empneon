"""Director protocol: pure proposers whose only output is a request for cognition."""

import json
import uuid
from dataclasses import dataclass, field
from typing import Protocol

from empneon.core.contracts import (
    AgentStateSnapshot,
    Clod,
    CognitiveRequest,
    WorldEvent,
    validate_clod,
)


@dataclass(frozen=True)
class DirectorView:
    """Read-only, game-agnostic snapshot a director reasons over.

    `now` is supplied by the caller (never read from a clock), so a fixed view gives a fixed
    result. It holds no store, adapter, or provider handle. Dict fields inside the snapshots are
    plain dicts: read-only is a convention enforced by tests, not a sandbox.
    """

    now: int
    agents: tuple[AgentStateSnapshot, ...] = ()
    recent_events: tuple[WorldEvent, ...] = ()
    _by_id: dict[str, AgentStateSnapshot] = field(
        init=False, repr=False, compare=False, default_factory=dict
    )

    def __post_init__(self) -> None:
        if self.now < 0:
            raise ValueError("view time must not be negative")
        by_id = {agent.agent_id: agent for agent in self.agents}
        if len(by_id) != len(self.agents):
            raise ValueError("view contains duplicate agent ids")
        object.__setattr__(self, "_by_id", by_id)

    def agent(self, agent_id: str) -> AgentStateSnapshot | None:
        return self._by_id.get(agent_id)


@dataclass(frozen=True)
class Opportunity:
    """A request for cognition. It carries no intent, target, or state change by design."""

    director_id: str
    kind: str
    agent_id: str
    urgency: float = 0.2
    deadline_ms: int = 3_000
    facts: dict[str, object] = field(default_factory=dict)
    id: str | None = None

    def __post_init__(self) -> None:
        for name in ("director_id", "kind", "agent_id"):
            if not getattr(self, name).strip():
                raise ValueError(f"opportunity {name} must not be blank")
        if self.id is not None and not self.id.strip():
            raise ValueError("opportunity id must not be blank")
        if not 0 <= self.urgency <= 1:
            raise ValueError("opportunity urgency must be between 0 and 1")
        if self.deadline_ms <= 0:
            raise ValueError("opportunity deadline_ms must be positive")
        try:
            json.dumps(self.facts, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("opportunity facts must be JSON-compatible") from exc


class Director(Protocol):
    """An optional policy module. `propose` must be synchronous, bounded, and side-effect free.

    Core truncates output to `max_opportunities` and clamps urgency to `max_urgency`, so one
    director cannot starve adapter-set work in the shared queue.
    """

    id: str
    max_opportunities: int
    max_urgency: float

    def propose(self, view: DirectorView) -> tuple[Opportunity, ...]: ...


def _key(opportunity: Opportunity, now: int) -> str:
    return f"{opportunity.director_id}:{opportunity.kind}:{opportunity.agent_id}:{now}"


def to_request(
    opportunity: Opportunity, view: DirectorView, *, preferred_clod: int = Clod.RULES
) -> CognitiveRequest:
    """Convert an opportunity into a `CognitiveRequest`, deterministically for a fixed view.

    The synthetic event is never persisted by Core. The agent's snapshot from `view` rides on
    `event.agent_state`, so `validate_decision` still applies the adapter's capabilities.
    """
    validate_clod(preferred_clod, "preferred_clod")
    state = view.agent(opportunity.agent_id)
    if state is None:
        raise ValueError("opportunity agent is not in the view")
    key = _key(opportunity, view.now)
    event = WorldEvent(
        type=f"opportunity.{opportunity.kind}",
        actor_ids=(opportunity.agent_id,),
        facts={**json.loads(json.dumps(opportunity.facts)), "director_id": opportunity.director_id},
        happened_at=view.now,
        id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"empneon:opportunity-event:{key}")),
        agent_state=state,
    )
    return CognitiveRequest(
        opportunity.agent_id,
        preferred_clod,
        event,
        urgency=opportunity.urgency,
        deadline_ms=opportunity.deadline_ms,
        id=opportunity.id or str(uuid.uuid5(uuid.NAMESPACE_URL, f"empneon:opportunity:{key}")),
    )


__all__ = ["Director", "DirectorView", "Opportunity", "to_request"]
