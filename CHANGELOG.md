# Changelog

All notable changes to Empneon Core are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows
[Semantic Versioning](https://semver.org/). Before 1.0, a minor release may change the supported
API with migration notes.

## [Unreleased]

## [0.5.0] - 2026-11-17

### Migration notes
- **Database schema 13** adds a nullable `cognition_usage.degradation_reason` column. The migration
  is automatic and forward-only on first open, and an older runtime then refuses the file. Stop every
  Empneon process and back up the database plus its `-wal` and `-shm` files before upgrading.
- `get_for_agent(limit=...)` on the event, belief, and action-record stores now raises `ValueError`
  for `0` or a negative limit (a negative limit used to mean unlimited).
- `CognitiveRuntime.process` records a `failed` result when `adapter.execute` raises instead of
  propagating the exception, and `resolve_with_fallback` degrades a `ValueError` (invalid model
  output) to CLOD 1 instead of raising.
- Provider URLs must use `http` or `https`; any other scheme is rejected before a network call.
- `AgentStateSnapshot` raises a clear `ValueError` for malformed `intents`, `state_paths`, or
  `schema_version`; `VectorMemoryStore` rejects reopening a table with different dimensions; and
  `PriorityScheduler.submit` discards expired entries before raising `SchedulerFull`.
- Import paths are unchanged. `DegradationReason` moved to `empneon.core.contracts` and is still
  importable from `empneon.core.clod`, and `UsageStore.telemetry()` gains a `by_degradation` key.

### Added
- `SemanticMemoryIndex` and `SemanticMatch` (`empneon.core.memory.semantic`): index event
  descriptions with an `EmbeddingProvider` and search them by meaning, scoped to the events an agent
  participated in or observed, with backfill and removal. `VectorMemoryStore.existing()` opens a
  vector table without knowing its dimensions.
- `EmbeddingProvider`, `EmbeddingResult`, `OpenAICompatibleEmbeddingProvider`, and
  `ResilientEmbeddingProvider`: opt-in embeddings (batching, L2 normalization, validated responses)
  built with `ConfiguredProviderRouter.embedding_provider_for()` from an explicit `embedding` task,
  with the same `retry` and `circuit_breaker` blocks as chat providers.
- `Clod` `IntEnum` for the five cognitive levels; plain integers are still accepted.
- `DegradationReason` and an optional `on_degrade` callback on `resolve_with_fallback`.
- `ProviderError.status` (HTTP status code when an endpoint returned one).
- `PriorityScheduler.expire()` and `RequestDeadlineExceeded.request`.
- Standard-library logging under the `empneon` logger namespace (`NullHandler` only; no prompts,
  replies, keys, or exception text are logged).
- Keyword-only `commit` argument on every store mutator, so callers can own the transaction.
- `CognitiveRuntime(enforce_deadlines=True)` enforces `deadline_ms` around the resolver and
  degrades to CLOD 1 on timeout (default off).
- `ResilientProvider` and `RetryPolicy` for opt-in retry with backoff, jitter, and `Retry-After`;
  `ConfiguredProviderRouter` enables it from a `retry` config block.
- `CircuitBreaker`, `CircuitBreakerPolicy`, `BreakerRegistry`, and `CircuitOpenError`: opt-in
  circuit breaker for providers, enabled from a `circuit_breaker` config block and shared across
  per-call routers.
- `validate_decision` and optional `intents` / `state_paths` adapter capabilities:
  `CognitiveRuntime.process` rejects decisions an adapter said it cannot execute, without calling
  `execute`. Nothing changes for adapters that do not publish the keys.
- `CognitiveRuntime(usage=...)` persists degradations to CLOD 1 with their `DegradationReason`;
  `UsageStore.record(degradation_reason=...)` and `UsageStore.telemetry()["by_degradation"]`.
  `DegradationReason` now lives in `empneon.core.contracts` (still importable from
  `empneon.core.clod`). `CognitiveRuntime(on_degrade=...)` reports the reason without writing, for
  adapters that keep their own usage rows; the Sims 4 adapter records reasons for player-dialogue
  fallbacks this way.
- `ProviderError.retry_after` and `ProviderError.transport`.
- `py.typed` marker so downstream type checkers use Core's inline types.
- `CLAUDE.md` guide for AI coding agents and contributors.

### Changed
- Provider requests accept only `http` and `https` URLs; any other scheme (for example `file:`) is
  rejected before any network call and reported as a non-retryable `ProviderError`.
- CI enforces the ruff rule sets `B`, `SIM`, and `S` in addition to `E, F, I, UP`, and fails when
  Core test coverage drops below 90%.
- Database schema 13: nullable `cognition_usage.degradation_reason` column (automatic,
  forward-only migration; back up the database and its `-wal`/`-shm` files first).
- `resolve_with_fallback` degrades invalid model output (`ValueError`) to CLOD 1 instead of
  raising.
- `CognitiveRuntime.process` records a `failed` result when `adapter.execute` raises, instead of
  losing the decision.
- `PriorityScheduler.submit` discards expired entries before reporting `SchedulerFull`.
- LM Studio and OpenAI-compatible providers share one private HTTP transport.
- `OpenAICompatibleProvider.api_key` is hidden from `repr()`.
- `get_for_agent(limit=...)` on the event, belief, and action-record stores rejects `0` and
  negative limits.
- A malformed agent-state `schema_version` raises a clear `ValueError`.
- `VectorMemoryStore` documents its Euclidean (L2) distance, rejects reopening a table with
  different dimensions, and no longer depends on `sqlite3.Row`.
- CI runs on Python 3.11 and 3.12 and prints a Core coverage summary (not a gate).
- `docs/api.md`, `CONTRIBUTING.md`, and `core/README.md` match the repository layout, PyPI
  distribution, and CI commands.

## [0.4.0] - 2026-07-30

Tagged release `v0.4.0`. See the
[GitHub release](https://github.com/mf-rl/Empneon/releases/tag/v0.4.0) for details.
