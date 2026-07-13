"""Deterministic SocietyBench workload definitions."""

from dataclasses import dataclass

from empneon.core.contracts import CognitiveRequest, WorldEvent

AGENT_COUNT = 20


@dataclass(frozen=True)
class BenchmarkScenario:
    name: str
    agent_ids: tuple[str, ...]
    requests: tuple[CognitiveRequest, ...]


def build_20_agent_scenarios() -> tuple[BenchmarkScenario, ...]:
    """Return stable social topologies for comparing later benchmark strategies."""
    agent_ids = tuple(f"agent-{index:02d}" for index in range(AGENT_COUNT))
    return (
        _build_scenario(
            "social-ring",
            agent_ids,
            tuple((index + 1) % AGENT_COUNT for index in range(AGENT_COUNT)),
        ),
        _build_scenario(
            "reciprocal-pairs",
            agent_ids,
            tuple(index + 1 if index % 2 == 0 else index - 1 for index in range(AGENT_COUNT)),
        ),
    )


def _build_scenario(
    name: str, agent_ids: tuple[str, ...], target_indexes: tuple[int, ...]
) -> BenchmarkScenario:
    requests = tuple(
        CognitiveRequest(
            id=f"{name}-request-{index:02d}",
            agent_id=agent_id,
            preferred_clod=1,
            event=WorldEvent(
                id=f"{name}-event-{index:02d}",
                type="benchmark_social",
                actor_ids=(agent_id, agent_ids[target_indexes[index]]),
                location="societybench",
                facts={"scenario": name, "sequence": index},
                happened_at=index,
            ),
        )
        for index, agent_id in enumerate(agent_ids)
    )
    return BenchmarkScenario(name, agent_ids, requests)
