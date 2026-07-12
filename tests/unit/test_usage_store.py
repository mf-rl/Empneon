from empneon.core.contracts import CognitiveRequest, WorldEvent
from empneon.core.scheduler.resources import ResourceEstimate
from empneon.core.scheduler.usage import UsageStore
from empneon.db.connection import open_db
from empneon.providers.llm import GenerationResult


def test_records_estimates_and_actual_provider_usage() -> None:
    store = UsageStore(open_db(":memory:"))
    request = CognitiveRequest("alice", 3, WorldEvent("conversation", id="event-1"))
    estimate = ResourceEstimate(100, 200, 800, 300, 2_000)

    created = store.record(
        request,
        estimate,
        "lmstudio",
        "local-model",
        GenerationResult("hello", 750, 42, 1_250),
    )

    assert store.get_for_request(request.id) == [created]
    assert created.estimate == estimate
    assert created.prompt_tokens == 750
    assert created.completion_tokens == 42
    assert created.latency_ms == 1_250
