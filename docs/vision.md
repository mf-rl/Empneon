# Empneon Project Vision

**Version:** 0.2
**Status:** Foundational specification

## Purpose

Empneon is a game-agnostic cognitive runtime for simulated societies. It provides
persistent identities and selectively allocates AI reasoning while keeping game
performance and operating cost within explicit limits.

Empneon is not a chatbot framework, a Sims-only mod, or an LLM that continuously
pretends to be an NPC.

## Non-Negotiable Principles

### 1. The core is game-agnostic

Empneon Core contains no Sims, Roblox, Unity, Unreal, animation, or game-specific
interaction concepts. It exchanges generic contracts with adapters:

```text
game observation -> WorldEvent -> Empneon Core
Empneon Core -> Decision + StateDelta -> game adapter
game adapter -> ActionResult -> Empneon Core
```

The Sims 4 is adapter number one and the first public demonstration. A deliberately
different second adapter must prove that the core contracts are portable. Roblox,
Unity, Unreal, and other integrations are adapter candidates, not core dependencies.

### 2. The core is provider-agnostic

Identity and memory never contain model references. Reasoning is requested through a
small provider protocol. A provider declares capabilities such as structured output,
streaming, batching, prefix caching, embeddings, locality, and context size.

Supported deployments may include:

- LM Studio, Ollama, llama.cpp, and other local runtimes
- OpenAI-compatible HTTP endpoints
- hosted AI providers
- user-written provider plugins
- mixed routing, with different providers per CLOD level

Basic generation must work everywhere. Backend-specific optimizations are enabled
only when declared and measured.

### 3. Resource constraints are runtime invariants

The game has priority over optional cognition. Empneon operates inside the resources
remaining after current game use and a configurable safety reserve.

Budgets cover:

- CPU utilization and simulation tick time
- RAM and VRAM
- concurrent requests
- prompt and completion tokens
- p50 and p95 latency
- game frame time or minimum FPS
- monetary cost for hosted providers

If a request exceeds budget, Empneon follows a deterministic degradation path:

```text
preferred cognition
-> shorter context or response
-> smaller model
-> lower CLOD
-> deterministic rule
-> defer or reject optional work
```

An out-of-memory condition or unavailable provider must not crash the game.

### 4. Claims require evidence

Prior art exists for simulation level of detail, cognitive architectures, affective
agents, social gossip, batching, and KV caching. Empneon will distinguish hypotheses,
implemented features, benchmarked results, and validated product claims.

## Identity and Consciousness

Every agent permanently exists as structured state:

- identity and adapter mapping
- personality and preferences
- relationships and goals
- emotional state
- episodic memory
- beliefs, sources, and confidence
- voice profile

An LLM temporarily provides reasoning. The resulting decision is validated and
persisted as data; the model session may then disappear without erasing the agent.

## Cognitive Level of Detail

CLOD is Empneon's vocabulary for selecting cognitive resolution. It is an application
of established level-of-detail principles, not a novelty claim by itself.

| Level | Function | Budget behavior |
|---|---|---|
| 0 | Stored state and event history | No model inference; bounded storage work |
| 1 | Rules and deterministic updates | Bounded CPU per simulation tick |
| 2 | Cheap approximate reasoning | Small model or heuristic under a short deadline |
| 3 | Interactive reasoning | Retrieved context and normal conversation/planning |
| 4 | Consequential reasoning | Rare, expensive, and explicitly budgeted |

The long-term scheduler should estimate the expected player-visible value of deeper
reasoning and choose the cheapest sufficient resolution.

The first implemented selector multiplies an expected-value estimate by request urgency.
When the threshold is met, it chooses the highest affordable provider route at or below the
requested CLOD, then clamps context and completion tokens to request limits, runtime limits,
and the provider's declared context window. Otherwise, or when no route fits, it uses the
provider-free CLOD 1 rule.

## Typed Cognition

Model output does not directly mutate a game or database. Providers return content;
Empneon parses it into typed decisions and state deltas. The core validates those
changes against adapter capabilities and simulation rules before committing them.

Every committed decision should be attributable and replayable:

- triggering event
- memories and beliefs considered
- provider and model metadata, outside identity
- selected CLOD and resource estimate
- proposed and accepted state changes
- action result from the game

## Epistemic Social Memory

Empneon separates canonical events from agent beliefs. An agent may observe an event,
misinterpret it, hear a distorted account, encounter a contradiction, or revise a
belief. Each belief records provenance and confidence.

This supports secrets, lies, rumors, investigations, misunderstandings, reputation,
and reconciliation while remaining inspectable by developers.

## Directors

Directors are optional policy modules that propose opportunities. They do not bypass
the scheduler, force character decisions, or mutate game state. World, relationship,
drama, narrative, and economy directors should exist only when a validated use case
requires them.

## Hardware Profiles

Initial profiles are conservative and configurable:

- **Minimum:** CPU or small-model inference, one conscious agent, CLOD 0-2 default
- **Baseline:** RTX 2060 6 GB and 16 GB RAM while The Sims 4 is running
- **Recommended:** larger VRAM/RAM budget enabling more concurrency and caching

The baseline is a validation target, not proof of feasibility. Measurements must be
taken with the game running, including frame time, model memory, KV-cache memory,
queue latency, tokens per second, and recovery behavior.

## Success Criteria

Empneon succeeds when it demonstrates that developers can:

1. Integrate two materially different games without changing core domain concepts.
2. Replace local or hosted model providers without changing identity or game code.
3. Run persistent multi-agent behavior inside a strict resource budget.
4. Inspect and replay why an agent made a decision.
5. Achieve better cost-to-believability than a one-LLM-call-per-agent baseline.

## Guiding Principle

> Memory persists. Consciousness is temporary. Identity is provider-independent.
> Thought is scheduled. The game simulates the world; Empneon simulates the mind.
