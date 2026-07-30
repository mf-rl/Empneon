# Sims 4 Backend Decomposition Design

**Status:** Implemented and behaviorally verified on 2026-07-30. The scoped Phase 3 Ruff gate is
clean; the broader repository Ruff command still has 50 findings in unchanged baseline files.

## Goal

Resolve technical-audit finding F-09 by decomposing
`adapters/thesims4/backend/ai_sims_server.py` without changing existing Sims 4
behavior or its Python compatibility surface.

The refactor must also replace the legacy cognition-runtime names with
`CognitionRuntime` / `COGNITION_RUNTIME` to avoid conflict with an existing
agent name.

## Baseline

Before this decomposition, `ai_sims_server.py` owned configuration, logging, database compatibility,
cognition scheduling, response generation and validation, HTTP dispatch, and
the executable entry point. Importing the module loaded configuration and
configured file and stream logging.

The audit overstates two effects: constructing `CognitionQueue` does not start
workers, and importing the module does not open a database. Queue workers start
on the first submitted request, while database migration and opening happen in
`run()` or explicit database calls.

The design finding remained valid because unrelated responsibilities and
import-time effects were concentrated in one module.

## Compatibility Contract

`backend.ai_sims_server` remains:

- the executable backend entry point;
- the stable import location for all existing constants, functions, classes,
  singleton objects, and imported Core types used by tests and scripts;
- the place where existing monkeypatch targets continue to affect runtime
  behavior;
- behaviorally identical for configuration precedence, HTTP routes and status
  codes, JSON response shapes, logging names, database paths and migrations,
  cognition scheduling, dialogue validation, autonomous actions, diagnostics,
  and self-test execution.

The supported cognition-runtime names become `CognitionRuntime` and
`COGNITION_RUNTIME`; the legacy names will not remain as aliases.

## Module Boundaries

Five focused modules were added under `adapters/thesims4/backend/`:

1. `config.py`
   - Default configuration.
   - Recursive configuration merging and environment overrides.
   - Logging setup.
   - Functions accept paths/configuration explicitly so importing the module
     does not read files, create directories, or attach handlers.

2. `db.py`
   - SQLite connection and schema initialization helpers.
   - Memory-session checkpoint file operations.
   - Legacy adapter schema compatibility.
   - Paths and state dependencies are passed explicitly or supplied by the
     compatibility façade.

3. `agent_manager.py`
   - `AgentManager`, `CognitionQueue`, and `Test10QueueGate`.
   - Importing the module creates no singleton and starts no thread.
   - Queue workers retain their existing lazy-start behavior.

4. `cognition.py`
   - `CognitionRuntime`.
   - Prompt construction, provider response normalization, response grounding,
     recalled-fact validation, and deterministic fallback behavior.
   - Runtime collaborators that tests currently monkeypatch through
     `ai_sims_server` are resolved through façade-owned callbacks instead of
     being captured as fixed imported values.

5. `server.py`
   - `EmpneonHTTPServer`, request authentication and validation, and handler
     dispatch.
   - Endpoint operations are supplied through façade-owned callbacks so
     existing monkeypatch targets remain effective.
   - Importing the module does not bind a socket or construct a server.

`ai_sims_server.py` retains minimal composition, compatibility wrappers,
singleton construction, `run()`, and `self_test()`.

## Initialization and Side Effects

Importing every extracted module is inert: no configuration file reads,
logging file creation, database connections, worker threads, migrations, or
server sockets.

For compatibility, importing `ai_sims_server` may continue to expose the
currently configured constants and singleton objects. Logging initialization
moved to `run()` and remains safe for direct function/test use through
standard named loggers without attached file handlers.

The existing singletons remain process-wide:

- `AGENTS`
- `COGNITION_QUEUE`
- `TEST10_QUEUE_GATE`
- `COGNITION_RUNTIME`
- `CORE_GOVERNOR`

Their construction must not start background work or perform I/O.

## Implementation Sequence

Each extraction was performed independently:

1. [x] Rename the cognition runtime class and singleton and update references.
2. [x] Extract configuration and logging.
3. [x] Extract scheduling and agent management.
4. [x] Extract database/session compatibility.
5. [x] Extract cognition and response processing.
6. [x] Extract HTTP server handling.
7. [x] Reduce `ai_sims_server.py` to composition and compatibility exports.
8. [x] Update the technical-audit status and current architecture documentation.

The Sims 4 tests run after every step. A failed step is corrected before the
next boundary moves.

## Verification

Regression coverage verifies:

- each extracted module imports without creating threads, files, database
  connections, or sockets;
- `backend.ai_sims_server` continues to expose the expected compatibility
  symbols;
- monkeypatching façade-level collaborators still changes the executed path;
- queue workers remain lazy and use one event loop per worker;
- existing Sims 4 backend, shared integration, Core, Godot, release, typing,
  compilation, and scenario behavior remains green.

The complete 2026-07-30 run produced 231 Core, 333 Sims 4, 4 Godot, and 23 shared/release
passing tests, plus the documented `1/1` regression scenario. mypy passed over 52 source files;
the façade and five extracted modules compiled; `git diff --check` and the conflicting-name grep
were clean. Ruff passed over the six decomposition backend modules and modified Sims test. The
broader `py -3.12 -m ruff check core adapters tests scripts` command reported 50 findings in
unchanged `empneon_state.py`, Sims smoke-client, and Python 3.7 game-script files.

## Non-Goals

- No HTTP contract, response schema, prompt policy, database schema, migration,
  provider behavior, scheduling policy, or gameplay behavior changes.
- No new dependency-injection framework, service container, package, or public
  API.
- No cleanup unrelated to the five module boundaries.
- No pull request or branch integration as part of implementation.
