"""Shared HTTP transport and failure handling for provider implementations (internal)."""

import asyncio
import contextlib
import http.client
import json
import logging
import urllib.error
import urllib.request
from collections.abc import AsyncIterator, Callable, Mapping
from typing import Any, TypeVar, cast
from urllib.parse import urlsplit

from empneon.providers.llm.base import GenerationRequest, ProviderError

_log = logging.getLogger(__name__)
_T = TypeVar("_T")
_TRANSPORT_ERRORS = (MemoryError, OSError, ValueError, KeyError, IndexError, TypeError)


def chat_completion_body(model: str, request: GenerationRequest) -> dict[str, object]:
    """Build an OpenAI-style chat-completions body, adding a JSON schema when requested."""
    body: dict[str, object] = {
        "model": model,
        "messages": [
            {"role": message.role, "content": message.content} for message in request.messages
        ],
        "max_tokens": request.max_tokens,
        "temperature": request.temperature,
    }
    if request.schema is not None:
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "response", "schema": request.schema},
        }
    return body


def delta_text(event: object) -> str:
    """Text delta of one streamed chat-completions chunk (role/usage-only chunks have none)."""
    choices = cast(dict[str, Any], event)["choices"]
    if not choices:
        return ""
    delta = choices[0]["delta"]
    if not isinstance(delta, dict):
        raise ValueError("streamed delta must be an object")
    content = delta.get("content")
    return content if isinstance(content, str) else ""


def _build_request(
    url: str, body: Mapping[str, object] | None, headers: Mapping[str, str] | None
) -> urllib.request.Request:
    if urlsplit(url).scheme.lower() not in {"http", "https"}:
        raise ValueError("provider URL must use http or https")
    return urllib.request.Request(  # noqa: S310 - scheme restricted to http(s) above
        url,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST" if body is not None else "GET",
    )


def request_json(
    url: str,
    *,
    body: Mapping[str, object] | None = None,
    headers: Mapping[str, str] | None = None,
    timeout: float,
) -> object:
    """POST `body` (or GET when None) and return the decoded JSON response.

    Only `http` and `https` URLs are accepted, so a misconfigured endpoint cannot make
    `urlopen` read a `file:` path or speak another scheme.
    """
    request = _build_request(url, body, headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - http(s) only
        return json.loads(response.read())


def open_stream(
    url: str,
    *,
    body: Mapping[str, object],
    headers: Mapping[str, str] | None = None,
    timeout: float,
) -> Any:
    """POST `body` and return the open response, which the caller must close (http(s) only)."""
    request = _build_request(url, body, headers)
    return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310 - http(s) only


def _status(exc: BaseException) -> int | None:
    return exc.code if isinstance(exc, urllib.error.HTTPError) else None


def _retry_after(exc: BaseException) -> float | None:
    """Return a non-negative `Retry-After` in seconds; HTTP-date values are ignored."""
    if not isinstance(exc, urllib.error.HTTPError):
        return None
    value = str(exc.headers.get("Retry-After", "") if exc.headers else "").strip()
    return float(value) if value.isdecimal() else None


def _is_transport(exc: BaseException) -> bool:
    """Connection-level failure: an OS error that is not an HTTP response."""
    return isinstance(exc, OSError) and not isinstance(exc, urllib.error.HTTPError)


def _provider_error(
    label: str, operation: str, exc: BaseException, *, transport: bool | None = None
) -> ProviderError:
    status = _status(exc)
    _log.warning("%s %s failed: %s status=%s", label, operation, type(exc).__name__, status)
    return ProviderError(
        f"{label} {operation} failed",
        status=status,
        retry_after=_retry_after(exc),
        transport=_is_transport(exc) if transport is None else transport,
    )


async def guarded_generate(
    label: str, call: Callable[[], _T], *, operation: str = "generation"
) -> _T:
    """Run a blocking provider call in a thread and map transport failures to ProviderError.

    Only the exception type and HTTP status are logged or exposed, never message text.
    """
    try:
        return await asyncio.to_thread(call)
    except _TRANSPORT_ERRORS as exc:
        raise _provider_error(label, operation, exc) from exc


async def guarded_health(label: str, call: Callable[[], object]) -> bool:
    """Return whether a blocking health probe succeeds."""
    try:
        await asyncio.to_thread(call)
    except _TRANSPORT_ERRORS as exc:
        _log.debug("%s health check failed: %s status=%s", label, type(exc).__name__, _status(exc))
        return False
    return True


def _sse_data(line: bytes) -> str | None:
    """Return the payload of an SSE `data:` line, or None for blanks, comments and other fields."""
    text = line.decode("utf-8").strip()
    if not text.startswith("data:"):
        return None
    return text[len("data:") :].strip()


async def guarded_stream(
    label: str,
    open_call: Callable[[], Any],
    extract: Callable[[object], str],
) -> AsyncIterator[str]:
    """Stream text from a blocking SSE response, mapping failures to ProviderError.

    `open_call` returns the open response. `extract` turns each decoded JSON event into its text
    delta (empty text is skipped). The stream ends at `data: [DONE]`. Blocking reads run in a
    thread, the response is always closed, and only the exception type and HTTP status are logged,
    never chunk content.
    """
    stack = contextlib.ExitStack()
    try:
        try:
            response = await asyncio.to_thread(open_call)
            stack.enter_context(response)
            lines = iter(response)
        except _TRANSPORT_ERRORS as exc:
            raise _provider_error(label, "stream", exc) from exc
        while True:
            try:
                line = await asyncio.to_thread(next, lines, None)
                if line is None:
                    return
                data = _sse_data(line)
                if data is None:
                    continue
                if data == "[DONE]":
                    return
                text = extract(json.loads(data))
            except _TRANSPORT_ERRORS as exc:
                raise _provider_error(label, "stream", exc) from exc
            except http.client.HTTPException as exc:
                # A truncated chunked body: the connection broke mid-stream, so it is transient.
                raise _provider_error(label, "stream", exc, transport=True) from exc
            if text:
                yield text
    finally:
        await asyncio.to_thread(stack.close)
