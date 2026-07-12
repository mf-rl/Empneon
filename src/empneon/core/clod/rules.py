"""Provider-free deterministic cognition for CLOD 1."""

import uuid

from empneon.core.contracts import CognitiveRequest, Decision


def resolve_clod1(request: CognitiveRequest) -> Decision:
    """Acknowledge an event without inference or speculative state changes."""
    target_id = next(
        (
            actor_id
            for actor_id in request.event.actor_ids
            if actor_id and actor_id != request.agent_id
        ),
        None,
    )
    decision_key = f"empneon:clod1:{request.agent_id}:{request.event.id}"
    return Decision(
        id=str(uuid.uuid5(uuid.NAMESPACE_URL, decision_key)),
        actor_id=request.agent_id,
        intent="acknowledge",
        target_id=target_id,
        evidence_ids=(request.event.id,),
    )
