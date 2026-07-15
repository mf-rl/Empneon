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
- [x] Route Sims POC cognition and action recording through Empneon Core

**Exit gate:** One Sims event becomes a generic event, produces a validated decision,
executes through the adapter, and persists its result without the POC duplicating core
state.

## Stage 2: Sims 4 Reference Adapter

- [x] Convert cheat-console conversation into a core-backed interaction
- [x] Observe game identities, relationships, locations, moods, and social events
- [x] Map generic decisions to valid available Sims actions
- [x] Persist game-confirmed consequences and action results
- [x] Run bounded autonomous NPC interactions without a player command
- [x] Recover safely from provider timeout and out-of-memory errors
- [x] Document installation, configuration, privacy, and hardware profiles

**Exit gate:** A playable session with at least 20 persistent agents creates observable
social consequences across save/reload cycles.

## Stage 3: SocietyBench Baseline

- [x] Build deterministic 20-agent benchmark scenarios
- [x] Measure one-call-per-agent and fixed-CLOD baselines
- [x] Record CPU, RAM, VRAM, frame time, tokens, and p50/p95 latency
- [x] Run The Sims 4 concurrently on baseline hardware
- [x] Add identity continuity and contradiction metrics
- [x] Run blinded believability evaluation
- [x] Publish configuration, raw results, and limitations

**Exit gate:** Results are reproducible and no scalability claim exceeds measured data.

## Stage 4: Epistemic Social Memory

- [x] Store canonical events separately from agent observations and beliefs
- [x] Record belief source, confidence, interpretation, and lineage
- [x] Implement contradiction and revision
- [x] Implement bounded trust-weighted propagation without mandatory LLM calls
- [x] Add secret, rumor, testimony, and correction scenarios
- [x] Add developer-facing causal trace output

**Exit gate:** Every tested belief can be traced to observations and transmissions, and
the system remains coherent after restart.

## Stage 5: Adaptive Value-of-Thought Scheduler

- [x] Collect cheap-versus-expensive cognition comparisons
- [x] Estimate player-visible value of deeper reasoning
- [x] Select CLOD, provider, context, and token budget dynamically
- [x] Add optional shared-prefix batching and cache preparation by capability
- [x] Evaluate archetype approximation; do not add without benchmark justification
- [x] Compare against Stage 3 baselines
- [x] Build a differentiated adaptive workload with predeclared urgency and value features
- [x] Re-run cost, consistency, and blinded-believability comparison

**Exit gate:** Adaptive scheduling reduces measured cost or latency while preserving a
predefined believability and consistency threshold.

## Stage 6: Portability Proof

- [x] Choose one materially different second environment: Godot 4
- [x] Build a minimal second adapter without adding game concepts to the core
- [x] Publish adapter contract tests and development guide
- [x] Measure adapter implementation effort
- [x] Run the same benchmark scenario through both adapters

The selected environment is a minimal Godot 4 project written in GDScript. It is materially
different from The Sims 4 adapter across engine, scripting language, process boundary, and
world model, while remaining small enough to run headlessly in CI. Godot provides
[headless command-line execution](https://docs.godotengine.org/en/stable/tutorials/editor/command_line_tutorial.html),
[HTTP requests](https://docs.godotengine.org/en/stable/classes/class_httprequest.html), and
[JSON support](https://docs.godotengine.org/en/stable/classes/class_json.html) without an
adapter dependency, and its
[MIT license](https://godotengine.org/license/) fits the repository's Apache-licensed work.

The proof contains only two agents and one deterministic encounter. GDScript translates
that encounter to the existing `WorldEvent` wire shape, submits it to a localhost-only
standard-library bridge, receives an unchanged Core `Decision`, maps the generic
`acknowledge` intent to a Godot state change, and returns an `ActionResult`. A Godot 4.7
headless run completed this round trip with `EMPNEON_GODOT_OK` and exit code 0. The change
adds no Godot types, imports, or concepts to `empneon.core`. A standalone
Python simulation was rejected as too close to Core to prove portability; Unity and Roblox
were deferred because their additional editor, account, or platform workflow is unnecessary
for this minimal contract proof.

**Exit gate:** Both adapters run the same benchmark scenario through unchanged core
contracts.

**Passed 2026-07-13.** `godot/portability/scenario.json` defines the canonical two-agent
encounter. The integration test constructed its `WorldEvent` and equivalent CLOD 1 requests,
then used the provider-free Core path with the Sims reference adapter and the Godot bridge.
Both paths produced decision `abc780ba-3e2c-501a-95a5-85e289d2a7f5`, preserved event evidence
and decision identity, and returned successful game-specific results. Godot 4.7 independently
consumed the same file headlessly, printed `EMPNEON_GODOT_OK`, and exited 0. The Sims side was
the in-process reference adapter, not a live game run; this gate demonstrates contract
portability rather than game performance or production readiness. Stage 6 is complete.

## Stage 6.5: Playable Sims 4 Prototype

- [x] Add one player-triggered Empneon social interaction to the Sim pie menu
- [x] Display generated dialogue and action outcome through native in-game UI
- [x] Map a whitelist of three to five generic intents to base-game social interactions
- [x] Execute the selected native interaction and persist only its game-confirmed outcome
- [x] Let retained memory, relationship, or belief context alter a later interaction choice
- [x] Reflect at least one confirmed native relationship or mood consequence back into Core
- [ ] Validate save/reload continuity and safe cancellation in a dedicated test save

This stage turns the working reference adapter into a noticeable gameplay vertical slice before
developer-product work begins. It must reuse base-game interactions and native UI where possible.
Custom animations, voice, unrestricted autonomous control, a large interaction library, and an
elaborate UI are outside this prototype.

**Pie-menu validation, 2026-07-13:** The packaged `Empneon:Social` interaction loaded in game,
appeared as **Empneon Social** when the player clicked another Sim, and recorded the selected
actor and target for two live invocations without the cheat console. The mod build and installer
now produce and deploy both the script archive and its interaction-tuning package.

**Native UI validation, 2026-07-14:** The completed second checklist item has a native transcript
dialog, a **Thinking...** notification, asynchronous `/chat` submission through the existing
payload path, and native error notifications. Focused tests cover repeated message capture and
rendering dialogue, intent, emotion, suggested action, and Empneon relationship deltas. Live LM
Studio requests returned generated dialogue and outcome metadata in the transcript. Safe
cancellation remains part of the final dedicated save/reload validation item.

Three Sims 4 `1.121.361.1020` UI compatibility problems were resolved during the live iterations:
icon overrides cannot use the older tuple form, text input entries must be `UiTextInput` objects
with the current required attributes, and the outer `text_inputs` mapping must support attribute
lookup. Disassembly of the installed `UiDialogTextInput.on_text_input` showed that it calls
`hasattr(self.text_inputs, text_input_name)`; using `FrozenAttributeDict` fixed the silently empty
message response. The focused test now preserves that contract.

**Native social whitelist, 2026-07-14:** Autonomous proposals now advertise only three mapped
base-game socials: `friendly_chat` resolves to **Ask About Day**, `apologize` to **Apologize**, and
`flirt` to **Compliment Appearance**. Core intent mapping and mod affordance-resolution tests cover
all three and reject unlisted actions.

**Native social execution, 2026-07-14:** The mod now reuses the game's autonomy-selected
interaction context to test and instantiate the chosen mapped affordance, registers its finishing
callback before queueing it, and reports `/action-result` only after the game finishes or cancels
that interaction. The focused regression proves the original target-selection interaction is not
queued and that a proposal or accepted queue entry is not persisted as a confirmed result. This is
implementation and automated-test evidence; live relationship or mood consequence validation
remains a later checklist item. The local `stage2-6-config.json` and generated databases remain
untracked. Stage 7 remains blocked until the full Stage 6.5 exit gate passes.

**Context-dependent choice, 2026-07-14:** The Sims adapter now uses the aggregate relationship
score already retained by the game and included in each autonomous payload. A generic
`acknowledge` decision selects **Apologize** while that score is negative and returns to **Ask
About Day** after it becomes non-negative. A focused regression proves the same decision changes
action when the retained relationship changes. This is implementation and automated-test
evidence; the full two-interaction live demonstration remains part of the Stage 6.5 exit gate.

**Confirmed Core consequence, 2026-07-14:** Successful `relationship.friendship` increments from
the native finishing callback now update Core's canonical directed relationship edge in the same
database transaction that confirms and removes the proposal. Sims friendship points are divided
by 100 and clamped to Core's `-1.0..1.0` strength range. Romance remains an ordered confirmed
consequence because Core has no canonical romance field. An integration regression confirms a
native `+5` friendship result becomes Core strength `0.05`. Live consequence and persistence
validation remains part of the final dedicated-save checklist item.

**Exit gate:** Without using the cheat console, a player invokes Empneon on another Sim, sees
generated dialogue and a native social action, and observes a game-confirmed relationship or
mood consequence. A second interaction between the same Sims must make a demonstrably different
choice because of retained context. The visible consequence and Core history must survive save,
backend restart, and game reload; unavailable Sims and canceled interactions must fail safely.

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
The action bridge now leaves the game's full-autonomy request and native object discovery
unchanged, accepts only winning interactions targeting another loaded NPC, then queues the
prevalidated interaction through the native executor. This avoids the current game build's
tuple-motive desync when a mod injects a restricted object list. Filterable
`ai.socialtunings` diagnostics remain available.
Provider timeout/OOM
recovery and the operating guide are complete. Follow the in-game protocol in
`docs/sims4-setup.md`. The Stage 2 exit gate passed in a live game across a restart with
20 persistent Core agents, all 20 participating, 15 successful autonomous results, zero
pending proposals, and 16 ordered consequences. Stage 2 is complete. SocietyBench now
defines deterministic 20-agent social-ring and reciprocal-pair workloads with stable
request and event data. Both workloads can run comparable one-call-per-agent and
provider-free fixed-CLOD 1 baselines while retaining their decisions and provider-call
counts. SocietyBench retains validated raw CPU, RAM, VRAM, frame-time, token, and latency
observations and summarizes peaks, token totals, and p50/p95 latency. Identity continuity
and contradiction metrics were subsequently added. The first foreground concurrent run
completed on baseline hardware with 20 provider calls and 20 fixed-CLOD decisions.
It measured 87.37 ms p50 Sims frame time, 18,821 ms p50 provider latency, and 5,918 MiB
peak VRAM use, demonstrating severe resource pressure rather than acceptable performance.
Identity continuity now reports retained expected agent IDs, while contradiction rate
reports agent-subject groups containing multiple distinct values. A 30-sim-minute Stage 2.6
regression run completed one NPC social and its ordered consequence with zero pending
proposals and no new desync. A seeded 20-sample blind comparison preferred the one-call
candidate 19 times and fixed CLOD 1 once. Its single evaluator, synthetic context,
recognizable output styles, and formatting violations prevent any broader player-quality
claim. The selected raw provider, PresentMon, packet, key, and score artifacts are published
with checksums, reproduction commands, configuration, privacy scope, and limitations.
Stage 3 is complete. Stage 4 stores canonical events, per-agent observations, and agent
beliefs separately. Schema migration 8 adds source foreign keys, bounded confidence,
interpretation, and ordered transmission lineage. The belief store validates direct
observations and derives lineage from transmitted beliefs; referenced evidence cannot be
deleted while a belief depends on it. Schema migration 9 adds explicit same-agent
contradiction links and directional revision links. Revisions atomically preserve the prior
belief as history while current-belief queries return its replacement. Propagation is now a
provider-free deterministic relay: recipient-to-source trust and per-hop decay
attenuate confidence, while hop, recipient, confidence, and cycle bounds stop propagation.
Persistent integration scenarios now verify secret containment, trust-decayed rumor lineage,
conflicting testimony, and evidence-backed correction across database close/reopen. These are
deterministic causal checks, not a player-realism claim. `BeliefStore.causal_trace()` returns
JSON-serializable canonical
event, originating observation, ordered belief lineage, and contradiction/revision records;
the correction scenario verifies the trace after restart. Stage 4 and its exit gate are
complete. Stage 5 now has validated per-request comparison records pairing the provider-free
fixed-CLOD 1 decision with the one-call provider decision. Collection rejects missing,
mis-sized, or agent-misaligned baseline results, and the existing blinded evaluator consumes
the same records. The first evidence set is the 20 paired Stage 3 samples; it remains
single-evaluator synthetic evidence, not a player study. The blinded ratings now provide a
signed net-preference estimate: `(deeper wins - cheap wins) / evaluated comparisons`. The
initial 19-to-1 result is `+0.90` on a `-1` to `+1` scale. This is a preliminary proxy from one
synthetic evaluator, not measured player utility. Core now gates deeper reasoning on expected
value times request urgency, then selects the highest affordable route at or below the requested
CLOD. Provider ordering uses declared resource estimates; context and completion budgets are
clamped to request limits, runtime limits, and the provider context window. Admission is
rechecked during reservation, and the absence of an eligible route degrades deterministically
to CLOD 1.
Generation preparation now finds the longest common message prefix, requires compatible
temperature and schema settings for a native batch, and invokes batching or prefix-cache
preparation only when the provider declares the matching capability. Ordinary providers keep
their existing per-request generation path. Capability/method mismatches and incomplete batch
results fail explicitly. No backend performance benefit has been measured.
The archetype gate found no pooled-versus-individual benchmark, no measured resource benefit,
no quality-loss result, and no promotion criterion. Stage 3 pressure establishes a need for
optimization, but not for this approximation specifically; the `+0.90` deeper-reasoning
preference increases the cost of guessing. Archetype code is therefore intentionally absent.
Reopen the gate only after a controlled SocietyBench comparison shows a resource or latency
benefit while meeting predefined identity-continuity, contradiction, and believability
thresholds. The initial replay used the published global value `0.90`, uniform request
urgency `0.50`, and the predeclared selection threshold `0.50`. Every score was `0.45`, so
all 20 requests chose CLOD 1. Provider calls fell from 20 to 0, but adaptive blinded
preference was 5% versus the
one-call baseline's 95%: only 5.26% retention against the predefined 90% threshold.
Consistency was not re-evaluated. That initial comparison failed the Stage 5 exit gate and
triggered remediation. The remediation workload declares 20 event-semantic
cases before observing outcomes: 8 low, 6 medium, and 6 high. Each records urgency,
consequence, novelty, and social complexity; expected value is their unweighted mean. At the
existing `0.50` threshold, the declared scores plan 8 CLOD 1 and 12 provider selections. This
split alone is not an exit-gate result. Cost, consistency, and blinded believability were
then re-run without label leakage. The blinded rerun selected 12 provider and 8 CLOD 1 decisions,
reducing provider calls 40%, selected-call tokens 40.31%, and selected-call summed latency
45.11%.
Adaptive preference retained 94.44% of the one-call-or-tie rate against the predefined 90%
minimum. Identity continuity was 100% and the one-target-per-agent consistency check found
0% contradictions, meeting its 100%/0% thresholds. Stage 5 therefore passes its exit gate.
The run used synthetic events and one assistant evaluator, and no new in-game frame timing;
those limits prevent a broader player-quality or hardware-performance claim.

The minimal Godot 4 adapter is now runnable. Its two-agent GDScript scene owns world mutation,
while a localhost JSON bridge translates only the existing generic contracts and invokes the
provider-free CLOD 1 resolver. The engine confirmed one deterministic encounter and returned
a successful applied state delta in a Godot 4.7 headless run. Shared contract tests and the
adapter development guide now document and verify the shared actor, evidence, decision-ID, and
confirmed-outcome invariants for the Sims 4 and Godot boundaries. The first working adapter
required a 29m42s commit window, 221 runtime lines across five files, 36 focused-test lines,
zero Core changes, and zero Python dependency changes. Publishing the contract suite and guide
added 36m26s and 167 lines. These are reproducible repository-session measurements, not
person-hours or production estimates. The canonical scenario subsequently passed through both
adapter boundaries and the real headless Godot engine, completing Stage 6.

Stage 6.5 is now the current focus. Its player-triggered pie-menu interaction and native transcript
passed live validation, three generic actions map to base-game socials, and the selected mapped
social is queued with results deferred until its game finishing callback. Retained negative versus
non-negative relationship context now changes a later generic autonomous choice. Confirmed native
friendship deltas also update Core's canonical relationship edge. Continue with the final dedicated
save/reload and safe-cancellation validation. Stage 7 must not begin until this playable prototype
passes its in-game exit gate.
