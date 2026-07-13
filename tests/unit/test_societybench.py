import asyncio

from empneon.benchmarks import build_20_agent_scenarios, measure_baselines
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
