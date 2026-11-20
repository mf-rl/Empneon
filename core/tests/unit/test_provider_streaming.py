import asyncio
import http.client
import json
import logging
import urllib.error
from collections.abc import Iterator
from unittest.mock import patch

import pytest

from empneon.providers.llm import (
    GenerationRequest,
    Message,
    OpenAICompatibleProvider,
    ProviderError,
)

SECRET = "super-secret-streamed-text"
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


def collect(provider: OpenAICompatibleProvider) -> list[str]:
    async def run() -> list[str]:
        return [chunk async for chunk in provider.stream(REQUEST)]

    return asyncio.run(run())


def provider() -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider("http://localhost:1234/v1", "local-model", "key")


def test_streams_text_deltas_and_requests_streaming() -> None:
    response = StreamResponse(
        [
            sse({"role": "assistant"}),
            b"\n",
            b": keep-alive\n",
            sse({"content": "Hel"}),
            sse({"content": ""}),
            b'data: {"choices": []}\n',
            sse({"content": "lo"}),
            b"data: [DONE]\n",
            sse({"content": "ignored"}),
        ]
    )
    with patch("urllib.request.urlopen", return_value=response) as urlopen:
        chunks = collect(provider())

    request = urlopen.call_args.args[0]
    assert request.full_url == "http://localhost:1234/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer key"
    assert json.loads(request.data)["stream"] is True
    assert chunks == ["Hel", "lo"]
    assert response.closed


def test_advertises_streaming_capability() -> None:
    assert provider().capabilities.streaming is True


def test_open_failure_maps_to_provider_error_with_status() -> None:
    error = urllib.error.HTTPError("http://x", 503, "unavailable", {"Retry-After": "2"}, None)  # type: ignore[arg-type]
    with patch("urllib.request.urlopen", side_effect=error), pytest.raises(ProviderError) as info:
            collect(provider())
    assert info.value.status == 503
    assert info.value.retry_after == 2.0


def test_mid_stream_failure_keeps_earlier_chunks_and_raises_transport_error() -> None:
    response = StreamResponse([sse({"content": "partial"})], then=ConnectionResetError())
    received: list[str] = []

    async def run() -> None:
        async for chunk in provider().stream(REQUEST):
            received.append(chunk)

    with (
        patch("urllib.request.urlopen", return_value=response),
        pytest.raises(ProviderError) as info,
    ):
        asyncio.run(run())
    assert received == ["partial"]
    assert info.value.transport is True
    assert response.closed


def test_malformed_chunk_raises_non_transient_provider_error() -> None:
    response = StreamResponse([sse({"content": "ok"}), b"data: {not json\n"])
    with (
        patch("urllib.request.urlopen", return_value=response),
        pytest.raises(ProviderError) as info,
    ):
        collect(provider())
    assert info.value.status is None
    assert info.value.transport is False


def test_stream_never_logs_chunk_content(caplog: pytest.LogCaptureFixture) -> None:
    response = StreamResponse([sse({"content": SECRET}), b"data: " + SECRET.encode() + b"\n"])
    with (
        caplog.at_level(logging.DEBUG),
        patch("urllib.request.urlopen", return_value=response),
        pytest.raises(ProviderError),
    ):
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


@pytest.mark.parametrize(
    "event",
    [{"choices": [{"delta": "text"}]}, {"choices": ["x"]}, {"choices": 5}, [1], {}],
)
def test_unexpected_event_shapes_raise_provider_error(event: object) -> None:
    response = StreamResponse([b"data: " + json.dumps(event).encode() + b"\n"])
    with (
        patch("urllib.request.urlopen", return_value=response),
        pytest.raises(ProviderError) as info,
    ):
        collect(provider())
    assert info.value.status is None
    assert info.value.transport is False


def test_truncated_chunked_body_is_a_transient_provider_error() -> None:
    response = StreamResponse([sse({"content": "a"})], then=http.client.IncompleteRead(b"x"))
    with (
        patch("urllib.request.urlopen", return_value=response),
        pytest.raises(ProviderError) as info,
    ):
        collect(provider())
    assert info.value.transport is True
