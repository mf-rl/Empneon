"""Translate between The Sims 4 observations and Empneon Core contracts."""

from collections.abc import Mapping

from empneon.core.contracts import ActionResult, Decision, StateDelta, WorldEvent

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


class Sims4Adapter:
    def __init__(self, payload: Mapping[str, object]) -> None:
        self._payload = payload

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
                },
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
            "dialogue": "I hear you.",
            "emotion": "neutral",
            "intent": decision.intent,
            "relationship": {
                "friendship_delta": 0,
                "romance_delta": 0,
                "trust_delta": 0,
            },
            "memory": {"importance": 0.2, "summary": "The conversation was acknowledged."},
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
