"""Game-independent adapter interface."""

from typing import Protocol

from empneon.core.contracts import ActionResult, Decision, WorldEvent


class GameAdapter(Protocol):
    """Collect generic events and execute validated decisions for one game."""

    def observe(self) -> tuple[WorldEvent, ...]: ...

    def execute(self, decision: Decision, /) -> ActionResult: ...
