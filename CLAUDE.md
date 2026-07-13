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
- Game-confirmed Sims action results and ordered consequences through Core
- Deterministic SocietyBench 20-agent social-ring and reciprocal-pair scenarios
- One-call-per-agent and provider-free fixed-CLOD baseline execution
- Raw CPU, RAM, VRAM, frame-time, token, and latency benchmark metrics
- Foreground Sims 4 baseline-hardware benchmark evidence
- SocietyBench identity-continuity and contradiction metrics
- Seeded blinded SocietyBench believability comparison and scoring
- Published Stage 3 configuration, raw evidence, checksums, and limitations

The POC `AgentManager` is a semaphore, not the target cognitive scheduler. A zone alarm
submits one instantiated NPC pair every 30 simulated minutes, prevents overlapping
requests, and routes the interaction through Core's admission limit and action records.

## Session Checkpoint: 2026-07-13

Stages 0 through 2 are complete. The Stage 2 exit gate passed across a game restart
using `stage2-5-config.json`: 20 persistent Core agents all participated, 15 automatic
actions succeeded, one failed safely as displaced, no proposals remained pending, and
16 ordered consequences persisted.

The final foundation changes were:

- `d70c8ae`: schema v2 adds transactional `v1 -> v2` migration, rejects newer
  databases, and installs SQLite validation triggers for persisted identity ranges.
- `d6bb573`: identity snapshot import validates its format version, requires every
  identity store to share one connection, and uses a SQLite savepoint so late failures
  roll back both new imports and updates.

Current verification: 131 tests and Ruff pass. Strict mypy passes for the changed benchmark
package and test; the full test tree still has pre-existing annotation failures. No product
performance benchmark has been published yet.

Stage 3 includes deterministic 20-agent social-ring and reciprocal-pair workloads plus
one-call-per-agent and provider-free fixed-CLOD 1 baseline execution. The workloads use
synthetic stable IDs and do not depend on personal Sims save data. Metric observations
retain raw values and summarize peaks, token totals, and p50/p95 latency.

The first foreground concurrent run used LM Studio with the 7.5B Q4_K_M Gemma model.
Twenty provider calls and 20 fixed-CLOD decisions completed. Sims frame time was
87.37 ms p50 / 229.27 ms p95; provider latency was 18,821 ms p50 / 33,701.65 ms p95;
peak system RAM was 15,705.23 MiB and peak VRAM was 5,918 MiB. Treat these as evidence
of severe pressure, not validated performance.

Consistency measurement reports retained expected identities and contradictory
agent-subject value groups without implementing the Stage 4 belief model early.

The Sims action bridge leaves full-autonomy object discovery native and filters the winning
result to loaded NPC targets. Injecting a restricted `object_list` triggers a game-build
`frozenset & tuple` desync. The regression test mirrors that branch, and a 30-sim-minute
Stage 2.6 live run completed one NPC social with one ordered consequence, zero pending
proposals, and no new desync.

The first seeded 20-sample blind believability run preferred one-call candidates 19 times
and fixed CLOD 1 once. Treat it only as single-evaluator synthetic evidence: output styles
were recognizable and several model candidates violated the requested response format.

Stage 3 evidence is published under `output/`: the foreground baseline JSON, raw PresentMon
CSV, blind packet, answer key, and score. `output/README.md` records checksums,
reproduction commands, configuration, privacy scope, and limitations. Stage 3 is complete.

## Current Work Order

1. Store canonical events separately from agent observations and beliefs.
2. Continue Stage 4 strictly in roadmap order.

See `docs/roadmap.md` for evidence gates.
