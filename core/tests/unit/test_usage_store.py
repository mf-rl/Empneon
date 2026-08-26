import pytest

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
        3,
    )

    assert store.get_for_request(request.id) == [created]
    assert created.estimate == estimate
    assert created.prompt_tokens == 750
    assert created.completion_tokens == 42
    assert created.latency_ms == 1_250
    assert created.clod == 3


def test_summarizes_resource_and_clod_telemetry() -> None:
    store = UsageStore(open_db(":memory:"))
    first = CognitiveRequest("alice", 2, WorldEvent("conversation", id="event-1"))
    second = CognitiveRequest("bob", 4, WorldEvent("conflict", id="event-2"))
    store.record(
        first,
        ResourceEstimate(100, 200, 800, 200, 1_000),
        "local",
        "small",
        GenerationResult("hello", 700, 40, 800),
        2,
    )
    store.record(
        second,
        ResourceEstimate(200, 300, 1_000, 300, 2_000),
        "hosted",
        "large",
        GenerationResult("reply", 900, 60, 1_200),
        4,
    )

    telemetry = store.telemetry()

    assert telemetry["attempts"] == telemetry["requests"] == 2
    assert telemetry["by_clod"] == {"2": 1, "4": 1}
    assert telemetry["by_provider"] == {"local": 1, "hosted": 1}
    assert telemetry["estimated"] == {
        "peak_ram_mb": 200,
        "peak_vram_mb": 300,
        "context_tokens": 1_800,
        "completion_tokens": 500,
        "latency_ms": 3_000,
    }
    assert telemetry["actual"] == {
        "prompt_tokens": 1_600,
        "completion_tokens": 100,
        "latency_ms": 2_000,
    }
    assert store.telemetry("alice")["by_clod"] == {"2": 1}
    estimate = ResourceEstimate()
    result = GenerationResult("", 0, 0, 0)
    with pytest.raises(ValueError, match="CLOD"):
        store.record(
            first,
            estimate,
            "local",
            "small",
            result,
            5,
        )
