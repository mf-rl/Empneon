import asyncio

import pytest

from empneon.benchmarks import (
    BaselineResult,
    BelievabilityRating,
    BenchmarkClaim,
    BenchmarkObservation,
    build_20_agent_scenarios,
    build_blinded_believability_evaluation,
    collect_cognition_comparisons,
    measure_baselines,
    measure_believability,
    measure_consistency,
    summarize_metrics,
)
from empneon.core.clod import resolve_clod1
from empneon.core.contracts import CognitiveRequest, Decision


def test_20_agent_scenarios_are_complete_and_deterministic() -> None:
    scenarios = build_20_agent_scenarios()
    rebuilt = build_20_agent_scenarios()

    assert scenarios == rebuilt
    assert [scenario.name for scenario in scenarios] == ["social-ring", "reciprocal-pairs"]
    for scenario, rebuilt_scenario in zip(scenarios, rebuilt, strict=True):
        assert len(scenario.agent_ids) == len(set(scenario.agent_ids)) == 20
        assert len(scenario.requests) == 20
        assert {request.agent_id for request in scenario.requests} == set(scenario.agent_ids)
        assert {
            actor_id
            for request in scenario.requests
            for actor_id in request.event.actor_ids
        } == set(scenario.agent_ids)
        assert all(request.preferred_clod == 1 for request in scenario.requests)
        assert [resolve_clod1(request) for request in scenario.requests] == [
            resolve_clod1(request) for request in rebuilt_scenario.requests
        ]


def test_baselines_measure_one_call_per_agent_against_fixed_clod() -> None:
    calls: list[CognitiveRequest] = []

    async def resolver(request: CognitiveRequest) -> Decision:
        calls.append(request)
        return Decision(request.agent_id, "provider-response", evidence_ids=(request.event.id,))

    scenario = build_20_agent_scenarios()[0]
    one_call, fixed_clod = asyncio.run(measure_baselines(scenario, resolver))

    assert one_call.strategy == "one-call-per-agent"
    assert len(one_call.decisions) == one_call.provider_calls == len(calls) == 20
    assert all(request.preferred_clod == 3 for request in calls)
    assert fixed_clod.strategy == "fixed-clod-1"
    assert len(fixed_clod.decisions) == 20
    assert fixed_clod.provider_calls == 0


def test_metrics_retain_raw_samples_and_compute_totals_and_percentiles() -> None:
    observations = tuple(
        BenchmarkObservation(
            cpu_percent=index * 10,
            ram_mb=index * 100,
            vram_mb=index * 200,
            frame_time_ms=index * 5,
            prompt_tokens=index,
            completion_tokens=index * 2,
            latency_ms=index * 10,
        )
        for index in range(1, 5)
    )

    metrics = summarize_metrics("one-call-per-agent", observations)

    assert metrics.observations == observations
    assert (metrics.peak_cpu_percent, metrics.peak_ram_mb, metrics.peak_vram_mb) == (
        40,
        400,
        800,
    )
    assert metrics.peak_frame_time_ms == 20
    assert (metrics.total_prompt_tokens, metrics.total_completion_tokens) == (10, 20)
    assert (metrics.latency_p50_ms, metrics.latency_p95_ms) == (25, 38.5)
    with pytest.raises(ValueError, match="finite and nonnegative"):
        BenchmarkObservation(-1, 0, 0, 0, 0, 0, 0)


def test_collects_aligned_cheap_and_expensive_cognition_comparisons() -> None:
    scenario = build_20_agent_scenarios()[0]
    expensive = BaselineResult(
        "one-call-per-agent",
        tuple(Decision(agent, "consider context") for agent in scenario.agent_ids),
        20,
    )
    cheap = BaselineResult(
        "fixed-clod-1",
        tuple(Decision(agent, "acknowledge") for agent in scenario.agent_ids),
        0,
    )

    comparisons = collect_cognition_comparisons(scenario, (expensive, cheap))

    assert len(comparisons) == 20
    assert comparisons[0].comparison_id == "social-ring-00"
    assert comparisons[0].request == scenario.requests[0]
    assert comparisons[0].cheap_strategy == "fixed-clod-1"
    assert comparisons[0].cheap_decision.intent == "acknowledge"
    assert comparisons[0].expensive_strategy == "one-call-per-agent"
    assert comparisons[0].expensive_decision.intent == "consider context"


def test_rejects_misaligned_cognition_comparisons() -> None:
    scenario = build_20_agent_scenarios()[0]
    decisions = tuple(Decision(agent, "acknowledge") for agent in scenario.agent_ids)
    misaligned = (Decision("wrong-agent", "consider context"),) + decisions[1:]

    with pytest.raises(ValueError, match="match the request agent"):
        collect_cognition_comparisons(
            scenario,
            (
                BaselineResult("fixed-clod-1", decisions, 0),
                BaselineResult("one-call-per-agent", misaligned, 20),
            ),
        )


def test_consistency_measures_identity_continuity_and_contradictions() -> None:
    agents = build_20_agent_scenarios()[0].agent_ids
    metrics = measure_consistency(
        agents,
        agents[:18] + ("unexpected-agent",),
        (
            BenchmarkClaim("agent-00", "mood", "happy"),
            BenchmarkClaim("agent-00", "mood", "happy"),
            BenchmarkClaim("agent-01", "mood", "happy"),
            BenchmarkClaim("agent-01", "mood", "angry"),
            BenchmarkClaim("agent-02", "intent", "greet"),
        ),
    )

    assert (metrics.retained_agents, metrics.expected_agents) == (18, 20)
    assert metrics.identity_continuity_rate == 0.9
    assert (metrics.contradictory_subjects, metrics.evaluated_subjects) == (1, 3)
    assert metrics.contradiction_rate == pytest.approx(1 / 3)


def test_believability_evaluation_blinds_and_reveals_baseline_preferences() -> None:
    scenario = build_20_agent_scenarios()[0]
    one_call = BaselineResult(
        "one-call-per-agent",
        tuple(Decision(agent, "ask about their day") for agent in scenario.agent_ids),
        20,
    )
    fixed_clod = BaselineResult(
        "fixed-clod-1",
        tuple(Decision(agent, "acknowledge") for agent in scenario.agent_ids),
        0,
    )

    samples, keys = build_blinded_believability_evaluation(
        scenario, (one_call, fixed_clod), seed=7
    )
    rebuilt, rebuilt_keys = build_blinded_believability_evaluation(
        scenario, (one_call, fixed_clod), seed=7
    )
    ratings = tuple(
        BelievabilityRating(
            sample.sample_id,
            "A" if key.option_a_strategy == "one-call-per-agent" else "B",
        )
        for sample, key in zip(samples, keys, strict=True)
    )
    ratings = ratings[:-1] + (BelievabilityRating(ratings[-1].sample_id, "tie"),)
    metrics = measure_believability(ratings, keys)

    assert (samples, keys) == (rebuilt, rebuilt_keys)
    assert {sample.option_a for sample in samples} == {"acknowledge", "ask about their day"}
    counts = (
        metrics.evaluated_samples,
        metrics.one_call_wins,
        metrics.fixed_clod_wins,
        metrics.ties,
    )
    assert counts == (
        20,
        19,
        0,
        1,
    )
    assert metrics.one_call_win_rate == 0.95
