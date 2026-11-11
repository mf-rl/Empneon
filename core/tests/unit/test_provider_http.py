import asyncio
import io
import logging
import urllib.error
from unittest.mock import patch

import pytest

from empneon.providers.llm import (
    GenerationRequest,
    LMStudioProvider,
    Message,
    OpenAICompatibleProvider,
    ProviderError,
)
from empneon.providers.llm._http import chat_completion_body

REQUEST = GenerationRequest((Message("user", "hi"),), max_tokens=8)
BODY = b"upstream-body-with-private-details"


def _http_error(status: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("http://x", status, "err", {}, io.BytesIO(BODY))  # type: ignore[arg-type]


def test_api_key_is_not_in_repr() -> None:
    provider = OpenAICompatibleProvider("http://x/v1", "m", api_key="sk-very-secret")
    assert "sk-very-secret" not in repr(provider)
    assert provider.api_key == "sk-very-secret"


@pytest.mark.parametrize(
    "provider", [OpenAICompatibleProvider("http://x/v1", "m"), LMStudioProvider("http://x", "m")]
)
def test_http_status_is_exposed_and_logged_without_body(
    provider: OpenAICompatibleProvider | LMStudioProvider, caplog: pytest.LogCaptureFixture
) -> None:
    with patch("urllib.request.urlopen", side_effect=_http_error(429)):
        with caplog.at_level(logging.WARNING, logger="empneon"):
            with pytest.raises(ProviderError) as info:
                asyncio.run(provider.generate(REQUEST))

    assert info.value.status == 429
    assert "429" in caplog.text
    assert BODY.decode() not in caplog.text


def test_non_http_failure_has_no_status() -> None:
    provider = OpenAICompatibleProvider("http://x/v1", "m")
    with patch("urllib.request.urlopen", side_effect=OSError):
        with pytest.raises(ProviderError) as info:
            asyncio.run(provider.generate(REQUEST))
    assert info.value.status is None


def test_chat_completion_body_includes_schema_only_when_requested() -> None:
    plain = chat_completion_body("m", REQUEST)
    assert plain == {
        "model": "m",
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 8,
        "temperature": 0.7,
    }
    schema = {"type": "object"}
    structured = chat_completion_body(
        "m", GenerationRequest(REQUEST.messages, 8, schema=schema)
    )
    assert structured["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "response", "schema": schema},
    }
