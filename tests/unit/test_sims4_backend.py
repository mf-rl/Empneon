from empneon.core.identity.relationships import RelationshipStore
from empneon.db.connection import open_db
from poc.backend import ai_sims_server


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
    assert relationship is not None
    assert relationship.strength == 0.05
