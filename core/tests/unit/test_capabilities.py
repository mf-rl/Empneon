import pytest

from empneon.core.capabilities import validate_decision
from empneon.core.contracts import AgentStateSnapshot, Decision, StateDelta


def decision(intent: str = "greet", *paths: str) -> Decision:
    return Decision("a", intent, state_changes=tuple(StateDelta(p, "set", "x") for p in paths))


def test_no_capabilities_or_keys_allow_everything() -> None:
    assert validate_decision(decision("anything", "any.path"), None) is None
    assert validate_decision(decision("anything", "any.path"), {}) is None
    assert validate_decision(decision(), {"actions": ["friendly_chat"]}) is None


def test_intents_restrict_when_published() -> None:
    caps = {"intents": ["greet", "acknowledge"]}
    assert validate_decision(decision("greet"), caps) is None
    assert validate_decision(decision("insult"), caps) == "intent not supported: insult"


def test_state_path_roots_restrict_when_published() -> None:
    caps = {"state_paths": ["dialogue", "relationship"]}
    assert validate_decision(decision("greet", "dialogue"), caps) is None
    assert validate_decision(decision("greet", "relationship.strength"), caps) is None
    assert (
        validate_decision(decision("greet", "dialogue", "inventory.gold"), caps)
        == "state path not supported: inventory.gold"
    )


def test_prefix_lookalikes_do_not_match_a_root() -> None:
    caps = {"state_paths": ["relationship"]}
    assert validate_decision(decision("greet", "relationships"), caps) is not None


def test_empty_lists_allow_nothing() -> None:
    assert validate_decision(decision("greet"), {"intents": []}) is not None
    assert validate_decision(decision("greet", "dialogue"), {"state_paths": []}) is not None
    assert validate_decision(decision("greet"), {"state_paths": []}) is None


def test_intent_is_checked_before_paths_and_first_bad_path_is_reported() -> None:
    caps = {"intents": ["greet"], "state_paths": ["dialogue"]}
    assert validate_decision(decision("insult", "bad.one"), caps) == "intent not supported: insult"
    assert validate_decision(decision("greet", "bad.one", "bad.two"), caps) == (
        "state path not supported: bad.one"
    )


@pytest.mark.parametrize("key", ["intents", "state_paths"])
@pytest.mark.parametrize("value", ["greet-and-more", {"greet": 1}, ["ok", 3], [""]])
def test_validate_decision_rejects_malformed_published_lists(key: str, value: object) -> None:
    with pytest.raises(ValueError, match=f"capabilities.{key}"):
        validate_decision(decision("greet", "dialogue"), {key: value})


def _snapshot(**capabilities: object) -> AgentStateSnapshot:
    return AgentStateSnapshot(1, "game", "a", capabilities=dict(capabilities))


@pytest.mark.parametrize("key", ["intents", "state_paths"])
@pytest.mark.parametrize("value", ["greet", {"greet": 1}, 5, ["ok", 3], ["ok", ""], ["  "]])
def test_snapshot_rejects_malformed_capability_lists(key: str, value: object) -> None:
    with pytest.raises(ValueError, match=f"capabilities.{key}"):
        _snapshot(**{key: value})


@pytest.mark.parametrize("key", ["intents", "state_paths"])
@pytest.mark.parametrize("value", [["a", "b"], ("a",), []])
def test_snapshot_accepts_well_formed_capability_lists(key: str, value: object) -> None:
    assert _snapshot(**{key: value}).capabilities[key] == value


def test_snapshot_with_only_actions_is_unchanged() -> None:
    assert _snapshot(actions=["friendly_chat", 3, None]).capabilities["actions"]
