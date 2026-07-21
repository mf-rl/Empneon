# Task 7 report

## Status

**NOT COMPLETE.** Documentation, source build, installation, and the live-test handoff are ready,
but Test 5 remains **PARTIAL** pending the user's in-game run and the Ruff gate awaits an owner
decision on whether the 119-finding broad legacy scope is required.

Documentation commit: `9869226 docs(sims4): prepare state-aware Test 5 retest`

Review-fix commit: `39178db fix(core): close Task 7 verification gaps`

## Documentation

- `core/docs/adapter-development.md`: common/native snapshot contract, normalized ranges,
  latest-snapshot persistence, proposal/confirmation authority boundary.
- `adapters/thesims4/docs/in-game-core-feature-test-plan.md`: exact source-build Test 5 and manual
  cancellation checklist.
- `adapters/thesims4/docs/in-game-core-feature-test-results.md`: observed Karmine response,
  automated regression, and partial in-game status.
- `adapters/thesims4/docs/setup.md`: development build/install/source-backend workflow.
- Approved design spec unchanged; verified behavior matches it.

## Verification

Run from the named component directories:

- `core`: `$env:PYTHONPATH='src'; py -3.12 -m pytest -q -p no:cacheprovider tests` — **174 passed**.
- `adapters/thesims4`: `$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests` — **71 passed, 1 failed** on two fresh full runs.
  `test_prepare_database_adopts_legacy_core_without_modifying_it` detects changed source-database
  bytes. Its immediate predecessor is `test_unified_database_is_the_only_active_default`; the
  failing test passes alone (**1 passed**). No production fix was attempted under Task 7.
- `adapters/godot`: `$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests` — **2 passed**.
- repository root: `$env:PYTHONPATH='core\src;adapters\thesims4\src;adapters\godot\src'; py -3.12 -m pytest -q -p no:cacheprovider tests` — **3 passed**.
- repository root: `$env:PYTHONPATH='.'; py -3.12 -m pytest -q -p no:cacheprovider scripts/test_release.py` — **18 passed**.
- `py -3.12 -m py_compile adapters/thesims4/backend/ai_sims_server.py adapters/thesims4/backend/empneon_state.py adapters/thesims4/ts4script/ai_sims_agent.py` — **passed**.
- `$env:PYTHONPATH='core\src'; py -3.12 -m empneon.cli.regress core/scenarios/clod1-regressions.json` — **failed**, because `empneon.cli` does not exist. The configured implementation,
  `py -3.12 -m empneon.benchmarks.regression core/scenarios/clod1-regressions.json`, passed
  **1/1 cases**.
- `py -3.12 -m ruff check core/src core/tests adapters/thesims4/src adapters/thesims4/tests adapters/thesims4/backend adapters/thesims4/ts4script adapters/godot/src adapters/godot/tests tests scripts` — **120 errors** in existing production scope.
- `py -3.12 -m mypy core/src adapters/thesims4/src adapters/godot/src` — **10 errors in 2 files**, `core/contracts.py` and the Sims adapter; **51 source files checked**.
- `git diff --check` — **passed** before commit.

The first sandboxed Core attempts hit the warned invalid repository CWD and inaccessible pytest
temp-directory conditions; the authoritative Core result above used the correct component CWD and
normal pytest temp access.

## Development build and backend

- `adapters/thesims4`: `py -3.12 .\build_mod.py` — passed.
- `dist/Empneon_TheSims4.ts4script`: **51,775 bytes**, SHA-256
  `E90D1194C98F203D764433A78369F9D463607E86762E5411A3EB4C905A712952`.
- `dist/Empneon_TheSims4.package`: **358 bytes**, SHA-256
  `B9F7F0758F07EFA1582E69E676E9755D44D4E049013918469D8AAEC43EF74622`.
- `.\install_mod.ps1` installed both files to
  `C:\Users\mauri\Documents\Electronic Arts\The Sims 4\Mods`; installed hashes match `dist`.
- Source backend started with `$env:PYTHONPATH='..\..\core\src;src'`; `/health` returns `status: ok`
  on `127.0.0.1:8765`. Listener PID at handoff: **11492**.

SQLite `-shm`/`-wal` sidecars were preserved and remain unstaged. Generated build artifacts and
reports were not staged.

## In-game Test 5 handoff

Use a disposable save. With Karmine, record `ai.relationship` before and after a romantic
invitation and capture the exact player message, displayed response, decision ID, selected native
action, finishing result, and whether the session continued or closed. Verify all of the following:

- original grounded dialogue is displayed;
- Empneon Social stays queued while the backend works;
- autonomy does not interrupt the session;
- every displayed turn updates memory and Empneon trust;
- a selected native action finishes before another input;
- only game-observed friendship/romance changes persist;
- cancelling the queue during a second backend wait suppresses the late result.

Do not mark Test 5 passed until natural dialogue, held queue lifecycle, cognitive delivery
confirmation, and at least one game-confirmed native relationship result all pass.

## Self-review

- Documentation states only behavior covered by the implementation/tests.
- Test 5 remains partial and contains no fabricated live evidence.
- No design-spec change was needed. Small production type-safety fixes were made in
  `core/contracts.py` and the Sims adapter: snapshot input conversion now narrows values before
  conversion, and Sims snapshot mappings/numeric relationship fields are typed and validated.
- Blocking verification failures and the stale regression command are reported rather than hidden.

## Review remediation evidence

This section supersedes the earlier blocked automated results while retaining them above as the
original evidence that triggered review.

### SQLite order failure

- Before the fix, the full Sims suite failed with **71 passed, 1 failed**. The requested exact
  sequence of `test_unified_database_is_the_only_active_default` followed by
  `test_prepare_database_adopts_legacy_core_without_modifying_it` passed **2/2**, as did the full
  22-test prefix. The failure therefore depended on collection/garbage-collection timing, not the
  named predecessor.
- Root cause attribution: the regression used `with open_db(old)` as though `sqlite3.Connection`'s
  context manager closes the connection. It only controls the transaction. A diagnostic held that
  connection explicitly and proved source bytes were unchanged during `prepare_database`, then
  changed only when the leaked legacy connection closed and checkpointed WAL (header
  `0000000100000001` to `0000000200000035`).
- Minimal fix: wrap both test connections in `contextlib.closing`. Production migration already
  opens the source read-only and closes it; no production migration change was justified.
- After the fix: exact two-test sequence **2 passed**; full Sims suite **72 passed**.

### Type and command corrections

- Core snapshot parsing now narrows scalar/list inputs before conversion. The Sims adapter uses
  string-key mappings, typed snapshot sections, and validated numeric relationship extraction.
- `py -3.12 -m mypy core/src adapters/thesims4/src adapters/godot/src` — **no issues in 51 files**.
- The implementation plan and Task 7 brief now use the real module,
  `empneon.benchmarks.regression`; the deterministic scenario passed **1/1**.
- Test 5 now explicitly overrides common release setup with the feature-worktree source workflow.

### Final verification after review fixes

- Exact SQLite sequence: **2 passed**.
- Sims full suite: **72 passed**.
- Core: **174 passed**.
- Godot: **2 passed**.
- Cross-adapter: **3 passed**.
- Release smoke: **18 passed**.
- `py_compile`: passed for the backend, state bridge, and script mod.
- Changed-file Ruff: passed.
- Established critical Ruff selection (`--select E9,F63,F7,F82`) across the backend, state bridge,
  script mod, and Sims tests: passed.
- `git diff --check`: passed.
- Broad legacy Ruff scope was measured but intentionally not cleaned: **119 findings**. The
  established critical selection passes, but the Task 7 Ruff gate awaits the owner's scope
  decision; Task 7 is not complete until that decision and the in-game Test 5 handoff are resolved.

No `ts4script` source changed, so the already installed source build did not require rebuilding.
The source backend and SQLite sidecars were preserved.
