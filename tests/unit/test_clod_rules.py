from empneon.core.clod import resolve_clod1
from empneon.core.contracts import CognitiveRequest, WorldEvent


def test_clod1_replays_the_same_provider_free_decision() -> None:
    request = CognitiveRequest(
        "alice",
        preferred_clod=1,
        event=WorldEvent("social_event", actor_ids=("alice", "bob"), id="event-1"),
    )

    first = resolve_clod1(request)

    assert first == resolve_clod1(request)
    assert first.intent == "acknowledge"
    assert first.target_id == "bob"
    assert first.evidence_ids == ("event-1",)
    assert first.state_changes == ()
