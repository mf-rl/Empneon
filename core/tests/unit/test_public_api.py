import tomllib
from pathlib import Path

import empneon


def test_supported_api_and_version_source() -> None:
    expected = {
        "ActionRecordStore",
        "ActionResult",
        "AgentStateSnapshot",
        "CognitiveRequest",
        "CognitiveRuntime",
        "Decision",
        "GameAdapter",
        "ResourceBudget",
        "ResourceEstimate",
        "ResourceGovernor",
        "StateDelta",
        "UsageStore",
        "WorldEvent",
        "agent_timeline",
        "db_session",
        "load_agent_state",
        "open_db",
        "replay_action_record",
        "save_agent_state",
    }
    assert empneon.__version__ == "0.3.0"
    assert set(empneon.__all__) == expected
    assert all(hasattr(empneon, name) for name in expected)

    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["dynamic"] == ["version"]
    assert pyproject["tool"]["setuptools"]["dynamic"]["version"] == {
        "attr": "empneon.__version__"
    }
