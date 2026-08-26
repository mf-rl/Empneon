"""Capture evidence for the Sims 4 Test 10 cognition-priority gate."""

import argparse
import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from simulate_http_interactions import request_json


def evaluate_lifecycle(recent, synthetic_actor_ids):
    blocker_id, waiting_id = synthetic_actor_ids

    def index_of(actor_id, state, event_type=None):
        for index, item in enumerate(recent):
            if item.get("actor_id") != actor_id or item.get("state") != state:
                continue
            if event_type is None or item.get("event_type") == event_type:
                return index
        return None

    blocker_started = index_of(blocker_id, "started")
    waiting_submitted = index_of(waiting_id, "submitted")
    player_submitted = next(
        (
            index
            for index, item in enumerate(recent)
            if item.get("event_type") == "player_conversation"
            and item.get("state") == "submitted"
            and item.get("actor_id") not in synthetic_actor_ids
        ),
        None,
    )
    player_started = next(
        (
            index
            for index, item in enumerate(recent)
            if item.get("event_type") == "player_conversation"
            and item.get("state") == "started"
            and item.get("actor_id") not in synthetic_actor_ids
        ),
        None,
    )
    waiting_started = index_of(waiting_id, "started")
    indices = {
        "blocker_started": blocker_started,
        "waiting_submitted": waiting_submitted,
        "player_submitted": player_submitted,
        "player_started": player_started,
        "waiting_started": waiting_started,
    }
    if blocker_started is None:
        return {
            "passed": False,
            "reason": "ambient blocker start was not observed",
            "indices": indices,
        }
    if waiting_submitted is None:
        return {
            "passed": False,
            "reason": "waiting ambient submission was not observed",
            "indices": indices,
        }
    if player_submitted is None or player_started is None:
        return {"passed": False, "reason": "player request was not observed", "indices": indices}
    if waiting_started is None:
        return {
            "passed": False,
            "reason": "waiting ambient start was not observed",
            "indices": indices,
        }
    if waiting_submitted > player_submitted:
        return {
            "passed": False,
            "reason": "ambient work was not waiting before player submission",
            "indices": indices,
        }
    if waiting_started < player_submitted:
        return {
            "passed": False,
            "inconclusive": True,
            "reason": "ambient backlog cleared before player submission",
            "indices": indices,
        }
    if waiting_started < player_started:
        return {
            "passed": False,
            "reason": "waiting ambient work started before player work",
            "indices": indices,
        }
    return {"passed": True, "reason": "", "indices": indices}


def _wait_for_snapshot(base_url, predicate, timeout):
    deadline = time.monotonic() + timeout
    snapshot = None
    while time.monotonic() < deadline:
        snapshot = request_json(
            "GET",
            base_url.rstrip("/") + "/diagnostics/cognition-queue",
            timeout=max(1, round(timeout)),
        )
        if predicate(snapshot):
            return snapshot
        time.sleep(0.1)
    return snapshot


def collect_evidence(
    base_url,
    *,
    setup_timeout=30,
    completion_timeout=180,
    prompt=input,
    run_id=None,
):
    base_url = base_url.rstrip("/")
    health = request_json("GET", base_url + "/health", timeout=10)
    if health.get("active_agent_limit") != 1:
        return {
            "status": "inconclusive",
            "reason": "active_agent_limit must be 1",
            "health": health,
        }

    prompt(
        "In The Sims 4, open Empneon Social and type the message, but do not submit it. "
        "Press Enter here when ready."
    )
    run_id = run_id or uuid.uuid4().hex[:12]
    started_at = time.time()
    gate_url = base_url + "/diagnostics/cognition-queue/test10-gate"
    armed = False
    snapshot = None
    actor_ids = ()
    try:
        gate = request_json(
            "POST",
            gate_url,
            {"action": "arm", "run_id": run_id},
            timeout=max(1, setup_timeout),
        )
        armed = True
        actors = gate.get("actor_ids") or {}
        actor_ids = (str(actors.get("blocker") or ""), str(actors.get("waiting") or ""))
        if not all(actor_ids):
            raise ValueError("gate response lacks actor IDs")

        prompt("Submit the prepared Empneon Social message now, then press Enter immediately.")

        def player_observed(value, state):
            return any(
                item.get("event_type") == "player_conversation"
                and item.get("actor_id") not in actor_ids
                and item.get("state") == state
                and float(item.get("recorded_at") or 0) >= started_at
                for item in value.get("recent", [])
            )

        snapshot = _wait_for_snapshot(
            base_url,
            lambda value: player_observed(value, "submitted"),
            min(completion_timeout, 50),
        )
        if snapshot is None or not player_observed(snapshot, "submitted"):
            return {
                "status": "inconclusive",
                "reason": "player request was not submitted while the gate was active",
                "run_id": run_id,
                "actor_ids": list(actor_ids),
                "snapshot": snapshot,
            }

        request_json(
            "POST",
            gate_url,
            {"action": "release", "run_id": run_id},
            timeout=10,
        )
        armed = False
        snapshot = _wait_for_snapshot(
            base_url,
            lambda value: (
                player_observed(value, "started")
                and any(
                    item.get("actor_id") == actor_ids[1]
                    and item.get("state") == "started"
                    for item in value.get("recent", [])
                )
            ),
            completion_timeout,
        )
    finally:
        if armed:
            try:
                request_json(
                    "POST",
                    gate_url,
                    {"action": "release", "run_id": run_id},
                    timeout=10,
                )
            except Exception:
                pass

    recent = [
        item
        for item in (snapshot or {}).get("recent", [])
        if float(item.get("recorded_at") or 0) >= started_at
    ]
    evaluation = evaluate_lifecycle(recent, actor_ids)
    if evaluation["passed"]:
        status = "passed"
    elif evaluation.get("inconclusive"):
        status = "inconclusive"
    else:
        status = "failed"
    return {
        "status": status,
        "reason": evaluation["reason"],
        "run_id": run_id,
        "actor_ids": list(actor_ids),
        "evaluation": evaluation,
        "recent": recent,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--output")
    parser.add_argument("--setup-timeout", type=int, default=30)
    parser.add_argument("--completion-timeout", type=int, default=180)
    args = parser.parse_args(argv)
    report = collect_evidence(
        args.base_url,
        setup_timeout=args.setup_timeout,
        completion_timeout=args.completion_timeout,
    )
    output = (
        Path(args.output)
        if args.output
        else Path(
            "output/test10-priority-{}.json".format(datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"))
        )
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("{}: {}".format(report["status"], report.get("reason") or "priority preserved"))
    print("Report:", output)
    return {"passed": 0, "failed": 1}.get(report["status"], 2)


if __name__ == "__main__":
    raise SystemExit(main())
