"""Deterministic SocietyBench workloads and baseline execution."""

from dataclasses import dataclass, replace
from math import isfinite

from empneon.core.clod.fallback import Resolver
from empneon.core.clod.rules import resolve_clod1
from empneon.core.contracts import CognitiveRequest, Decision, WorldEvent

AGENT_COUNT = 20


@dataclass(frozen=True)
class BenchmarkScenario:
    name: str
    agent_ids: tuple[str, ...]
    requests: tuple[CognitiveRequest, ...]


@dataclass(frozen=True)
class BaselineResult:
    strategy: str
    decisions: tuple[Decision, ...]
    provider_calls: int


@dataclass(frozen=True)
class BenchmarkObservation:
    cpu_percent: float
    ram_mb: float
    vram_mb: float
    frame_time_ms: float
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float

    def __post_init__(self) -> None:
        values = (
            self.cpu_percent,
            self.ram_mb,
            self.vram_mb,
            self.frame_time_ms,
            self.prompt_tokens,
            self.completion_tokens,
            self.latency_ms,
        )
        if any(not isfinite(value) or value < 0 for value in values):
            raise ValueError("benchmark observations must be finite and nonnegative")


@dataclass(frozen=True)
class BenchmarkMetrics:
    strategy: str
    observations: tuple[BenchmarkObservation, ...]
    peak_cpu_percent: float
    peak_ram_mb: float
    peak_vram_mb: float
    peak_frame_time_ms: float
    total_prompt_tokens: int
    total_completion_tokens: int
    latency_p50_ms: float
    latency_p95_ms: float


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


async def measure_baselines(
    scenario: BenchmarkScenario, resolver: Resolver
) -> tuple[BaselineResult, BaselineResult]:
    """Run one forced provider call per agent and the provider-free fixed CLOD 1 path."""
    one_call = tuple(
        [await resolver(replace(request, preferred_clod=3)) for request in scenario.requests]
    )
    fixed_clod = tuple(resolve_clod1(request) for request in scenario.requests)
    return (
        BaselineResult("one-call-per-agent", one_call, len(one_call)),
        BaselineResult("fixed-clod-1", fixed_clod, 0),
    )


def summarize_metrics(
    strategy: str, observations: tuple[BenchmarkObservation, ...]
) -> BenchmarkMetrics:
    """Retain raw observations and summarize one benchmark strategy."""
    if not strategy.strip() or not observations:
        raise ValueError("strategy and observations are required")
    latencies = tuple(observation.latency_ms for observation in observations)
    return BenchmarkMetrics(
        strategy,
        observations,
        max(observation.cpu_percent for observation in observations),
        max(observation.ram_mb for observation in observations),
        max(observation.vram_mb for observation in observations),
        max(observation.frame_time_ms for observation in observations),
        sum(observation.prompt_tokens for observation in observations),
        sum(observation.completion_tokens for observation in observations),
        _percentile(latencies, 0.50),
        _percentile(latencies, 0.95),
    )


def _percentile(values: tuple[float, ...], quantile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


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
