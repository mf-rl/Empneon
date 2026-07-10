# Empneon — Full Roadmap

Tracks all work from current state to full product (core + cloud + commercial).
Check items off as completed. This is the source of truth for session continuity.

---

## Phase 0 — Foundation
*Project scaffolding and repo structure.*

- [x] Project vision documented (`docs/vision.md`)
- [x] Novel innovations documented (`docs/innovations.md`)
- [x] Business model documented (`docs/business-model.md`)
- [x] Claude working context created (`CLAUDE.md`)
- [x] Define folder/module structure for Empneon Core
- [x] Set up Python project (`pyproject.toml`, packaging, virtual env)
- [x] Set up GitHub Actions CI (lint, test, type check)
- [x] Set up testing framework (pytest)
- [x] Contributing guide + PR/issue templates
- [x] Code of conduct
- [x] Choose and add license (Apache 2.0 recommended)

---

## Phase 1 — Core: Identity System
*Persistent character data independent of any AI model.*

- [x] Define Identity DB schema (SQLite)
- [ ] Implement Identity CRUD operations
- [ ] Personality vector storage (5-dimensional OCEAN or custom)
- [ ] Relationship graph schema (agent-to-agent edges with weight + type)
- [ ] Emotional state storage (value + velocity + acceleration per emotion)
- [ ] Long-term goals schema
- [ ] Voice profile schema
- [ ] Identity serialization / deserialization
- [ ] Identity survives: game restart, computer restart, model change (integration test)

---

## Phase 2 — Core: Memory Architecture
*Structured memory storage — never load all memories into LLM.*

- [ ] SQLite episodic memory store (events, timestamps, participants)
- [ ] Vector search integration (`sqlite-vec` or `chromadb`)
- [ ] Memory embedding pipeline (local embedding model)
- [ ] Relevance scoring for memory retrieval
- [ ] Knowledge graph (`NetworkX` — nodes: entities, edges: relationships)
- [ ] Memory consolidation (summarization of old memories)
- [ ] Memory pruning (goal-directed, keep load-bearing memories)
- [ ] Cross-agent shared event store (one event record, N perspective records)

---

## Phase 3 — Core: CLOD System
*Tiered cognition — most agents never consume AI resources.*

- [ ] CLOD level interface/protocol definition
- [ ] CLOD 0: pure DB state machine (no AI, no CPU beyond reads)
- [ ] CLOD 1: rule-based simulation engine (deterministic updates)
- [ ] CLOD 2: small/local model integration (fast decisions, < 1B param models)
- [ ] CLOD 3: full LLM interactive cognition (conversation, planning, memory retrieval)
- [ ] CLOD 4: deep reasoning (major story events, emotional conflicts)
- [ ] CLOD transition triggers (threshold events, urgency scoring)
- [ ] CLOD transition tests (agent moves up/down correctly)

---

## Phase 4 — Core: Consciousness Scheduler
*Manages when agents think — like a CPU scheduler for cognition.*

- [ ] Agent wake/sleep lifecycle
- [ ] Priority queue (urgency + narrative importance scoring)
- [ ] CLOD level management per agent
- [ ] Token budget tracking (per-session, per-agent)
- [ ] VRAM budget tracking and enforcement
- [ ] Request queue with backpressure
- [ ] Performance monitoring hooks (latency, queue depth, VRAM usage)
- [ ] Scheduler benchmark on baseline hardware (RTX 2060, 16GB RAM)

---

## Phase 5 — Core: LLM Provider Abstraction
*Pluggable AI backends — framework never depends on one model.*

- [ ] OpenAI-compatible API base interface
- [ ] LM Studio provider adapter
- [ ] Ollama provider adapter
- [ ] llama.cpp provider adapter (direct)
- [ ] Provider health check + fallback
- [ ] Model capability registry (context length, supports batching, speed profile)
- [ ] Streaming response support

---

## Phase 6 — Core: Voice Provider Abstraction
*Pluggable voice synthesis — character owns voice profile, not engine.*

- [ ] Voice provider base interface
- [ ] XTTS adapter
- [ ] Kokoro adapter
- [ ] Piper adapter (lightweight, offline)
- [ ] Voice profile persistence (per agent)
- [ ] Voice profile survives engine change

---

## Phase 7 — Innovations Implementation
*The six novel systems that make Empneon genuinely research-level.*

- [ ] **Gossip protocol** — knowledge/rumor propagation through social graph
  - [ ] Edge trust weights + fidelity decay
  - [ ] Distortion model (weak edge = content mutation)
  - [ ] Propagation stopping conditions
  - [ ] CLOD 0 integration (pure math, no AI)
- [ ] **Emotion as differential state** — ODE-based emotional simulation
  - [ ] Emotional state vector (value, velocity, acceleration per emotion)
  - [ ] ODE tick integration (CLOD 0, runs every simulation step)
  - [ ] Threshold detection (triggers CLOD escalation)
  - [ ] External event impulse injection
- [ ] **Multi-agent speculative batching** — one LLM call for N agents on shared event
  - [ ] Shared prefix + per-agent suffix prompt construction
  - [ ] Batch inference via OpenAI-compatible batch API
  - [ ] KV cache reuse validation
  - [ ] Latency benchmark vs. sequential calls
- [ ] **Personality as sampling parameter modulation** — no prompt tokens for personality
  - [ ] OCEAN-to-hyperparameter mapping (temperature, top-p, top-k, rep penalty)
  - [ ] Parameter injection at inference time
  - [ ] Validation: personality affects output without prompt tokens
- [ ] **Predictive consciousness pre-warming** — branch prediction for LLM context
  - [ ] Behavioral pattern logger (agent, trigger type, time, social context)
  - [ ] Frequency model (predict upcoming reasoning events)
  - [ ] Background pre-load at idle priority
  - [ ] Warm cache hit rate benchmark
- [ ] **Archetype pool / shared consciousness slots** — instanced cognition for background agents
  - [ ] Pool grouping logic (role similarity clustering)
  - [ ] Per-member difference vector storage
  - [ ] Post-generation variation application
  - [ ] Divergence tracking + pool promotion threshold
  - [ ] Cost benchmark: 1000 pooled agents vs. 10 individual

---

## Phase 8 — AI Directors
*Specialized directors that create narrative opportunities — never control agents.*

- [ ] Director base interface
- [ ] World Director (environmental events, ambient world changes)
- [ ] Relationship Director (monitors relationship tension, creates interaction opportunities)
- [ ] Drama Director (pacing, conflict escalation/de-escalation)
- [ ] Narrative Director (emergent story arc tracking)
- [ ] Economy Director (resource scarcity, opportunity creation)
- [ ] Director-to-Scheduler communication protocol
- [ ] Director autonomy limits (directors propose, agents decide)

---

## Phase 9 — Sims 4 Adapter
*First game integration — proves the framework is game-agnostic.*

- [ ] Game adapter base interface (generalizes to all future adapters)
- [ ] Sims 4 adapter scaffold (`.ts4script` integration)
- [ ] Empneon Core ↔ Sims 4 API bridge
- [ ] Social interactions integration
- [ ] Dynamic interaction menus
- [ ] Phone application UI
- [ ] Messaging system
- [ ] Autonomous NPC conversations (no player trigger)
- [ ] Emotion-aware animation triggers
- [ ] Voice playback integration
- [ ] Story generation / event log
- [ ] Sims 4 adapter documentation
- [ ] Sims 4 end-to-end test on baseline hardware

---

## Phase 10 — Performance Validation
*Every subsystem proven on baseline hardware.*

- [ ] Full benchmark suite (Ryzen 7 4800H + RTX 2060 + 16GB RAM)
- [ ] CLOD transition profiling
- [ ] VRAM usage per CLOD level (must fit in 6GB with game running)
- [ ] Latency budget validation per CLOD level
- [ ] 1000-agent simulation stress test
- [ ] Multi-agent batching VRAM + latency benchmark
- [ ] Gossip propagation performance test (large social graph)
- [ ] Memory retrieval latency test (large memory store)

---

## Phase 11 — Developer Experience
*Framework is only as good as its docs.*

- [ ] Architecture overview doc
- [ ] Getting started guide (run Empneon locally in 15 minutes)
- [ ] Adapter development guide (build your own game adapter)
- [ ] Plugin development guide (custom LLM + voice providers)
- [ ] API reference (auto-generated from docstrings)
- [ ] Example project: minimal adapter (non-Sims)
- [ ] Changelog + versioning policy

---

## Phase 12 — First Public Release (v0.1.0)
*Open-source launch.*

- [ ] All Phase 1–10 core items complete
- [ ] README polished with install instructions + demo
- [ ] GitHub Releases set up
- [ ] PyPI package published
- [ ] Announce: Reddit (r/thesims, r/gamedev, r/LocalLLaMA), Discord communities
- [ ] Sims 4 modding community outreach (ModTheSims, LoversLab, etc.)

---

## Phase 13 — Empneon Cloud
*Hosted consciousness scheduling — main revenue path.*

- [ ] Cloud architecture design (hosted scheduler + LLM backend)
- [ ] API gateway (OpenAI-compatible endpoint for remote consciousness calls)
- [ ] Usage metering (per agent-hour, per conscious episode)
- [ ] Billing integration (Stripe or equivalent)
- [ ] Developer dashboard (usage, quota, agent stats)
- [ ] Cloud provider adapter (Empneon Core pointing to Cloud instead of local LLM)
- [ ] SLA definition
- [ ] Cloud documentation + onboarding
- [ ] Beta launch (invite-only, indie devs first)
- [ ] Public launch

---

## Phase 14 — Commercial License
*Studios shipping games with Empneon pay; modders don't.*

- [ ] Commercial license terms drafted (lawyer review)
- [ ] License detection tooling (SDK watermarking or honor system with ToS)
- [ ] Studio onboarding process
- [ ] Commercial tier pricing page
- [ ] First commercial licensee signed

---

## Phase 15 — Support Contracts
*Red Hat model — open source is free, support is paid.*

- [ ] Support tier definitions (response SLA, included hours, escalation path)
- [ ] Support portal / ticketing system
- [ ] Custom adapter development service offering
- [ ] Studio training materials (workshops, implementation guides)
- [ ] First support contract signed

---

## Current Focus

**Phase 0 complete.** Working on Phase 1 — Core: Identity System.

Next immediate task: Implement Identity CRUD operations.
