"""Local JSON bridge between a Godot process and Empneon Core contracts."""

import argparse
import dataclasses
import json
from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, cast

from empneon.core.clod.rules import resolve_clod1
from empneon.core.contracts import (
    ActionResult,
    AgentStateSnapshot,
    CognitiveRequest,
    StateDelta,
    WorldEvent,
)

MAX_BODY_BYTES = 65_536


class GodotBridge:
    def __init__(self) -> None:
        self._pending: set[str] = set()

    def decide(self, payload: Mapping[str, object]) -> dict[str, object]:
        event_data = payload.get("event")
        if not isinstance(event_data, Mapping):
            raise ValueError("event object is required")
        event_id = str(event_data.get("id") or "")
        if not event_id:
            raise ValueError("event id is required")
        actors = event_data.get("actor_ids")
        facts = event_data.get("facts", {})
        if not isinstance(actors, (list, tuple)) or not isinstance(facts, Mapping):
            raise ValueError("event actor_ids and facts are invalid")
        agent_id = str(payload.get("agent_id") or "")
        actor_ids = tuple(str(actor) for actor in actors if str(actor))
        if not agent_id or agent_id not in actor_ids:
            raise ValueError("agent_id must identify an event actor")
        raw_state = event_data.get("agent_state")
        state = (
            AgentStateSnapshot.from_mapping(raw_state)
            if isinstance(raw_state, Mapping)
            else AgentStateSnapshot(
                1,
                "godot",
                agent_id,
                capabilities={"actions": ["acknowledge"]},
                native={"facts": dict(facts)},
            )
        )
        if state.agent_id != agent_id:
            raise ValueError("agent state agent_id must match request agent_id")
        if state.adapter != "godot":
            raise ValueError("agent state adapter must be godot")
        event = WorldEvent(
            id=event_id,
            type=str(event_data.get("type") or ""),
            actor_ids=actor_ids,
            location=str(event_data["location"]) if event_data.get("location") else None,
            facts=dict(facts),
            happened_at=int(event_data.get("happened_at", 0)),
            agent_state=state,
        )
        decision = resolve_clod1(CognitiveRequest(agent_id, 1, event))
        self._pending.add(decision.id)
        return cast(dict[str, object], dataclasses.asdict(decision))

    def confirm(self, payload: Mapping[str, object]) -> dict[str, object]:
        decision_id = str(payload.get("decision_id") or "")
        if decision_id not in self._pending:
            raise ValueError("unknown or already confirmed decision")
        status = str(payload.get("status") or "")
        if status not in {"succeeded", "rejected", "failed"}:
            raise ValueError("invalid action status")
        raw_changes = payload.get("applied_changes", [])
        if not isinstance(raw_changes, list):
            raise ValueError("applied_changes must be a list")
        changes = []
        for raw_change in raw_changes:
            if not isinstance(raw_change, Mapping) or raw_change.get("operation") not in {
                "set",
                "increment",
                "append",
                "remove",
            }:
                raise ValueError("invalid applied change")
            changes.append(
                StateDelta(
                    str(raw_change.get("path") or ""),
                    cast(Any, raw_change["operation"]),
                    raw_change.get("value"),
                )
            )
        result = ActionResult(
            decision_id,
            cast(Any, status),
            tuple(changes),
            str(payload["reason"]) if payload.get("reason") else None,
        )
        self._pending.remove(decision_id)
        return cast(dict[str, object], dataclasses.asdict(result))


BRIDGE = GodotBridge()


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY_BYTES:
                raise ValueError("request body size is invalid")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("JSON object is required")
            if self.path == "/decision":
                response = BRIDGE.decide(payload)
            elif self.path == "/result":
                response = {"accepted": True, "result": BRIDGE.confirm(payload)}
            else:
                self._send(404, {"error": "not found"})
                return
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self._send(400, {"error": str(exc)})
            return
        self._send(200, response)

    def _send(self, status: int, value: Mapping[str, object]) -> None:
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8790)
    args = parser.parse_args()
    HTTPServer((args.host, args.port), _Handler).serve_forever()


if __name__ == "__main__":
    main()
