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
├── Godot 4 portability adapter
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
- [x] OpenAI-compatible provider for LM Studio and compatible APIs
- [x] Ollama support through its OpenAI-compatible endpoint
- [x] Deterministic provider-free CLOD 1 rule path
- [x] Bounded priority scheduler with deadlines and backpressure
- [x] Context, token, latency, concurrency, RAM, and VRAM admission budgets
- [x] Persistent request-estimate and provider-usage records
- [x] Deterministic CLOD 1 degradation for provider timeout and out-of-memory failures
- [x] Sims POC autonomous event-to-action vertical slice through Empneon Core
- [x] Core-backed Sims cheat-console conversation
- [x] Sims identity, relationship, location, mood, and social-event observations
- [x] Generic-intent mapping to validated available Sims actions
- [x] Game-confirmed Core action results and ordered consequences
- [x] Executed automatic NPC-to-NPC Sims interactions
- [x] Sims 4 installation, configuration, privacy, and hardware-profile guide
- [x] Initial RAM/VRAM/concurrency resource governor
- [x] Sims 4 connectivity proof of concept
- [x] Adaptive CLOD scheduler
- [x] Epistemic social memory
- [x] Sims 4 reference adapter using Empneon Core
- [x] Deterministic SocietyBench 20-agent scenarios
- [x] One-call-per-agent and fixed-CLOD baseline execution
- [x] SocietyBench resource, frame-time, token, and latency metrics
- [x] Concurrent Sims 4 run on baseline hardware
- [x] SocietyBench identity-continuity and contradiction metrics
- [x] Blinded SocietyBench believability evaluation
- [x] Published Stage 3 configuration, raw results, and limitations
- [x] Separate canonical event, agent-observation, and agent-belief storage
- [x] Belief source, confidence, interpretation, and transmission lineage
- [x] Persistent belief contradiction and revision history
- [x] Bounded provider-free trust-weighted belief propagation
- [x] Persistent secret, rumor, testimony, and correction scenarios
- [x] JSON-serializable developer-facing belief causal traces
- [x] Validated cheap-versus-expensive cognition comparison collection
- [x] Preliminary player-visible value proxy from blinded preferences
- [x] Dynamic CLOD, provider, context, and completion-token selection
- [x] Capability-gated shared-prefix batching and cache preparation
- [x] Archetype approximation gate (not justified; not implemented)
- [x] Initial adaptive-policy comparison against Stage 3 baselines
- [x] Minimal Godot 4 second adapter
- [x] Published adapter contract tests and development guide
- [x] Measured minimal adapter implementation effort
- [x] Cross-adapter portability exit gate
- [x] Player-triggered Empneon Sims 4 pie-menu interaction
- [ ] Playable Sims 4 prototype with visible native consequences
- [ ] Validated in-game performance benchmarks

Foundation Stage 0 and Stage 1 are complete. The Sims POC autonomous and conversation
paths now resolve through Core, execute through the adapter, and persist action results
and their ordered game-confirmed consequences.
The adapter now observes game identities, relationships, locations, moods, and social
events, and maps generic intents to whitelisted actions reported available by the game.
While a lot is active, one non-player pair is submitted every 30 simulated minutes, with
overlap prevented in the mod and concurrency bounded again by Core. Provider transport
timeouts and memory exhaustion degrade through CLOD 1, persist the fallback result, and
release reserved resources. Installation, configuration, privacy, conservative hardware
profiles, and the in-game exit-gate procedure are documented. The current automatic path
persists observed identities, stores a pending proposal, attempts the validated Sims
interaction, and finalizes the result only from the game's completion callback. This path
uses the game's full-autonomy request and native object discovery unchanged, rejects a
winning result unless its target is another loaded NPC, then queues that prevalidated
interaction through the native executor.
Filterable `ai.socialtunings friendly`
diagnostics remain available for game-version investigation. Live validation passed
across a game restart with 20 persistent Core agents, all 20 participating, 15 successful
autonomous results, zero pending proposals, and 16 ordered consequences. Stage 2 is
complete. Stage 3 now includes deterministic 20-agent social-ring and reciprocal-pair
workloads plus comparable one-call-per-agent and provider-free fixed-CLOD baseline
execution. Raw metric observations retain CPU, RAM, VRAM, frame time, tokens, and
latency, with aggregate token totals and p50/p95 latency. The concurrent in-game
hardware run completed but showed severe pressure:
87.37 ms p50 Sims frame time and 18.821 s p50 provider latency with 5,918 MiB peak VRAM
use. These are preliminary measurements, not a performance claim. See
[SocietyBench results](docs/benchmark-results.md).
SocietyBench can also measure retained expected identities and contradictory values per
agent subject; scenario-specific consistency evaluation remains separate from the raw
hardware run. A 30-sim-minute Stage 2.6 regression run confirmed that native target
discovery avoids the game-build desync caused by injecting an object list: one NPC social
completed, its ordered consequence persisted, and no proposal remained pending.
The first blinded 20-sample believability comparison preferred the one-call candidates
19 times and fixed CLOD 1 once. This is a single-evaluator synthetic result, not a player
study; recognizable output styles and model formatting violations limit the evidence.
The foreground provider observations, raw PresentMon rows, blind evaluation artifacts,
checksums, configuration, and limitations are published in the
[Stage 3 artifact manifest](output/README.md). Stage 3 is complete, but its preliminary
results support no scalability or acceptable-performance claim.
Stage 4 now has separate canonical-event, observation, and belief storage plus schema-backed
belief provenance. Direct beliefs reference their agent's observation; transmitted beliefs
reference their source belief and inherit an ordered lineage. Confidence is bounded, source
evidence is protected by foreign keys, and contradictions can be recorded symmetrically
between one agent's beliefs. Atomic revisions retain the original belief for audit while
current-belief queries expose its single replacement.
Beliefs now propagate without model calls through directed relationship trust. Confidence
decays multiplicatively, statements remain unchanged, and hard hop, recipient, minimum-
confidence, and cycle bounds prevent unbounded relay.
Four deterministic integration scenarios now survive database close/reopen: a contained
secret, a trust-decayed rumor, conflicting witness testimony, and a correction that revises
the rumor while preserving history. Developers can request a JSON-serializable causal trace
containing the canonical event, observation, ordered belief chain, and contradiction/revision
records. The correction scenario verifies this output after restart, completing Stage 4.
Stage 5 now begins from reusable comparison records that align each cognitive request with
its provider-free fixed-CLOD 1 decision and one-call provider decision. The collector
validates strategy coverage, result counts, and agent alignment before the records feed the
existing blinded evaluation. The initial evidence remains the 20 paired Stage 3 samples;
the following estimate reuses those samples rather than claiming an independent run.
The same blinded ratings now yield a signed net-preference estimate: deeper-reasoning
wins minus cheap-reasoning wins, divided by evaluated pairs. The initial 19-to-1 result
is `+0.90` on a `-1` to `+1` scale. This is a synthetic single-evaluator proxy, not
measured player utility.
Core now accepts provider routes with a CLOD, capability declaration, resource estimate,
and resolver. Expected value multiplied by request urgency gates deeper cognition; eligible
routes are degraded to the highest affordable CLOD, with provider choice ordered by estimated
cost. Context and completion limits are clamped to the request, runtime budget, and provider
context window before the existing governor reserves resources. If no route fits, selection
remains deterministic at provider-free CLOD 1. The overall adaptive-scheduler item remains
validated by the differentiated Stage 5 result below.
Provider helpers now detect the longest common message prefix across compatible generation
requests. Native batching is used only when the provider declares `batching`; prefix
preparation is invoked only when it declares `prefix_caching`. Providers declaring neither
capability continue through ordinary generation unchanged, and the OpenAI-compatible adapter
currently declares neither. This is working capability routing, not a latency or cache-hit
claim.
The archetype approximation gate found no supporting comparison in the published evidence.
Stage 3 measured individual one-call and fixed-CLOD paths, not pooled policies; it contains no
archetype resource delta, quality-loss score, or promotion criterion. The `+0.90` preference
for deeper individual reasoning also makes unmeasured approximation a quality risk. No
archetype code was added. The adaptive replay reduced provider calls from 20 to 0, but
retained only 5.26% of the one-call baseline's blinded preference rate: 5% adaptive versus
95% one-call, below the predefined 90% retention threshold. Consistency was not re-evaluated,
so the Stage 5 exit gate failed. The
uniform Stage 3 urgency made every request choose CLOD 1, exposing that the first policy is too
coarse rather than validating it. Stage 5 now requires a differentiated, predeclared workload
and a new comparison before Stage 6. That workload is now implemented as 20 deterministic
events: 8 low-, 6 medium-, and 6 high-value cases. Each event declares urgency plus
consequence, novelty, and social-complexity features before any cognition output or rating
exists. Their unweighted mean supplies expected value, producing a planned split of 8 cheap
and 12 provider routes at the existing `0.50` threshold. This is a test design, not a quality
or cost result; it required the rerun below.

The differentiated rerun passes the Stage 5 exit gate. Its 8 CLOD 1 and 12 provider
selections reduced provider calls by 40%, selected-call tokens by 40.31%, and selected-call
summed latency by 45.11%. Blinded adaptive preference was 85% versus a 90% one-call-or-tie rate,
retaining 94.44% against the predefined 90% minimum. All 20 identities were retained and
the one-target-per-agent consistency check found no contradictions. This remains one
synthetic workload and one assistant evaluator; The Sims was not running, so no new frame
timing was measured. Stage 5 is complete and Stage 6 is next.

Stage 6 uses a minimal Godot 4 project as the second environment. GDScript, a separate
engine process, and a deliberately different two-agent world provide a stronger portability
boundary than another Python simulation. The implemented adapter sends one deterministic
encounter through a localhost-only standard-library bridge using the existing `WorldEvent`,
`Decision`, and `ActionResult` shapes. Godot applies the generic `acknowledge` intent to its
own agent state and reports the result; no Godot concepts were added to Core. A Godot 4.7
headless run completed with `EMPNEON_GODOT_OK` and exit code 0. A published parametrized
contract suite now applies the same actor, evidence, decision-ID, and confirmed-outcome
invariants to both adapters, and the development guide documents in-process and external-engine
integration.
The first working adapter took a 29m42s commit window and 221 runtime lines across five files,
with 36 focused-test lines, no Core changes, and no Python dependency changes. Contract-suite
and guide publication added 36m26s and 167 lines. These are repository-session measurements,
not person-hours or production-integration estimates.

The Stage 6 exit gate now passes. `godot/portability/scenario.json` is the single canonical
two-agent encounter used by the integration test and the Godot scene. The Sims reference
adapter and Godot bridge produced the same deterministic Core decision
`abc780ba-3e2c-501a-95a5-85e289d2a7f5`, preserved its evidence and decision ID, and returned
successful game-specific results. Godot 4.7 then ran that file headlessly and exited 0 with
`EMPNEON_GODOT_OK`. This validates adapter portability, not live Sims performance or production
readiness. Stage 6 is complete.

Stage 6.5 now precedes the developer-product stage. It will turn the Sims reference adapter into
a bounded playable vertical slice: one pie-menu entry, native in-game dialogue/outcome feedback,
three to five whitelisted base-game socials, game-confirmed relationship or mood consequences,
and a later choice changed by retained context. Its exit gate requires save/reload continuity
and safe cancellation without relying on cheat-console commands. Custom animation, voice, broad
autonomy, and elaborate UI remain out of scope.

The first Stage 6.5 item passed live validation on 2026-07-13. Clicking another Sim exposed an
**Empneon Social** pie-menu entry, and two selections recorded the correct player and target Sims
without a cheat-console command. The second item is in progress: the interaction now opens a
native transcript dialog, captures repeated messages, shows progress/error notifications, and
sends the existing `/chat` payload without using the cheat console. Live LM Studio requests
returned generated dialogue and outcome metadata in the transcript, completing the native-UI
checklist item. Native walking and social execution belong to the following
whitelist/execution items and are not implemented yet. See the Stage 6.5 handoff in the roadmap and
the troubleshooting notes in `docs/sims4-setup.md` before resuming.

## Documentation

- [Vision and architecture](docs/vision.md)
- [Adapter development guide](docs/adapter-development.md)
- [Research and innovation program](docs/innovations.md)
- [SocietyBench results](docs/benchmark-results.md)
- [Business model](docs/business-model.md)
- [Validated roadmap](docs/roadmap.md)
- [Sims 4 POC setup and privacy](docs/sims4-setup.md)

## License

Empneon Core is licensed under Apache 2.0, including commercial use. Revenue may
come from hosting, production tooling, managed observability, integration, and
support; use of the Apache-licensed core does not require a commercial license.
