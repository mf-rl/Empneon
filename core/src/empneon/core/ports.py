"""Game-independent adapter interface."""

from collections.abc import Awaitable, Callable
from typing import Protocol

from empneon.core.contracts import ActionResult, CognitiveRequest, Decision, WorldEvent

Resolver = Callable[[CognitiveRequest], Awaitable[Decision]]


class GameAdapter(Protocol):
    """Collect generic events and execute validated decisions for one game."""

    def observe(self) -> tuple[WorldEvent, ...]: ...

    def execute(self, decision: Decision, /) -> ActionResult: ...
