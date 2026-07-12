# Empneon Working Context

**Specification version:** 0.2

## Product

Empneon is a game-agnostic, provider-agnostic cognitive runtime for persistent
simulated societies. The game simulates the world; Empneon simulates the mind.

The Sims 4 is the first reference adapter and demo. It must not introduce Sims-specific
concepts into Empneon Core. A second materially different adapter will prove portability.

## Non-Negotiable Requirements

1. **Game independence:** adapters translate generic events, decisions, state deltas,
   and action results.
2. **Provider independence:** LM Studio, Ollama, llama.cpp, hosted APIs, and custom
   providers plug in through a capability-based protocol. Identity never references a
   model or provider.
3. **Strict resource budgets:** cognition must remain inside configurable CPU, RAM,
   VRAM, concurrency, latency, token, frame-time, and monetary budgets. Degrade or
   defer optional work instead of destabilizing the game.
4. **Evidence before claims:** distinguish hypotheses, implementation, benchmarks,
   and validated results.

## Research Program

- Adaptive value-of-thought scheduling under hard budgets
- Epistemic social memory with provenance, confidence, contradiction, and lineage
- Typed, validated, replayable cognition
- SocietyBench for cost, consistency, and believability

Graph gossip, emotional differential state, batching, cache preparation, personality
sampling, and archetype pooling are supporting techniques to validate, not standalone
novelty claims.

## Architecture Boundaries

```text
Game <-> Adapter <-> Empneon Core <-> LLM Provider
```

- The adapter owns game APIs, animations, interactions, and action translation.
- The core owns identity, memory, beliefs, scheduling, validation, and replay.
- The provider owns transport and model-specific capabilities.
- The resource governor owns admission; the scheduler owns degradation policy.

## Business Model

Empneon Core is Apache 2.0, including commercial use. Do not describe a required
commercial license for the core. Potential revenue: hosting, production tooling,
managed observability, integration, enterprise support, and training.

Target users are developers of simulation, sandbox, management, RPG, and social games.
Modders are the initial distribution and validation community.

## Hardware Baseline

Ryzen 7 4800H, RTX 2060 Laptop 6 GB, and 16 GB RAM with The Sims 4 running at the same
time. Budget the resources left after the game and a safety reserve. Do not publish
performance numbers until measured in-game.

## Current Implementation

- Identity, personality, relationships, emotional state, goals, and voice persistence
- Episodic events and SQLite vector search
- Transactional schema migrations and database-enforced identity ranges
- Atomic, version-validated identity snapshot import
- Generic cognition contracts
- LLM provider capability protocol
- Initial RAM/VRAM/concurrency resource governor
- Persistent Core action results and ordered consequences
- Deterministic timeout and out-of-memory fallback with resource release
- Separate Sims 4 connectivity POC that must be migrated behind the core

The POC `AgentManager` is a semaphore, not the target cognitive scheduler. A zone alarm
submits one instantiated NPC pair every 30 simulated minutes, prevents overlapping
requests, and routes the interaction through Core's admission limit and action records.

## Session Checkpoint: 2026-07-10

Stage 0 is complete. The final foundation changes were:

- `d70c8ae`: schema v2 adds transactional `v1 -> v2` migration, rejects newer
  databases, and installs SQLite validation triggers for persisted identity ranges.
- `d6bb573`: identity snapshot import validates its format version, requires every
  identity store to share one connection, and uses a SQLite savepoint so late failures
  roll back both new imports and updates.

Last verification: 96 unit tests passed with one filesystem temporary-path test
deselected; Ruff and strict mypy passed. Two existing persistence integration tests
could not run locally because the managed environment denied pytest temporary-directory
access. No product benchmark or in-game hardware validation has been performed yet.

Stage 2 remains pending in-game validation. The zone alarm submits bounded NPC pairs,
persists observed Core identities and pending proposals, queues the base-game social
interaction on the simulation thread, and reports its finishing result and observed
relationship delta. The adapter maps generic intent to a whitelisted available action.

## Current Work Order

1. Run the documented in-game confirmation test and fix any Sims API/tuning mismatch.
2. Check the remaining Stage 2 items only after game-confirmed evidence passes.
3. Build SocietyBench only after the gate passes.

See `docs/roadmap.md` for evidence gates.
