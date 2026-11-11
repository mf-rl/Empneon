"""Game-independent contracts exchanged by adapters and the cognitive runtime."""

import dataclasses
import json
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Literal

DeltaOperation = Literal["set", "increment", "append", "remove"]
ActionStatus = Literal["succeeded", "rejected", "failed"]
SocialCategory = Literal["friendly", "funny", "romance", "mean", "mischief"]
SOCIAL_CATEGORIES: tuple[SocialCategory, ...] = (
    "friendly",
    "funny",
    "romance",
    "mean",
    "mischief",
)


class Clod(IntEnum):
    """Cognitive Level of Detail. Plain ints are accepted wherever a level is expected."""

    STATE = 0
    RULES = 1
    SMALL_MODEL = 2
    INTERACTIVE = 3
    CONSEQUENTIAL = 4


def validate_clod(value: int, label: str = "CLOD") -> None:
    """Raise ValueError unless `value` is a documented CLOD level (0 through 4)."""
    if not Clod.STATE <= value <= Clod.CONSEQUENTIAL:
        raise ValueError(f"{label} must be between {int(Clod.STATE)} and {int(Clod.CONSEQUENTIAL)}")


def _mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def _schema_version(value: object) -> int:
    """Return an integer schema version; a missing value is reported as 0 (unsupported)."""
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError("agent state schema_version must be an integer")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError("agent state schema_version must be an integer")
    try:
        return int(value)
    except ValueError:
        raise ValueError("agent state schema_version must be an integer") from None


def _items(value: object) -> list[object]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _bounded(mapping: Mapping[str, object], key: str, low: float, high: float) -> None:
    value = mapping.get(key)
    if value is not None and (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not low <= float(value) <= high
    ):
        raise ValueError(f"agent state {key} must be between {low} and {high}")


def _validate_social_context(facts: Mapping[str, object]) -> None:
    social = facts.get("social")
    if social is None:
        return
    if not isinstance(social, Mapping):
        raise ValueError("event social context must be a mapping")
    if social.get("incoming_category") not in SOCIAL_CATEGORIES:
        raise ValueError("event social category is invalid")
    available = social.get("available_response_categories")
    if not isinstance(available, (list, tuple)) or any(
        category not in SOCIAL_CATEGORIES for category in available
    ):
        raise ValueError("event available social category is invalid")


def _validate_needs(needs: Mapping[str, object]) -> None:
    for need in needs.values():
        if not isinstance(need, Mapping):
            continue
        _bounded(need, "level", 0.0, 1.0)
        _bounded(need, "urgency", 0.0, 1.0)
        status = need.get("status")
        if status is not None and status not in ("satisfied", "low", "critical"):
            raise ValueError("agent state need status is invalid")


def _validate_relationships(relationships: Mapping[str, object]) -> None:
    for relationship in relationships.values():
        if not isinstance(relationship, Mapping):
            continue
        _bounded(relationship, "affinity", -1.0, 1.0)
        _bounded(relationship, "romance", 0.0, 1.0)
        _bounded(relationship, "trust", 0.0, 1.0)
        _bounded(relationship, "attraction", -1.0, 1.0)


@dataclass(frozen=True)
class AgentStateSnapshot:
    schema_version: int
    adapter: str
    agent_id: str
    affect: dict[str, object] = field(default_factory=dict)
    needs: dict[str, object] = field(default_factory=dict)
    effects: list[object] = field(default_factory=list)
    relationships: dict[str, object] = field(default_factory=dict)
    goals: list[object] = field(default_factory=list)
    intentions: list[object] = field(default_factory=list)
    capabilities: dict[str, object] = field(default_factory=dict)
    native: dict[str, object] = field(default_factory=dict)
    identity: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported agent state schema_version")
        if not self.adapter.strip() or not self.agent_id.strip():
            raise ValueError("agent state adapter and agent_id are required")
        _bounded(self.affect, "valence", -1.0, 1.0)
        _bounded(self.affect, "arousal", 0.0, 1.0)
        _bounded(self.affect, "intensity", 0.0, 1.0)
        _validate_needs(self.needs)
        for effect in self.effects:
            if isinstance(effect, Mapping):
                _bounded(effect, "intensity", 0.0, 1.0)
        _validate_relationships(self.relationships)
        try:
            json.dumps(dataclasses.asdict(self), allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("agent state must be JSON-compatible") from exc

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "AgentStateSnapshot":
        return cls(
            schema_version=_schema_version(value.get("schema_version")),
            adapter=str(value.get("adapter") or ""),
            agent_id=str(value.get("agent_id") or ""),
            affect=_mapping(value.get("affect")),
            needs=_mapping(value.get("needs")),
            effects=_items(value.get("effects")),
            relationships=_mapping(value.get("relationships")),
            goals=_items(value.get("goals")),
            intentions=_items(value.get("intentions")),
            capabilities=_mapping(value.get("capabilities")),
            native=_mapping(value.get("native")),
            identity=_mapping(value.get("identity")),
        )


@dataclass(frozen=True)
class WorldEvent:
    """A game observation translated into provider-independent data."""

    type: str
    actor_ids: tuple[str, ...] = ()
    location: str | None = None
    facts: dict[str, object] = field(default_factory=dict)
    happened_at: int = field(default_factory=lambda: int(time.time()))
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_state: AgentStateSnapshot | None = None

    def __post_init__(self) -> None:
        if not self.type.strip():
            raise ValueError("event type must not be empty")
        _validate_social_context(self.facts)


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
    max_context_tokens: int = 4_096

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.agent_id.strip():
            raise ValueError("request id and agent_id must not be empty")
        validate_clod(self.preferred_clod, "preferred_clod")
        if not 0.0 <= self.urgency <= 1.0:
            raise ValueError("urgency must be between 0 and 1")
        if self.max_tokens <= 0 or self.max_context_tokens < 0 or self.deadline_ms <= 0:
            raise ValueError(
                "max_tokens and deadline_ms must be positive; max_context_tokens cannot be negative"
            )
