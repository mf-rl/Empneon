import json
import sqlite3

from empneon.core.identity.relationships import RelationshipStore
from empneon.core.runtime import ActionRecordStore
from empneon.db.connection import open_db
from poc.backend import ai_sims_server


def test_recent_conversation_is_added_to_prompt(monkeypatch) -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    ai_sims_server.init_db(connection)
    monkeypatch.setattr(ai_sims_server, "connect_db", lambda: connection)
    ai_sims_server.save_conversation(
        "travis-robin",
        "travis",
        "robin",
        "Let's meet for pizza tomorrow at 7 PM.",
        {"dialogue": "Pizza sounds good, let's plan it."},
    )
    ai_sims_server.save_conversation(
        "travis-robin",
        "travis",
        "robin",
        "When and why did we agree to meet?",
        {"dialogue": "Pizza sounds good. Let's plan it."},
    )

    context = ai_sims_server.build_context(
        {"speaker": {}, "listener": {}, "message": "When are we meeting?"},
        {"name": "Travis"},
        {"name": "Robin"},
        {},
        {},
        [],
        {},
    )
    context.update(
        {
            "conversation": ai_sims_server.recent_conversation("travis", "robin"),
            "speaker_id": "travis",
            "listener_id": "robin",
        }
    )

    prompt = ai_sims_server.build_chat_prompt(
        {"message": "When and why did we agree to meet?"}, context
    )

    assert "Robin: Let's meet for pizza tomorrow at 7 PM." in prompt
    assert "Travis: Pizza sounds good, let's plan it." in prompt
    assert "Pizza sounds good. Let's plan it." not in prompt
    assert "source of truth for past facts" in prompt
    assert prompt.index("Recent conversation") < prompt.index("Player says")

def test_lmstudio_chat_disables_reasoning(monkeypatch) -> None:
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b'{"output":[{"type":"message","content":"Hello Robin"}]}'

    def urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(
        ai_sims_server,
        "task_model_config",
        lambda _task="large": {
            "name": "lmstudio",
            "endpoint": "http://127.0.0.1:1234/api/v1",
            "model": "gemma",
            "temperature": 0.4,
            "max_tokens": 120,
        },
    )
    monkeypatch.setattr(ai_sims_server, "loaded_model_id", lambda _task="large": "gemma")
    monkeypatch.setattr(ai_sims_server.urllib.request, "urlopen", urlopen)

    result = ai_sims_server.llm_chat([{"role": "user", "content": "Hello"}])

    assert result == "Hello Robin"
    assert captured == {
        "url": "http://127.0.0.1:1234/api/v1/chat",
        "body": {
            "model": "gemma",
            "input": "USER:\nHello",
            "temperature": 0.4,
            "max_output_tokens": 120,
            "reasoning": "off",
        },
        "timeout": 90,
    }


def test_confirmed_friendship_updates_core_relationship(tmp_path, monkeypatch) -> None:
    core_db = str(tmp_path / "core.sqlite3")
    monkeypatch.setattr(ai_sims_server, "CORE_DB_PATH", core_db)
    proposal = ai_sims_server.autonomous_action(
        {
            "speaker": {"id": "bella", "name": "Bella"},
            "listener": {"id": "mortimer", "name": "Mortimer"},
            "event": {"type": "autonomous_social", "source": "test"},
            "available_actions": ["friendly_chat", "apologize", "flirt"],
        }
    )

    ai_sims_server.confirm_action(
        {
            "decision_id": proposal["decision_id"],
            "action": proposal["suggested_action"],
            "status": "succeeded",
            "changes": [
                {
                    "path": "relationship.friendship",
                    "operation": "increment",
                    "value": 5,
                }
            ],
        }
    )

    with open_db(core_db) as conn:
        relationship = RelationshipStore(conn).get("bella", "mortimer")
        record = ActionRecordStore(conn).get(proposal["decision_id"])
    assert relationship is not None
    assert relationship.strength == 0.05
    assert record is not None
    assert record.result.status == "succeeded"


def test_chat_waits_for_native_game_confirmation(tmp_path, monkeypatch) -> None:
    core_db = str(tmp_path / "core.sqlite3")
    memory_db = str(tmp_path / "memory.sqlite3")
    monkeypatch.setattr(ai_sims_server, "CORE_DB_PATH", core_db)
    monkeypatch.setattr(ai_sims_server, "DB_PATH", memory_db)
    monkeypatch.setattr(ai_sims_server, "ACTIVE_DB_PATH", None)
    monkeypatch.setattr(
        ai_sims_server.HERMES,
        "dialogue",
        lambda _payload, _context: {
            "dialogue": "Hello.",
            "emotion": "happy",
            "intent": "greet",
            "relationship": {
                "friendship_delta": 2,
                "romance_delta": 0,
                "trust_delta": 0,
            },
            "memory": {"importance": 0.2, "summary": "A greeting."},
            "animation": "friendly_chat",
        },
    )

    result = ai_sims_server.chat(
        {
            "speaker": {"id": "bella", "name": "Bella"},
            "listener": {"id": "mortimer", "name": "Mortimer"},
            "message": "Hello",
            "event": {"type": "player_conversation", "source": "test"},
            "available_actions": ["friendly_chat", "apologize", "flirt"],
        }
    )

    with open_db(core_db) as conn:
        actions = ActionRecordStore(conn)
        proposal = actions.get_proposal(result["decision_id"])
        record = actions.get(result["decision_id"])
    assert result["action_status"] == "proposed"
    assert result["animation"] == "friendly_chat"
    assert proposal is not None
    assert record is None
