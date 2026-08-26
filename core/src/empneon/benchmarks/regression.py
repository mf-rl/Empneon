"""Deterministic JSON scenario regression runner."""

import argparse
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import cast

from empneon.core.clod import resolve_clod1
from empneon.core.contracts import CognitiveRequest, Decision, WorldEvent

DecisionResolver = Callable[[CognitiveRequest], Decision]


def run_regressions(
    payload: Mapping[str, object], resolver: DecisionResolver = resolve_clod1
) -> dict[str, object]:
    """Run JSON cases and return a deterministic machine-readable report."""
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("regression fixture requires a non-empty cases list")
    names: set[str] = set()
    results: list[dict[str, object]] = []
    for raw_case in raw_cases:
        if not isinstance(raw_case, Mapping):
            raise ValueError("each regression case must be an object")
        name = str(raw_case.get("name") or "")
        if not name or name in names:
            raise ValueError("regression case names must be non-empty and unique")
        names.add(name)
        request = _request(raw_case.get("request"))
        raw_expected = raw_case.get("expected")
        if not isinstance(raw_expected, Mapping) or not raw_expected:
            raise ValueError(f"{name} requires expected decision fields")
        expected = cast(Mapping[str, object], raw_expected)
        actual = cast(dict[str, object], json.loads(json.dumps(asdict(resolver(request)))))
        unknown = set(expected) - set(actual)
        if unknown:
            raise ValueError(f"{name} has unknown decision fields: {sorted(unknown)}")
        mismatches = {
            key: {"expected": value, "actual": actual[key]}
            for key, value in expected.items()
            if actual[key] != value
        }
        results.append(
            {
                "name": name,
                "passed": not mismatches,
                "mismatches": mismatches,
                "actual": actual,
            }
        )
    passed = sum(bool(result["passed"]) for result in results)
    return {
        "passed": passed == len(results),
        "total": len(results),
        "passed_cases": passed,
        "failed_cases": len(results) - passed,
        "results": results,
    }


def _request(value: object) -> CognitiveRequest:
    if not isinstance(value, Mapping):
        raise ValueError("regression case requires a request object")
    event_data = value.get("event")
    if not isinstance(event_data, Mapping):
        raise ValueError("regression request requires an event object")
    actors = event_data.get("actor_ids", [])
    raw_facts = event_data.get("facts", {})
    if not isinstance(actors, list) or not isinstance(raw_facts, Mapping):
        raise ValueError("event actor_ids and facts are invalid")
    facts = cast(Mapping[str, object], raw_facts)
    event_id = str(event_data.get("id") or "")
    if not event_id:
        raise ValueError("regression event id is required")
    try:
        event = WorldEvent(
            id=event_id,
            type=str(event_data.get("type") or ""),
            actor_ids=tuple(str(actor) for actor in actors),
            location=str(event_data["location"]) if event_data.get("location") else None,
            facts=dict(facts),
            happened_at=int(event_data.get("happened_at", 0)),
        )
        return CognitiveRequest(
            id=str(value.get("id") or ""),
            agent_id=str(value.get("agent_id") or ""),
            preferred_clod=int(value.get("preferred_clod", 1)),
            event=event,
            urgency=float(value.get("urgency", 0.5)),
            max_tokens=int(value.get("max_tokens", 300)),
            deadline_ms=int(value.get("deadline_ms", 3_000)),
            max_context_tokens=int(value.get("max_context_tokens", 4_096)),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("regression request is invalid") from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.fixture.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("regression fixture must be a JSON object")
        report = run_regressions(payload)
        body = json.dumps(report, indent=2) + "\n"
        if args.output:
            if args.output.exists():
                raise FileExistsError(f"refusing to overwrite {args.output}")
            args.output.write_text(body, encoding="utf-8", newline="\n")
        else:
            print(body, end="")
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        print(f"regression error: {exc}", file=sys.stderr)
        return 2
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
