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

### Predictive Cache Preparation

Behavioral patterns may predict future context needs. Preparation is enabled only when
its measured latency benefit exceeds its VRAM and CPU cost.

### Archetype Approximation

Background agents may share cheap policies while retaining individual state and being
promoted when their histories diverge. Quality loss and promotion criteria must be
measured rather than assumed.

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
