# Package, API, and Compatibility Policy

Empneon `0.5.0` supports Python 3.11 or newer. It is a pre-1.0 developer release:
the package artifact and the API listed below are supported, but minor releases may
make documented breaking changes.

## Install and build

Install the released package from PyPI:

```console
pip install empneon
```

Install a checkout for development (Core lives in `core/`):

```console
pip install -e "core[dev]"
```

Build the Core wheel and source distribution:

```console
cd core
python -m build
```

CI builds the Core and adapter artifacts on every pull request and push to `main`.

## Supported Python API

The names exported by `empneon.__all__` are the supported top-level API:

| Area | Imports |
|---|---|
| Contracts | `WorldEvent`, `CognitiveRequest`, `Decision`, `StateDelta`, `ActionResult`, `AgentStateSnapshot`, `Clod` |
| Runtime | `CognitiveRuntime`, `ActionRecordStore`, `GameAdapter`, `validate_decision` |
| Resources | `ResourceBudget`, `ResourceEstimate`, `ResourceGovernor`, `UsageStore` |
| Persistence and inspection | `open_db`, `db_session`, `load_agent_state`, `save_agent_state`, `agent_timeline`, `replay_action_record` |

Provider integrations use the supported `empneon.providers.llm` namespace. Its
`__all__` declares the provider protocol, request/result types, capabilities,
native LM Studio and OpenAI-compatible implementations, configuration-driven router,
and generation preparation helpers. `ProviderError.status` carries the HTTP status code when an endpoint returned one. Adapter-specific persistent extensions use
`empneon.core.memory.documents.DocumentMemoryStore`; SQLite is the implemented backend.

The supported command-line interface is:

```console
empneon-regress path/to/fixture.json
```

Other modules remain available for development, but paths not documented here or exported
through these `__all__` lists are internal and may change without a compatibility shim.

## Transactions

Every Core store mutator accepts keyword-only `commit` (default `True`). With the default, the
store commits (or rolls back on error) its own writes. Pass `commit=False` to join a transaction you
own, then commit or roll back yourself. `import_agent` uses this to import atomically.

## Levels and limits

`Clod` is an `IntEnum` (`STATE`, `RULES`, `SMALL_MODEL`, `INTERACTIVE`, `CONSEQUENTIAL` = 0-4); plain
integers remain accepted wherever a CLOD is expected. Store `get_for_agent(..., limit)` arguments
must be positive: `0` and negative values raise `ValueError` (SQLite would otherwise treat a
negative limit as unlimited).

## Scheduling

`empneon.core.scheduler.PriorityScheduler` is a bounded queue ordered by urgency (optionally aged,
below), then deadline. A request past its deadline is never returned: `pop` raises
`RequestDeadlineExceeded` (its `request` attribute is the expired request), `expire()` removes and
returns all expired requests, and `submit` discards expired entries before reporting
`SchedulerFull`, so stale work cannot block new requests.

Aging is opt-in: `PriorityScheduler(n, aging_per_second=0.1)` adds that much to a queued request's
effective urgency for every second it waits, so a request with urgency `u` outranks a steady stream
of urgency-`1.0` arrivals after at most `(1 - u) / aging_per_second` seconds (plus requests already
ahead of it). Effective urgency is not clamped, so an aged request can outrank a new urgency-`1.0`
arrival. Without aging (the default `0.0`), a steady stream of urgent requests can starve
low-urgency ones indefinitely.

Aging changes ordering only; deadlines are never extended, so a request whose deadline falls before
its aged turn is still discarded: aging helps requests whose deadline is long relative to
`(1 - u) / aging_per_second`. `expire()` returns expired requests in aged-key order. The rate must
be finite and non-negative. The cost is one multiply and one subtract per `submit`, with no extra
memory.

## Provider resilience

Retries are opt-in. Wrap any provider as `ResilientProvider(provider, RetryPolicy(...))`, or add a
`retry` mapping to a provider or task entry in the `ConfiguredProviderRouter` configuration:

```json
{"retry": {"max_attempts": 3, "base_delay_s": 0.5, "max_delay_s": 8.0, "jitter": 0.2}}
```

`generate` is retried with exponential backoff and jitter on HTTP 408, 425, 429, 500, 502, 503,
504 (override with `retry_statuses`) and on connection-level failures (`ProviderError.transport`).
A server `Retry-After` in seconds is honored, capped at `max_delay_s` (`respect_retry_after`).
Other HTTP statuses and malformed payloads are never retried, `health_check` is never retried,
and cancellation stops retrying immediately. Unknown or mistyped `retry` keys raise `ValueError`.
Without a `retry` block nothing changes. Total latency can reach `max_attempts` times the provider
timeout plus the delays, so size `deadline_ms` accordingly.

### Circuit breaker

Add a `circuit_breaker` mapping (alone or next to `retry`) to stop calling an endpoint that keeps
failing: `{"circuit_breaker": {"failure_threshold": 5, "reset_timeout_s": 30.0}}` (those are the
defaults for an empty block). After `failure_threshold` consecutive retry-exhausted transient
failures the circuit opens and `generate` raises `CircuitOpenError` (a `ProviderError`) immediately,
without calling the provider or sleeping, so the runtime degrades to CLOD 1 at once. After
`reset_timeout_s` one probe call is allowed: success closes the circuit, failure reopens it for a
full timeout. HTTP client errors and malformed payloads show the endpoint is responding and count as
healthy. Without `retry`, a breaker-only config does not retry.

Breaker state is shared per `(provider name, endpoint, model)` so it survives routers that are
rebuilt for every call (as the Sims 4 adapter does). `ConfiguredProviderRouter(..., breakers=...)`
accepts a `BreakerRegistry`; otherwise a lazily created process-wide registry is used and
`BreakerRegistry.default().reset()` clears it (for tests or an operator reset). Compose directly
with `ResilientProvider(provider, policy, breaker=CircuitBreaker(CircuitBreakerPolicy(...)))`.

## Streaming generation

Streaming is opt-in and separate from `LLMProvider`, so `generate` and custom providers are
unchanged. `StreamingLLMProvider` adds `stream(request) -> AsyncIterator[str]`, which yields
non-empty text deltas as they arrive; `ModelCapabilities.streaming` advertises support.
`OpenAICompatibleProvider` implements it over server-sent events (`"stream": true`), and so does
`LMStudioProvider`, through LM Studio's OpenAI-compatible `/v1/chat/completions` endpoint. Plain
`LMStudioProvider.generate` still uses the native `/api/v1/chat` endpoint with `reasoning: off`;
the streaming path does not send that option. Errors, including mid-stream ones, raise `ProviderError`; chunk content is
never logged.

`ResilientProvider.stream` wraps a streaming provider (otherwise it raises `TypeError`). Retries
apply only before the first chunk, because retrying later would repeat or contradict text already
delivered; a mid-stream failure is raised to the caller after the chunks received so far. With a
breaker, each stream records one outcome: a transient failure counts against the circuit, a
completed stream or non-transient error counts as healthy, and abandoning the stream early frees
the half-open probe slot. An open circuit raises `CircuitOpenError` without calling the provider.
`ConfiguredProviderRouter.stream_for(task)` returns a streaming provider only when the task or
provider config sets `streaming: true` (a non-boolean value raises `ValueError`); it applies the same
`retry` and `circuit_breaker` wrapping as `provider_for`, which is unchanged and ignores the key.
`CognitiveRuntime` has no streaming API: a resolver consumes the stream and returns a `Decision`, so
admission, `deadline_ms` enforcement and CLOD 1 degradation on a mid-stream `ProviderError` apply
as for any resolver.

## Embeddings

`EmbeddingProvider` (`embed(texts) -> EmbeddingResult`, `health_check()`) is a separate protocol from
`LLMProvider`, so custom chat providers are unaffected and the embedding model and endpoint can
differ. `OpenAICompatibleEmbeddingProvider` calls an OpenAI-style `/embeddings` endpoint (OpenRouter,
Ollama, llama.cpp, and LM Studio's OpenAI-compatible `/v1` API). Configure it as an explicit
`embedding` task and build it with `ConfiguredProviderRouter.embedding_provider_for()`:

```json
{"embedding": {"provider": "lmstudio", "model": "nomic-embed-text", "dimensions": 768,
               "batch_size": 64, "normalize": true,
               "retry": {}, "circuit_breaker": {}}}
```

The task must name its own `model`; a missing entry raises `ValueError` instead of reusing the chat
model. For `lmstudio` the native `/api/v1` endpoint is rewritten to `/v1`. Inputs are split into
`batch_size` requests and returned in input order. Vectors are L2-normalized by default so
`VectorMemoryStore`'s Euclidean distance orders like cosine similarity (`normalize: false` returns
raw values). A malformed response (wrong count or index, empty, non-finite or ragged vectors, or a
mismatch with the configured `dimensions`) raises a non-transport `ProviderError`, which retry and
the circuit breaker never retry or count. `retry`, `circuit_breaker`, `Retry-After`, and
cancellation behave exactly as for chat providers (`ResilientEmbeddingProvider`), with breaker state
kept separate from the chat model's.

`VectorMemoryStore` tables are created with fixed dimensions (384 by default) and reject reopening
with different dimensions, so use a new database or table when switching to a model with another
size. The Sims 4 adapter still uses its hashed 384-dimension vectors and does not meter embeddings.
For usage telemetry see Embedding usage telemetry below.

### Semantic memory index

`empneon.core.memory.semantic.SemanticMemoryIndex(conn, embedder, ownership="participants")` turns
an `EmbeddingProvider` into agent-scoped recall by meaning:

```python
index = SemanticMemoryIndex(conn, router.embedding_provider_for())
await index.index_events(events)                 # one embed call; re-indexing replaces vectors
await index.index_unindexed(limit=256)           # backfill events that have no vector yet
matches = await index.search("bella", "that dinner we planned", limit=5)  # [SemanticMatch]
index.remove(event_id)                           # events do not cascade to vectors
```

`search` returns at most `limit` `SemanticMatch(event, distance)` pairs, closest first (0 is
identical; ties by event id), and only events the agent owns: `ownership="participants"` uses
`event_participants`, `"observations"` uses `event_observations`. The vector store is a global
nearest-neighbour search, so the index over-fetches (4x the limit, doubling up to the corpus size)
until enough owned events are found. Vector dimensions come from the embedder's first result and a
table with other dimensions raises `ValueError`. Embedding happens before any write; with
`commit=False` the caller owns the transaction, otherwise a failure rolls back the whole batch.
`ProviderError` (including `CircuitOpenError`) propagates untouched so the caller chooses a
fallback, and no text, query, or vector is logged. Deleting an event leaves its vector behind;
search skips such orphans and `remove` clears them.

## Directors

`empneon.core.directors` is an optional, supported import path (not part of `empneon.__all__`).
A director is a pure proposer: `propose(view: DirectorView) -> tuple[Opportunity, ...]`, with an `id`,
`max_opportunities`, and `max_urgency`. An `Opportunity` (`director_id`, `kind`, `agent_id`, `urgency`,
`deadline_ms`, JSON-compatible `facts`) is a request for cognition and carries no intent, target, or
state change. `run_directors(directors, view, preferred_clod=Clod.RULES)` returns
`CognitiveRequest`s for the host to submit to its own scheduler; Core never calls `submit` and starts
no loop. `to_request` converts one opportunity: the synthetic event has type `opportunity.<kind>`,
carries `director_id` in its facts and the agent's snapshot as `agent_state`, and is never stored.
Ids are deterministic for a fixed `DirectorView`. A raising director is skipped, output is truncated
and urgency clamped to the director's limits, and only counts and exception type names are logged.
`IdleCheckInDirector` is a throwaway reference. Design: [directors-protocol](directors-protocol.md).

## Capability validation

An adapter may publish two optional lists in `AgentStateSnapshot.capabilities`: `intents` (decision
intents it can execute) and `state_paths` (allowed `StateDelta.path` roots, the text before the first
`.`; `relationship` allows `relationship.strength`). A published key restricts, an empty list allows
nothing, and an absent key allows everything. `CognitiveRuntime.process` checks each decision with
`validate_decision(decision, capabilities)` before calling `adapter.execute`: a violation is
recorded as a `rejected` result with the reason and `execute` is never called. Adapters that call
`decide` themselves can use `validate_decision` directly. Malformed lists raise `ValueError` when the
snapshot is built. The CLOD 1 fallback intent `acknowledge` is checked like any other, so include it
in `intents` if fallbacks should execute. The `actions` capability (native action names) is not
checked by Core.

## Degradation telemetry

`CognitiveRuntime(governor, actions, usage=UsageStore(conn))` persists every degradation to CLOD 1
as a `core-rules` / `clod1` usage row with its `DegradationReason` (`provider_error`, `timeout`,
`memory`, `budget`, `invalid_output`). `UsageStore.telemetry()` adds `by_degradation`, a count per
reason (empty when there were none). Without `usage=` nothing is written. Recording failures are
logged (exception type only) and never change the decision. A deliberate CLOD 1 choice, such as a
request below the value threshold, is not a degradation: `CognitiveRuntime.decide_dynamic` records
it (with `usage=`) as a `core-rules` / `clod1` row with `deliberate_clod1` set and no degradation
reason, and `UsageStore.telemetry()` counts those rows under `deliberate_clod1`, never under
`by_degradation`. A request where no route was affordable is neither and is not recorded.
`UsageStore.record(deliberate_clod1=True)` and `UsageRecord.deliberate_clod1` expose the flag; a
record cannot be both deliberate and degraded. Adapters that keep
their own usage rows pass `CognitiveRuntime(on_degrade=callback)` instead: the callback receives the
reason without anything being written (if both `usage=` and `on_degrade` are set, each runs and a
failure in one never affects the other or the decision). `CognitiveRuntime(on_deliberate=callback)` is the writeless counterpart for a deliberate CLOD 1 choice made in `decide_dynamic`. The Sims 4 adapter uses the callback to
attach the reason to the CLOD 1 row it records for player dialogue, and `on_deliberate` to flag deliberate ones. This needs database schema 14
(schema 13 added the nullable `cognition_usage.degradation_reason` column and schema 14 the
`deliberate_clod1` flag, `NOT NULL DEFAULT 0`, so existing rows read as not deliberate); migration
is automatic and forward-only (see Database migrations).

### Embedding usage telemetry

Embedding calls are metered separately from generation, in the `embedding_usage` table (database
schema 15), so the generation aggregates above never mix with them.
`ConfiguredProviderRouter.embedding_provider_for(task, usage=UsageStore(conn).embedding_sink())`
wraps the provider (outermost, with or without `retry` or `circuit_breaker`) in
`UsageMeteredEmbeddingProvider`, which reports one `EmbeddingOutcome` per `embed` call: provider,
model, input count, prompt tokens when the endpoint reports them, wall-clock latency including any
retries, `status` (`succeeded` or `failed`), the HTTP status when there was one, and for failures a
`DegradationReason` value (`ProviderError` and `CircuitOpenError` give `provider_error`,
`TimeoutError` gives `timeout`, `MemoryError` gives `memory`, `ValueError` gives `invalid_output`).
Other exceptions and cancellation record nothing. Without `usage` nothing is written. `UsageStore.telemetry()`
gains an `embeddings` key (`calls`, `by_status`, `by_degradation`, `prompt_tokens`, `latency_ms`);
it is omitted when `telemetry(agent_id)` filters by agent, because embedding calls carry no agent.
Texts, queries, and vectors are never stored or logged, and a sink failure is logged by exception
type only and never fails the embedding. The sink commits only when the connection has no open
transaction, so an embed call inside a caller-owned transaction (`commit=False`) does not commit it.

## Deadlines and failures

`CognitiveRuntime(governor, actions, enforce_deadlines=True)` cancels a resolver that has not
finished within the request's `deadline_ms` and degrades to CLOD 1 (degradation reason `timeout`).
It is off by default. Cancellation always releases the governor reservation. A provider running in
a worker thread continues until its own transport timeout and its result is discarded.

If `adapter.execute` raises in `CognitiveRuntime.process`, Core records a `failed` result with the
reason `adapter raised <ExceptionType>` and no applied changes, logs the exception type only, and
returns that record. `asyncio.CancelledError` and other `BaseException`s still propagate.

## Logging

Core logs through the standard `logging` module under the `empneon` logger namespace and installs
only a `NullHandler`, so applications choose handlers and levels. Records contain event metadata
(degradation reasons, exception type names, schema migration versions) and never prompts, replies,
API keys, or exception messages.

## Versioning

Empneon follows Semantic Versioning. `empneon.__version__` is the single package-version
source used by the build configuration.

- Before `1.0`, a minor release may change the supported API when its release notes include
  the migration steps. Patch releases remain backward compatible.
- From `1.0`, breaking supported-API changes require a major release. Additions are minor,
  and backward-compatible fixes are patches.
- Database schema versions are independent from package versions.

## Database migrations

`open_db` returns a caller-owned connection and automatically applies known schema upgrades in one
transaction. Call `close()` when retaining that connection, or use `with db_session(path) as conn`
for a transaction-scoped connection that always closes. If any migration statement fails, the
transaction rolls back and the connection is closed. A database created by a newer runtime is
rejected instead of being modified.

Before upgrading a persistent world, stop all Empneon processes and back up its database plus
the SQLite `-wal` and `-shm` files when present. Empneon does not automatically downgrade or run
destructive migrations. Rollback means restoring that backup and the earlier Empneon version.
Every new migration must be tested from the preceding schema and against a fresh database.
