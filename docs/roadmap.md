# Empneon Open-Source Roadmap

This roadmap records implemented work and the next verifiable engineering gates. It is not a
feature promise.

## Implemented

- Generic game contracts and structural `GameAdapter` protocol
- The Sims 4 reference adapter and Godot 4 portability adapter
- Game-confirmed action proposals, results, consequences, timeline, and replay
- Persistent identity, relationships, emotions, goals, voice, episodic memory, observations,
  beliefs, provenance, contradictions, and revisions
- Provider-independent request/result contracts
- Native LM Studio and OpenAI-compatible providers selected by Core configuration
- Deterministic CLOD 1 fallback, bounded scheduling, resource admission, and usage telemetry
- SocietyBench scenarios, raw benchmark artifacts, and regression fixtures
- Versioned SQLite migrations and Core-owned adapter memory documents
- Save-aware The Sims 4 memory checkpoints and one-time legacy memory import
- Single-turn The Sims 4 player dialogue with cancelable waiting, cosmetic conversation animation,
  and bounded game-observed relationship outcomes
- Bounded, pair-scoped semantic memory selection with deterministic fallback; live date-plan recall
  succeeds across paraphrasing

## Next gates

- Treat recalled exchanges only as evidence when composing dialogue so a correct memory is answered
  naturally instead of replaying the earlier model response verbatim.
- Repeat the semantic-memory live matrix with non-date plans, preferences, promises, identities,
  conflicts, and locations.
- Verify the exact two-portrait notification layout and native floating relationship symbols for
  each mild Sims outcome; a more consistently neutral waiting animation is optional polish.

### Core integration

- Route The Sims 4 model-backed cognition through `decide_dynamic` after route estimates are
  measured on the baseline hardware.
- Persist actual provider token and latency results from the configured router in `UsageStore`.
- Replace remaining adapter metadata documents with typed Core concepts only when a second game
  demonstrates a shared concept.

### Resource evidence

- Measure process RAM, provider VRAM, latency, and Sims frame time for the current single-request
  default on the stated baseline.
- Define safe budgets from measurements before increasing concurrency or claiming scalability.

### Portability

- Keep shared contract tests passing for both adapters.
- Add another adapter only when it exercises a materially different integration boundary.

### Developer experience

- Publish tagged monorepo releases with built Core and adapter artifacts.
- Add concise migration notes whenever a supported API or database schema changes.

## Project boundary

If separate deployment infrastructure becomes viable in the future, it should live in an
independent repository and must not change Core's open-source contracts.
