"""Sims 4 POC translation for the Stage 1 autonomous vertical slice."""

from collections.abc import Mapping

from empneon.core.contracts import ActionResult, Decision, StateDelta, WorldEvent


class Sims4PocAdapter:
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
        actor_ids = (actor_id, listener_id) if listener_id else (actor_id,)
        return (
            WorldEvent(
                "conversation" if message else "autonomous_tick",
                actor_ids=actor_ids,
                location=str(self._payload.get("location") or "unknown"),
                facts={"source": "sims4_poc", "message": message},
            ),
        )

    def execute(self, decision: Decision, /) -> ActionResult:
        supported = {"dialogue", "emotion", "memory", "animation"}
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
        return ActionResult(decision.id, "succeeded", decision.state_changes)

    def decision_from_response(self, response: Mapping[str, object], event_id: str) -> Decision:
        relationship = response.get("relationship")
        relationship_data = relationship if isinstance(relationship, Mapping) else {}
        memory = response.get("memory")
        changes = [
            StateDelta("dialogue", "set", str(response.get("dialogue") or "...")),
            StateDelta("emotion", "set", str(response.get("emotion") or "neutral")),
            StateDelta("memory", "append", memory if isinstance(memory, Mapping) else {}),
            StateDelta("animation", "set", str(response.get("animation") or "friendly_chat")),
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

    def response_for(self, decision: Decision) -> dict[str, object]:
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
        for change in decision.state_changes:
            if change.path.startswith("relationship."):
                relationship[f"{change.path.split('.', 1)[1]}_delta"] = change.value
            elif change.path in response:
                response[change.path] = change.value
        return response
