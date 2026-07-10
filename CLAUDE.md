# Empneon — Claude Working Context

This file gives Claude full context to resume work across sessions without losing ground.

## What Empneon Is

Open-source **Cognitive Operating System** for simulation games.
Not an NPC dialogue system. Not a chatbot mod.
A reusable AI cognition framework — The Sims 4 is only the first adapter.

Core philosophy: **The game simulates the world. Empneon simulates the mind.**

Guiding principle:
- Memory is permanent
- Consciousness is temporary
- Identity persists
- Thought is scheduled

## Original Vision (from [Project Vision](https://github.com/PandaBakers/Empneon/blob/main/docs/vision.md))

Key architectural concepts already defined by the author:

- **Identity/Consciousness separation** — character is structured DB data; LLM temporarily provides consciousness
- **CLOD (Cognitive Level of Detail)** — tiered cognition: CLOD 0 (DB only) → CLOD 4 (deep LLM reasoning)
- **Consciousness Scheduler** — manages when agents get LLM time, like CPU scheduler
- **Persistent Identity** — survives game restarts, computer restarts, AI model changes
- **Memory Architecture** — SQLite + knowledge graph + vector search; never loads all memories into LLM
- **Society-Centric Design** — models societies, not isolated NPCs
- **AI Directors** — specialized directors (World, Relationship, Drama, Narrative, Economy) that create opportunities, not control characters
- **Game Adapter pattern** — Empneon Core → Game Adapter → Game API → Simulation
- **AI/Voice model independence** — pluggable providers (Ollama, LM Studio, llama.cpp, etc.)

Target hardware (baseline): Ryzen 7 4800H, RTX 2060 Laptop (6GB VRAM), 16GB RAM.

## Innovations Added in Session (2026-07-09)

The original vision is solid engineering but not novel research. Six innovations were identified that would make Empneon genuinely novel AND stay within hardware constraints:

### 1. Gossip Protocol for Knowledge Propagation
- Information spreads through social graph via distributed systems gossip algorithms
- Decay rate + distortion factor + trust-weighted fidelity per edge
- Truth travels faithfully on strong edges, distorts on weak ones → rumors emerge naturally
- Zero LLM calls — pure graph math at CLOD 0
- Novel: nobody has applied epidemic/gossip protocols to NPC knowledge simulation

### 2. Emotion as Differential State
- Store emotional *velocity*, not labels: `sadness=0.7, sadness_delta=-0.02/tick`
- CLOD 0 runs differential equations continuously — no LLM
- LLM wakes only when state crosses threshold OR velocity reverses sharply (unexpected shift)
- Novel: emotional realism from ODEs, not inference tokens

### 3. Multi-Agent Speculative Batching
- When N agents witness same event, ONE LLM call handles all of them
- Shared context prefix + N parallel continuations via batch inference
- KV cache shared across agents → VRAM cost barely scales with N
- Directly solves the latency bottleneck the original doc ignores
- On 6GB VRAM, a 7B model generates ~25 tokens/sec; without batching, concurrent agents serialize and stall
- Novel in games: no game engine does multi-agent batched reasoning

### 4. Personality as Sampling Parameter Modulation
- Map personality dimensions directly to inference hyperparameters
- High neuroticism → higher temperature + lower repetition penalty
- Low agreeableness → truncate top-p
- Conscientiousness → lower top-k
- Zero prompt tokens consumed for personality — frees context window for actual memory
- Novel: nobody uses inference parameters as personality expression

### 5. Predictive Consciousness Pre-Warming
- Learn behavioral patterns per agent; predict when reasoning will be needed
- Pre-load context window before trigger fires (like CPU branch prediction)
- Learning is cheap: frequency analysis on past event logs
- Eliminates worst latency spikes for predictable social patterns
- Novel: predictive LLM context pre-warming based on learned behavioral patterns

### 6. Archetype Pool / Shared Consciousness Slots
- N similar background agents (20 café workers) share ONE conscious episode
- Scheduler runs one LLM call for archetype, applies per-member variation vectors from DB
- Like GPU instanced rendering but for cognition
- Characters diverge over time as difference vectors accumulate
- Unique agents get promoted out of pool; background stays cheap indefinitely
- Novel in games: scales NPC count to thousands with near-zero marginal LLM cost

## Business Model

**Verdict: Open-source now, monetize later via cloud + commercial licensing.**

### What doesn't work
- Charging modders → they fork it
- Pure open-source forever → sustains hobby, not business
- Targeting AAA studios first → they build in-house

### What works: Open Core + Cloud

| Layer | Model |
|---|---|
| Empneon Core | Open-source, forever free |
| Empneon Cloud | Hosted consciousness scheduling, pay per agent-hour |
| Commercial License | Studios shipping games pay; modders don't |
| Support Contracts | Red Hat model for studios |

**Empneon Cloud** is the main revenue path: developers who can't/won't run local LLMs pay for hosted consciousness scheduling. Inworld AI charges ~$0.001–0.01 per NPC interaction. Empneon undercuts because CLOD means most agents never reach billable inference.

### Sequencing
1. Build open-source, Sims 4 adapter ships first
2. Modding community proves concept, creates noise
3. Indie devs see it, want it for their games
4. Launch Empneon Cloud (hosted LLM consciousness as a service)
5. Commercial license for studios shipping products
6. Framework stays open; cloud and commercial are revenue

### Competitive moat
Local-first + open-source + game-agnostic vs. Inworld AI / Convai (cloud-dependent, expensive, proprietary). Closing the license later (HashiCorp/Redis style) destroys the moat — don't do it.

## Collaboration Model

- Author handles: architecture decisions, game adapter specifics, product direction
- Claude handles: implementation engineering, specifications, tests, documentation
- Claude does NOT make architectural decisions unilaterally
- Every feature needs: requirements → acceptance criteria → performance budget → tests → docs → implementation

## Current State

- Proof of concept exists: local LLM + LM Studio + Python `.ts4script` + cheat console conversations
- No framework structure yet — that's what we're building
- Starting point: define the core framework architecture before touching game-specific code

## Tech Stack (proposed, not finalized)

- Python (existing .ts4script compatibility)
- SQLite (identity + memory persistence)
- Local LLM via OpenAI-compatible API (LM Studio, Ollama, llama.cpp)
- Vector search for memory retrieval (likely sqlite-vec or chromadb)
- Knowledge graph (likely NetworkX or a lightweight graph DB)

## Next Steps (as of 2026-07-09)

1. Define folder/module structure for Empneon Core
2. Specify Identity schema (DB schema for persistent character data)
3. Specify Memory architecture (SQLite + vector + knowledge graph layers)
4. Implement Consciousness Scheduler (basic version, no prediction yet)
5. Implement CLOD system (levels 0–4)
6. Sims 4 adapter as first game integration
7. Validate on baseline hardware (RTX 2060, 6GB VRAM)
