"""Exercise the Sims 4 backend through the same HTTP contract as the mod."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
import sqlite3
from typing import Any
import urllib.request


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
    return result


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
        return {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in COUNT_TABLES
        }
