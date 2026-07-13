"""Deterministic SocietyBench workloads and baseline execution."""

from dataclasses import dataclass, replace
from math import isfinite
from random import Random
from typing import Literal

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
class CognitionComparison:
    comparison_id: str
    request: CognitiveRequest
    cheap_strategy: str
    cheap_decision: Decision
    expensive_strategy: str
    expensive_decision: Decision


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


@dataclass(frozen=True)
class BenchmarkClaim:
    agent_id: str
    subject: str
    value: str

    def __post_init__(self) -> None:
        if not self.agent_id.strip() or not self.subject.strip() or not self.value.strip():
            raise ValueError("benchmark claim fields must not be empty")


@dataclass(frozen=True)
class ConsistencyMetrics:
    retained_agents: int
    expected_agents: int
    identity_continuity_rate: float
    contradictory_subjects: int
    evaluated_subjects: int
    contradiction_rate: float


@dataclass(frozen=True)
class BelievabilitySample:
    sample_id: str
    request_id: str
    event_type: str
    actor_ids: tuple[str, ...]
    option_a: str
    option_b: str


@dataclass(frozen=True)
class BelievabilityKey:
    sample_id: str
    option_a_strategy: str
    option_b_strategy: str

    def __post_init__(self) -> None:
        if {self.option_a_strategy, self.option_b_strategy} != {
            "one-call-per-agent",
            "fixed-clod-1",
        }:
            raise ValueError("each answer key must contain both baseline strategies")


@dataclass(frozen=True)
class BelievabilityRating:
    sample_id: str
    preferred: Literal["A", "B", "tie"]

    def __post_init__(self) -> None:
        if not self.sample_id.strip() or self.preferred not in {"A", "B", "tie"}:
            raise ValueError("rating requires a sample id and A, B, or tie preference")


@dataclass(frozen=True)
class BelievabilityMetrics:
    evaluated_samples: int
    one_call_wins: int
    fixed_clod_wins: int
    ties: int
    one_call_win_rate: float
    fixed_clod_win_rate: float
    deeper_reasoning_net_preference: float


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


def collect_cognition_comparisons(
    scenario: BenchmarkScenario,
    results: tuple[BaselineResult, BaselineResult],
) -> tuple[CognitionComparison, ...]:
    """Pair cheap and expensive decisions for the same cognitive request."""
    by_strategy = {result.strategy: result for result in results}
    required = {"one-call-per-agent", "fixed-clod-1"}
    if set(by_strategy) != required:
        raise ValueError("one-call-per-agent and fixed-clod-1 results are required")
    if any(len(result.decisions) != len(scenario.requests) for result in results):
        raise ValueError("each strategy must contain one decision per request")
    cheap = by_strategy["fixed-clod-1"]
    expensive = by_strategy["one-call-per-agent"]
    comparisons = []
    for index, request in enumerate(scenario.requests):
        cheap_decision = cheap.decisions[index]
        expensive_decision = expensive.decisions[index]
        if {
            cheap_decision.actor_id,
            expensive_decision.actor_id,
        } != {request.agent_id}:
            raise ValueError("comparison decisions must match the request agent")
        comparisons.append(
            CognitionComparison(
                f"{scenario.name}-{index:02d}",
                request,
                cheap.strategy,
                cheap_decision,
                expensive.strategy,
                expensive_decision,
            )
        )
    return tuple(comparisons)


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


def measure_consistency(
    expected_agent_ids: tuple[str, ...],
    observed_agent_ids: tuple[str, ...],
    claims: tuple[BenchmarkClaim, ...],
) -> ConsistencyMetrics:
    """Measure retained identities and conflicting values for each agent subject."""
    expected = set(expected_agent_ids)
    if not expected:
        raise ValueError("expected agent ids are required")
    retained = len(expected & set(observed_agent_ids))
    values_by_subject: dict[tuple[str, str], set[str]] = {}
    for claim in claims:
        values_by_subject.setdefault((claim.agent_id, claim.subject), set()).add(claim.value)
    contradictory = sum(len(values) > 1 for values in values_by_subject.values())
    evaluated = len(values_by_subject)
    return ConsistencyMetrics(
        retained,
        len(expected),
        retained / len(expected),
        contradictory,
        evaluated,
        contradictory / evaluated if evaluated else 0.0,
    )


def build_blinded_believability_evaluation(
    scenario: BenchmarkScenario,
    results: tuple[BaselineResult, BaselineResult],
    seed: int = 0,
) -> tuple[tuple[BelievabilitySample, ...], tuple[BelievabilityKey, ...]]:
    """Randomize baseline labels while retaining a separate answer key."""
    random = Random(seed)
    samples = []
    keys = []
    for comparison in collect_cognition_comparisons(scenario, results):
        options = [
            (comparison.expensive_decision.intent, comparison.expensive_strategy),
            (comparison.cheap_decision.intent, comparison.cheap_strategy),
        ]
        if random.randrange(2):
            options.reverse()
        samples.append(
            BelievabilitySample(
                comparison.comparison_id,
                comparison.request.id,
                comparison.request.event.type,
                comparison.request.event.actor_ids,
                options[0][0],
                options[1][0],
            )
        )
        keys.append(
            BelievabilityKey(comparison.comparison_id, options[0][1], options[1][1])
        )
    return tuple(samples), tuple(keys)


def measure_believability(
    ratings: tuple[BelievabilityRating, ...],
    keys: tuple[BelievabilityKey, ...],
) -> BelievabilityMetrics:
    """Reveal blinded preferences and count wins for each baseline."""
    key_by_id = {key.sample_id: key for key in keys}
    if not ratings or len(key_by_id) != len(keys):
        raise ValueError("ratings and unique answer keys are required")
    if len({rating.sample_id for rating in ratings}) != len(ratings):
        raise ValueError("ratings must have unique sample ids")
    one_call_wins = 0
    fixed_clod_wins = 0
    ties = 0
    for rating in ratings:
        key = key_by_id.get(rating.sample_id)
        if key is None:
            raise ValueError(f"missing answer key for {rating.sample_id}")
        if rating.preferred == "tie":
            ties += 1
        elif getattr(key, f"option_{rating.preferred.lower()}_strategy") == "one-call-per-agent":
            one_call_wins += 1
        else:
            fixed_clod_wins += 1
    evaluated = len(ratings)
    return BelievabilityMetrics(
        evaluated,
        one_call_wins,
        fixed_clod_wins,
        ties,
        one_call_wins / evaluated,
        fixed_clod_wins / evaluated,
        (one_call_wins - fixed_clod_wins) / evaluated,
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
