import re
import tomllib
from pathlib import Path

import empneon
import empneon.providers.llm as llm


def test_supported_api_and_version_source() -> None:
    expected = {
        "ActionRecordStore",
        "ActionResult",
        "AgentStateSnapshot",
        "Clod",
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
        "validate_decision",
    }
    assert re.fullmatch(r"\d+\.\d+\.\d+(?:[.-]?(?:a|b|rc|dev)\d*)?", empneon.__version__)
    assert set(empneon.__all__) == expected
    assert all(hasattr(empneon, name) for name in expected)

    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    assert pyproject["project"]["dynamic"] == ["version"]
    assert pyproject["tool"]["setuptools"]["dynamic"]["version"] == {
        "attr": "empneon.__version__"
    }


def test_package_advertises_inline_types() -> None:
    package_dir = Path(empneon.__file__).resolve().parent
    assert (package_dir / "py.typed").is_file()

    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    assert pyproject["tool"]["setuptools"]["package-data"]["empneon"] == ["py.typed"]


def test_streaming_names_are_public_provider_api() -> None:
    assert "StreamingLLMProvider" in llm.__all__
    assert llm.StreamingLLMProvider is not None
    # The non-streaming protocol is unchanged: custom providers need not implement `stream`.
    assert "stream" not in llm.LLMProvider.__dict__


def test_directors_names_are_a_supported_import_path() -> None:
    from empneon.core import directors

    assert set(directors.__all__) == {
        "Director",
        "DirectorView",
        "IdleCheckInDirector",
        "Opportunity",
        "run_directors",
        "to_request",
    }
    assert all(hasattr(directors, name) for name in directors.__all__)
    # Optional module: not part of the pinned top-level `empneon.__all__`.
    assert "run_directors" not in empneon.__all__
