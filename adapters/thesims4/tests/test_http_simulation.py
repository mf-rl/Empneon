import contextlib
import io
import json
from pathlib import Path
import sqlite3
import sys


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
    assert payload["available_actions"] == ["friendly_chat", "apologize", "flirt"]
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
