import contextlib
import io
import json
import sqlite3
import sys
import urllib.error
import urllib.parse
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import simulate_http_interactions as simulation  # noqa: E402


def test_chat_payload_matches_mod_contract() -> None:
    speaker = simulation.sim_payload(
        "run-1", "b", mood="uncomfortable", needs={"bladder": 10}
    )
    listener = simulation.sim_payload("run-1", "a")

    payload = simulation.chat_payload(
        "run-1", speaker, listener, "The code is BLUE-731"
    )

    assert payload["speaker"] == speaker
    assert payload["listener"] == listener
    assert payload["event"] == {
        "type": "player_conversation",
        "source": "http_simulation",
    }
    assert payload["available_response_categories"] == [
        "friendly",
        "funny",
        "romance",
        "mean",
        "mischief",
    ]
    assert payload["relationship"] == {
        "friendship": 50,
        "romance": 0,
        "trust": 50,
        "resentment": 0,
    }
    assert payload["listener_relationship"] == payload["relationship"]
    assert "available_actions" not in payload
    assert payload["message"] == "The code is BLUE-731"


def test_confirmation_uses_proposed_decision_and_action() -> None:
    payload = simulation.confirmation_payload(
        {"decision_id": "decision-1", "animation": "friendly_chat"},
        "succeeded",
    )

    assert payload == {
        "decision_id": "decision-1",
        "action": "friendly_chat",
        "status": "succeeded",
        "reason": "",
        "changes": [],
    }


def test_request_json_sends_and_decodes_json(monkeypatch) -> None:
    captured = {}
    monkeypatch.setenv("AI_SIM_API_TOKEN", "secret")

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response(b'{"status":"ok"}')

    monkeypatch.setattr(simulation.urllib.request, "urlopen", fake_urlopen)

    result = simulation.request_json(
        "POST", "http://example.test/chat", {"message": "hello"}, timeout=7
    )

    assert result == {"status": "ok"}
    assert captured["request"].method == "POST"
    assert captured["request"].get_header("X-empneon-token") == "secret"
    assert json.loads(captured["request"].data) == {"message": "hello"}
    assert captured["timeout"] == 7


def test_database_counts_reads_known_tables() -> None:
    database = Path(__file__).with_name(".http_simulation_test.sqlite3")
    database.unlink(missing_ok=True)
    try:
        with contextlib.closing(sqlite3.connect(database)) as conn:
            for table in simulation.COUNT_TABLES:
                conn.execute(f"CREATE TABLE {table} (id TEXT)")
            conn.execute("INSERT INTO agents VALUES ('sim-1')")
            conn.execute("INSERT INTO events VALUES ('event-1')")
            conn.commit()

        counts = simulation.database_counts(database)

        assert counts["agents"] == 1
        assert counts["events"] == 1
        assert all(counts[name] == 0 for name in simulation.COUNT_TABLES[2:])
    finally:
        database.unlink(missing_ok=True)


def _empty_core_database(name: str) -> Path:
    database = Path(__file__).with_name(name)
    database.unlink(missing_ok=True)
    with contextlib.closing(sqlite3.connect(database)) as conn:
        for table in simulation.COUNT_TABLES:
            conn.execute(f"CREATE TABLE {table} (id TEXT)")
        conn.commit()
    return database


def test_run_scenarios_records_all_evidence(monkeypatch) -> None:
    database = _empty_core_database(".http_scenarios_test.sqlite3")
    calls = []
    decisions = {}
    fact = ""

    def fake_request(method, url, payload=None, timeout=120):
        nonlocal fact
        path = urllib.parse.urlparse(url).path
        calls.append((method, path, payload))
        if path == "/health":
            return {"status": "ok", "provider": "lmstudio", "memory_db": str(database)}
        if path == "/chat":
            number = len(decisions) + 1
            decision_id = f"decision-{number}"
            message = payload["message"]
            if message.startswith("PRIVATE-GARDEN-"):
                fact = message
            dialogue = fact if payload["speaker"]["id"].endswith("-b") else "I do not know."
            response = {
                "decision_id": decision_id,
                "animation": "social.friendly",
                "suggested_action": "social.friendly",
                "dialogue": dialogue,
                "response_category": "friendly",
                "tone_tags": [],
                "trust_delta": 0,
                "selected_clod": 3,
            }
            decisions[decision_id] = {"status": None, "response": response}
            return response
        if path == "/action-result":
            decisions[payload["decision_id"]]["status"] = payload["status"]
            return {"decision_id": payload["decision_id"], "status": payload["status"]}
        if path == "/autonomous":
            return {
                "decision_id": "autonomous-1",
                "suggested_action": "friendly_chat",
                "selected_clod": 1,
            }
        if path == "/diagnostics/sim":
            sim_id = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["sim_id"][0]
            informed = sim_id.endswith("-b")
            return {
                "agent": {"id": sim_id, "name": sim_id, "adapter": "sims4"},
                "personality": {"openness": 0.7},
                "emotions": [{"emotion": "uncomfortable", "value": 0.75}],
                "goals": [{"description": "Restore bladder", "status": "active"}],
                "beliefs": [{"statement": fact}] if informed and fact else [],
                "accessible_memories": [{"description": fact}] if informed and fact else [],
            }
        if path == "/diagnostics/usage":
            return {
                "attempts": 2,
                "by_clod": {"1": 1, "3": 1},
                "by_provider": {"core-rules": 1, "lmstudio": 1},
            }
        if path == "/diagnostics/timeline":
            return {
                "entries": [
                    {"type": "event", "id": "event-1"},
                    {"type": "decision", "id": "decision-1"},
                ]
            }
        if path == "/diagnostics/replay":
            decision_id = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)[
                "decision_id"
            ][0]
            status = decisions[decision_id]["status"]
            return {
                "decision": {"id": decision_id},
                "result": {"status": status, "applied_changes": []},
                "consequence_integrity": True,
            }
        if path == "/identity/export":
            sim_id = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["sim_id"][0]
            return {"agent": {"id": sim_id, "name": sim_id}, "version": 1}
        if path == "/identity/import":
            return {"agent": payload["agent"]}
        raise AssertionError(f"unexpected request: {method} {url}")

    monkeypatch.setattr(simulation, "request_json", fake_request)
    try:
        report = simulation.run_scenarios("http://example.test", database, run_id="run-1")
    finally:
        database.unlink(missing_ok=True)

    assert report["passed"] is True
    assert [item["name"] for item in report["scenarios"]] == [
        "health",
        "canonical_state",
        "successful_confirmation",
        "failed_confirmation",
        "private_fact",
        "topical_retrieval",
        "usage",
        "timeline_and_replay",
        "identity_round_trip",
    ]
    assert report["database"]["before"]["agents"] <= report["database"]["after"]["agents"]
    assert any(path == "/action-result" for _method, path, _payload in calls)


def test_run_scenarios_stops_when_health_fails(monkeypatch) -> None:
    database = _empty_core_database(".http_health_test.sqlite3")
    calls = []

    def unavailable(method, url, payload=None, timeout=120):
        calls.append((method, url))
        raise urllib.error.URLError("backend unavailable")

    monkeypatch.setattr(simulation, "request_json", unavailable)
    try:
        report = simulation.run_scenarios("http://example.test", database, run_id="run-2")
    finally:
        database.unlink(missing_ok=True)

    assert report["passed"] is False
    assert [item["name"] for item in report["scenarios"]] == ["health"]
    assert "backend unavailable" in report["scenarios"][0]["error"]
    assert calls == [("GET", "http://example.test/health")]
