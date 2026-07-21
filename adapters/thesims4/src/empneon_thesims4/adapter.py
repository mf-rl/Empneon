"""Translate between The Sims 4 observations and Empneon Core contracts."""

import hashlib
import math
import re
from collections.abc import Mapping

from empneon.core.contracts import (
    ActionResult,
    AgentStateSnapshot,
    Decision,
    StateDelta,
    WorldEvent,
)

SIMS_ACTIONS = frozenset(
    {
        "idle",
        "friendly_chat",
        "funny_chat",
        "romantic_chat",
        "awkward_chat",
        "angry_chat",
        "sad_chat",
        "apologize",
        "argue",
        "flirt",
        "laugh",
    }
)

INTENT_ACTIONS = {
    "acknowledge": "idle",
    "accept_apology": "apologize",
    "apologize": "apologize",
    "argue": "argue",
    "deflect": "awkward_chat",
    "flirt": "flirt",
    "greet": "friendly_chat",
    "joke": "funny_chat",
    "reassure": "friendly_chat",
    "respond": "friendly_chat",
    "set_boundary": "awkward_chat",
}


def feature_hash(text: str, dimensions: int = 384) -> list[float]:
    vector = [0.0] * dimensions
    for token in re.findall(r"\w+", text.casefold()):
        raw = int.from_bytes(
            hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest(), "big"
        )
        vector[raw % dimensions] += -1.0 if raw & 1 else 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else vector


def _mapping(value: object) -> dict[object, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def _items(value: object) -> list[object]:
    return list(value) if isinstance(value, (list, tuple)) else []


def cognition_priority(
    payload: Mapping[str, object],
    *,
    novel: bool = False,
    emotion_intensity: float = 0.0,
    goal_relevant: bool = False,
) -> tuple[float, int, float]:
    event = payload.get("event")
    event_data = event if isinstance(event, Mapping) else {}
    event_type = str(event_data.get("type") or "")
    if event_type == "player_conversation":
        urgency, preferred_clod = 1.0, 3
    elif event_type in ("crisis", "critical_need"):
        urgency, preferred_clod = 0.85, 3
    elif goal_relevant:
        urgency, preferred_clod = 0.65, 2
    else:
        urgency, preferred_clod = 0.35, 1
    value = (
        (0.4 if event_type == "player_conversation" else 0.0)
        + (0.2 if novel else 0.0)
        + 0.2 * max(0.0, min(1.0, float(emotion_intensity)))
        + (0.2 if goal_relevant else 0.0)
    )
    return urgency, preferred_clod, min(1.0, value)


class Sims4Adapter:
    def __init__(self, payload: Mapping[str, object]) -> None:
        self._payload = payload

    def agent_state(self) -> AgentStateSnapshot:
        speaker = _mapping(self._payload.get("speaker"))
        listener = _mapping(self._payload.get("listener"))
        relationship = _mapping(self._payload.get("relationship"))
        listener_id = str(listener.get("id") or "")
        needs = {
            str(name): {
                "level": max(0.0, min(1.0, float(value) / 100)),
                "urgency": max(0.0, min(1.0, 1 - float(value) / 100)),
            }
            for name, value in _mapping(speaker.get("needs")).items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }
        relationships = {}
        if listener_id:
            relationships[listener_id] = {
                "affinity": max(
                    -1.0,
                    min(1.0, float(relationship.get("friendship", 0)) / 100),
                ),
                "romance": max(
                    0.0, min(1.0, float(relationship.get("romance", 0)) / 100)
                ),
                "trust": max(
                    0.0, min(1.0, float(relationship.get("trust", 50)) / 100)
                ),
            }
        mood = str(speaker.get("current_mood") or "unknown")
        native = _mapping(speaker.get("native"))
        native.setdefault("mood", mood)
        native.setdefault("moodlets", _items(speaker.get("moodlets")))
        return AgentStateSnapshot(
            1,
            "sims4",
            str(speaker.get("id") or speaker.get("name") or "unknown-sim"),
            affect={"tags": [] if mood == "unknown" else [mood]},
            needs=needs,
            effects=_items(speaker.get("effects")),
            relationships=relationships,
            goals=_items(speaker.get("goals")),
            intentions=_items(speaker.get("intentions")),
            capabilities={
                "actions": _items(self._payload.get("available_actions"))
            },
            native=native,
        )

    def observe(self) -> tuple[WorldEvent, ...]:
        sim = self._payload.get("sim")
        speaker = self._payload.get("speaker")
        sim_data = sim if isinstance(sim, Mapping) else speaker
        sim_data = sim_data if isinstance(sim_data, Mapping) else self._payload
        actor_id = str(sim_data.get("id") or sim_data.get("name") or "unknown-sim")
        listener = self._payload.get("listener")
        listener_data = listener if isinstance(listener, Mapping) else {}
        listener_id = str(listener_data.get("id") or listener_data.get("name") or "")
        message = str(self._payload.get("message") or "")
        relationship = self._payload.get("relationship")
        relationship_data = relationship if isinstance(relationship, Mapping) else {}
        social_event = self._payload.get("event")
        social_event_data = social_event if isinstance(social_event, Mapping) else {}
        event_type = str(
            social_event_data.get("type") or ("conversation" if message else "autonomous_tick")
        )
        actor_ids = (actor_id, listener_id) if listener_id else (actor_id,)
        return (
            WorldEvent(
                event_type,
                actor_ids=actor_ids,
                location=str(self._payload.get("location") or "unknown"),
                facts={
                    "source": str(social_event_data.get("source") or "sims4"),
                    "message": message,
                    "participants": tuple(dict(item) for item in (sim_data, listener_data) if item),
                    "moods": {
                        str(item.get("id") or item.get("name")): item.get("current_mood")
                        for item in (sim_data, listener_data)
                        if item
                    },
                    "relationship": dict(relationship_data),
                    "needs": _mapping(sim_data.get("needs")),
                    "moodlets": _items(sim_data.get("moodlets")),
                    "aspiration": str(sim_data.get("aspiration") or "unknown"),
                    "career": str(sim_data.get("career") or "unknown"),
                    "skills": _mapping(sim_data.get("skills")),
                    "household": _mapping(sim_data.get("household")),
                    "nearby_sims": _items(self._payload.get("nearby_sims")),
                    "available_actions": _items(
                        self._payload.get("available_actions")
                    ),
                },
                agent_state=self.agent_state(),
            ),
        )

    def execute(self, decision: Decision, /) -> ActionResult:
        supported = {"dialogue", "emotion", "memory"}
        unsupported = [
            change.path
            for change in decision.state_changes
            if change.path.split(".", 1)[0] not in supported | {"relationship"}
        ]
        if unsupported:
            return ActionResult(
                decision.id,
                "rejected",
                reason=f"unsupported Sims state path: {unsupported[0]}",
            )
        action = self.action_for(decision)
        if action is None:
            return ActionResult(
                decision.id, "rejected", reason="no supported Sims action available"
            )
        applied = decision.state_changes + (StateDelta("animation", "set", action),)
        return ActionResult(decision.id, "succeeded", applied)

    def action_for(self, decision: Decision) -> str | None:
        return self._action_for(decision.intent)

    def decision_from_response(self, response: Mapping[str, object], event_id: str) -> Decision:
        relationship = response.get("relationship")
        relationship_data = relationship if isinstance(relationship, Mapping) else {}
        memory = response.get("memory")
        changes = [
            StateDelta("dialogue", "set", str(response.get("dialogue") or "...")),
            StateDelta("emotion", "set", str(response.get("emotion") or "neutral")),
            StateDelta("memory", "append", memory if isinstance(memory, Mapping) else {}),
        ]
        changes.extend(
            StateDelta(f"relationship.{key.removesuffix('_delta')}", "increment", value)
            for key, value in relationship_data.items()
            if key.endswith("_delta")
        )
        event = self.observe()[0]
        return Decision(
            actor_id=event.actor_ids[0],
            intent=str(response.get("intent") or "respond"),
            target_id=event.actor_ids[1] if len(event.actor_ids) > 1 else None,
            evidence_ids=(event_id,),
            state_changes=tuple(changes),
        )

    def response_for(
        self, decision: Decision, result: ActionResult | None = None
    ) -> dict[str, object]:
        response: dict[str, object] = {
            "dialogue": (
                "My language model is unavailable, so I can't answer reliably right now."
            ),
            "emotion": "neutral",
            "intent": decision.intent,
            "relationship": {
                "friendship_delta": 0,
                "romance_delta": 0,
                "trust_delta": 0,
            },
            "memory": {"importance": 0.0, "summary": ""},
            "animation": "friendly_chat",
        }
        relationship = response["relationship"]
        assert isinstance(relationship, dict)
        changes = result.applied_changes if result is not None else decision.state_changes
        for change in changes:
            if change.path.startswith("relationship."):
                relationship[f"{change.path.split('.', 1)[1]}_delta"] = change.value
            elif change.path in response:
                response[change.path] = change.value
        return response

    def _action_for(self, intent: str) -> str | None:
        configured = self._payload.get("available_actions")
        if isinstance(configured, (list, tuple)):
            available = [str(action) for action in configured if str(action) in SIMS_ACTIONS]
        else:
            available = sorted(SIMS_ACTIONS)
        preferred = INTENT_ACTIONS.get(intent, "friendly_chat")
        relationship = self._payload.get("relationship")
        if intent == "acknowledge" and isinstance(relationship, Mapping):
            raw_score = relationship.get("raw_score")
            if isinstance(raw_score, (int, float)) and raw_score < 0:
                preferred = "apologize"
        if preferred in available:
            return preferred
        if "friendly_chat" in available:
            return "friendly_chat"
        return available[0] if available else None
