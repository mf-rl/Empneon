# Empneon

**Open-source Cognitive Operating System for simulation games.**

Empneon is not an NPC dialogue system or chatbot mod. It is a reusable AI cognition framework that gives simulation game characters persistent identity, memory, relationships, and scheduled consciousness — running on consumer hardware.

> The game simulates the world. Empneon simulates the mind.

---

## The Problem

Existing AI NPC systems ask: *"How do we make one NPC intelligent?"*

Empneon asks: *"How do we make an entire simulated society computationally feasible while maintaining believable intelligence?"*

Running a full LLM for every NPC continuously is impossible on consumer hardware. Empneon solves this with **Cognitive Level of Detail (CLOD)** — the same principle graphics engines use for LOD, applied to cognition.

---

## Core Concepts

### Identity / Consciousness Separation

Every character permanently exists as structured data (identity, personality, relationships, memories, goals). The LLM temporarily provides consciousness when reasoning is needed. When reasoning finishes, consciousness disappears. Identity remains.

### Cognitive Level of Detail (CLOD)

| Level | Description | AI Cost |
|---|---|---|
| CLOD 0 | Database only. Pure state. | None |
| CLOD 1 | Rule-based deterministic simulation | None |
| CLOD 2 | Lightweight local model reasoning | Low |
| CLOD 3 | Full LLM: conversation, planning, memory | Medium |
| CLOD 4 | Deep cognition: major story events, emotional conflicts | High |

Thousands of agents exist at CLOD 0–1. Only a handful ever reach CLOD 3–4 simultaneously.

### Consciousness Scheduler

Manages when agents think — like a CPU scheduler, but for cognition. Handles wake/sleep cycles, CLOD transitions, token budgeting, VRAM budgeting, and request batching.

---

## Novel Innovations

Six systems that distinguish Empneon from prior work:

1. **Gossip Protocol for Knowledge Propagation** — rumors and information spread through the social graph via epidemic algorithms. Truth distorts on weak edges, travels faithfully on strong ones. Zero LLM calls.

2. **Emotion as Differential State** — emotional velocity, not labels. `sadness = (0.7, -0.02/tick)`. CLOD 0 runs the ODEs continuously. LLM wakes only at threshold crossings or sharp reversals.

3. **Multi-Agent Speculative Batching** — when N agents witness the same event, one LLM call handles all of them via shared KV cache prefix. Solves the serialization bottleneck on consumer GPUs.

4. **Personality as Sampling Parameter Modulation** — personality maps directly to inference hyperparameters (temperature, top-p, top-k). Zero prompt tokens consumed for personality.

5. **Predictive Consciousness Pre-Warming** — learns behavioral patterns per agent, pre-loads context before triggers fire. Like CPU branch prediction for LLM latency.

6. **Archetype Pool / Shared Consciousness Slots** — N similar background agents share one conscious episode. Per-member variation applied from stored difference vectors. Like GPU instanced rendering, for cognition.

---

## Architecture

```
Empneon Core
├── Identity System       (SQLite — persistent character data)
├── Memory Architecture   (SQLite + vector search + knowledge graph)
├── CLOD Engine           (tiered cognition levels 0–4)
├── Consciousness Scheduler
├── LLM Provider Layer    (OpenAI-compatible — LM Studio, Ollama, llama.cpp, ...)
├── Voice Provider Layer  (XTTS, Kokoro, Piper, ...)
└── AI Directors          (World, Relationship, Drama, Narrative, Economy)

Game Adapters
└── Sims 4 Adapter        (first adapter — .ts4script)
    └── [future adapters: InZOI, Skyrim, Unity, Unreal, ...]
```

---

## Hardware Target

Empneon is designed to run on consumer gaming hardware.

**Baseline:** Ryzen 7 4800H · RTX 2060 Laptop (6 GB VRAM) · 16 GB RAM

Every subsystem defines explicit CPU, RAM, VRAM, token, and latency budgets.

---

## Status

Early development. Core framework under construction.

- [x] Vision and architecture documented
- [x] Novel innovations specified
- [x] Project scaffolded (src layout, pyproject.toml, CI, license)
- [ ] Core framework implementation *(Phase 2 Memory Architecture: 2/8 complete)*
- [ ] Sims 4 adapter
- [ ] First public release

See [`docs/roadmap.md`](docs/roadmap.md) for full task breakdown.

---

## Docs

| Document | Description |
|---|---|
| [`docs/vision.md`](docs/vision.md) | Full project vision and foundational architecture |
| [`docs/innovations.md`](docs/innovations.md) | The six novel technical innovations |
| [`docs/business-model.md`](docs/business-model.md) | Business model and monetization strategy |
| [`docs/roadmap.md`](docs/roadmap.md) | Full development roadmap from current state to launch |

---

## License

Apache 2.0 — free for modders and non-commercial use.
Commercial use by studios shipping games will require a commercial license.
