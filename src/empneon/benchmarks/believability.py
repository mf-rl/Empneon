"""Generate and score a blinded SocietyBench believability packet."""

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal, cast

from empneon.benchmarks.societybench import (
    BelievabilityKey,
    BelievabilityRating,
    build_20_agent_scenarios,
    build_blinded_believability_evaluation,
    measure_baselines,
    measure_believability,
)
from empneon.core.contracts import CognitiveRequest, Decision
from empneon.providers.llm import GenerationRequest, Message, OpenAICompatibleProvider

RUBRIC = (
    "Choose A, B, or tie for the action that is more believable in context. "
    "Consider contextual fit, social plausibility, and specificity."
)


async def generate_packet(
    base_url: str, model: str, seed: int
) -> tuple[dict[str, object], dict[str, object]]:
    provider = OpenAICompatibleProvider(base_url, model, timeout_seconds=90)

    async def resolver(request: CognitiveRequest) -> Decision:
        target = next(actor for actor in request.event.actor_ids if actor != request.agent_id)
        prompt = (
            f"Agent {request.agent_id} encounters {target} during {request.event.type}. "
            "Return only one concise believable social action of two to six words."
        )
        result = await provider.generate(
            GenerationRequest((Message("user", prompt),), max_tokens=16, temperature=0.2)
        )
        intent = " ".join(result.content.strip().split())
        if not intent:
            raise ValueError("provider returned an empty believability candidate")
        return Decision(request.agent_id, intent, target_id=target)

    scenario = build_20_agent_scenarios()[0]
    results = await measure_baselines(scenario, resolver)
    samples, keys = build_blinded_believability_evaluation(scenario, results, seed)
    return (
        {
            "scenario": scenario.name,
            "model": model,
            "seed": seed,
            "rubric": RUBRIC,
            "samples": [{**asdict(sample), "preferred": None} for sample in samples],
        },
        {
            "scenario": scenario.name,
            "model": model,
            "seed": seed,
            "keys": [asdict(key) for key in keys],
        },
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
    return asdict(measure_believability(ratings, keys))


def _read_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _write_json(path: Path, value: dict[str, object]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate")
    generate.add_argument("--base-url", default="http://127.0.0.1:1234/v1")
    generate.add_argument("--model", required=True)
    generate.add_argument("--seed", type=int, default=0)
    generate.add_argument("--packet", type=Path, required=True)
    generate.add_argument("--key", type=Path, required=True)
    score = subparsers.add_parser("score")
    score.add_argument("--packet", type=Path, required=True)
    score.add_argument("--key", type=Path, required=True)
    score.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "generate":
        if args.packet.exists() or args.key.exists():
            raise FileExistsError("refusing to overwrite packet or answer key")
        packet, key = asyncio.run(generate_packet(args.base_url, args.model, args.seed))
        _write_json(args.packet, packet)
        _write_json(args.key, key)
    else:
        _write_json(args.result, score_packet(_read_json(args.packet), _read_json(args.key)))


if __name__ == "__main__":
    main()
