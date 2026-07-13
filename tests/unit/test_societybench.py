from empneon.benchmarks import build_20_agent_scenarios
from empneon.core.clod import resolve_clod1


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
