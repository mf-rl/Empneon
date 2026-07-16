# Empneon Research and Innovation Program

**Version:** 0.2

This document records hypotheses to implement and test. It does not claim that an
idea is novel, feasible, or commercially valuable before evidence exists.

## Primary Research Contributions

### 1. Adaptive Value-of-Thought Scheduling

**Question:** Can a runtime predict when expensive cognition will materially improve
a player-visible outcome?

The scheduler chooses CLOD, provider, model, context size, response budget, batching,
and timing subject to resource constraints. A learned or calibrated policy may compare
cheap and expensive outcomes to estimate the value of deeper reasoning.

**Validation:** Compare adaptive scheduling with fixed thresholds and one-call-per-agent
baselines using tokens, latency, memory, contradictions, and blinded believability.

Stage 5 comparison collection now pairs each request with its fixed-CLOD 1 and one-call
decisions, preserving both labeled strategies and rejecting incomplete or agent-misaligned
results. The first 20 records reuse the Stage 3 social-ring evidence. They are inputs for
value estimation, not evidence that the adaptive policy is effective. Blinded preferences
produce a signed net estimate where `+1` always favors deeper reasoning, `0` is neutral, and
`-1` always favors cheap reasoning. The first 19-to-1 result is `+0.90`; because it comes from
one synthetic evaluator, it is a preliminary player-visible proxy rather than player data.

The first adaptive policy uses that value as a calibrated input rather than a learned model.
It multiplies expected value by request urgency, keeps low-value work at CLOD 1, and otherwise
chooses the highest affordable provider route no deeper than the requested CLOD. The route's
declared context window and resource estimate clamp context and completion tokens before
atomic admission. This is an implemented deterministic policy, not evidence that it beats
the Stage 3 baselines.

The first Stage 3 replay did not beat both baselines. Uniform urgency made all 20 requests
select CLOD 1, eliminating provider calls but retaining only 5.26% of the one-call baseline's
blinded preference rate, far below the predeclared 90% threshold. A differentiated workload
must declare urgency and value features before outcomes are observed, then repeat cost,
consistency, and blinded-believability evaluation without label leakage.

The remediation workload now fixes those inputs independently of generated decisions and
ratings. Twenty event-semantic cases are divided into 8 low-, 6 medium-, and 6 high-value
tiers. Each declares urgency plus bounded consequence, novelty, and social-complexity values;
the scheduler input is their unweighted mean. At the existing `0.50` gate this design yields
8 cheap and 12 provider routes. The tier rubric is hand-authored and deliberately simple,
not a learned value model or evidence that the resulting routing preserves quality.

The blinded differentiated rerun passed the predeclared gate. Twelve provider selections
and eight CLOD 1 selections reduced provider calls 40%, selected-call tokens 40.31%, and
selected-call summed latency 45.11%. Adaptive selections retained 94.44% of the one-call-or-tie
preference rate, above the 90% minimum; identity continuity was 100% and the
one-target-per-agent contradiction rate was 0%. This supports the deterministic policy for
this synthetic workload only. It is not a learned value model, player study, longitudinal
consistency test, or in-game performance result.

### 2. Epistemic Social Memory

**Question:** Can provenance-aware beliefs create coherent social consequences without
requiring an LLM call for every transmission?

Canonical events produce agent-specific observations and beliefs. Beliefs contain
source, confidence, interpretation, transmission lineage, contradiction, and revision.
Graph propagation, trust weighting, decay, and bounded distortion are implementation
techniques within this larger system.

**Validation:** Secret, rumor, conflicting-testimony, correction, and relationship
recovery scenarios must remain causally traceable across save/reload cycles.

The first four deterministic scenarios now pass across SQLite close/reopen. Relationship
recovery remains outside this checklist item and broader believability still requires player
evaluation. A JSON-serializable trace exposes each tested belief's canonical event,
observation, transmission chain, contradictions, and revisions after restart.

### 3. Typed and Replayable Cognition

**Question:** Can structured decisions preserve generative behavior while providing
the determinism and control required by game developers?

LLM output becomes a proposed `Decision` with explicit evidence and `StateDelta`
records. The core validates it, the adapter attempts it, and the resulting action is
recorded for replay and debugging.

**Validation:** Invalid actions are rejected safely; accepted scenarios replay to the
same stored state; developers can trace every consequence to its inputs.

### 4. SocietyBench

SocietyBench will be a reproducible benchmark for society-scale cognition:

- 20, 50, and 100-agent workloads before any 1,000-agent claim
- identity continuity and contradiction rate
- secrets, rumors, conflicting evidence, and corrections
- relationship and emotional consequences
- provider timeout and out-of-memory recovery
- RAM, VRAM, CPU, tokens, cost, and p50/p95 latency
- blinded player or evaluator believability

The benchmark, scenarios, and raw measurements should be public and repeatable.

## Supporting Techniques

These are useful techniques, not standalone novelty claims:

### Cognitive Level of Detail

Tiered resolution routes most work to stored state, rules, heuristics, or small models.
The research contribution is adaptive selection under budget, not LOD itself.

### Graph-Based Information Propagation

Trust, fidelity, decay, and bounded mutation can propagate beliefs cheaply. Complexity
and fidelity depend on topology and implementation and must be measured.

The current Stage 4 baseline uses deterministic breadth-first relay with multiplicative
trust and decay plus hard hop, recipient, confidence, and cycle bounds. It preserves the
statement exactly and makes no model call; distortion remains scenario work, not a claim.

### Dynamic Emotional State

Value, velocity, acceleration, impulses, decay, and thresholds are candidate state
models. They require stable integration, bounded values, and player evaluation before
any realism claim.

### Shared-Prefix Batching and Cache Reuse

The scheduler may batch compatible requests or reuse prefixes when a backend exposes
the capability. One prompt producing several characters is not equivalent to
independent continuations with shared KV cache. Each backend needs its own benchmark.

Generation preparation now detects the exact longest common message prefix. Compatible
requests use a provider's native batch method only when `batching` is declared; the prefix is
prepared only when `prefix_caching` is declared. Providers without either capability retain
ordinary independent generation. This implements capability routing without claiming that
batching or caching improves a particular backend.

### Predictive Cache Preparation

Behavioral patterns may predict future context needs. Preparation is enabled only when
its measured latency benefit exceeds its VRAM and CPU cost.

The implemented cache preparation applies only to already queued requests with an observed
shared prefix. Predictive prewarming remains unimplemented pending measured benefit.

### Archetype Approximation

Background agents may share cheap policies while retaining individual state and being
promoted when their histories diverge. Quality loss and promotion criteria must be
measured rather than assumed.

The current evidence does not justify implementation. Stage 3 has no archetype arm and thus
measures neither pooled-policy savings nor identity, contradiction, or believability loss.
The observed `+0.90` preference for deeper individual reasoning makes an unmeasured shortcut
especially risky. This remains a deferred hypothesis until a controlled comparison establishes
both benefit and safe promotion criteria.

### Personality Expression

Prompt content, retrieved behavioral evidence, rules, fine-tuning, and sampling
parameters may all influence personality. Sampling parameters alone are not treated
as a psychological model. Controlled evaluation must select the approach.

## Evidence Levels

Every research item uses one label:

- **Hypothesis:** documented mechanism, not implemented
- **Implemented:** runnable with focused tests
- **Benchmarked:** compared against a stated baseline with raw results
- **Validated:** independently repeatable and improves the target outcome

Current status: all four primary contributions remain hypotheses. Generic contracts, an
initial resource governor, deterministic 20-agent SocietyBench workloads, and comparable
one-call-per-agent and fixed-CLOD execution with raw resource, frame-time, token, and
latency recording are implementation foundations, not in-game benchmarked or validated
research results. One foreground baseline-hardware run is measured and documents severe
resource pressure; it is not sufficient to validate a research contribution. Identity
continuity and generic agent-subject contradiction metrics are implemented for later
scenario evaluation.
