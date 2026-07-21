import contextlib
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from empneon.core.contracts import (
    AgentStateSnapshot,
    CognitiveRequest,
    Decision,
    StateDelta,
    WorldEvent,
)
from empneon.core.identity.emotions import EmotionalState, EmotionalStateStore
from empneon.core.identity.goals import Goal, GoalStore
from empneon.core.identity.models import Agent
from empneon.core.identity.personality import PersonalityStore
from empneon.core.identity.relationships import Relationship, RelationshipStore
from empneon.core.identity.serialization import export_agent
from empneon.core.identity.store import AgentStore
from empneon.core.identity.voice import VoiceProfileStore
from empneon.core.memory.documents import DocumentMemoryStore
from empneon.core.memory.episodic import EpisodicMemoryStore, Event, ObservationStore
from empneon.core.replay import replay_action_record
from empneon.core.runtime import ActionRecordStore
from empneon.core.scheduler.usage import UsageStore
from empneon.core.state import save_agent_state
from empneon.db.connection import open_db
from empneon.providers.llm import GenerationResult, ModelCapabilities

from backend import ai_sims_server


def test_backend_script_imports_from_outside_release_root(tmp_path) -> None:
    script = Path(ai_sims_server.__file__).resolve()
    core_src = Path(ai_sims_server.ROOT).parents[1] / "core" / "src"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(core_src)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import runpy; runpy.run_path({str(script)!r}, run_name='release_import')",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_cognition_queue_prioritizes_waiting_player_work() -> None:
    assert hasattr(ai_sims_server, "CognitionQueue")
    queue = ai_sims_server.CognitionQueue(1, 4)
    blocker_started = threading.Event()
    release_blocker = threading.Event()
    order = []

    def request(name, urgency):
        return CognitiveRequest(
            name,
            1,
            WorldEvent("test", (name,)),
            urgency=urgency,
            deadline_ms=5_000,
        )

    def block():
        blocker_started.set()
        release_blocker.wait(2)
        order.append("blocker")

    threads = [
        threading.Thread(target=lambda: queue.run(request("blocker", 0.5), block)),
        threading.Thread(
            target=lambda: queue.run(
                request("ambient", 0.35), lambda: order.append("ambient")
            )
        ),
        threading.Thread(
            target=lambda: queue.run(
                request("player", 1.0), lambda: order.append("player")
            )
        ),
    ]
    threads[0].start()
    assert blocker_started.wait(1)
    threads[1].start()
    while len(queue) < 1:
        time.sleep(0.001)
    threads[2].start()
    while len(queue) < 2:
        time.sleep(0.001)
    release_blocker.set()
    for thread in threads:
        thread.join(2)

    assert order == ["blocker", "player", "ambient"]


def test_unified_database_is_the_only_active_default() -> None:
    path = getattr(ai_sims_server, "MEMORY_DB_PATH", "")

    assert path.endswith("empneon_core_memory.sqlite3")


def test_prepare_database_adopts_legacy_core_without_modifying_it(tmp_path) -> None:
    old = tmp_path / "empneon_core.sqlite3"
    new = tmp_path / "empneon_core_memory.sqlite3"
    with contextlib.closing(open_db(old)) as conn:
        AgentStore(conn).create(
            Agent("bella", "Bella", game_id="bella", adapter="sims4")
        )
    before = old.read_bytes()
    state = getattr(ai_sims_server, "empneon_state", None)

    assert state is not None
    status = state.prepare_database(
        str(new), str(old), str(tmp_path / "ai_sims_memory.sqlite3")
    )

    with contextlib.closing(open_db(new)) as conn:
        assert AgentStore(conn).get("bella").name == "Bella"
    assert old.read_bytes() == before
    assert status.active_path == str(new.resolve())
    assert status.completed is True


def test_prepare_database_hides_legacy_unconfirmed_observations(tmp_path) -> None:
    database = tmp_path / "empneon_core_memory.sqlite3"
    state = ai_sims_server.empneon_state
    with open_db(database) as conn:
        state.sync_sim(conn, {"id": "bella", "name": "Bella"})
        state.record_observed_event(
            conn,
            Event(
                json.dumps(
                    {
                        "kind": "observed_interaction",
                        "message": "Where is PRIVATE-GARDEN-731?",
                    }
                ),
                ["bella"],
            ),
            {"bella": "Where is PRIVATE-GARDEN-731?"},
            factual_statement="Where is PRIVATE-GARDEN-731?",
        )

    status = state.prepare_database(
        str(database),
        str(tmp_path / "legacy-core.db"),
        str(tmp_path / "legacy-adapter.db"),
    )

    with open_db(database) as conn:
        diagnostics = state.sim_diagnostics(conn, "bella")
    assert status.completed is True
    assert diagnostics["beliefs"] == []
    assert diagnostics["accessible_memories"] == []


def test_sync_sim_populates_canonical_identity_stores(tmp_path, monkeypatch) -> None:
    state = ai_sims_server.empneon_state
    assert hasattr(state, "sync_sim")

    with open_db(tmp_path / "memory.db") as conn:
        profile = state.sync_sim(
            conn,
            {
                "id": "bella",
                "name": "Bella",
                "age": 42,
                "traits": ["Outgoing", "Good"],
                "current_mood": "happy",
                "aspiration": "Successful Lineage",
                "needs": {"hunger": 20, "commodity_burnout_mentaltracker": 5},
                "career": "Secret Agent",
                "voice": {
                    "provider": "piper",
                    "voice": "bella",
                    "speed": 1.1,
                    "pitch": 0.9,
                },
            },
        )

        agent = AgentStore(conn).get("bella")
        assert agent.occupation == "Secret Agent"
        assert agent.age == 42
        assert PersonalityStore(conn).get("bella").extraversion > 0.5
        assert EmotionalStateStore(conn).get("bella", "happiness").value > 0
        assert {
            goal.description for goal in GoalStore(conn).get_all("bella", "active")
        } == {"Aspiration: Successful Lineage", "Restore hunger"}
        assert VoiceProfileStore(conn).get("bella").voice_id == "bella"
        assert profile["id"] == "bella"

        goals = GoalStore(conn)
        hunger = next(
            goal for goal in goals.get_all("bella", "active")
            if goal.description == "Restore hunger"
        )
        legacy = Goal("bella", "Restore ev:internal_counter", id="legacy-internal")
        goals.set(legacy)
        EmotionalStateStore(conn).set(
            EmotionalState(
                "bella", "<class 'sims4.tuning.instances.mood_uncomfortable'>", 0.75
            )
        )
        monkeypatch.setattr(state.time, "time", lambda: hunger.updated_at + 1)
        state.sync_sim(
            conn,
            {
                "id": "bella",
                "name": "Bella",
                "age": 42,
                "needs": {"hunger": 80},
            },
        )
        completed = goals.get(hunger.id)
        assert completed.status == "completed"
        assert completed.updated_at > hunger.updated_at
        assert goals.get("legacy-internal").status == "completed"
        assert (
            EmotionalStateStore(conn).get(
                "bella", "<class 'sims4.tuning.instances.mood_uncomfortable'>"
            )
            is None
        )


def test_legacy_adapter_import_is_idempotent_and_read_only(tmp_path) -> None:
    legacy = tmp_path / "ai_sims_memory.sqlite3"
    connection = sqlite3.connect(legacy)
    connection.row_factory = sqlite3.Row
    ai_sims_server.init_db(connection)
    connection.execute(
        "INSERT INTO sim_profiles VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            "bella",
            "Bella",
            json.dumps({"traits": ["Good"], "career": "Painter"}),
            "{}",
            "[]",
            "[]",
            "{}",
            "[]",
            json.dumps({"provider": "piper", "voice": "bella"}),
            1,
            1,
        ),
    )
    connection.execute(
        "INSERT INTO goals(sim_id, goal, status, importance, updated_at)"
        " VALUES ('bella','Protect family','active',0.8,1)"
    )
    connection.commit()
    connection.close()
    before = legacy.read_bytes()

    with open_db(tmp_path / "empneon_core_memory.sqlite3") as conn:
        assert hasattr(ai_sims_server.empneon_state, "import_legacy_adapter")
        assert ai_sims_server.empneon_state.import_legacy_adapter(conn, str(legacy)) is True
        assert ai_sims_server.empneon_state.import_legacy_adapter(conn, str(legacy)) is False
        assert AgentStore(conn).get("bella").occupation == "Painter"
        assert [goal.description for goal in GoalStore(conn).get_all("bella")] == [
            "Protect family"
        ]
        assert VoiceProfileStore(conn).get("bella").voice_id == "bella"
    assert legacy.read_bytes() == before


def test_vector_retrieval_never_leaks_an_unobserved_secret(tmp_path) -> None:
    state = ai_sims_server.empneon_state
    assert hasattr(state, "record_observed_event")
    assert hasattr(state, "relevant_memories")

    with open_db(tmp_path / "memory.db") as conn:
        state.sync_sim(conn, {"id": "bella", "name": "Bella"})
        state.sync_sim(conn, {"id": "mortimer", "name": "Mortimer"})
        event = Event("A key is hidden in the garden", ["bella"])
        state.record_observed_event(
            conn,
            event,
            {"bella": "I saw the garden key"},
            factual_statement="The key is in the garden",
        )

        assert state.relevant_memories(conn, "bella", "garden key")
        assert state.relevant_memories(conn, "mortimer", "garden key") == []


def test_relevant_memories_searches_every_observable_candidate(tmp_path, monkeypatch) -> None:
    state = ai_sims_server.empneon_state
    with open_db(tmp_path / "memory.db") as conn:
        for index in range(40):
            event = Event(f"Memory {index}", ["karmine"])
            state.record_observed_event(conn, event, {"karmine": event.description})

        captured = {}

        class FakeVectors:
            def __init__(self, _conn):
                pass

            def search(self, _embedding, limit):
                captured["limit"] = limit
                return []

        monkeypatch.setattr(state, "VectorMemoryStore", FakeVectors)
        assert state.relevant_memories(conn, "karmine", "garden", 6)

    assert captured["limit"] == 40


def test_memories_for_pair_filters_complete_observable_ranking(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ai_sims_server, "CORE_DB_PATH", str(tmp_path / "core.db"))
    target = {
        "id": "target",
        "summary": "PRIVATE-GARDEN-731 is under the blue bench",
        "participant_ids": ["karmine", "bernard"],
        "created_at": 1,
    }
    distractors = [
        {
            "id": f"other-{index}",
            "summary": f"Other memory {index}",
            "participant_ids": ["karmine", f"other-{index}"],
            "created_at": index + 2,
        }
        for index in range(25)
    ]
    captured = {}

    def find(_conn, _agent_id, _query, limit):
        captured["limit"] = limit
        return (distractors + [target])[:limit]

    monkeypatch.setattr(ai_sims_server.empneon_state, "relevant_memories", find)

    found = ai_sims_server.memories_for_pair(
        "karmine", "bernard", query="Where is the garden code item?"
    )

    assert found == [target]
    assert captured["limit"] > len(distractors)


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
    with open_db(tmp_path / "core.db") as conn:
        assert DocumentMemoryStore(conn).list("thesims4.conversation") == []

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


def test_rich_game_state_is_grounded_in_dialogue_prompt() -> None:
    payload = {
        "speaker": {
            "id": "bella",
            "needs": {"Hunger": 18},
            "moodlets": ["Uncomfortable"],
            "aspiration": "MasterChef",
            "career": "Painter",
            "skills": {"Cooking": 7},
            "household": {"name": "Goth Household"},
        },
        "listener": {},
        "message": "How are you?",
    }
    context = ai_sims_server.build_context(
        payload,
        {"name": "Bella"},
        {"name": "Mortimer"},
        {},
        {},
        [],
        {},
    )
    context.update({"conversation": [], "speaker_id": "bella", "listener_id": "mortimer"})

    prompt = ai_sims_server.build_chat_prompt(payload, context)

    for expected in (
        'Needs: {"Hunger": 18}',
        "Moodlets: Uncomfortable",
        "Aspiration: MasterChef",
        "Career: Painter",
        'Skills: {"Cooking": 7}',
        "Household: Goth Household",
    ):
        assert expected in prompt


def test_prompt_action_explanations_only_include_request_actions_and_none() -> None:
    payload = {
        "speaker": {"id": "bella"},
        "listener": {"id": "mortimer"},
        "message": "Hello.",
        "available_actions": ["friendly_chat"],
    }
    context = ai_sims_server.build_context(
        payload,
        {"name": "Bella"},
        {"name": "Mortimer"},
        {},
        {},
        [],
        {},
    )
    context.update(conversation=[], speaker_id="bella", listener_id="mortimer")

    prompt = ai_sims_server.build_chat_prompt(payload, context)

    assert "- friendly_chat: continue a friendly conversation." in prompt
    assert "- none: dialogue only; perform no Sims action." in prompt
    assert "apologize" not in prompt
    assert "flirt" not in prompt


def test_memories_for_pair_uses_current_query_and_preserves_relevance(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(ai_sims_server, "CORE_DB_PATH", str(tmp_path / "core.db"))
    captured = {}
    relevant = [
        {
            "id": "most-relevant",
            "summary": "PRIVATE-GARDEN-731 is under the blue bench.",
            "participant_ids": ["bella", "mortimer"],
            "created_at": 1,
        },
        {
            "id": "newer",
            "summary": "Unrelated recent conversation.",
            "participant_ids": ["bella", "mortimer"],
            "created_at": 2,
        },
    ]

    def find(_conn, agent_id, query, limit):
        captured.update(agent_id=agent_id, query=query, limit=limit)
        return relevant

    monkeypatch.setattr(ai_sims_server.empneon_state, "relevant_memories", find)

    memories = ai_sims_server.memories_for_pair(
        "bella", "mortimer", limit=2, query="Where was the garden item hidden?"
    )

    assert captured["query"] == "Where was the garden item hidden?"
    assert [item["id"] for item in memories] == ["most-relevant", "newer"]


def test_dialogue_fallback_mentions_critical_need_and_refuses_unsupported_fact(
    monkeypatch,
) -> None:
    responses = iter(
        [
            json.dumps({"dialogue": "I feel fine."}),
            json.dumps({"dialogue": "Everything is okay."}),
            json.dumps({"dialogue": "It is behind the main house."}),
            json.dumps({"dialogue": "Try the back garden."}),
        ]
    )
    monkeypatch.setattr(ai_sims_server, "llm_chat", lambda *_args, **_kwargs: next(responses))
    payload = {
        "speaker": {"needs": {"bladder": 10}, "moodlets": ["ReallyHasToPee"]},
        "listener": {},
        "message": "How are you feeling and what needs attention?",
    }
    context = ai_sims_server.build_context(
        payload,
        {"name": "Bella"},
        {"name": "Mortimer"},
        {},
        {"current_mood": "uncomfortable"},
        [],
        {},
    )
    context.update(conversation=[], speaker_id="bella", listener_id="mortimer")

    need_response = ai_sims_server.HERMES.dialogue(payload, context)
    assert "bladder" in need_response["dialogue"].casefold()
    assert "critical" in need_response["dialogue"].casefold()

    payload["speaker"] = {}
    payload["message"] = "Where is PRIVATE-GARDEN-731?"
    context["game_state"]["needs"] = {}
    context["game_state"]["moodlets"] = []
    context["message"] = payload["message"]
    context["memories"] = [{"summary": "We talked about pizza yesterday."}]
    context["summary"] = "We talked about pizza yesterday."
    unknown_response = ai_sims_server.HERMES.dialogue(payload, context)
    assert any(
        phrase in unknown_response["dialogue"].casefold()
        for phrase in ("don't know", "do not know", "don't remember", "do not remember")
    )


def test_grounding_rejects_stale_needs_memory_denial_and_ignored_romance() -> None:
    context = ai_sims_server.build_context(
        {"speaker": {"needs": {"hunger": 80}}, "listener": {}},
        {"name": "Karmine"},
        {"name": "Bernard"},
        {},
        {},
        [{"summary": "PRIVATE-GARDEN-731 is under the blue bench"}],
        {"summary": "PRIVATE-GARDEN-731 is under the blue bench"},
    )
    context.update(conversation=[], speaker_id="karmine", listener_id="bernard")

    stale_need = ai_sims_server.normalize_response(
        {"dialogue": "My hunger is critical.", "intent": "respond"}
    )
    assert ai_sims_server.response_grounding_issue(
        {"message": "Would you like to go on a date?"}, stale_need, context
    )

    denial = ai_sims_server.normalize_response(
        {"dialogue": "What are you talking about?", "intent": "clarify"}
    )
    assert "supporting memory" in ai_sims_server.response_grounding_issue(
        {"message": "Where is the garden code item?"}, denial, context
    )

    ignored = ai_sims_server.normalize_response(
        {"dialogue": "It is nice to see you.", "intent": "agree"}
    )
    assert ai_sims_server.response_grounding_issue(
        {"message": "Would you like to go on a date?"}, ignored, context
    ) == ""

    for message in (
        "Would you go out with me sometime?",
        "Let's be girlfriends.",
        "Would you be my boyfriend?",
    ):
        assert ai_sims_server.response_grounding_issue(
            {"message": message}, ignored, context
        ) == ""

    accepted = ai_sims_server.normalize_response(
        {
            "dialogue": "Yes, I would like to go on a date.",
            "intent": "flirt",
            "relationship": {"romance_delta": 1},
        }
    )
    assert ai_sims_server.response_grounding_issue(
        {"message": "Would you like to go on a date?"}, accepted, context
    ) == ""

    declined = ai_sims_server.normalize_response(
        {
            "dialogue": "No, I would rather stay friends.",
            "intent": "set_boundary",
            "relationship": {"romance_delta": 0},
        }
    )
    assert ai_sims_server.response_grounding_issue(
        {"message": "Would you like to go on a date?"}, declined, context
    ) == ""

    echoed = ai_sims_server.normalize_response(
        {
            "dialogue": (
                "It's nice to meet you too, Bernard. Meeting you today has made my day "
                "very happy."
            ),
            "intent": "agree",
        }
    )
    copy_context = dict(
        context,
        speaker={"name": "Billie"},
        listener={"name": "Bernard"},
    )
    assert "copy" in ai_sims_server.response_grounding_issue(
        {
            "message": (
                "It's nice to meet you too, Billie. Meeting you today has made my day "
                "very happy."
            )
        },
        echoed,
        copy_context,
    )

    near_copy = ai_sims_server.normalize_response(
        {
            "dialogue": "It's just looking at you, baby. You really make my world spin.",
            "intent": "respond",
            "player_interaction_kind": "romantic_compliment",
        }
    )
    assert "copy" in ai_sims_server.response_grounding_issue(
        {"message": "Just looking at you, baby. You really make my world spin."},
        near_copy,
        copy_context,
    )

    context["conversation"] = [
        {
            "speaker_id": "billie",
            "message": "It is nice to meet you.",
            "dialogue": "You have a very kind presence.",
        }
    ]
    copy_context["conversation"] = context["conversation"]
    reused = ai_sims_server.normalize_response(
        {"dialogue": "You have a very kind presence.", "intent": "recall"}
    )
    assert "previous reply" in ai_sims_server.response_grounding_issue(
        {"message": "Would you go out with me sometime?"}, reused, copy_context
    )

    fallback = ai_sims_server.reasoning_fallback_response(
        {"message": "Would you go out with me sometime?"}, context
    )
    assert fallback["intent"] == "set_boundary"
    assert fallback["relationship"]["romance_delta"] == 0


def test_natural_date_reply_survives_non_romantic_action_metadata() -> None:
    context = ai_sims_server.build_context(
        {"speaker": {}, "listener": {}},
        {"name": "Karmine"},
        {"name": "Bernard"},
        {},
        {},
        [],
        {"summary": ""},
    )
    payload = {
        "message": "I would love to take you on a date sometime.",
        "available_actions": ["friendly_chat", "apologize", "flirt"],
    }
    response = ai_sims_server.normalize_response(
        {
            "dialogue": "That's sweet! A date sounds like fun. You have a certain charm.",
            "expressed_emotion": "confidence",
            "intent": "friendly",
            "player_interaction_kind": "romantic_compliment",
            "suggested_action": "friendly_chat",
            "relationship": {
                "friendship_delta": 1,
                "romance_delta": 0,
                "trust_delta": 50,
            },
            "memory": {
                "importance": 0.75,
                "summary": "Bernard invited Karmine on a date.",
            },
        },
        payload["available_actions"],
    )

    assert ai_sims_server.response_grounding_issue(payload, response, context) == ""
    assert response["dialogue"].startswith("That's sweet!")
    assert response["suggested_action"] == "friendly_chat"
    assert response["relationship"]["trust_delta"] == 10


def test_action_metadata_is_request_scoped_and_does_not_replace_dialogue() -> None:
    actions = ["friendly_chat", "flirt"]

    unavailable = ai_sims_server.normalize_response(
        {"dialogue": "I can talk, but I cannot do that.", "suggested_action": "argue"},
        actions,
    )
    declined = ai_sims_server.normalize_response(
        {
            "dialogue": "No, I would rather stay friends.",
            "suggested_action": "flirt",
        },
        actions,
    )

    assert unavailable["dialogue"] == "I can talk, but I cannot do that."
    assert unavailable["suggested_action"] == "none"
    assert declined["suggested_action"] == "none"
    assert ai_sims_server.dialogue_schema(actions)["properties"]["suggested_action"] == {
        "type": "string",
        "enum": ["friendly_chat", "flirt", "none"],
    }


def test_repetition_retry_removes_recent_conversation_history(monkeypatch) -> None:
    prompts = []
    responses = iter(
        [
            {
                "dialogue": "You have a very kind presence.",
                "emotion": "happy",
                "intent": "respond",
                "player_interaction_kind": "friendly",
                "relationship": {},
                "memory": {},
                "animation": "friendly_chat",
            },
            {
                "dialogue": "Thank you. I enjoy spending time with you too.",
                "emotion": "happy",
                "intent": "agree",
                "player_interaction_kind": "friendly",
                "relationship": {},
                "memory": {},
                "animation": "friendly_chat",
            },
        ]
    )

    def fake_llm(messages, **_kwargs):
        prompts.append(messages[-1]["content"])
        return json.dumps(next(responses))

    monkeypatch.setattr(ai_sims_server, "llm_chat", fake_llm)
    payload = {
        "speaker": {},
        "listener": {},
        "message": "You are very nice. Let's be friends!",
    }
    context = ai_sims_server.build_context(
        payload,
        {"name": "Karmine"},
        {"name": "Bernard"},
        {},
        {},
        [],
        {"summary": ""},
    )
    context.update(
        speaker_id="karmine",
        listener_id="bernard",
        conversation=[
            {
                "speaker_id": "karmine",
                "message": "It is nice to meet you.",
                "dialogue": "You have a very kind presence.",
            }
        ],
    )

    response = ai_sims_server.HERMES.dialogue(payload, context)

    assert response["dialogue"] == "Thank you. I enjoy spending time with you too."
    assert "You have a very kind presence." in prompts[0]
    assert "Recent conversation:\nNone yet" in prompts[1]


def test_local_social_classifier_distinguishes_common_player_interactions() -> None:
    examples = {
        "Would you go out with me sometime?": "romantic_invitation",
        "Let's be girlfriends.": "romantic_invitation",
        (
            "I like you, Karmine. You are very beautiful. "
            "I would love to take you on a date sometime."
        ): "romantic_invitation",
        "I'm very attracted to you. You are really hot.": "romantic_compliment",
        "You are very nice. Let's be friends!": "friendly",
        "Where is the garden code item?": "informational",
        "I hate you. Leave me alone.": "hostile",
        "The weather changed today.": "neutral",
    }

    assert {
        message: ai_sims_server.classify_player_interaction(message)
        for message in examples
    } == examples


def test_romantic_compliment_does_not_require_invitation_consent_shape() -> None:
    context = ai_sims_server.build_context(
        {"speaker": {}, "listener": {}},
        {"name": "Karmine"},
        {"name": "Bernard"},
        {},
        {},
        [],
        {"summary": ""},
    )
    context.update(conversation=[], speaker_id="karmine", listener_id="bernard")
    response = ai_sims_server.normalize_response(
        {
            "dialogue": "That is flattering, Bernard. You have caught my attention.",
            "emotion": "flattered",
            "intent": "respond",
            "player_interaction_kind": "romantic_compliment",
            "relationship": {"romance_delta": 0},
        }
    )

    assert ai_sims_server.response_grounding_issue(
        {"message": "I'm very attracted to you. You are really hot."}, response, context
    ) == ""


def test_reasoning_fallback_responds_relevantly_to_romantic_compliment() -> None:
    context = ai_sims_server.build_context(
        {"speaker": {}, "listener": {}},
        {"name": "Karmine"},
        {"name": "Bernard"},
        {},
        {},
        [],
        {"summary": ""},
    )

    response = ai_sims_server.reasoning_fallback_response(
        {"message": "I'm very attracted to you. You are really hot."}, context
    )

    assert response["player_interaction_kind"] == "romantic_compliment"
    assert "give me a moment" not in response["dialogue"].casefold()
    assert "attracted to you" not in response["dialogue"].casefold()


def test_romantic_invitation_fallback_does_not_recall_an_earlier_player_message() -> None:
    previous_message = (
        "I like you, Karmine. You are very beautiful. "
        "I would love to take you on a date sometime."
    )
    context = ai_sims_server.build_context(
        {"speaker": {}, "listener": {}},
        {"name": "Karmine"},
        {"name": "Bernard"},
        {},
        {},
        [{"summary": previous_message}],
        {"summary": previous_message},
    )

    response = ai_sims_server.reasoning_fallback_response(
        {"message": "I love you very much. Would you like to be my girlfriend?"},
        context,
    )

    assert response["player_interaction_kind"] == "romantic_invitation"
    assert response["intent"] == "set_boundary"
    assert response["dialogue"] != previous_message


def test_reasoning_fallback_stays_relevant_across_social_kinds() -> None:
    context = ai_sims_server.build_context(
        {"speaker": {}, "listener": {}},
        {"name": "Karmine"},
        {"name": "Bernard"},
        {},
        {},
        [],
        {"summary": ""},
    )
    messages = {
        "You are very nice. Let's be friends!": "friendly",
        "I hate you. Leave me alone.": "hostile",
        "How do you feel about gardening?": "informational",
        "The weather changed today.": "neutral",
    }

    responses = {
        expected: ai_sims_server.reasoning_fallback_response(
            {"message": message}, context
        )
        for message, expected in messages.items()
    }

    assert set(responses) == set(messages.values())
    assert all(
        response["player_interaction_kind"] == kind
        and "give me a moment" not in response["dialogue"].casefold()
        for kind, response in responses.items()
    )
    assert responses["hostile"]["intent"] == "set_boundary"


def test_reasoning_fallback_recalls_supported_fact_and_uses_concrete_summary() -> None:
    context = ai_sims_server.build_context(
        {"speaker": {}, "listener": {}},
        {"name": "Karmine"},
        {"name": "Bernard"},
        {},
        {},
        [{"summary": "PRIVATE-GARDEN-731 is under the blue bench"}],
        {"summary": "PRIVATE-GARDEN-731 is under the blue bench"},
    )
    recall = ai_sims_server.reasoning_fallback_response(
        {"message": "Where is the garden code item?"}, context
    )
    assert "under the blue bench" in recall["dialogue"]

    context["memories"] = []
    context["summary"] = ""
    fallback = ai_sims_server.reasoning_fallback_response(
        {"message": "Hello there"}, context
    )
    assert fallback["memory"]["summary"] != "The conversation needed a careful response."
    assert "Hello there" in fallback["memory"]["summary"]

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


def test_provider_output_parsing_uses_first_json_and_never_exposes_malformed_data() -> None:
    first = {"dialogue": "Pizza sounds good.", "emotion": "happy"}
    duplicated = f"```json\n{json.dumps(first)}\n```\n```json\n{json.dumps(first)}\n```"

    assert ai_sims_server.extract_json(duplicated) == first
    fallback = ai_sims_server.fallback_response(
        '{"dialogue": "partial"}\n```json\n{"dialogue": "duplicate"'
    )
    assert "{\"dialogue\"" not in fallback["dialogue"]
    assert fallback["memory"] == {"importance": 0.0, "summary": ""}


def test_player_dialogue_uses_dynamic_clod_and_records_provider_usage(
    tmp_path, monkeypatch
) -> None:
    content = json.dumps(
        {
            "dialogue": "Hello.",
            "emotion": "happy",
            "intent": "greet",
            "relationship": {
                "friendship_delta": 0,
                "romance_delta": 0,
                "trust_delta": 0,
            },
            "memory": {"importance": 0.2, "summary": "One concrete event memory."},
            "animation": "friendly_chat",
        }
    )

    class Provider:
        capabilities = ModelCapabilities(structured_output=True, local=True)

    class Router:
        def config_for(self, _task):
            return {
                "name": "test",
                "model": "stub",
                "max_tokens": 300,
                "context_tokens": 4096,
                "latency_ms": 1000,
                "ram_mb": 64,
                "vram_mb": 0,
            }

        def provider_for(self, _task):
            return Provider()

        async def generate_result(self, *_args, **_kwargs):
            return GenerationResult(content, 20, 8, 30)

        async def generate(self, *_args, **_kwargs):
            return content

    core_db = str(tmp_path / "empneon_core_memory.sqlite3")
    monkeypatch.setattr(ai_sims_server, "provider_router", lambda: Router())
    monkeypatch.setattr(ai_sims_server, "CORE_DB_PATH", core_db)
    monkeypatch.setattr(ai_sims_server, "DB_PATH", core_db)

    result = ai_sims_server.chat(
        {
            "speaker": {"id": "bella", "name": "Bella"},
            "listener": {"id": "mortimer", "name": "Mortimer"},
            "message": "PRIVATE-GARDEN-731 is under the blue bench.",
            "event": {"type": "player_conversation", "source": "test"},
            "available_actions": ["friendly_chat"],
        }
    )

    with open_db(core_db) as conn:
        telemetry = UsageStore(conn).telemetry("bella")
        pending = ai_sims_server.empneon_state.sim_diagnostics(conn, "bella")
    assert result["selected_clod"] == 3
    assert pending["beliefs"] == []
    assert pending["accessible_memories"] == []
    assert telemetry["by_clod"] == {"3": 1}
    assert telemetry["actual"] == {
        "prompt_tokens": 20,
        "completion_tokens": 8,
        "latency_ms": 30,
    }

    ai_sims_server.confirm_dialogue_delivery(
        {"decision_id": result["decision_id"], "status": "displayed"}
    )
    ai_sims_server.confirm_action(
        {
            "decision_id": result["decision_id"],
            "action": result["animation"],
            "status": "succeeded",
        }
    )
    with open_db(core_db) as conn:
        confirmed = ai_sims_server.empneon_state.sim_diagnostics(conn, "bella")
    assert [item["statement"] for item in confirmed["beliefs"]] == [
        "PRIVATE-GARDEN-731 is under the blue bench."
    ]
    assert len(confirmed["accessible_memories"]) == 1
    description = json.loads(confirmed["accessible_memories"][0]["description"])
    assert description["summary"] != "One concrete event memory."
    assert "PRIVATE-GARDEN-731" in description["summary"]

    question = ai_sims_server.chat(
        {
            "speaker": {"id": "bella", "name": "Bella"},
            "listener": {"id": "mortimer", "name": "Mortimer"},
            "message": "Where is PRIVATE-GARDEN-731?",
            "event": {"type": "player_conversation", "source": "test"},
            "available_actions": ["friendly_chat"],
        }
    )
    ai_sims_server.confirm_dialogue_delivery(
        {"decision_id": question["decision_id"], "status": "displayed"}
    )
    ai_sims_server.confirm_action(
        {
            "decision_id": question["decision_id"],
            "action": question["animation"],
            "status": "succeeded",
        }
    )
    with open_db(core_db) as conn:
        after_question = ai_sims_server.empneon_state.sim_diagnostics(conn, "bella")
    assert [item["statement"] for item in after_question["beliefs"]] == [
        "PRIVATE-GARDEN-731 is under the blue bench."
    ]


def test_player_dialogue_uses_relevant_adapter_fallback_when_provider_fails(
    tmp_path, monkeypatch
) -> None:
    class Provider:
        capabilities = ModelCapabilities(structured_output=True, local=True)

    class Router:
        def config_for(self, _task):
            return {
                "name": "unavailable",
                "model": "offline",
                "max_tokens": 300,
                "context_tokens": 4096,
                "latency_ms": 1000,
                "ram_mb": 64,
                "vram_mb": 0,
            }

        def provider_for(self, _task):
            return Provider()

    def fail_dialogue(_payload, _context):
        raise RuntimeError("provider unavailable")

    core_db = str(tmp_path / "empneon_core_memory.sqlite3")
    monkeypatch.setattr(ai_sims_server, "provider_router", lambda: Router())
    monkeypatch.setattr(ai_sims_server, "CORE_DB_PATH", core_db)
    monkeypatch.setattr(ai_sims_server, "DB_PATH", core_db)
    monkeypatch.setattr(ai_sims_server.HERMES, "dialogue", fail_dialogue)

    result = ai_sims_server.chat(
        {
            "speaker": {"id": "karmine", "name": "Karmine"},
            "listener": {"id": "bernard", "name": "Bernard"},
            "message": "I'm very attracted to you. You are really hot.",
            "event": {"type": "player_conversation", "source": "test"},
            "available_actions": ["friendly_chat", "flirt"],
        }
    )

    with open_db(core_db) as conn:
        telemetry = UsageStore(conn).telemetry("karmine")
    assert result["selected_clod"] == 1
    assert "language model is unavailable" not in result["dialogue"].casefold()
    assert "give me a moment" not in result["dialogue"].casefold()
    assert "attracted to you" not in result["dialogue"].casefold()
    assert result["relationship"]["romance_delta"] == 0
    assert telemetry["by_provider"] == {"core-rules": 1}


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
        usage = UsageStore(conn).telemetry("bella")
    assert relationship is not None
    assert relationship.strength == 0.05
    assert record is not None
    assert record.result.status == "succeeded"
    assert usage["by_clod"] == {"1": 1}
    assert usage["actual"]["prompt_tokens"] == 0


def test_failed_action_records_replay_but_applies_no_consequences(
    tmp_path, monkeypatch
) -> None:
    core_db = str(tmp_path / "core.sqlite3")
    monkeypatch.setattr(ai_sims_server, "CORE_DB_PATH", core_db)
    proposal = ai_sims_server.autonomous_action(
        {
            "speaker": {"id": "bella", "name": "Bella"},
            "listener": {"id": "mortimer", "name": "Mortimer"},
            "event": {"type": "autonomous_social", "source": "test"},
            "available_actions": ["friendly_chat"],
        }
    )

    ai_sims_server.confirm_action(
        {
            "decision_id": proposal["decision_id"],
            "action": "friendly_chat",
            "status": "failed",
            "reason": "cancelled",
        }
    )

    with open_db(core_db) as conn:
        replay = replay_action_record(conn, proposal["decision_id"])
        relationship = RelationshipStore(conn).get("bella", "mortimer")
        diagnostics = ai_sims_server.empneon_state.sim_diagnostics(conn, "bella")
    assert replay["result"]["status"] == "failed"
    assert relationship is None
    assert diagnostics["beliefs"] == []
    assert diagnostics["accessible_memories"] == []


def test_action_confirmation_is_idempotent_after_lost_response(
    tmp_path, monkeypatch
) -> None:
    core_db = str(tmp_path / "core.sqlite3")
    monkeypatch.setattr(ai_sims_server, "CORE_DB_PATH", core_db)
    proposal = ai_sims_server.autonomous_action(
        {
            "speaker": {"id": "bella", "name": "Bella"},
            "listener": {"id": "mortimer", "name": "Mortimer"},
            "event": {"type": "autonomous_social", "source": "test"},
            "available_actions": ["friendly_chat"],
        }
    )
    payload = {
        "decision_id": proposal["decision_id"],
        "action": "friendly_chat",
        "status": "succeeded",
        "changes": [
            {
                "path": "relationship.friendship",
                "operation": "increment",
                "value": 5,
            }
        ],
    }

    first = ai_sims_server.confirm_action(payload)
    second = ai_sims_server.confirm_action(payload)

    assert second == first
    with open_db(core_db) as conn:
        relationship = RelationshipStore(conn).get("bella", "mortimer")
    assert relationship is not None
    assert relationship.strength == 0.05


def test_successful_confirmation_applies_validated_identity_consequences(
    tmp_path, monkeypatch
) -> None:
    core_db = str(tmp_path / "core.sqlite3")
    monkeypatch.setattr(ai_sims_server, "CORE_DB_PATH", core_db)
    proposal = ai_sims_server.autonomous_action(
        {
            "speaker": {
                "id": "bella",
                "name": "Bella",
                "aspiration": "MasterChef",
                "needs": {"Hunger": 10},
            },
            "listener": {"id": "mortimer", "name": "Mortimer"},
            "event": {"type": "autonomous_social", "source": "test"},
            "available_actions": ["friendly_chat"],
        }
    )
    with open_db(core_db) as conn:
        goals = GoalStore(conn).get_all("bella")
        aspiration = next(goal for goal in goals if goal.description.startswith("Aspiration:"))
        hunger = next(goal for goal in goals if goal.description == "Restore hunger")

    ai_sims_server.confirm_action(
        {
            "decision_id": proposal["decision_id"],
            "action": "friendly_chat",
            "status": "succeeded",
            "changes": [
                {"path": "relationship.romance", "operation": "increment", "value": 5},
                {"path": "emotion.happiness", "operation": "set", "value": 80},
                {"path": "need.Hunger", "operation": "set", "value": 60},
                {"path": f"goal.{aspiration.id}.status", "operation": "set", "value": "completed"},
            ],
        }
    )

    with open_db(core_db) as conn:
        relationship = RelationshipStore(conn).get("bella", "mortimer")
        emotion = EmotionalStateStore(conn).get("bella", "happiness")
        goals = GoalStore(conn)
        replay = replay_action_record(conn, proposal["decision_id"])
        timeline = ai_sims_server.agent_timeline(conn, "bella")
    assert relationship.relationship_type == "romantic"
    assert relationship.trust == 0.5
    assert emotion.value == 0.8
    assert goals.get(hunger.id).status == "completed"
    assert goals.get(aspiration.id).status == "completed"
    assert replay["consequence_integrity"] is True
    assert any(entry["id"] == proposal["decision_id"] for entry in timeline["entries"])


def test_identity_export_import_round_trip_uses_unified_database(tmp_path) -> None:
    with open_db(tmp_path / "source.db") as source:
        ai_sims_server.empneon_state.sync_sim(
            source, {"id": "bella", "name": "Bella", "traits": ["Good"]}
        )
        exported = ai_sims_server.empneon_state.export_identity(source, "bella")
    with open_db(tmp_path / "target.db") as target:
        imported = ai_sims_server.empneon_state.import_identity(target, exported)
        assert imported.id == "bella"
        restored = export_agent(
            "bella", ai_sims_server.empneon_state.identity_stores(target)
        )
        assert restored == exported


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
        diagnostics = ai_sims_server.empneon_state.sim_diagnostics(conn, "bella")
        observed = EpisodicMemoryStore(conn).get(proposal.event_id)
    assert result["action_status"] == "proposed"
    assert result["animation"] == "friendly_chat"
    assert proposal is not None
    assert record is None
    assert diagnostics["agent_state"]["agent_id"] == "bella"
    assert json.loads(observed.description)["agent_state"]["agent_id"] == "bella"


def test_generated_memory_is_episodic_only_after_game_confirmation(
    tmp_path, monkeypatch
) -> None:
    core_db = str(tmp_path / "core.sqlite3")
    monkeypatch.setattr(ai_sims_server, "CORE_DB_PATH", core_db)
    monkeypatch.setattr(ai_sims_server, "DB_PATH", str(tmp_path / "memory.sqlite3"))
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
            "memory": {"importance": 0.8, "summary": "Bella greeted Mortimer."},
            "animation": "friendly_chat",
        },
    )
    result = ai_sims_server.chat(
        {
            "speaker": {"id": "bella", "name": "Bella"},
            "listener": {"id": "mortimer", "name": "Mortimer"},
            "message": "Hello",
            "event": {"type": "player_conversation", "source": "test"},
            "available_actions": ["friendly_chat"],
        }
    )

    with open_db(core_db) as conn:
        before = ai_sims_server.empneon_state.relevant_memories(
            conn, "bella", "greeted Mortimer"
        )
    assert "Bella greeted Mortimer." not in {item["summary"] for item in before}

    ai_sims_server.confirm_dialogue_delivery(
        {"decision_id": result["decision_id"], "status": "displayed"}
    )

    with open_db(core_db) as conn:
        after = ai_sims_server.empneon_state.relevant_memories(
            conn, "bella", "greeted Mortimer"
        )
    assert "Bella greeted Mortimer." in {item["summary"] for item in after}


def test_dialogue_delivery_records_experience_and_empneon_trust_once(
    tmp_path, monkeypatch
) -> None:
    core_db = str(tmp_path / "core.sqlite3")
    monkeypatch.setattr(ai_sims_server, "CORE_DB_PATH", core_db)
    monkeypatch.setattr(ai_sims_server, "DB_PATH", str(tmp_path / "memory.sqlite3"))
    monkeypatch.setattr(ai_sims_server, "ACTIVE_DB_PATH", None)
    monkeypatch.setattr(
        ai_sims_server.HERMES,
        "dialogue",
        lambda _payload, _context: {
            "dialogue": "I hear you.",
            "emotion": "warm",
            "intent": "reassure",
            "relationship": {
                "friendship_delta": 0,
                "romance_delta": 0,
                "trust_delta": 1,
            },
            "memory": {"importance": 0.8, "summary": "Karmine reassured Bernard."},
            "animation": "friendly_chat",
        },
    )
    result = ai_sims_server.chat(
        {
            "speaker": {"id": "karmine", "name": "Karmine"},
            "listener": {"id": "bernard", "name": "Bernard"},
            "message": "Can I trust you?",
            "event": {"type": "player_conversation", "source": "test"},
            "available_actions": ["friendly_chat"],
        }
    )
    decision_id = result["decision_id"]

    delivered = ai_sims_server.confirm_dialogue_delivery(
        {"decision_id": decision_id, "status": "displayed"}
    )
    assert delivered == {"decision_id": decision_id, "status": "displayed"}

    with open_db(core_db) as conn:
        proposal = ActionRecordStore(conn).get_proposal(decision_id)
        relationship = RelationshipStore(conn).get("karmine", "bernard")
        observations = len(ObservationStore(conn).get_for_agent("karmine"))
    assert proposal is not None
    assert relationship is not None and relationship.trust == pytest.approx(0.51)
    assert observations == 1
    assert ai_sims_server.confirm_dialogue_delivery(
        {"decision_id": decision_id, "status": "displayed"}
    ) == {"decision_id": decision_id, "status": "already_displayed"}


def test_dialogue_delivery_closes_none_action_without_native_changes(
    tmp_path, monkeypatch
) -> None:
    core_db = str(tmp_path / "core.sqlite3")
    monkeypatch.setattr(ai_sims_server, "CORE_DB_PATH", core_db)
    decision = Decision(
        "karmine",
        "respond",
        target_id="bernard",
        state_changes=(StateDelta("dialogue", "set", "I hear you."),),
    )
    with open_db(core_db) as conn:
        ai_sims_server.empneon_state.sync_sim(conn, {"id": "karmine", "name": "Karmine"})
        ai_sims_server.empneon_state.sync_sim(conn, {"id": "bernard", "name": "Bernard"})
        event = Event("delivered turn", ["karmine", "bernard"])
        ai_sims_server.empneon_state.record_pending_event(conn, event)
        ActionRecordStore(conn).propose(event.id, decision, "none")

    ai_sims_server.confirm_dialogue_delivery(
        {"decision_id": decision.id, "status": "displayed"}
    )

    with open_db(core_db) as conn:
        record = ActionRecordStore(conn).get(decision.id)
        relationship = RelationshipStore(conn).get("karmine", "bernard")
    assert record is not None and record.result.status == "succeeded"
    assert record.result.applied_changes == ()
    assert relationship is None


def test_dialogue_delivery_concurrent_acknowledgements_apply_effects_once(
    tmp_path, monkeypatch
) -> None:
    core_db = str(tmp_path / "core.sqlite3")
    monkeypatch.setattr(ai_sims_server, "CORE_DB_PATH", core_db)
    monkeypatch.setattr(ai_sims_server, "DB_PATH", str(tmp_path / "memory.sqlite3"))
    monkeypatch.setattr(ai_sims_server, "ACTIVE_DB_PATH", None)
    monkeypatch.setattr(
        ai_sims_server.HERMES,
        "dialogue",
        lambda _payload, _context: {
            "dialogue": "I hear you.",
            "emotion": "warm",
            "intent": "reassure",
            "relationship": {
                "friendship_delta": 0,
                "romance_delta": 0,
                "trust_delta": 1,
            },
            "memory": {"importance": 0.8, "summary": "Karmine reassured Bernard."},
            "animation": "friendly_chat",
        },
    )
    result = ai_sims_server.chat(
        {
            "speaker": {"id": "karmine", "name": "Karmine"},
            "listener": {"id": "bernard", "name": "Bernard"},
            "message": "Can I trust you?",
            "event": {"type": "player_conversation", "source": "test"},
            "available_actions": ["friendly_chat"],
        }
    )
    barrier = threading.Barrier(2)
    responses = []
    errors = []

    def acknowledge() -> None:
        try:
            barrier.wait()
            responses.append(
                ai_sims_server.confirm_dialogue_delivery(
                    {"decision_id": result["decision_id"], "status": "displayed"}
                )
            )
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=acknowledge) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert sorted(response["status"] for response in responses) == [
        "already_displayed",
        "displayed",
    ]
    with open_db(core_db) as conn:
        relationship = RelationshipStore(conn).get("karmine", "bernard")
        observations = ObservationStore(conn).get_for_agent("karmine")
    assert relationship is not None and relationship.trust == pytest.approx(0.51)
    assert len(observations) == 1


def test_dialogue_delivery_retry_rolls_back_failed_none_closure(
    tmp_path, monkeypatch
) -> None:
    core_db = str(tmp_path / "core.sqlite3")
    monkeypatch.setattr(ai_sims_server, "CORE_DB_PATH", core_db)
    decision = Decision(
        "karmine",
        "respond",
        target_id="bernard",
        state_changes=(
            StateDelta("dialogue", "set", "I hear you."),
            StateDelta("relationship.trust", "increment", 1),
        ),
    )
    with open_db(core_db) as conn:
        ai_sims_server.empneon_state.sync_sim(conn, {"id": "karmine", "name": "Karmine"})
        ai_sims_server.empneon_state.sync_sim(conn, {"id": "bernard", "name": "Bernard"})
        event = Event("delivered turn", ["karmine", "bernard"])
        ai_sims_server.empneon_state.record_pending_event(conn, event)
        ActionRecordStore(conn).propose(event.id, decision, "none")

    original_confirm = ActionRecordStore.confirm

    def interrupt_closure(self, result, adapter_action, **kwargs):
        raise RuntimeError("interrupted none closure")

    monkeypatch.setattr(ActionRecordStore, "confirm", interrupt_closure)
    with pytest.raises(RuntimeError, match="interrupted none closure"):
        ai_sims_server.confirm_dialogue_delivery(
            {"decision_id": decision.id, "status": "displayed"}
        )

    with open_db(core_db) as conn:
        assert DocumentMemoryStore(conn).get(
            "thesims4.dialogue-delivery", decision.id
        ) is None
        assert ActionRecordStore(conn).get_proposal(decision.id) is not None
        assert ActionRecordStore(conn).get(decision.id) is None
        assert RelationshipStore(conn).get("karmine", "bernard") is None
        assert ObservationStore(conn).get_for_agent("karmine") == []

    monkeypatch.setattr(ActionRecordStore, "confirm", original_confirm)
    assert ai_sims_server.confirm_dialogue_delivery(
        {"decision_id": decision.id, "status": "displayed"}
    ) == {"decision_id": decision.id, "status": "displayed"}
    with open_db(core_db) as conn:
        relationship = RelationshipStore(conn).get("karmine", "bernard")
        assert relationship is not None and relationship.trust == pytest.approx(0.51)
        assert len(ObservationStore(conn).get_for_agent("karmine")) == 1
        record = ActionRecordStore(conn).get(decision.id)
        assert record is not None and record.result.applied_changes == ()


def test_relationship_source_diagnostic_separates_native_and_empneon(tmp_path) -> None:
    with open_db(tmp_path / "core.sqlite3") as conn:
        ai_sims_server.empneon_state.sync_sim(conn, {"id": "karmine", "name": "Karmine"})
        ai_sims_server.empneon_state.sync_sim(conn, {"id": "bernard", "name": "Bernard"})
        RelationshipStore(conn).set(
            Relationship("karmine", "bernard", "acquaintance", trust=0.51)
        )
        save_agent_state(
            conn,
            AgentStateSnapshot(
                1,
                "sims4",
                "karmine",
                relationships={"bernard": {"affinity": 0.07, "romance": 0.12}},
            ),
        )

        diagnostic = ai_sims_server.empneon_state.relationship_diagnostic(
            conn, "karmine", "bernard"
        )

    assert diagnostic == {
        "direction": {"source_id": "karmine", "target_id": "bernard"},
        "native": {"friendship": 7, "romance": 12},
        "empneon": {"trust": 51},
    }


def test_adapter_memory_is_stored_by_core(tmp_path, monkeypatch) -> None:
    core_db = str(tmp_path / "core.sqlite3")
    legacy_db = str(tmp_path / "legacy.sqlite3")
    monkeypatch.setattr(ai_sims_server, "CORE_DB_PATH", core_db)
    monkeypatch.setattr(ai_sims_server, "DB_PATH", legacy_db)
    monkeypatch.setattr(ai_sims_server, "ACTIVE_DB_PATH", None)

    ai_sims_server.add_memory("bella", "mortimer", "A greeting", 0.8)

    with open_db(core_db) as conn:
        documents = DocumentMemoryStore(conn).list("thesims4.memory")
        memories = ai_sims_server.empneon_state.relevant_memories(
            conn, "bella", "greeting"
        )
    assert documents == []
    assert [memory["summary"] for memory in memories] == ["A greeting"]
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

    with open_db(core_db) as conn:
        assert ai_sims_server.empneon_state.import_legacy_adapter(conn, legacy_db) is True
        memories = ai_sims_server.empneon_state.relevant_memories(
            conn, "bella", "Legacy"
        )
        assert DocumentMemoryStore(conn).list("thesims4.memory") == []
    assert [item["summary"] for item in memories] == ["Legacy"]


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


def test_diagnostics_sim_returns_canonical_state_without_secrets(
    tmp_path, monkeypatch
) -> None:
    database = str(tmp_path / "memory.db")
    monkeypatch.setattr(ai_sims_server, "CORE_DB_PATH", database)
    with open_db(database) as conn:
        ai_sims_server.empneon_state.sync_sim(
            conn, {"id": "bella", "name": "Bella", "traits": ["Good"]}
        )
    handler = ai_sims_server.Handler.__new__(ai_sims_server.Handler)
    handler.path = "/diagnostics/sim?sim_id=bella"
    responses = []
    monkeypatch.setattr(
        handler, "send_json", lambda status, body: responses.append((status, body))
    )

    handler.do_GET()

    status, body = responses[0]
    assert status == 200
    assert body["agent"]["name"] == "Bella"
    assert "api_key" not in json.dumps(body).casefold()


def test_diagnostics_require_identifiers_and_report_missing_records(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(ai_sims_server, "CORE_DB_PATH", str(tmp_path / "memory.db"))
    for path, expected in (
        ("/diagnostics/sim", 400),
        ("/diagnostics/replay?decision_id=missing", 404),
    ):
        handler = ai_sims_server.Handler.__new__(ai_sims_server.Handler)
        handler.path = path
        responses = []
        monkeypatch.setattr(
            handler, "send_json", lambda status, body: responses.append((status, body))
        )
        handler.do_GET()
        assert responses[0][0] == expected


def test_identity_import_route_rejects_non_object(monkeypatch) -> None:
    handler = ai_sims_server.Handler.__new__(ai_sims_server.Handler)
    handler.path = "/identity/import"
    responses = []
    monkeypatch.setattr(handler, "read_json", lambda: [])
    monkeypatch.setattr(
        handler, "send_json", lambda status, body: responses.append((status, body))
    )

    handler.do_POST()

    assert responses[0][0] == 400
