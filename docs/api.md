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
