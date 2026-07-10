# Empneon — Project Vision & Foundational Architecture

**Version:** 0.1 (Foundational Vision)

---

## Executive Summary

Empneon is an open-source Cognitive Operating System (Cognitive OS) for simulation games.

Its purpose is not to create better chatbots or NPC dialogue systems. Instead, Empneon provides a complete cognitive framework that enables persistent digital identities capable of thinking, remembering, learning, evolving, and interacting naturally within simulated worlds.

The first implementation target is **The Sims 4**, but the architecture is intentionally designed to be game-agnostic. The Sims 4 is merely the first adapter built on top of the framework.

Future adapters may include games such as InZOI, Skyrim, Fallout, Unity-based games, Unreal Engine games, Roblox experiences, Stardew Valley mods, and entirely new simulation games.

Empneon is therefore not a Sims mod.

It is a reusable AI cognition framework.

---

## The Core Philosophy

Existing AI NPC systems usually ask:

> "How can we make an NPC intelligent?"

Empneon asks a different question:

> "How can we make an entire simulated society computationally feasible while maintaining believable intelligence?"

This distinction defines the entire architecture.

---

## The Main Innovation

The most important innovation is the separation between **Identity** and **Consciousness**.

Traditional AI NPC systems usually treat an NPC as the current LLM prompt.

Empneon does not.

Instead, every character permanently exists as structured data.

A character owns:

- Identity
- Personality
- Relationships
- Memories
- Goals
- Knowledge
- Emotional State
- Voice Profile
- Preferences
- Behavioral Rules

These are stored persistently in databases and structured data.

The Large Language Model is **not** the character.

The LLM temporarily provides consciousness.

When reasoning finishes, consciousness disappears.

Identity remains.

This allows rich AI characters without requiring continuous LLM execution.

---

## Consciousness is a Scheduled Resource

This is one of the defining concepts of Empneon.

Characters are not continuously thinking.

Instead:

```
Persistent Identity
↓
Dormant
↓
Reasoning Required
↓
Temporary Consciousness
↓
Decision
↓
Persist Changes
↓
Dormant
```

Thinking becomes an expensive resource managed by the engine.

This is similar to how operating systems schedule CPU time.

---

## Cognitive Level of Detail (CLOD)

Graphics engines introduced Level of Detail (LOD).

Physics engines introduced sleeping rigid bodies.

Empneon introduces **Cognitive Level of Detail (CLOD)**.

Each agent operates at one of several cognition levels.

| Level | Description |
|---|---|
| CLOD 0 | Database only. No reasoning. No CPU usage. No AI. |
| CLOD 1 | Rule-based simulation. Simple deterministic updates. No LLM. |
| CLOD 2 | Lightweight reasoning. Small local models. Quick decisions. |
| CLOD 3 | Interactive cognition. Conversation. Planning. Memory retrieval. Relationship updates. |
| CLOD 4 | Deep cognition. Major story events. Emotional conflicts. Life-changing decisions. Expensive reasoning. |

Only a tiny number of agents should ever exist at CLOD 4 simultaneously.

CLOD allows thousands of agents to exist while only a handful actively consume AI resources.

This concept is considered one of Empneon's primary architectural innovations.

---

## Performance-First Architecture

Performance is not an optimization step.

Performance is a design principle.

Empneon must run on consumer hardware.

**Baseline development machine:**
- Ryzen 7 4800H
- RTX 2060 Laptop (6 GB VRAM)
- 16 GB RAM

If Empneon runs well on this machine, it should run well for a large percentage of gamers.

Every subsystem must define:
- CPU cost
- RAM usage
- VRAM usage
- Token budget
- Latency budget

No subsystem may assume unlimited resources.

---

## Consciousness Scheduler

Empneon contains a scheduler responsible for cognition.

Responsibilities include:
- Waking agents
- Sleeping agents
- Managing CLOD
- Token budgeting
- GPU budgeting
- Request batching
- Queue prioritization
- Predictive loading
- Model selection
- Performance monitoring

This component is conceptually similar to a CPU scheduler in an operating system.

---

## Persistent Identity

Every character owns persistent data independent of any AI model.

Identity includes:
- Name
- Age
- Family
- Occupation
- Personality
- Traits
- Preferences
- Relationships
- Memories
- Emotional history
- Voice profile
- Knowledge graph
- Long-term goals

Identity survives:
- Game restarts
- Computer restarts
- AI model changes

The character exists independently of whichever LLM is currently being used.

---

## Memory Architecture

Memories are not stored inside prompts.

Instead they exist inside structured storage:
- SQLite
- Knowledge Graph
- Vector Search
- Summaries

Memory retrieval only supplies relevant memories to the reasoning process.

Empneon never attempts to load every memory into an LLM.

---

## Knowledge Graph

Empneon should gradually evolve from plain text memories into a semantic knowledge graph.

Instead of storing: `"Bob met Alice."`

The engine stores relationships between entities:

```
Bob
└─[Friend Of]─► Alice
               └─[Works At]─► Hospital
                              └─[Located In]─► Willow Creek
```

Reasoning becomes more consistent and scalable.

---

## Society-Centric Design

Empneon does not think in terms of isolated NPCs.

It models societies.

Important systems include:
- Relationship Network
- Community Dynamics
- Social Groups
- Families
- Organizations
- Economies
- Neighborhoods

Emergent stories should arise naturally from interactions between many persistent identities.

---

## AI Directors

Instead of a single director, Empneon will eventually support multiple specialized directors:

- World Director
- Relationship Director
- Drama Director
- Narrative Director
- Economy Director

Each monitors different aspects of the simulation and proposes opportunities for meaningful interactions.

The Directors do not control characters.

They create opportunities.

Characters remain autonomous.

---

## Game Adapters

Empneon is independent from any game. Games provide adapters.

```
Empneon Core
↓
Game Adapter
↓
Game API
↓
Simulation
```

The Sims 4 becomes Adapter #1. Future adapters may target entirely different engines.

---

## AI Model Independence

Empneon should never depend on a specific model.

Supported providers may include:
- LM Studio
- Ollama
- llama.cpp
- KoboldCPP
- OpenAI-compatible APIs
- Cloud providers
- Future reasoning systems

The AI provider is replaceable. The framework remains unchanged.

---

## Voice Independence

Voice synthesis is modular.

Potential providers include:
- XTTS
- Kokoro
- Piper
- StyleTTS2
- ElevenLabs
- OpenAI TTS
- Future engines

Characters own voice profiles independent of the synthesis engine.

---

## Sims 4 Implementation

The first implementation target is The Sims 4.

The existing proof-of-concept already supports:
- Local LLM
- LM Studio integration
- Python `.ts4script`
- Cheat console conversations

Future work includes:
- Social interactions
- Dynamic interaction menus
- Phone application
- Messaging
- Notifications
- Conversation sessions
- Relationship visualization
- Autonomous NPC conversations
- Emotion-aware animations
- Voice playback
- Story generation

The Sims implementation should become an adapter built on top of the general framework rather than containing game-specific business logic.

---

## Development Philosophy

Empneon should be developed like a professional software platform.

- Documentation first
- Architecture first
- Specifications before implementation

Every feature should have:
1. Requirements
2. Acceptance Criteria
3. Performance Budget
4. Tests
5. Documentation
6. Implementation

Codex or Claude should be treated as implementation engineers rather than software architects.

Architectural decisions remain human-driven.

---

## Long-Term Vision

Empneon aims to become the standard cognitive framework for simulation games.

It should eventually provide:
- Persistent digital identities
- Temporary consciousness
- Emergent storytelling
- Scalable cognition
- Plugin-based AI providers
- Plugin-based voice systems
- Plugin-based game adapters
- Open architecture
- Excellent documentation
- Strong developer experience
- Community contributions

---

## Elevator Pitch

Empneon is an open-source Cognitive Operating System for simulation games.

Rather than making every NPC continuously intelligent, Empneon treats consciousness as a scheduled computational resource.

Characters maintain persistent identities, memories, relationships, goals, and emotional histories while only becoming consciously active when meaningful reasoning is required.

Its Cognitive Level of Detail (CLOD) architecture enables rich, emergent societies to run efficiently on consumer hardware, making advanced AI simulation practical for real games rather than only research environments or cloud-scale infrastructure.

---

## Guiding Principle

> Memory is permanent.  
> Consciousness is temporary.  
> Identity persists.  
> Thought is scheduled.  
>
> The game simulates the world.  
> Empneon simulates the mind.

This principle should guide every architectural decision made throughout the lifetime of the project.
