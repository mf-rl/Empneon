import asyncio
import json
import logging
import urllib.error
from collections.abc import Iterator
from unittest.mock import patch

import pytest

from empneon.providers.llm import (
    GenerationRequest,
    LMStudioProvider,
    Message,
    ProviderError,
)

SECRET = "super-secret-lmstudio-text"
REQUEST = GenerationRequest((Message("user", "Hi"),), max_tokens=20)


def sse(delta: object) -> bytes:
    return b"data: " + json.dumps({"choices": [{"delta": delta}]}).encode() + b"\n"


class StreamResponse:
    """Fake urlopen response yielding SSE lines, optionally failing after them."""

    def __init__(self, lines: list[bytes], then: BaseException | None = None) -> None:
        self.lines = lines
        self.then = then
        self.closed = False

    def __enter__(self) -> "StreamResponse":
        return self

    def __exit__(self, *args: object) -> None:
        self.closed = True

    def __iter__(self) -> Iterator[bytes]:
        yield from self.lines
        if self.then is not None:
            raise self.then


def collect(provider: LMStudioProvider, request: GenerationRequest = REQUEST) -> list[str]:
    async def run() -> list[str]:
        return [chunk async for chunk in provider.stream(request)]

    return asyncio.run(run())


def provider(model: str = "qwen") -> LMStudioProvider:
    return LMStudioProvider("http://localhost:1234/api/v1", model)


def test_streams_deltas_from_the_openai_compatible_endpoint() -> None:
    response = StreamResponse(
        [
            sse({"role": "assistant"}),
            sse({"content": "Hel"}),
            sse({"content": "lo"}),
            b"data: [DONE]\n",
        ]
    )
    with patch("urllib.request.urlopen", return_value=response) as urlopen:
        chunks = collect(provider())

    request = urlopen.call_args.args[0]
    assert request.full_url == "http://localhost:1234/v1/chat/completions"
    body = json.loads(request.data)
    assert body["stream"] is True
    assert body["model"] == "qwen"
    assert chunks == ["Hel", "lo"]
    assert response.closed


def test_streaming_keeps_the_json_schema_request() -> None:
    schema = {"type": "object", "properties": {}}
    request = GenerationRequest((Message("user", "Hi"),), max_tokens=20, schema=schema)
    response = StreamResponse([sse({"content": "{}"}), b"data: [DONE]\n"])
    with patch("urllib.request.urlopen", return_value=response) as urlopen:
        collect(provider(), request)

    assert "response_format" in json.loads(urlopen.call_args.args[0].data)


def test_default_model_is_resolved_before_streaming() -> None:
    models = StreamResponse([])
    models.read = lambda: json.dumps(  # type: ignore[attr-defined]
        {"models": [{"key": "k", "loaded_instances": [{"id": "loaded-id"}]}]}
    ).encode()
    stream = StreamResponse([sse({"content": "x"}), b"data: [DONE]\n"])
    with patch("urllib.request.urlopen", side_effect=[models, stream]) as urlopen:
        collect(provider("local-model"))

    assert urlopen.call_args_list[0].args[0].full_url == "http://localhost:1234/api/v1/models"
    assert json.loads(urlopen.call_args_list[1].args[0].data)["model"] == "loaded-id"


def test_advertises_streaming_capability() -> None:
    capabilities = provider().capabilities
    assert capabilities.streaming
    assert capabilities.structured_output
    assert capabilities.local


def test_open_failure_maps_to_provider_error_with_status() -> None:
    error = urllib.error.HTTPError("http://x", 503, "unavailable", {}, None)  # type: ignore[arg-type]
    with (
        patch("urllib.request.urlopen", side_effect=error),
        pytest.raises(ProviderError) as caught,
    ):
        collect(provider())
    assert caught.value.status == 503


def test_mid_stream_failure_keeps_earlier_chunks() -> None:
    response = StreamResponse([sse({"content": "a"})], then=ConnectionResetError("boom"))
    seen: list[str] = []

    async def run() -> None:
        async for chunk in provider().stream(REQUEST):
            seen.append(chunk)

    with (
        patch("urllib.request.urlopen", return_value=response),
        pytest.raises(ProviderError) as caught,
    ):
        asyncio.run(run())
    assert seen == ["a"]
    assert caught.value.transport is True


def test_stream_never_logs_chunk_content(caplog: pytest.LogCaptureFixture) -> None:
    response = StreamResponse([sse({"content": SECRET})], then=ConnectionResetError(SECRET))
    caplog.set_level(logging.DEBUG)
    with patch("urllib.request.urlopen", return_value=response), pytest.raises(ProviderError):
        collect(provider())
    assert SECRET not in caplog.text


def test_abandoned_stream_closes_the_response() -> None:
    response = StreamResponse([sse({"content": "a"}), sse({"content": "b"})])

    async def run() -> None:
        stream = provider().stream(REQUEST)
        assert await anext(stream) == "a"
        await stream.aclose()  # type: ignore[attr-defined]

    with patch("urllib.request.urlopen", return_value=response):
        asyncio.run(run())
    assert response.closed
