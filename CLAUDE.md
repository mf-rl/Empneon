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
- Validated per-request cheap-versus-expensive cognition comparisons
- Signed deeper-reasoning net-preference estimate from blinded ratings
- Dynamic CLOD, provider, context, and completion-token route selection
- Capability-gated shared-prefix batching and cache preparation
- Archetype approximation gate deferred for lack of benchmark justification
- Passing differentiated adaptive cost, consistency, and blinded-preference validation
- Godot 4 selected as the materially different Stage 6 environment
- Minimal Godot 4 adapter round trip through unchanged Core contracts
- Published shared adapter contract tests and development guide
- Reproducible minimal Godot adapter implementation-effort measurement
- Passing canonical cross-adapter Stage 6 portability benchmark

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

Current verification: 163 tests and Ruff pass. Strict mypy passes for Core, both adapter
boundaries, and the published contract suite; the full test tree still has pre-existing
annotation failures. Published evidence supports no scalability or player-quality claim.

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

Schema migration 7 stores canonical events, per-agent observations, and beliefs separately.
Migration 8 adds a one-to-one provenance record with a foreign key to either an observation
or source belief, bounded confidence, interpretation, and ordered transmission lineage.
The store validates sources and derives lineage; SQLite prevents referenced evidence from
being deleted.

Schema migration 9 stores symmetric contradiction and directional revision relations.
The store restricts contradictions and revisions to one agent, writes revisions atomically,
retains superseded beliefs as history, and exposes unrevised beliefs as current.

Belief propagation is deterministic and provider-free. It follows incoming directed trust
edges (`recipient -> source`), multiplies confidence by trust and per-hop decay, preserves
statements, extends lineage through ordinary belief creation, and enforces hop, recipient,
minimum-confidence, and cycle bounds.

Persistent integration scenarios cover secret containment, a two-hop trust-decayed rumor,
conflicting testimony held by one agent, and correction through contradiction plus revision.
Each scenario closes and reopens its SQLite database before asserting causal state.

`BeliefStore.causal_trace()` returns JSON-serializable canonical event, originating
observation, ordered belief chain, and contradiction/revision relation records. The correction
scenario verifies this developer output after restart. Stage 4 is complete.

Stage 5 comparison collection pairs each request with its provider-free fixed-CLOD 1
decision and one-call provider decision. Strategy coverage, result counts, and decision-agent
alignment are validated, and the blinded evaluator consumes the same records. The first
collection reuses the 20 Stage 3 social-ring pairs. The existing 19-to-1 blinded result
produces a `+0.90` signed net preference, where `+1` always favors deeper reasoning, `0` is
neutral, and `-1` always favors cheap reasoning.
This is a single synthetic evaluator's player-visible proxy, not measured player utility.

Dynamic selection accepts provider routes containing CLOD, capabilities, a resource estimate,
and a resolver. Expected value multiplied by urgency gates provider use. Eligible routes are
ordered by the highest affordable CLOD and then estimated cost; context and completion tokens
are clamped to request limits, runtime limits, and the provider context window. The runtime
executes the selected resolver through the existing atomic governor reservation and CLOD 1
failure fallback. The differentiated Stage 5 validation below benchmarks this policy.

Generation preparation detects the longest exact common message prefix. Multiple requests
use native batching only when their temperature and schema settings are compatible and the
provider declares `batching`; cache preparation runs only when `prefix_caching` is declared.
Providers declaring neither keep ordinary generation unchanged. The OpenAI-compatible
provider currently declares neither capability. This path has contract tests but no backend
performance evidence; predictive prewarming is intentionally excluded.

Archetype approximation was evaluated and intentionally not implemented. Published evidence
has no pooled-versus-individual arm, resource delta attributable to pooling, quality-loss
measurement, or promotion criterion. Severe Stage 3 pressure does not identify archetypes as
the solution, and the `+0.90` deeper-reasoning preference makes speculative pooling risky.
Reopen only after a controlled SocietyBench comparison meets predefined consistency and
believability thresholds while reducing cost or latency.

The initial adaptive replay fixed preference retention at 90% before scoring. Global value
`0.90` times uniform urgency `0.50` produced `0.45`, below the `0.50` selection threshold, so
all 20 requests chose CLOD 1. Provider calls fell 100%, but adaptive preference was 5% versus
the one-call baseline's 95%, retaining only 5.26%; consistency was not re-evaluated. The
initial comparison failed the Stage 5 exit gate and triggered the remediation below.

The remediation workload declares 20 deterministic event-semantic requests before provider
output or rating: 8 low-, 6 medium-, and 6 high-value cases. Urgency and bounded consequence,
novelty, and social-complexity features determine each selection score. Their declared split
at the existing threshold is 8 CLOD 1 and 12 provider routes; this is workload design, not an
exit-gate result.

The differentiated rerun passes Stage 5: 40% fewer provider calls, 40.31% fewer selected-call
tokens, 45.11% lower selected-call summed latency, 94.44% preference retention against a 90%
minimum, 100% identity continuity, and 0% one-target-per-agent contradictions. It is a
single synthetic run with one assistant evaluator and no new in-game frame timing. Stage 5
is complete.

The minimal Godot 4 adapter uses a two-agent GDScript scene and a localhost-only Python
standard-library bridge. Godot translates one deterministic encounter into the existing
`WorldEvent` shape, receives an unchanged provider-free `Decision`, owns the resulting world
mutation, and confirms it as an `ActionResult`. Godot 4.7 completed the headless round trip
with `EMPNEON_GODOT_OK` and exit code 0. No Godot concept or import was added to Core. The
published parametrized contract suite checks both adapters against the same actor, evidence,
decision-ID, and confirmed-outcome invariants. `docs/adapter-development.md` documents the
in-process and external-engine paths. The canonical exit benchmark below subsequently completed
Stage 6.

Godot proof effort is measured from repository evidence: 29m42s from target selection to the
first working adapter; 221 runtime lines across five files; 36 focused-test lines; zero Core
or Python dependency changes. Publishing the contract suite and guide added 36m26s and 167
lines, for 1h06m08s from selection through publication. These commit windows are not
person-hours or production estimates.

Stage 6 uses `godot/portability/scenario.json` as one canonical two-agent benchmark. The Sims
reference adapter and Godot bridge produced the same deterministic Core decision
`abc780ba-3e2c-501a-95a5-85e289d2a7f5`, preserved its evidence and ID, and confirmed successful
game-specific results. Godot 4.7 independently consumed the same file headlessly, printed
`EMPNEON_GODOT_OK`, and exited 0. The Sims side was the in-process adapter, not a live game run;
this proves contract portability, not game performance. Stage 6 is complete.

Stage 6.5 is a bounded playable Sims 4 prototype required before Stage 7. Its player-triggered
pie-menu interaction passed live validation. Remaining work adds native in-game message input
and dialogue/outcome feedback, three to five whitelisted
base-game socials, confirmed native relationship or mood consequences, one later choice altered
by retained context, and save/reload plus cancellation validation. Custom animation, voice, broad
autonomy, and elaborate UI remain deferred.

## Current Work Order

1. Display generated dialogue and action outcome through native in-game UI, beginning with a
   message-input dialog from the validated Empneon Social pie-menu entry.

See `docs/roadmap.md` for evidence gates.
