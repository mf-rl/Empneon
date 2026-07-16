"""Generate and score a blinded SocietyBench believability packet."""

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal, cast

from empneon.benchmarks.societybench import (
    AdaptiveSelection,
    BelievabilityKey,
    BelievabilityRating,
    BenchmarkClaim,
    BenchmarkScenario,
    build_20_agent_scenarios,
    build_blinded_believability_evaluation,
    build_differentiated_adaptive_workload,
    compare_adaptive_to_baselines,
    measure_baselines,
    measure_believability,
    measure_consistency,
)
from empneon.core.contracts import CognitiveRequest, Decision
from empneon.providers.llm import GenerationRequest, Message, OpenAICompatibleProvider

RUBRIC = (
    "Choose A, B, or tie for the action that is more believable in context. "
    "Consider contextual fit, social plausibility, and specificity."
)


async def generate_packet(
    base_url: str, model: str, seed: int, adaptive: bool = False
) -> tuple[dict[str, object], dict[str, object]]:
    provider = OpenAICompatibleProvider(base_url, model, timeout_seconds=90)
    observations: list[dict[str, int | None]] = []

    async def resolver(request: CognitiveRequest) -> Decision:
        target = next(actor for actor in request.event.actor_ids if actor != request.agent_id)
        prompt = (
            f"Agent {request.agent_id} encounters {target} during {request.event.type}. "
            "Return only one concise believable social action of two to six words."
        )
        result = await provider.generate(
            GenerationRequest((Message("user", prompt),), max_tokens=16, temperature=0.2)
        )
        observations.append(
            {
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "latency_ms": result.latency_ms,
            }
        )
        intent = " ".join(result.content.strip().split())
        if not intent:
            raise ValueError("provider returned an empty believability candidate")
        return Decision(request.agent_id, intent, target_id=target)

    workload = build_differentiated_adaptive_workload() if adaptive else ()
    scenario = (
        BenchmarkScenario(
            "adaptive-differentiated",
            tuple(case.request.agent_id for case in workload),
            tuple(case.request for case in workload),
        )
        if adaptive
        else build_20_agent_scenarios()[0]
    )
    results = await measure_baselines(scenario, resolver)
    samples, keys = build_blinded_believability_evaluation(scenario, results, seed)
    key: dict[str, object] = {
        "scenario": scenario.name,
        "model": model,
        "seed": seed,
        "keys": [asdict(item) for item in keys],
    }
    if adaptive:
        selections = tuple(
            AdaptiveSelection(
                sample.sample_id,
                "one-call-per-agent"
                if case.selection_score >= 0.5
                else "fixed-clod-1",
            )
            for sample, case in zip(samples, workload, strict=True)
        )
        chosen = tuple(
            results[0].decisions[index]
            if selection.strategy == "one-call-per-agent"
            else results[1].decisions[index]
            for index, selection in enumerate(selections)
        )
        consistency = measure_consistency(
            scenario.agent_ids,
            tuple(decision.actor_id for decision in chosen),
            tuple(
                BenchmarkClaim(decision.actor_id, "target", decision.target_id or "none")
                for decision in chosen
            ),
        )
        key["adaptive"] = {
            "minimum_value": 0.5,
            "minimum_preference_retention": 0.9,
            "minimum_identity_continuity": 1.0,
            "maximum_contradiction_rate": 0.0,
            "selections": [asdict(selection) for selection in selections],
            "one_call_observations": observations,
            "consistency": asdict(consistency),
        }
    return (
        {
            "scenario": scenario.name,
            "model": model,
            "seed": seed,
            "rubric": RUBRIC,
            "samples": [{**asdict(sample), "preferred": None} for sample in samples],
        },
        key,
    )


def score_packet(packet: dict[str, Any], answer_key: dict[str, Any]) -> dict[str, object]:
    sample_rows = cast(list[dict[str, object]], packet.get("samples"))
    key_rows = cast(list[dict[str, str]], answer_key.get("keys"))
    if not isinstance(sample_rows, list) or not isinstance(key_rows, list):
        raise ValueError("packet samples and answer keys are required")
    allowed = {"A", "B", "tie"}
    if any(row.get("preferred") not in allowed for row in sample_rows):
        raise ValueError("every sample preference must be A, B, or tie")
    ratings = tuple(
        BelievabilityRating(
            str(row["sample_id"]),
            cast(Literal["A", "B", "tie"], row["preferred"]),
        )
        for row in sample_rows
    )
    keys = tuple(BelievabilityKey(**row) for row in key_rows)
    baseline = asdict(measure_believability(ratings, keys))
    adaptive = answer_key.get("adaptive")
    if not isinstance(adaptive, dict):
        return baseline
    selection_rows = cast(list[dict[str, object]], adaptive.get("selections"))
    observations = cast(
        list[dict[str, int | None]], adaptive.get("one_call_observations")
    )
    if (
        not isinstance(selection_rows, list)
        or not isinstance(observations, list)
        or len(observations) != len(selection_rows)
        or any(
            row.get("strategy") not in {"one-call-per-agent", "fixed-clod-1"}
            for row in selection_rows
        )
    ):
        raise ValueError("adaptive selections and observations must align")
    selections = tuple(
        AdaptiveSelection(str(row["sample_id"]), cast(Any, row["strategy"]))
        for row in selection_rows
    )
    comparison = compare_adaptive_to_baselines(
        selections,
        ratings,
        keys,
        float(adaptive["minimum_preference_retention"]),
    )
    selected_indexes = {
        index
        for index, selection in enumerate(selections)
        if selection.strategy == "one-call-per-agent"
    }
    token_total = sum(
        (row["prompt_tokens"] or 0) + (row["completion_tokens"] or 0)
        for row in observations
    )
    adaptive_tokens = sum(
        (row["prompt_tokens"] or 0) + (row["completion_tokens"] or 0)
        for index, row in enumerate(observations)
        if index in selected_indexes
    )
    latency_total = sum(row["latency_ms"] or 0 for row in observations)
    adaptive_latency = sum(
        row["latency_ms"] or 0
        for index, row in enumerate(observations)
        if index in selected_indexes
    )
    consistency = cast(dict[str, int | float], adaptive["consistency"])
    meets_consistency = (
        consistency["identity_continuity_rate"]
        >= float(adaptive["minimum_identity_continuity"])
        and consistency["contradiction_rate"]
        <= float(adaptive["maximum_contradiction_rate"])
    )
    return {
        "baseline_believability": baseline,
        "adaptive_comparison": asdict(comparison),
        "cost": {
            "one_call_tokens": token_total,
            "adaptive_tokens": adaptive_tokens,
            "token_reduction": 1 - adaptive_tokens / token_total if token_total else 0.0,
            "one_call_latency_ms": latency_total,
            "adaptive_latency_ms": adaptive_latency,
            "latency_reduction": 1 - adaptive_latency / latency_total
            if latency_total
            else 0.0,
        },
        "consistency": consistency,
        "meets_consistency_threshold": meets_consistency,
        "stage5_exit_gate_passed": comparison.meets_believability_threshold
        and meets_consistency
        and comparison.provider_call_reduction > 0,
    }


def _read_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _write_json(path: Path, value: dict[str, object]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.write_text(json.dumps(value, indent=2), encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate")
    generate.add_argument("--base-url", default="http://127.0.0.1:1234/v1")
    generate.add_argument("--model", required=True)
    generate.add_argument("--seed", type=int, default=0)
    generate.add_argument("--packet", type=Path, required=True)
    generate.add_argument("--key", type=Path, required=True)
    generate.add_argument("--adaptive", action="store_true")
    score = subparsers.add_parser("score")
    score.add_argument("--packet", type=Path, required=True)
    score.add_argument("--key", type=Path, required=True)
    score.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "generate":
        if args.packet.exists() or args.key.exists():
            raise FileExistsError("refusing to overwrite packet or answer key")
        packet, key = asyncio.run(
            generate_packet(args.base_url, args.model, args.seed, args.adaptive)
        )
        _write_json(args.packet, packet)
        _write_json(args.key, key)
    else:
        _write_json(args.result, score_packet(_read_json(args.packet), _read_json(args.key)))


if __name__ == "__main__":
    main()
