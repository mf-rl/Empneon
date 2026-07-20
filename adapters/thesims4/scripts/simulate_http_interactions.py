"""Exercise the Sims 4 backend through the same HTTP contract as the mod."""

from __future__ import annotations

import argparse
import contextlib
from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3
import time
from typing import Any, Callable, cast
import urllib.parse
import urllib.request
import uuid


AVAILABLE_ACTIONS = ["friendly_chat", "apologize", "flirt"]
COUNT_TABLES = (
    "agents",
    "events",
    "beliefs",
    "action_proposals",
    "action_results",
    "cognition_usage",
)


def request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    timeout: int = 120,
) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not isinstance(result, dict):
        raise ValueError("backend response is not a JSON object")
    return cast(dict[str, Any], result)


def sim_payload(
    run_id: str,
    role: str,
    *,
    mood: str = "fine",
    needs: dict[str, int] | None = None,
) -> dict[str, Any]:
    return {
        "id": f"empneon-test-{run_id}-{role}",
        "name": f"empneon-test-{run_id}-{role}",
        "age": "adult",
        "traits": ["good", "creative"],
        "current_mood": mood,
        "needs": needs or {"bladder": 75, "hunger": 75, "fun": 75},
        "moodlets": [],
        "aspiration": "Test Empneon",
        "career": "Quality Assurance",
        "skills": {"logic": 5},
        "household": {"id": f"empneon-test-{run_id}", "name": "Empneon Test"},
    }


def chat_payload(
    run_id: str,
    speaker: dict[str, Any],
    listener: dict[str, Any],
    message: str,
) -> dict[str, Any]:
    return {
        "speaker": speaker,
        "listener": listener,
        "relationship": {
            "friendship": 50,
            "romance": 0,
            "trust": 50,
            "resentment": 0,
        },
        "location": f"empneon-test-zone-{run_id}",
        "nearby_sims": [],
        "event": {"type": "player_conversation", "source": "http_simulation"},
        "available_actions": AVAILABLE_ACTIONS,
        "message": message,
    }


def confirmation_payload(
    response: dict[str, Any], status: str, reason: str = ""
) -> dict[str, Any]:
    decision_id = str(response.get("decision_id") or "")
    action = str(response.get("suggested_action") or response.get("animation") or "")
    if not decision_id or not action:
        raise ValueError("chat response lacks decision or action")
    return {
        "decision_id": decision_id,
        "action": action,
        "status": status,
        "reason": reason,
        "changes": [],
    }


def database_counts(path: Path) -> dict[str, int]:
    with contextlib.closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as conn:
        counts = {}
        for table in COUNT_TABLES:
            row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            if row is None:
                raise ValueError(f"could not count {table}")
            counts[table] = int(row[0])
        return counts


def run_scenarios(
    base_url: str,
    database: Path,
    *,
    run_id: str | None = None,
) -> dict[str, Any]:
    run_id = run_id or datetime.now(UTC).strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:8]
    base_url = base_url.rstrip("/")
    calls: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "run_id": run_id,
        "started_at": datetime.now(UTC).isoformat(),
        "base_url": base_url,
        "database": {"path": str(database), "before": database_counts(database)},
        "scenarios": [],
    }

    def call(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = base_url + path
        entry: dict[str, Any] = {"method": method, "url": url}
        if payload is not None:
            entry["payload"] = payload
        calls.append(entry)
        response = request_json(method, url, payload)
        entry["response"] = response
        return response

    scenarios = cast(list[dict[str, Any]], report["scenarios"])

    def record(name: str, scenario: Callable[[], Any]) -> bool:
        started = time.monotonic()
        first_call = len(calls)
        item: dict[str, Any] = {"name": name}
        try:
            item["evidence"] = scenario()
            item["passed"] = True
        except Exception as exc:
            item["passed"] = False
            item["error"] = f"{type(exc).__name__}: {exc}"
        item["requests"] = calls[first_call:]
        item["duration_ms"] = round((time.monotonic() - started) * 1000)
        scenarios.append(item)
        return bool(item["passed"])

    if not record("health", lambda: call("GET", "/health")):
        report["database"]["after"] = database_counts(database)
        report["passed"] = False
        report["completed_at"] = datetime.now(UTC).isoformat()
        return report

    player = sim_payload(run_id, "a")
    informed = sim_payload(run_id, "b", mood="uncomfortable", needs={"bladder": 10})
    uninformed = sim_payload(run_id, "c")
    fact_code = f"PRIVATE-GARDEN-{run_id}"
    fact = f"{fact_code} is under the blue bench."
    state: dict[str, Any] = {}

    def get_diagnostic(path: str, name: str, identifier: str) -> dict[str, Any]:
        query = urllib.parse.urlencode({name: identifier})
        return call("GET", f"{path}?{query}")

    def propose(speaker: dict[str, Any], listener: dict[str, Any], message: str) -> dict[str, Any]:
        return call("POST", "/chat", chat_payload(run_id, speaker, listener, message))

    def confirm(response: dict[str, Any], status: str, reason: str = "") -> dict[str, Any]:
        return call("POST", "/action-result", confirmation_payload(response, status, reason))

    def canonical_state() -> dict[str, Any]:
        state["successful"] = propose(informed, player, fact)
        diagnostic = get_diagnostic("/diagnostics/sim", "sim_id", informed["id"])
        goals = diagnostic.get("goals") or []
        emotions = diagnostic.get("emotions") or []
        assert diagnostic.get("agent", {}).get("adapter") == "sims4"
        assert any(
            goal.get("description") == "Restore bladder" and goal.get("status") == "active"
            for goal in goals
        )
        assert any(emotion.get("emotion") == "uncomfortable" for emotion in emotions)
        return {"proposal": state["successful"], "diagnostic": diagnostic}

    record("canonical_state", canonical_state)

    def successful_confirmation() -> dict[str, Any]:
        proposal = cast(dict[str, Any], state["successful"])
        confirmation = confirm(proposal, "succeeded")
        replay = get_diagnostic(
            "/diagnostics/replay", "decision_id", str(proposal["decision_id"])
        )
        assert confirmation.get("status") == "succeeded"
        assert replay.get("result", {}).get("status") == "succeeded"
        assert replay.get("consequence_integrity") is True
        return {"confirmation": confirmation, "replay": replay}

    record("successful_confirmation", successful_confirmation)

    def failed_confirmation() -> dict[str, Any]:
        proposal = propose(informed, player, "This interaction will be cancelled.")
        state["failed"] = proposal
        confirmation = confirm(proposal, "failed", "simulated native cancellation")
        replay = get_diagnostic(
            "/diagnostics/replay", "decision_id", str(proposal["decision_id"])
        )
        assert confirmation.get("status") == "failed"
        assert replay.get("result", {}).get("status") == "failed"
        assert not replay.get("result", {}).get("applied_changes")
        return {"confirmation": confirmation, "replay": replay}

    record("failed_confirmation", failed_confirmation)

    def private_fact() -> dict[str, Any]:
        informed_state = get_diagnostic("/diagnostics/sim", "sim_id", informed["id"])
        uninformed_response = propose(
            uninformed, player, f"Where is {fact_code}?"
        )
        confirm(uninformed_response, "succeeded")
        uninformed_state = get_diagnostic("/diagnostics/sim", "sim_id", uninformed["id"])
        informed_text = json.dumps(
            {
                "beliefs": informed_state.get("beliefs"),
                "memories": informed_state.get("accessible_memories"),
            }
        )
        uninformed_text = json.dumps(
            {
                "beliefs": uninformed_state.get("beliefs"),
                "memories": uninformed_state.get("accessible_memories"),
            }
        )
        assert fact_code in informed_text and "blue bench" in informed_text
        assert "blue bench" not in str(uninformed_response.get("dialogue", "")).casefold()
        assert "blue bench" not in uninformed_text.casefold()
        return {
            "informed": informed_state,
            "uninformed_response": uninformed_response,
            "uninformed": uninformed_state,
        }

    record("private_fact", private_fact)

    def topical_retrieval() -> dict[str, Any]:
        proposal = propose(informed, player, "Where is the garden code item?")
        confirmation = confirm(proposal, "succeeded")
        diagnostic = get_diagnostic("/diagnostics/sim", "sim_id", informed["id"])
        assert "blue bench" in str(proposal.get("dialogue", "")).casefold()
        assert fact_code in json.dumps(diagnostic.get("accessible_memories") or [])
        return {"proposal": proposal, "confirmation": confirmation, "diagnostic": diagnostic}

    record("topical_retrieval", topical_retrieval)

    def usage() -> dict[str, Any]:
        autonomous = call(
            "POST",
            "/autonomous",
            {
                "speaker": informed,
                "listener": uninformed,
                "relationship": {"friendship": 50, "romance": 0, "trust": 50},
                "location": f"empneon-test-zone-{run_id}",
                "nearby_sims": [],
                "event": {"type": "autonomous_social", "source": "http_simulation"},
                "available_actions": AVAILABLE_ACTIONS,
            },
        )
        telemetry = get_diagnostic("/diagnostics/usage", "sim_id", informed["id"])
        providers = telemetry.get("by_provider") or {}
        clods = telemetry.get("by_clod") or {}
        assert autonomous.get("selected_clod") == 1
        assert int(clods.get("1", clods.get(1, 0))) >= 1
        assert int(clods.get("3", clods.get(3, 0))) >= 1
        assert int(providers.get("core-rules", 0)) >= 1
        assert any(name != "core-rules" and count for name, count in providers.items())
        return {"autonomous": autonomous, "telemetry": telemetry}

    record("usage", usage)

    def timeline_and_replay() -> dict[str, Any]:
        timeline = get_diagnostic("/diagnostics/timeline", "sim_id", informed["id"])
        successful = cast(dict[str, Any], state["successful"])
        failed = cast(dict[str, Any], state["failed"])
        success_replay = get_diagnostic(
            "/diagnostics/replay", "decision_id", str(successful["decision_id"])
        )
        failed_replay = get_diagnostic(
            "/diagnostics/replay", "decision_id", str(failed["decision_id"])
        )
        types = {entry.get("type") for entry in timeline.get("entries") or []}
        assert {"event", "decision"} <= types
        assert success_replay.get("consequence_integrity") is True
        assert failed_replay.get("consequence_integrity") is True
        return {
            "timeline": timeline,
            "successful_replay": success_replay,
            "failed_replay": failed_replay,
        }

    record("timeline_and_replay", timeline_and_replay)

    def identity_round_trip() -> dict[str, Any]:
        before = get_diagnostic("/identity/export", "sim_id", informed["id"])
        imported = call("POST", "/identity/import", before)
        after = get_diagnostic("/identity/export", "sim_id", informed["id"])
        assert before.get("agent", {}).get("id") == after.get("agent", {}).get("id")
        assert before.get("agent", {}).get("name") == after.get("agent", {}).get("name")
        assert imported.get("agent", {}).get("id") == informed["id"]
        return {"before": before, "imported": imported, "after": after}

    record("identity_round_trip", identity_round_trip)
    report["database"]["after"] = database_counts(database)
    report["passed"] = all(item["passed"] for item in scenarios)
    report["completed_at"] = datetime.now(UTC).isoformat()
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = run_scenarios(args.base_url, args.database)
    output = args.output or Path("output") / (
        "http-simulation-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + ".json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    for scenario in report["scenarios"]:
        print(f"{'PASS' if scenario['passed'] else 'FAIL'} {scenario['name']}")
    print(f"Report: {output.resolve()}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
