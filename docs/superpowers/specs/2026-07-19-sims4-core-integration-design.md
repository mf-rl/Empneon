# The Sims 4 Full Core Integration Design

**Date:** 2026-07-19
**Status:** Approved for implementation planning

## Objective

Make the The Sims 4 adapter use most production-ready Empneon Core capabilities while preserving existing installations and the current mod/backend protocol. Empneon Core owns cognition and persistence; the adapter only observes The Sims 4, exposes currently available actions, and reports game-confirmed outcomes.

## Chosen Approach

Use compatible vertical consolidation. This replaces competing persistence paths incrementally without rewriting the backend or maintaining permanent dual writes.

Rejected alternatives:

- A complete modular rewrite would increase regression risk before delivering player-visible cognition.
- Permanent dual writes would leave two authoritative representations that can diverge.

## Unified Database and Migration

`empneon_core_memory.sqlite3` is the only active database after this change. It contains Core tables and any adapter-specific migration markers needed by the backend.

The former `empneon_core.sqlite3` and `ai_sims_memory.sqlite3` files are legacy migration inputs only. On startup:

1. If the unified database does not exist and `empneon_core.sqlite3` exists, copy it with SQLite's backup API into the unified path.
2. Open the unified database through `empneon.db.open_db()` so every Core schema migration is applied.
3. If `ai_sims_memory.sqlite3` exists, back it up before reading it and import profiles, relationships, emotions, goals, voice settings, memories, summaries, and conversations.
4. Record migration markers in the unified database. Repeated startup must not duplicate records.
5. Never delete or write to either legacy file.
6. If migration fails, leave legacy files unchanged, do not record completion, and return a clear startup/diagnostic error.

The new configuration key is `memory_database`, defaulting to `empneon_core_memory.sqlite3`. Existing `core_database` and `database` values are accepted only as legacy source locations. Save-slot checkpoints are copies of the unified database and use its filename as their prefix.

## Canonical Identity

Every observed Sim is upserted by stable game ID into `AgentStore`. Core stores are authoritative:

- `PersonalityStore`: OCEAN values derived deterministically from game traits. Unknown traits leave the neutral value `0.5`.
- `GoalStore`: current aspiration and needs at or below `25%` become deterministic, source-prefixed goals. Syncing the same state is idempotent. A replaced aspiration closes its former active goal; a need above `25%` completes its active need goal.
- `EmotionalStateStore`: mood and moodlet intensities become normalized emotional states in the range `0.0..1.0`.
- `RelationshipStore`: directed relationship strength and trust use normalized game values. Confirmed deltas update the Core edge only after the game reports success.
- `VoiceProfileStore`: provider, voice ID, speed, pitch, and provider settings replace legacy voice JSON.

Traits, values, and behavioral rules are derived from the current game observation when building context rather than stored in a second profile format. Private knowledge is represented by beliefs, not profile JSON.

## Epistemic and Vector Memory

Each incoming game interaction produces one canonical `Event`. Each participating or witnessing Sim receives a separate `Observation`. A direct belief may be created only from that Sim's observation; another Sim does not acquire it merely by being nearby.

Player-supplied factual dialogue becomes a high-confidence belief for the addressed Sim with observation provenance. Generated dialogue remains a proposed action and does not become memory or belief until the game confirms it. Failed and cancelled interactions remain action records but create no fictional consequences.

Confirmed experiences are indexed through `VectorMemoryStore`. A deterministic, standard-library feature-hashing encoder case-folds word tokens, maps each token with BLAKE2b into one of 384 signed buckets, and L2-normalizes the result. This provides local topical retrieval without a network service or new model dependency. Retrieval results are filtered against the requesting Sim's observations so vector search cannot leak another Sim's private memory. The encoder is replaceable by a semantic embedding provider later without changing episodic records.

`DocumentMemoryStore` remains available for documents and migration markers; new experiences and conversations use episodic stores.

## Cognition, Scheduling, and Usage

Requests use Core contracts and are assigned urgency from their source:

- Player conversation: `1.0`.
- Critical need, crisis, or strong negative moodlet: `0.85`.
- Goal-relevant autonomy: `0.65`.
- Ambient autonomy: `0.35`.
- Background reflection/indexing: `0.1`.

`PriorityScheduler` orders pending cognition by urgency, deadline, and arrival. The existing active-agent bound remains the execution-capacity limit; sleeping and dormant Sims do not occupy it.

`CognitiveRuntime.decide_dynamic()` selects cognition:

- CLOD 1 for routine, low-value ambient actions and provider fallback.
- CLOD 2 for ordinary goal-relevant autonomy.
- CLOD 3 for player dialogue, novel events, or emotionally important choices.
- CLOD 4 is allowed only when configured and when urgency, available budget, and deeper-reasoning value justify it.

Deeper-reasoning value is the bounded sum of player initiation (`0.4`), novelty (`0.2` when no accessible related event exists), emotional intensity (`0.2 * intensity`), and active-goal relevance (`0.2`). Player dialogue prefers CLOD 3, goal-relevant autonomy prefers CLOD 2, and crises prefer CLOD 3. CLOD 4 requires an explicit `deep` model route. Core's `ResourceGovernor` remains the hard admission boundary.

Provider generation must retain its `GenerationResult` so `UsageStore` can record provider, model, selected CLOD, estimated context/completion/latency/RAM/VRAM, actual prompt/completion tokens, and actual latency. CLOD 1 records zero provider tokens under the provider name `core-rules`.

## Rich Sims Observation Contract

The mod sends fields only when the installed Sims API safely exposes them; absence is valid and maps to an empty or unknown value. The observation contract includes:

- stable Sim ID and display name;
- traits and current mood;
- motives/needs and moodlets;
- aspiration;
- career and skills;
- lot, zone, and room context where available;
- household/family relationship context;
- nearby Sims and witnesses;
- aggregate relationship state;
- currently available adapter actions;
- interaction success, failure, cancellation, and confirmed deltas.

The adapter never proposes an action outside the payload's current `available_actions` list. Existing payloads and commands remain valid when none of the new optional fields are present.

## Confirmation and Goal Progress

The game remains authoritative for mutations. The backend first records an action proposal. A confirmation then records the result and applies only validated consequences supplied by the mod. Supported consequences include relationship values, emotional changes, need changes, and explicit goal status changes. Rejected or failed outcomes require a reason and do not apply state deltas.

Confirmed outcomes become timeline entries and episodic evidence. `replay_action_record()` must reproduce the recorded decision and applied consequences without executing the game action again.

## Identity Portability and Save Slots

Core's identity serialization exports and imports an individual Sim's agent, personality, goals, emotions, relationships, and voice profile. Import validates the existing Core format and writes to the unified database.

Save-slot isolation backs up and restores `empneon_core_memory.sqlite3`. Existing behavior controlled by `preserve_memory_only_on_game_save` remains compatible. Import/export is explicit and does not silently cross save slots.

## Local Diagnostics

Diagnostics are read-only HTTP GET endpoints served by the already configured local backend listener:

- `/diagnostics/sim?sim_id=...`: agent, personality, goals, emotions, relationships, voice, observations, beliefs, and accessible memories.
- `/diagnostics/timeline?sim_id=...`: `agent_timeline()` output.
- `/diagnostics/replay?decision_id=...`: `replay_action_record()` output.
- `/diagnostics/usage?sim_id=...`: `UsageStore.telemetry()` output.
- `/diagnostics/migration`: unified path, detected legacy sources, backup state, completion markers, and last error.

Identity portability uses `/identity/export?sim_id=...` and `/identity/import`. Existing diagnostic commands retain their aliases; concise `empneon.*` cheat-console aliases expose status, timeline, beliefs, goals, and usage for in-game verification.

Endpoints validate identifiers and return `400` for invalid input, `404` for unknown agents/decisions, and `500` with a non-secret error message for storage failures. They never return API keys, environment variables, provider credentials, or arbitrary files.

## Error Handling and Degradation

- Missing optional Sims fields use neutral defaults.
- An unavailable LLM route falls back through Core's existing CLOD fallback behavior.
- A vector-extension failure disables vector retrieval for that request while episodic persistence continues.
- A full scheduler queue rejects background work before player interactions.
- Invalid or mismatched action confirmations are rejected without changing state.
- Database writes that represent one observation or confirmation use a transaction.

## Automated Verification

Tests are written first and use real temporary SQLite databases. No external provider is required; provider tests use deterministic local test doubles at the HTTP/provider boundary.

Coverage includes:

- default unified filename and legacy configuration compatibility;
- backup and idempotent migration from both legacy databases;
- canonical identity, personality, goals, emotions, relationships, and voice;
- per-Sim observations and belief provenance with no knowledge leakage;
- vector indexing/retrieval and privacy filtering;
- urgency mapping, priority ordering, dynamic CLOD selection, fallback, and usage telemetry;
- proposal/confirmation semantics, goal progress, timeline, and replay;
- identity export/import and save-slot isolation;
- diagnostics validation and secret exclusion;
- optional rich payload fields and old-payload compatibility;
- full Core and adapter regression suites;
- extracted release ZIP backend bootstrap smoke test.

## In-Game Test Plan Deliverable

Implementation produces `adapters/thesims4/docs/in-game-core-feature-test-plan.md`. Each implemented capability has prerequisites, exact cheat-console or gameplay steps, expected visible behavior, expected diagnostic output, persistence/restart verification, and cleanup. It covers both an available LLM and an unavailable LLM so fallback behavior is observable.

## Explicit Boundaries

- The feature-hashing vectors improve topical/lexical retrieval but are not equivalent to neural semantic embeddings.
- The mod reads only stable or safely probed Sims APIs; unsupported game-version internals do not block the backend.
- Provider monetary cost is not recorded because Core's current usage schema has no pricing field; tokens and latency are recorded.
- No new UI, cloud service, external token, embedding model, or database is introduced.
