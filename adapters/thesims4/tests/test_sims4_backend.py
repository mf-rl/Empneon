import json
import sqlite3
from pathlib import Path

from empneon.core.identity.relationships import RelationshipStore
from empneon.core.identity.models import Agent
from empneon.core.identity.store import AgentStore
from empneon.core.memory.documents import DocumentMemoryStore
from empneon.core.runtime import ActionRecordStore
from empneon.db.connection import open_db

from backend import ai_sims_server


def test_unified_database_is_the_only_active_default() -> None:
    path = getattr(ai_sims_server, "MEMORY_DB_PATH", "")

    assert path.endswith("empneon_core_memory.sqlite3")


def test_prepare_database_adopts_legacy_core_without_modifying_it(tmp_path) -> None:
    old = tmp_path / "empneon_core.sqlite3"
    new = tmp_path / "empneon_core_memory.sqlite3"
    with open_db(old) as conn:
        AgentStore(conn).create(
            Agent("bella", "Bella", game_id="bella", adapter="sims4")
        )
    before = old.read_bytes()
    state = getattr(ai_sims_server, "empneon_state", None)

    assert state is not None
    status = state.prepare_database(
        str(new), str(old), str(tmp_path / "ai_sims_memory.sqlite3")
    )

    with open_db(new) as conn:
        assert AgentStore(conn).get("bella").name == "Bella"
    assert old.read_bytes() == before
    assert status.active_path == str(new.resolve())
    assert status.completed is True


def test_openrouter_and_baseline_defaults_are_configured() -> None:
    config = json.loads(
        (Path(ai_sims_server.ROOT) / "config" / "config.json").read_text(encoding="utf-8")
    )

    assert config["active_agent_limit"] == 1
    assert config["providers"]["openrouter"] == {
        "endpoint": "https://openrouter.ai/api/v1",
        "model": "openai/gpt-4.1-mini",
    }


def test_recent_conversation_is_added_to_prompt(monkeypatch, tmp_path) -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    ai_sims_server.init_db(connection)
    monkeypatch.setattr(ai_sims_server, "connect_db", lambda: connection)
    monkeypatch.setattr(ai_sims_server, "CORE_DB_PATH", str(tmp_path / "core.db"))
    monkeypatch.setattr(ai_sims_server, "DB_PATH", str(tmp_path / "legacy.db"))
    monkeypatch.setattr(ai_sims_server.time, "time_ns", lambda: 1)
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
    assert "The Speaker's earlier generated replies" in prompt
    assert "When asked for an unsupported fact, do not guess" in prompt
    assert "25 to 60 words" in ai_sims_server.SYSTEM_PROMPT
    assert "Never invent a past event" in ai_sims_server.SYSTEM_PROMPT
    assert (
        "preserve concrete facts supplied by the player exactly"
        in ai_sims_server.SYSTEM_PROMPT
    )
    assert prompt.index("Recent conversation") < prompt.index("Player says")

def test_llm_chat_delegates_provider_selection_to_core(monkeypatch) -> None:
    captured = {}

    class Router:
        async def generate(self, task, messages, *, schema=None, temperature=None):
            captured.update(
                task=task,
                messages=messages,
                schema=schema,
                temperature=temperature,
            )
            return "Hello Robin"

    monkeypatch.setattr(ai_sims_server, "provider_router", lambda: Router())

    result = ai_sims_server.llm_chat(
        [{"role": "user", "content": "Hello"}],
        temperature=0.4,
        schema={"type": "object"},
    )

    assert result == "Hello Robin"
    assert captured["task"] == "large"
    assert captured["messages"][0].role == "user"
    assert captured["messages"][0].content == "Hello"
    assert captured["schema"] == {"type": "object"}
    assert captured["temperature"] == 0.4


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


def test_adapter_memory_is_stored_by_core(tmp_path, monkeypatch) -> None:
    core_db = str(tmp_path / "core.sqlite3")
    legacy_db = str(tmp_path / "legacy.sqlite3")
    monkeypatch.setattr(ai_sims_server, "CORE_DB_PATH", core_db)
    monkeypatch.setattr(ai_sims_server, "DB_PATH", legacy_db)
    monkeypatch.setattr(ai_sims_server, "ACTIVE_DB_PATH", None)

    ai_sims_server.add_memory("bella", "mortimer", "A greeting", 0.8)

    with open_db(core_db) as conn:
        documents = DocumentMemoryStore(conn).list("thesims4.memory")
    assert len(documents) == 1
    assert documents[0].value["summary"] == "A greeting"
    assert not Path(legacy_db).exists()


def test_legacy_adapter_memory_imports_once_into_core(tmp_path, monkeypatch) -> None:
    core_db = str(tmp_path / "core.sqlite3")
    legacy_db = str(tmp_path / "legacy.sqlite3")
    monkeypatch.setattr(ai_sims_server, "CORE_DB_PATH", core_db)
    monkeypatch.setattr(ai_sims_server, "DB_PATH", legacy_db)
    monkeypatch.setattr(ai_sims_server, "ACTIVE_DB_PATH", None)
    with ai_sims_server.connect_db() as conn:
        conn.execute(
            "INSERT INTO memories"
            "(speaker_id, listener_id, sim_id, target_id, event, summary, importance, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            ("bella", "mortimer", "bella", "mortimer", "Legacy", "Legacy", 0.8, 1),
        )
        conn.commit()

    assert [
        item["summary"] for item in ai_sims_server.memories_for_pair("bella", "mortimer")
    ] == ["Legacy"]
    assert len(ai_sims_server._memory_values("thesims4.memory")) == 1


def test_memory_session_requires_game_save(tmp_path, monkeypatch) -> None:
    memory_db = str(tmp_path / "memory.sqlite3")
    core_db = str(tmp_path / "core.sqlite3")
    monkeypatch.setattr(ai_sims_server, "DB_PATH", memory_db)
    monkeypatch.setattr(ai_sims_server, "CORE_DB_PATH", core_db)
    monkeypatch.setattr(ai_sims_server, "ACTIVE_DB_PATH", None)
    monkeypatch.setattr(ai_sims_server, "PRESERVE_MEMORY_ONLY_ON_GAME_SAVE", True)
    ai_sims_server.connect_db().close()

    ai_sims_server.start_memory_session("session-1", "1")
    ai_sims_server.add_memory("bella", "mortimer", "Unsaved memory", 0.8)
    ai_sims_server.start_memory_session("session-2", "1")
    assert ai_sims_server.memories_for_pair("bella", "mortimer") == []

    ai_sims_server.add_memory("bella", "mortimer", "Save 1 memory", 0.8)
    ai_sims_server.save_memory_session("session-2", "1")
    ai_sims_server.add_memory("bella", "mortimer", "Save 2 memory", 0.8)
    ai_sims_server.save_memory_session("session-2", "2")

    ai_sims_server.start_memory_session("session-3", "1")
    memories = ai_sims_server.memories_for_pair("bella", "mortimer")
    assert [memory["summary"] for memory in memories] == ["Save 1 memory"]

    ai_sims_server.start_memory_session("session-4", "2")
    memories = ai_sims_server.memories_for_pair("bella", "mortimer")
    assert [memory["summary"] for memory in memories] == [
        "Save 2 memory",
        "Save 1 memory",
    ]
    assert (tmp_path / "core.sqlite3.empneon-saved.slot-1").exists()
    assert (tmp_path / "core.sqlite3.empneon-saved.slot-2").exists()


def test_legacy_memory_checkpoint_is_migrated(tmp_path, monkeypatch) -> None:
    memory_db = str(tmp_path / "memory.sqlite3")
    core_db = str(tmp_path / "core.sqlite3")
    monkeypatch.setattr(ai_sims_server, "DB_PATH", memory_db)
    monkeypatch.setattr(ai_sims_server, "CORE_DB_PATH", core_db)
    monkeypatch.setattr(ai_sims_server, "ACTIVE_DB_PATH", None)
    monkeypatch.setattr(ai_sims_server, "PRESERVE_MEMORY_ONLY_ON_GAME_SAVE", True)
    ai_sims_server.connect_db().close()
    ai_sims_server.add_memory("bella", "mortimer", "Legacy memory", 0.8)
    database, legacy, session = ai_sims_server.memory_session_paths()
    ai_sims_server.backup_memory_database(database, legacy)
    ai_sims_server.write_memory_session(session, "old-session", "1")

    ai_sims_server.start_memory_session("new-session", "1")

    assert (tmp_path / "core.sqlite3.empneon-saved.slot-1").exists()
    memories = ai_sims_server.memories_for_pair("bella", "mortimer")
    assert [memory["summary"] for memory in memories] == ["Legacy memory"]


def test_memory_is_continuous_when_save_flag_is_disabled(tmp_path, monkeypatch) -> None:
    memory_db = str(tmp_path / "memory.sqlite3")
    core_db = str(tmp_path / "core.sqlite3")
    monkeypatch.setattr(ai_sims_server, "DB_PATH", memory_db)
    monkeypatch.setattr(ai_sims_server, "CORE_DB_PATH", core_db)
    monkeypatch.setattr(ai_sims_server, "ACTIVE_DB_PATH", None)
    monkeypatch.setattr(ai_sims_server, "PRESERVE_MEMORY_ONLY_ON_GAME_SAVE", False)
    ai_sims_server.connect_db().close()

    ai_sims_server.start_memory_session("session-1", "slot-1")
    ai_sims_server.add_memory("bella", "mortimer", "Continuous memory", 0.8)
    ai_sims_server.save_memory_session("session-1", "slot-1")
    ai_sims_server.start_memory_session("session-2", "slot-2")
    memories = ai_sims_server.memories_for_pair("bella", "mortimer")
    assert [memory["summary"] for memory in memories] == ["Continuous memory"]
    assert list(tmp_path.glob("*.empneon-*")) == []


def test_memories_route_without_target_returns_all_sim_memories(monkeypatch) -> None:
    handler = ai_sims_server.Handler.__new__(ai_sims_server.Handler)
    handler.path = "/memories?sim_id=bella&limit=5"
    responses = []
    monkeypatch.setattr(
        ai_sims_server,
        "memories_for_sim",
        lambda sim_id, limit: [{"sim_id": sim_id, "limit": limit}],
    )
    monkeypatch.setattr(handler, "send_json", lambda status, body: responses.append((status, body)))

    handler.do_GET()

    assert responses == [
        (
            200,
            {
                "memories": [{"sim_id": "bella", "limit": 5}],
                "summary": {"summary": "", "updated_at": 0},
            },
        )
    ]
