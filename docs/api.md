# Package, API, and Compatibility Policy

Empneon `0.4.0` supports Python 3.11 or newer. It is a pre-1.0 developer release:
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
| Runtime | `CognitiveRuntime`, `ActionRecordStore`, `GameAdapter` |
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

`empneon.core.scheduler.PriorityScheduler` is a bounded queue ordered by urgency, then deadline. A
request past its deadline is never returned: `pop` raises `RequestDeadlineExceeded` (its `request`
attribute is the expired request), `expire()` removes and returns all expired requests, and
`submit` discards expired entries before reporting `SchedulerFull`, so stale work cannot block new
requests.

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
