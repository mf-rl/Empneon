# Empneon

**A game-agnostic cognitive runtime for persistent simulated societies.**

Empneon gives simulation-game characters persistent identity, memory, beliefs,
relationships, and temporary AI reasoning while respecting explicit hardware or
monetary budgets.

> The game simulates the world. Empneon simulates the mind.

## Project Contract

Empneon Core is independent of:

- **Games.** Games integrate through adapters. The Sims 4 is the first reference
  adapter and demo, not the product boundary.
- **AI providers.** Local models in LM Studio, Ollama, or llama.cpp and hosted
  providers are interchangeable through a capability-based provider interface.
- **Hardware scale.** Cognition degrades predictably when CPU, RAM, VRAM, latency,
  token, frame-time, or cost budgets are exhausted.

The core owns cognition. An adapter only translates game events into generic
Empneon events and validated Empneon decisions back into game actions.

## Core Model

### Persistent identity, temporary consciousness

Characters remain structured data when no model is running. An LLM is a temporary
reasoning resource, never the source of character identity.

### Cognitive Level of Detail (CLOD)

| Level | Resolution | Typical mechanism |
|---|---|---|
| CLOD 0 | Persistent state | Database and event records |
| CLOD 1 | Deterministic simulation | Rules and bounded state updates |
| CLOD 2 | Lightweight cognition | Small model or heuristic |
| CLOD 3 | Interactive cognition | Conversation, planning, retrieval |
| CLOD 4 | Exceptional cognition | Expensive reasoning for consequential events |

Every level consumes some resources. The scheduler selects the cheapest level that
preserves a player-visible outcome within the configured budget.

### Enforced resource budgets

Empneon budgets only the resources left after the game and a safety reserve. When a
request cannot be admitted, the scheduler must shorten, downgrade, defer, resolve by
rules, or reject optional cognition instead of destabilizing the game.

## Research Direction

Empneon does not claim novelty from isolated techniques such as graph propagation,
level of detail, emotional state vectors, or prefix caching. Its research program is:

1. **Adaptive value-of-thought scheduling** under hard runtime budgets.
2. **Epistemic social memory** with belief provenance, confidence, contradiction,
   transmission, and distortion.
3. **Typed, validated, replayable cognition** instead of direct LLM mutation.
4. **SocietyBench**, a reproducible cost, consistency, and believability benchmark.

See [docs/innovations.md](docs/innovations.md) for hypotheses and validation gates.

## Architecture

```text
Games
├── Sims 4 reference adapter
├── second portability adapter
└── community adapters (Roblox, Unity, Unreal, custom engines, ...)
            │
            ▼
Empneon Core
├── generic events, decisions, and state deltas
├── identity, episodic memory, and social beliefs
├── adaptive CLOD scheduler and resource governor
├── provider capability routing
└── observability and deterministic replay
            │
            ▼
Providers
├── LM Studio / Ollama / llama.cpp
├── OpenAI-compatible endpoints
├── hosted AI providers
└── user-defined providers
```

Backend-specific optimizations such as KV-cache reuse are optional capabilities,
never requirements for running Empneon.

## Hardware Baseline

Initial validation target:

- Ryzen 7 4800H
- RTX 2060 Laptop with 6 GB VRAM
- 16 GB RAM
- The Sims 4 running concurrently with Empneon

No performance claim is accepted without an in-game benchmark. See
[docs/roadmap.md](docs/roadmap.md).

## Status

Version **0.2.0** is an early framework release.

- [x] Persistent identity and relationship storage
- [x] Episodic memory and SQLite vector search
- [x] Transactional schema migrations and database-enforced ranges
- [x] Atomic, version-validated identity snapshot import
- [x] Generic cognition contracts
- [x] Generic game-adapter and action-result contracts
- [x] Provider capability contract
- [x] Initial RAM/VRAM/concurrency resource governor
- [x] Sims 4 connectivity proof of concept
- [ ] Adaptive CLOD scheduler
- [ ] Epistemic social memory
- [ ] Sims 4 reference adapter using Empneon Core
- [ ] Second adapter proving portability
- [ ] In-game performance and believability benchmarks

Foundation Stage 0 and the first Stage 1 task are complete. The next task is one
OpenAI-compatible provider usable by LM Studio and compatible APIs.

## Documentation

- [Vision and architecture](docs/vision.md)
- [Research and innovation program](docs/innovations.md)
- [Business model](docs/business-model.md)
- [Validated roadmap](docs/roadmap.md)

## License

Empneon Core is licensed under Apache 2.0, including commercial use. Revenue may
come from hosting, production tooling, managed observability, integration, and
support; use of the Apache-licensed core does not require a commercial license.
