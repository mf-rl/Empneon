# Empneon Validated Roadmap

**Version:** 0.2

Work advances through evidence gates. Later stages do not begin merely because earlier
code exists.

## Stage 0: Correct The Foundation

- [x] State game-, provider-, and hardware-independence as project requirements
- [x] Correct Apache 2.0 commercial-use documentation
- [x] Replace unsupported novelty and performance claims with hypotheses
- [x] Implement persistent identity and relationship storage
- [x] Implement episodic memory and SQLite vector search
- [x] Define generic world-event, cognition-request, decision, and state-delta types
- [x] Define the LLM provider capability protocol
- [x] Implement initial RAM, VRAM, and concurrency admission control
- [x] Add real schema migrations and database range constraints
- [x] Make multi-store identity import atomic and version-validated

## Stage 1: Minimal Runtime Vertical Slice

- [x] Define the game-adapter protocol and action-result contract
- [x] Implement one OpenAI-compatible provider usable by LM Studio and compatible APIs
- [x] Implement Ollama only where its API needs a distinct adapter (none required)
- [x] Implement a deterministic CLOD 1 rule path
- [x] Implement a basic priority scheduler with deadlines and backpressure
- [x] Enforce context, token, latency, concurrency, RAM, and VRAM budgets
- [x] Record request estimates and actual provider usage
- [x] Add deterministic degradation and provider-failure fallback
- [x] Move Sims POC persistence and cognition behind Empneon Core

**Exit gate:** One Sims event becomes a generic event, produces a validated decision,
executes through the adapter, and persists its result without the POC duplicating core
state.

## Stage 2: Sims 4 Reference Adapter

- [x] Convert cheat-console conversation into a core-backed interaction
- [x] Observe game identities, relationships, locations, moods, and social events
- [x] Map generic decisions to valid available Sims actions
- [ ] Persist game-confirmed consequences and action results
- [ ] Run bounded autonomous NPC interactions without a player command
- [x] Recover safely from provider timeout and out-of-memory errors
- [x] Document installation, configuration, privacy, and hardware profiles

**Exit gate:** A playable session with at least 20 persistent agents creates observable
social consequences across save/reload cycles.

## Stage 3: SocietyBench Baseline

- [ ] Build deterministic 20-agent benchmark scenarios
- [ ] Measure one-call-per-agent and fixed-CLOD baselines
- [ ] Record CPU, RAM, VRAM, frame time, tokens, and p50/p95 latency
- [ ] Run The Sims 4 concurrently on baseline hardware
- [ ] Add identity continuity and contradiction metrics
- [ ] Run blinded believability evaluation
- [ ] Publish configuration, raw results, and limitations

**Exit gate:** Results are reproducible and no scalability claim exceeds measured data.

## Stage 4: Epistemic Social Memory

- [ ] Store canonical events separately from agent observations and beliefs
- [ ] Record belief source, confidence, interpretation, and lineage
- [ ] Implement contradiction and revision
- [ ] Implement bounded trust-weighted propagation without mandatory LLM calls
- [ ] Add secret, rumor, testimony, and correction scenarios
- [ ] Add developer-facing causal trace output

**Exit gate:** Every tested belief can be traced to observations and transmissions, and
the system remains coherent after restart.

## Stage 5: Adaptive Value-of-Thought Scheduler

- [ ] Collect cheap-versus-expensive cognition comparisons
- [ ] Estimate player-visible value of deeper reasoning
- [ ] Select CLOD, provider, context, and token budget dynamically
- [ ] Add optional shared-prefix batching and cache preparation by capability
- [ ] Add archetype approximation only if benchmarks justify it
- [ ] Compare against Stage 3 baselines

**Exit gate:** Adaptive scheduling reduces measured cost or latency while preserving a
predefined believability and consistency threshold.

## Stage 6: Portability Proof

- [ ] Choose one materially different second environment
- [ ] Build a minimal second adapter without adding game concepts to the core
- [ ] Publish adapter contract tests and development guide
- [ ] Measure adapter implementation effort

Candidates include a small Unity sample, Roblox experience, or standalone simulation.

**Exit gate:** Both adapters run the same benchmark scenario through unchanged core
contracts.

## Stage 7: Developer Product

- [ ] Agent, event, decision, and belief timeline
- [ ] Replay and state-delta inspection
- [ ] Resource and CLOD telemetry
- [ ] Scenario regression runner
- [ ] Stable package, API reference, versioning, and migration policy
- [ ] Recruit three studio design partners

## Stage 8: Optional Managed Service

Begin only after repeated customer demand:

- [ ] Hosted provider routing and scheduler
- [ ] Usage and cost reporting
- [ ] Managed persistence and observability
- [ ] Authentication, tenancy, privacy, and retention controls
- [ ] Billing and service-level objectives

## Deferred Until Evidence Requires Them

- multiple AI directors
- broad voice-provider matrix
- many game adapters
- custom cloud infrastructure
- 1,000-agent claims
- backend-specific inference optimizations without measured benefit

## Current Focus

Stage 0, the game-adapter contract, and the OpenAI-compatible provider are complete.
Ollama's `/v1/chat/completions` and `/v1/models` endpoints require no distinct adapter,
and a provider-free deterministic CLOD 1 path is implemented. A bounded priority queue
now enforces deadlines and backpressure. The resource governor admits work against
context, token, latency, concurrency, RAM, and VRAM ceilings. SQLite records request
estimates and actual provider usage. Resource-admission and provider failures degrade
deterministically to the provider-free CLOD 1 path. The Sims POC autonomous endpoint now
runs generic autonomous and conversation events through Core and persists their adapter
results. Stage 1 is complete. Sims observations enter generic world-event facts, and
generic intents map to whitelisted actions reported available by the game. Core can store
adapter-returned results and ordered consequences, and a bounded zone alarm submits NPC
pairs without a player command. The confirmation path now persists observed Core
identities, stores pending proposals separately, attempts the base-game social interaction,
and finalizes results and observed relationship deltas from the game's finishing callback.
The action bridge now uses a base-game friendly mixer's social commodities to let the
game's autonomy component select a valid parent interaction and NPC target, then queues
that exact prevalidated interaction through the native executor. Filterable
`ai.socialtunings` diagnostics remain available.
Provider timeout/OOM
recovery and the operating guide are complete. Follow the in-game
protocol in `docs/sims4-setup.md`; keep the two action items unchecked until the game path
passes, and do not begin Stage 3 before the exit gate passes.
