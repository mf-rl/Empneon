"""Shared HTTP transport and failure handling for provider implementations (internal)."""

import asyncio
import json
import logging
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from typing import TypeVar

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


def request_json(
    url: str,
    *,
    body: Mapping[str, object] | None = None,
    headers: Mapping[str, str] | None = None,
    timeout: float,
) -> object:
    """POST `body` (or GET when None) and return the decoded JSON response."""
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST" if body is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def _status(exc: BaseException) -> int | None:
    return exc.code if isinstance(exc, urllib.error.HTTPError) else None


async def guarded_generate(label: str, call: Callable[[], _T]) -> _T:
    """Run a blocking provider call in a thread and map transport failures to ProviderError.

    Only the exception type and HTTP status are logged or exposed, never message text.
    """
    try:
        return await asyncio.to_thread(call)
    except _TRANSPORT_ERRORS as exc:
        status = _status(exc)
        _log.warning("%s generation failed: %s status=%s", label, type(exc).__name__, status)
        raise ProviderError(f"{label} generation failed", status=status) from exc


async def guarded_health(label: str, call: Callable[[], object]) -> bool:
    """Return whether a blocking health probe succeeds."""
    try:
        await asyncio.to_thread(call)
    except _TRANSPORT_ERRORS as exc:
        _log.debug("%s health check failed: %s status=%s", label, type(exc).__name__, _status(exc))
        return False
    return True
