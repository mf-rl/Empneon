"""Game-independent contracts exchanged by adapters and the cognitive runtime."""

import time
import uuid
from dataclasses import dataclass, field
from typing import Literal

DeltaOperation = Literal["set", "increment", "append", "remove"]
ActionStatus = Literal["succeeded", "rejected", "failed"]


@dataclass(frozen=True)
class WorldEvent:
    """A game observation translated into provider-independent data."""

    type: str
    actor_ids: tuple[str, ...] = ()
    location: str | None = None
    facts: dict[str, object] = field(default_factory=dict)
    happened_at: int = field(default_factory=lambda: int(time.time()))
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        if not self.type.strip():
            raise ValueError("event type must not be empty")


@dataclass(frozen=True)
class StateDelta:
    """A proposed generic state change; adapters decide how to apply it."""

    path: str
    operation: DeltaOperation
    value: object | None = None

    def __post_init__(self) -> None:
        if not self.path.strip():
            raise ValueError("state delta path must not be empty")


@dataclass(frozen=True)
class Decision:
    """A validated cognitive intent, not a direct game mutation."""

    actor_id: str
    intent: str
    target_id: str | None = None
    evidence_ids: tuple[str, ...] = ()
    state_changes: tuple[StateDelta, ...] = ()
    confidence: float = 1.0
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.actor_id.strip() or not self.intent.strip():
            raise ValueError("decision id, actor_id, and intent must not be empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("decision confidence must be between 0 and 1")


@dataclass(frozen=True)
class ActionResult:
    """The game-confirmed outcome of executing one decision."""

    decision_id: str
    status: ActionStatus
    applied_changes: tuple[StateDelta, ...] = ()
    reason: str | None = None
    completed_at: int = field(default_factory=lambda: int(time.time()))

    def __post_init__(self) -> None:
        if not self.decision_id.strip():
            raise ValueError("action result decision_id must not be empty")
        if self.status != "succeeded" and not (self.reason or "").strip():
            raise ValueError("unsuccessful action result requires a reason")
        if self.status == "rejected" and self.applied_changes:
            raise ValueError("rejected action result cannot include applied changes")


@dataclass(frozen=True)
class CognitiveRequest:
    """A request for cognition with hard per-request limits."""

    agent_id: str
    preferred_clod: int
    event: WorldEvent
    urgency: float = 0.5
    max_tokens: int = 300
    deadline_ms: int = 3_000
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.agent_id.strip():
            raise ValueError("request id and agent_id must not be empty")
        if not 0 <= self.preferred_clod <= 4:
            raise ValueError("preferred_clod must be between 0 and 4")
        if not 0.0 <= self.urgency <= 1.0:
            raise ValueError("urgency must be between 0 and 1")
        if self.max_tokens <= 0 or self.deadline_ms <= 0:
            raise ValueError("max_tokens and deadline_ms must be positive")
