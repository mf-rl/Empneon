import asyncio
import logging
from pathlib import Path

import pytest

from empneon.core.clod import resolve_clod1, resolve_with_fallback
from empneon.core.contracts import CognitiveRequest, Decision, WorldEvent
from empneon.db.connection import open_db
from empneon.providers.llm import (
    GenerationRequest,
    LMStudioProvider,
    Message,
    OpenAICompatibleProvider,
    ProviderError,
)

SECRET_PROMPT = "super-secret-player-message"
SECRET_KEY = "sk-secret-key-123"
UNREACHABLE = "http://127.0.0.1:9/v1"


def test_library_installs_null_handler_only() -> None:
    handlers = logging.getLogger("empneon").handlers
    assert any(isinstance(handler, logging.NullHandler) for handler in handlers)


def test_fallback_logs_reason_without_exception_text(caplog: pytest.LogCaptureFixture) -> None:
    request = CognitiveRequest("alice", 3, WorldEvent("event", id="event-1"))

    async def failed(_: CognitiveRequest) -> Decision:
        raise ProviderError(SECRET_PROMPT)

    with caplog.at_level(logging.WARNING, logger="empneon"):
        asyncio.run(resolve_with_fallback(request, failed))

    assert "provider_error" in caplog.text
    assert SECRET_PROMPT not in caplog.text


def test_no_fallback_log_on_success(caplog: pytest.LogCaptureFixture) -> None:
    request = CognitiveRequest("alice", 3, WorldEvent("event", id="event-1"))

    async def succeeds(current: CognitiveRequest) -> Decision:
        return resolve_clod1(current)

    with caplog.at_level(logging.DEBUG, logger="empneon"):
        asyncio.run(resolve_with_fallback(request, succeeds))
    assert caplog.text == ""


@pytest.mark.parametrize(
    "provider",
    [
        LMStudioProvider(UNREACHABLE, "m", timeout_seconds=1),
        OpenAICompatibleProvider(UNREACHABLE, "m", api_key=SECRET_KEY, timeout_seconds=1),
    ],
)
def test_provider_failure_logs_type_not_content(
    provider: LMStudioProvider | OpenAICompatibleProvider, caplog: pytest.LogCaptureFixture
) -> None:
    request = GenerationRequest((Message("user", SECRET_PROMPT),), max_tokens=8)
    with caplog.at_level(logging.DEBUG, logger="empneon"):
        with pytest.raises(ProviderError):
            asyncio.run(provider.generate(request))
        assert asyncio.run(provider.health_check()) is False

    assert "generation failed" in caplog.text
    assert SECRET_PROMPT not in caplog.text
    assert SECRET_KEY not in caplog.text


def test_migration_is_logged(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="empneon.db"):
        open_db(tmp_path / "fresh.sqlite3").close()
    assert "migrated" in caplog.text

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="empneon.db"):
        open_db(tmp_path / "fresh.sqlite3").close()
    assert caplog.text == ""
