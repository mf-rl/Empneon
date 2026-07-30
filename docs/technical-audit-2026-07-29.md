# Technical Audit Remediation — 2026-07-29

This document records the validation and remediation of the external
`Empneon Technical Audit - 2026-07-29`. Every tracked Markdown document and each reported code
path were reviewed before changes were made. Findings were accepted only when the current code
and a reproducible regression supported them.

## Outcome

The review found fourteen actionable issues or narrower variants of issues described by the audit.
Three findings were false, outdated, or proposed a change that would have broken existing
transaction behavior. The accepted work was implemented in remediation-plan order and independently
reviewed. No Critical or Important issue remained after the final review.

| Finding | Assessment and resolution |
|---|---|
| F01 | Dynamic legacy-table SQL was reachable only through constant callers, but the construction was unsafe. Legacy table names now use a closed allowlist. |
| F02 | Legacy schema identifiers were constant in current callers, but the helper accepted arbitrary SQL fragments. Table, column, and type values now use closed allowlists. |
| F03 | Production adapter context managers committed or rolled back without closing raw SQLite connections. The supported `db_session()` context manager now owns transaction completion and closure; production adapter callers use it, while `open_db()` remains explicitly caller-owned for compatibility. |
| F04 | The loopback API had no authentication. `AI_SIM_API_TOKEN` optionally enables constant-time shared-token validation, returns HTTP 401 before request work, and is propagated by the script mod, smoke test, and HTTP simulation client. Authentication remains opt-in to avoid breaking existing local installations. |
| F05 | False. `confirm(commit=False)` participates in its caller's explicit transaction. Adding an inner context manager would have changed atomic confirmation behavior. |
| F06 | The reported deadlock was false because a zero-capacity governor rejects work immediately. Zero concurrency is nevertheless invalid configuration and is now rejected at construction. |
| F07 | Repeated `asyncio.run()` calls created avoidable loops. Backend worker threads now reuse a thread-local event loop. |
| F08 | A failed legacy database open silently redirected writes to a temporary database. The fallback was removed; the configured path and original failure are reported instead. |
| F09 | Real as a responsibility and import-side-effect concentration issue, but the audit incorrectly claimed that importing the backend started cognition workers and opened the database. Workers were already lazy and database work already occurred only in `run()` or explicit calls. Configuration/logging, database/session compatibility, agent scheduling, cognition/response processing, and HTTP dispatch now live in five inert modules: `config.py`, `db.py`, `agent_manager.py`, `cognition.py`, and `server.py`. `ai_sims_server.py` remains the executable compatibility façade with late-bound monkeypatch targets. The cognition runtime is exposed as `CognitionRuntime` / `COGNITION_RUNTIME`. |
| F10 | The audit incorrectly described `Event` as frozen, but store insertion did mutate caller-owned timestamps. Stores now persist copies and leave caller objects unchanged. |
| F11 | The audit incorrectly described lineage as a list append, but belief insertion still mutated caller-owned lineage. Stored beliefs are now copied with derived lineage. |
| F12 | Document-memory timestamps used nanoseconds while the rest of Core used Unix seconds. Schema 12 migrates legacy nanosecond values transactionally and new records use seconds. |
| F13 | Recall loaded an agent's complete event history into Python. Recall now performs exact confirmed-pair filtering in SQL and combines capped 100-row relevance and first/latest boundary windows. Terms are passed as one JSON parameter through SQLite `json_each`, so queries with more than 1,000 normalized terms retain all terms without exceeding expression or variable limits. Relevant old facts, first/last recall, and existing deterministic ranking remain covered. SQLite still scans pair history for term relevance; an FTS index is the documented upgrade if measured latency warrants it. |
| F14 | Timeline assembly loaded every event, action, and belief before applying its limit. Limits now reach each store query, with descending ID tie-breaks consistent with the final timeline ordering. |
| F15 | The reported server race was false because self-test and server execution are mutually exclusive CLI modes. The Phase 2 follow-up nevertheless removed the temporary `DB_PATH`, `CORE_DB_PATH`, and `ACTIVE_DB_PATH` mutation: self-test now operates through one explicit temporary `db_session()` and validates current response and memory shapes. |
| F16 | False. Caught errors return before report rendering and uncaught errors propagate; the reported undefined-variable path is unreachable. |
| F17 | Outdated. Current dialogue name matching already tokenizes whole words rather than using substring matching. |

## Compatibility decisions

- `open_db()` retains its existing raw-connection ownership contract. `db_session()` is the new
  transaction-scoped closing API.
- API authentication is enabled only when `AI_SIM_API_TOKEN` is configured.
- Recall retains deterministic fact validation and old relevant-fact access rather than applying a
  recent-only limit.
- The Sims 4 adapter remains a loopback reference adapter; this work does not claim production
  network hardening or broad scalability.
- No database or legacy migration source is deleted automatically.

## Verification

The Phase 3 decomposition verification on 2026-07-30 produced:

- Core: `231` tests
- The Sims 4 adapter: `333` tests
- Godot adapter: `4` tests
- Shared and release tests: `23` tests
- CLOD regression scenario: `1/1`
- Ruff over the six decomposition backend modules and the modified Sims backend test
- mypy over `52` source files
- Python compilation of the façade and all five extracted modules
- `git diff --check`
- no conflicting cognition-runtime name in tracked Python or Markdown

The broader planned command, `py -3.12 -m ruff check core adapters tests scripts`, still reports
`50` findings, all in unchanged baseline files: `backend/empneon_state.py`, the Sims smoke client,
and the Python 3.7 game script. Those unrelated files were not rewritten as part of the
behavior-preserving decomposition, so repository-wide Ruff is not recorded as passing.

Focused regressions cover hostile SQL identifiers, connection closure, failed database opens,
optional API authentication and client propagation, event-loop reuse, lazy worker startup,
caller-object immutability, schema 11-to-12 timestamp migration, bounded timeline queries with
timestamp ties, and bounded recall with an old relevant fact behind 150 newer events and a query
containing more than 1,000 terms. Phase 2 adds self-test coverage proving current response and
memory shapes while observing that database globals remain unchanged throughout the run. Phase 3
adds inert-import, façade-surface, and late-bound callback coverage for the five extracted modules.
