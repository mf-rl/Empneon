from empneon.core.contracts import AgentStateSnapshot
from empneon.core.state import load_agent_state, save_agent_state
from empneon.db.connection import open_db


def test_latest_agent_state_replaces_temporary_native_state(tmp_path) -> None:
    path = tmp_path / "state.sqlite3"
    first = AgentStateSnapshot.from_mapping(
        {
            "schema_version": 1,
            "adapter": "test",
            "agent_id": "alice",
            "effects": [{"kind": "buff", "label": "wet"}],
            "native": {"buffs": ["wet"]},
        }
    )
    second = AgentStateSnapshot.from_mapping(
        {
            "schema_version": 1,
            "adapter": "test",
            "agent_id": "alice",
            "effects": [],
            "native": {"buffs": []},
        }
    )

    with open_db(path) as conn:
        save_agent_state(conn, first)
        save_agent_state(conn, second)
        loaded = load_agent_state(conn, "alice")

    assert loaded == second
