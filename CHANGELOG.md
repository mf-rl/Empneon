# Changelog

All notable changes to Empneon Core are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows
[Semantic Versioning](https://semver.org/). Before 1.0, a minor release may change the supported
API with migration notes.

## [Unreleased]

### Added
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
- `ProviderError.retry_after` and `ProviderError.transport`.
- `py.typed` marker so downstream type checkers use Core's inline types.
- `CLAUDE.md` guide for AI coding agents and contributors.

### Changed
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
