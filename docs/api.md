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
| Contracts | `WorldEvent`, `CognitiveRequest`, `Decision`, `StateDelta`, `ActionResult`, `AgentStateSnapshot` |
| Runtime | `CognitiveRuntime`, `ActionRecordStore`, `GameAdapter` |
| Resources | `ResourceBudget`, `ResourceEstimate`, `ResourceGovernor`, `UsageStore` |
| Persistence and inspection | `open_db`, `db_session`, `load_agent_state`, `save_agent_state`, `agent_timeline`, `replay_action_record` |

Provider integrations use the supported `empneon.providers.llm` namespace. Its
`__all__` declares the provider protocol, request/result types, capabilities,
native LM Studio and OpenAI-compatible implementations, configuration-driven router,
and generation preparation helpers. Adapter-specific persistent extensions use
`empneon.core.memory.documents.DocumentMemoryStore`; SQLite is the implemented backend.

The supported command-line interface is:

```console
empneon-regress path/to/fixture.json
```

Other modules remain available for development, but paths not documented here or exported
through these `__all__` lists are internal and may change without a compatibility shim.

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
