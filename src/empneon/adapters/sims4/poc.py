"""Sims 4 POC translation for the Stage 1 autonomous vertical slice."""

from collections.abc import Mapping

from empneon.core.contracts import ActionResult, Decision, WorldEvent


class Sims4PocAdapter:
    def __init__(self, payload: Mapping[str, object]) -> None:
        self._payload = payload

    def observe(self) -> tuple[WorldEvent, ...]:
        sim = self._payload.get("sim")
        sim_data = sim if isinstance(sim, Mapping) else self._payload
        actor_id = str(sim_data.get("id") or sim_data.get("name") or "unknown-sim")
        return (
            WorldEvent(
                "autonomous_tick",
                actor_ids=(actor_id,),
                facts={"source": "sims4_poc"},
            ),
        )

    def execute(self, decision: Decision, /) -> ActionResult:
        return ActionResult(decision.id, "succeeded")
