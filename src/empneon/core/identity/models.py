"""Agent identity dataclass — persistent character data independent of any LLM."""

import time
import uuid
from dataclasses import dataclass, field


@dataclass
class Agent:
    id: str
    name: str
    age: int | None = None
    occupation: str | None = None
    game_id: str | None = None
    adapter: str | None = None
    created_at: int = field(default_factory=lambda: int(time.time()))
    updated_at: int = field(default_factory=lambda: int(time.time()))

    @staticmethod
    def new(
        name: str,
        age: int | None = None,
        occupation: str | None = None,
        game_id: str | None = None,
        adapter: str | None = None,
    ) -> "Agent":
        now = int(time.time())
        return Agent(
            id=str(uuid.uuid4()),
            name=name,
            age=age,
            occupation=occupation,
            game_id=game_id,
            adapter=adapter,
            created_at=now,
            updated_at=now,
        )
