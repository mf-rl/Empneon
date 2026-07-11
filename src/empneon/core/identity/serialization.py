"""Full agent identity export / import — portable JSON-serializable dict."""

import dataclasses
from dataclasses import dataclass
from typing import Any

from empneon.core.identity.emotions import EmotionalState, EmotionalStateStore
from empneon.core.identity.goals import Goal, GoalStore
from empneon.core.identity.models import Agent
from empneon.core.identity.personality import Personality, PersonalityStore
from empneon.core.identity.relationships import Relationship, RelationshipStore
from empneon.core.identity.store import AgentStore
from empneon.core.identity.voice import VoiceProfile, VoiceProfileStore

SERIALIZATION_VERSION = 1


@dataclass
class IdentityStores:
    agents: AgentStore
    personality: PersonalityStore
    relationships: RelationshipStore
    emotions: EmotionalStateStore
    goals: GoalStore
    voice: VoiceProfileStore


def export_agent(agent_id: str, stores: IdentityStores) -> dict[str, Any]:
    """Return a JSON-serializable snapshot of every identity layer for one agent."""
    agent = stores.agents.get(agent_id)
    if agent is None:
        raise ValueError(f"Agent {agent_id!r} not found")

    personality = stores.personality.get(agent_id)
    voice = stores.voice.get(agent_id)

    return {
        "version": SERIALIZATION_VERSION,
        "agent": dataclasses.asdict(agent),
        "personality": dataclasses.asdict(personality) if personality else None,
        "relationships": [dataclasses.asdict(r) for r in stores.relationships.get_all(agent_id)],
        "emotions": [dataclasses.asdict(e) for e in stores.emotions.get_all(agent_id)],
        "goals": [dataclasses.asdict(g) for g in stores.goals.get_all(agent_id)],
        "voice_profile": dataclasses.asdict(voice) if voice else None,
    }


def import_agent(data: dict[str, Any], stores: IdentityStores) -> Agent:
    """Write a previously exported snapshot into stores. Idempotent — safe to reimport."""
    if data.get("version") != SERIALIZATION_VERSION:
        raise ValueError(f"unsupported identity version: {data.get('version')!r}")
    agent = Agent(**data["agent"])
    if stores.agents.get(agent.id) is None:
        stores.agents.create(agent)
    else:
        stores.agents.update(agent)

    if data["personality"] is not None:
        stores.personality.set(Personality(**data["personality"]))

    for rel_data in data["relationships"]:
        stores.relationships.set(Relationship(**rel_data))

    for emo_data in data["emotions"]:
        stores.emotions.set(EmotionalState(**emo_data))

    for goal_data in data["goals"]:
        stores.goals.set(Goal(**goal_data))

    if data["voice_profile"] is not None:
        stores.voice.set(VoiceProfile(**data["voice_profile"]))

    return agent
