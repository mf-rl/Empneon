import asyncio
import json
from unittest.mock import patch

import pytest

from empneon.providers.llm import (
    GenerationRequest,
    Message,
    OpenAICompatibleProvider,
    ProviderError,
)


class Response:
    def __init__(self, data: dict[str, object]) -> None:
        self.data = data

    def __enter__(self) -> "Response":
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def read(self) -> bytes:
        return json.dumps(self.data).encode()


def test_generates_with_openai_compatible_chat_endpoint() -> None:
    provider = OpenAICompatibleProvider("http://localhost:1234/v1", "local-model", "key")
    result_data = {
        "choices": [{"message": {"content": "hello"}}],
        "usage": {"prompt_tokens": 4, "completion_tokens": 1},
    }

    with patch("urllib.request.urlopen", return_value=Response(result_data)) as urlopen:
        result = asyncio.run(
            provider.generate(GenerationRequest((Message("user", "Hi"),), max_tokens=20))
        )

    request = urlopen.call_args.args[0]
    assert request.full_url == "http://localhost:1234/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer key"
    assert json.loads(request.data)["model"] == "local-model"
    assert result.content == "hello"
    assert result.prompt_tokens == 4
    assert result.completion_tokens == 1


def test_health_check_returns_false_when_endpoint_is_unavailable() -> None:
    provider = OpenAICompatibleProvider("http://localhost:1234/v1", "local-model")

    with patch("urllib.request.urlopen", side_effect=OSError):
        assert asyncio.run(provider.health_check()) is False


@pytest.mark.parametrize("failure", [OSError(), TimeoutError(), MemoryError()])
def test_generation_normalizes_provider_failures(failure: Exception) -> None:
    provider = OpenAICompatibleProvider("http://localhost:1234/v1", "local-model")

    with patch("urllib.request.urlopen", side_effect=failure):
        with pytest.raises(ProviderError):
            asyncio.run(
                provider.generate(GenerationRequest((Message("user", "Hi"),), max_tokens=20))
            )
