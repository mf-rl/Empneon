"""Run the Windows baseline workload while The Sims 4 is active."""

import argparse
import asyncio
import json
import subprocess
import time
from pathlib import Path

import psutil  # type: ignore[import-untyped]
from empneon.benchmarks import build_20_agent_scenarios, measure_baselines
from empneon.core.contracts import CognitiveRequest, Decision
from empneon.providers.llm import GenerationRequest, Message, OpenAICompatibleProvider


def _vram_mb() -> float:
    output = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=memory.used",
            "--format=csv,noheader,nounits",
        ],
        text=True,
        timeout=10,
    )
    return float(output.splitlines()[0])


async def run(base_url: str, model: str) -> dict[str, object]:
    if not any(
        (process.info["name"] or "").lower() == "ts4_x64.exe"
        for process in psutil.process_iter(["name"])
    ):
        raise RuntimeError("The Sims 4 is not running")
    provider = OpenAICompatibleProvider(base_url, model, timeout_seconds=60)
    observations: list[dict[str, float | int | None]] = []

    async def resolver(request: CognitiveRequest) -> Decision:
        started = time.perf_counter()
        result = await provider.generate(
            GenerationRequest(
                (Message("user", f"Reply with one word for {request.event.type}."),),
                max_tokens=16,
                temperature=0,
            )
        )
        observations.append(
            {
                "cpu_percent": psutil.cpu_percent(),
                "ram_mb": psutil.virtual_memory().used / 1024**2,
                "vram_mb": _vram_mb(),
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "latency_ms": result.latency_ms
                or round((time.perf_counter() - started) * 1000),
            }
        )
        return Decision(
            request.agent_id,
            "provider-response",
            evidence_ids=(request.event.id,),
        )

    scenario = build_20_agent_scenarios()[0]
    one_call, fixed_clod = await measure_baselines(scenario, resolver)
    return {
        "scenario": scenario.name,
        "model": model,
        "captured_at": int(time.time()),
        "one_call": {
            "decisions": len(one_call.decisions),
            "provider_calls": one_call.provider_calls,
            "observations": observations,
        },
        "fixed_clod": {
            "decisions": len(fixed_clod.decisions),
            "provider_calls": fixed_clod.provider_calls,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:1234/v1")
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}")
    args.output.write_text(
        json.dumps(asyncio.run(run(args.base_url, args.model)), indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
