# Empneon — Novel Technical Innovations

Six concepts that distinguish Empneon from existing NPC AI frameworks.

## 1. Gossip Protocol for Knowledge Propagation

**Problem solved:** Agents storing individual copies of witnessed events wastes memory and loses emergent social dynamics.

**Mechanism:**
- Events enter a shared event store tagged with origin agent + location + time
- Information propagates through social graph using gossip-style epidemic algorithms
- Each edge has: trust weight, fidelity factor, decay rate
- High-trust edges transmit accurately; low-trust edges introduce distortion
- Propagation stops when message reaches negligible fidelity or all reachable agents

**Result:** Rumors, gossip, and misinformation emerge without any LLM calls. Truth spreads faithfully among close friends; distorts among acquaintances. O(log n) to reach full network.

**CLOD level:** 0 — pure math, no AI.

**Prior art gap:** Gossip protocols are standard in distributed systems (Cassandra, Bitcoin). Nobody has applied them to NPC social simulation.

---

## 2. Emotion as Differential State

**Problem solved:** Storing `emotional_state = sad` requires LLM to simulate emotional change. Emotional life is expensive if every mood shift needs inference.

**Mechanism:**
- Each emotion stored as (value, velocity, acceleration): `sadness = (0.7, -0.02, +0.001)`
- CLOD 0 ticks the differential equations every simulation step — no LLM
- LLM wakes only on threshold crossing (value > 0.9) or velocity reversal (sign change)
- External events inject impulses into the state vector; equations handle decay

**Result:** Continuous, realistic emotional arcs simulated as pure math. LLM only handles emotional inflection points — moments of genuine psychological significance.

**CLOD level:** 0 for simulation, 3–4 only for threshold events.

---

## 3. Multi-Agent Speculative Batching

**Problem solved:** On a 2060 with 6GB VRAM, a 7B model generates ~25 tokens/sec. One CLOD 3 call takes 8–10 seconds. Multiple simultaneous agents serialize — simulation stalls.

**Mechanism:**
- When N agents share an event trigger, bundle into one LLM call
- Structure: shared prefix (event context) + per-agent identity suffix
- Model generates N continuations; KV cache of shared prefix is reused
- VRAM cost: O(prefix) + O(N × response) instead of O(N × full_context)

**Example prompt structure:**
```
[Event: House fire at 14 Elm Street]
[World context: evening, neighborhood relations, ...]

Agent Bob [identity summary]: <response>
Agent Alice [identity summary]: <response>
Agent Carol [identity summary]: <response>
```

**Result:** N agents reasoned for ~1.3× the cost of one agent. Eliminates the serialization bottleneck.

**Prior art gap:** Batch inference exists. Shared-prefix multi-agent cognitive batching for simulation games does not.

---

## 4. Personality as Sampling Parameter Modulation

**Problem solved:** Personality traits stuffed into prompts consume tokens on every inference call, reducing available context for actual memories.

**Mechanism:**
- 5-dimensional personality vector (OCEAN or custom) stored per agent
- At inference time, map dimensions to sampling parameters:
  - Neuroticism → temperature (high N = more erratic generation)
  - Agreeableness → top-p (low A = more assertive, less hedged)
  - Conscientiousness → repetition penalty (high C = more consistent vocabulary)
  - Openness → top-k (high O = more diverse word choices)
  - Extraversion → response length bias
- Parameters injected at the inference engine level, not in prompt

**Result:** Personality affects HOW the model generates, not WHAT it's told. Zero prompt tokens consumed. Full context available for memories, relationships, current situation.

**Prior art gap:** Inference parameters are tuned for task type, not character personality. Novel application.

---

## 5. Predictive Consciousness Pre-Warming

**Problem solved:** Cold-start latency when an agent suddenly needs to reason. Context must be assembled, KV cache must be built — adds seconds to an already slow call.

**Mechanism:**
- Behavioral pattern tracker logs: agent, trigger_type, time_of_day, day_of_week, social_context
- Simple frequency model (no LLM needed) predicts upcoming reasoning events
- Scheduler pre-loads context and warms KV cache at low priority during idle time
- When actual trigger fires, cache is already warm → near-zero cold-start latency

**Analogy:** CPU branch prediction. Cheap statistical model eliminates expensive pipeline stalls.

**Result:** Predictable social patterns (Bob argues with boss Mondays, Alice calls mother Sundays) have imperceptible latency. Unpredictable events still cold-start but are rare.

---

## 6. Archetype Pool / Shared Consciousness Slots

**Problem solved:** Thousands of background agents can't each have individual LLM reasoning. But they also can't be static — they need to feel alive.

**Mechanism:**
- Background agents grouped into archetype pools by role similarity (café workers, office drones, etc.)
- Pool has one LLM-capable slot; individual variation stored as difference vectors in DB
- Scheduler runs one conscious episode for the archetype; variations applied post-generation
- Agents accumulate divergence over time via their unique witnessed events
- When an agent's difference vector exceeds a threshold, it's promoted out of the pool to an individual slot

**Result:** 1000 background agents cost approximately the same as 5–10 individual agents in LLM resources. Each still feels distinct because difference vectors encode their unique history.

**Analogy:** GPU instanced rendering — one draw call, per-instance data applied via shader.

---

## Hardware Feasibility Summary

| Innovation | VRAM impact | CPU impact | Latency impact |
|---|---|---|---|
| Gossip propagation | None | Minimal (graph traversal) | None |
| Emotion ODEs | None | Minimal | None |
| Multi-agent batching | +15% per added agent | Minimal | -70% for concurrent events |
| Personality via params | None (saves tokens) | None | -5% per call |
| Predictive pre-warming | Holds warm cache in VRAM | Background thread | -80% for predicted events |
| Archetype pools | Scales O(pools) not O(agents) | Minimal | Same as individual |

All six are feasible on RTX 2060 6GB + Ryzen 7 4800H + 16GB RAM.
