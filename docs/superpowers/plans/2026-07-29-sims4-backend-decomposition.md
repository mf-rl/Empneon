# Sims 4 Backend Decomposition Implementation Plan

**Status:** Tasks 1–7 are complete and independently approved. Task 8 documentation and
verification ran on 2026-07-30; all behavioral/static gates pass except the broad repository Ruff
command, which retains 50 findings in unchanged baseline files.

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve audit finding F-09 by splitting the Sims backend into five
inert, focused modules while preserving `backend.ai_sims_server` as the
executable compatibility façade and preserving all existing gameplay behavior.

**Architecture:** Extract configuration, database compatibility, cognition
scheduling, response generation, and HTTP dispatch behind façade-owned
wrappers or late-bound callbacks. Keep initialization and public compatibility
symbols in `ai_sims_server.py`. Rename the cognition runtime to
`CognitionRuntime` / `COGNITION_RUNTIME` across code, tests, and documentation.

**Tech Stack:** Python 3.11+, standard library, SQLite, existing Empneon Core,
pytest, Ruff, mypy.

## Global Constraints

- Preserve all HTTP routes, status codes, JSON shapes, database behavior,
  provider behavior, prompt behavior, scheduling, and Sims gameplay behavior.
- Preserve existing `backend.ai_sims_server` imports and monkeypatch targets,
  except for the explicitly requested cognition-runtime rename.
- Extracted modules perform no I/O and start no threads when imported.
- Add no dependencies or framework.
- Run the Sims suite after every extraction boundary.
- Do not commit or push until the user explicitly requests it.

---

### Task 1: Rename the cognition runtime

**Files:**

- Modify: `adapters/thesims4/backend/ai_sims_server.py`
- Modify: `adapters/thesims4/tests/test_sims4_backend.py`
- Modify: tracked Markdown files containing the legacy runtime name

**Produces:**

- `CognitionRuntime`
- `COGNITION_RUNTIME`
- No repository reference to the conflicting legacy name

- [x] **Step 1: Update one representative test to use the new singleton**

Add:

```python
def test_cognition_runtime_is_exposed() -> None:
    assert isinstance(
        ai_sims_server.COGNITION_RUNTIME,
        ai_sims_server.CognitionRuntime,
    )
```

- [x] **Step 2: Run the representative test and verify RED**

From `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k cognition_runtime
```

Expected: failure because the new class/singleton names do not exist yet.

- [x] **Step 3: Rename the class, singleton, and runtime call sites**

Rename only identifiers; do not retain aliases for the old names.

- [x] **Step 4: Replace the legacy name in all tracked tests and Markdown**

Use neutral historical wording where a document discusses the old component,
and the new identifiers where it describes code.

- [x] **Step 5: Verify the conflicting name is absent**

```powershell
$legacyName = 'her' + 'mes'
git grep -in $legacyName -- '*.py' '*.md'
```

Expected: no output.

- [x] **Step 6: Run the Sims suite**

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests
```

Expected: all tests pass.

---

### Task 2: Distribute import-side-effect coverage

**Execution decision:**

- [x] Add each extracted-module import regression in its corresponding Task
  3–7 RED step and make it GREEN in that same task.
- [x] Add the complete façade compatibility-surface assertion in Task 7 after
  all five modules exist.

This replaces the original standalone Task 2, which would have deliberately
left the Sims suite failing between extraction boundaries and conflicted with
the plan's global green-suite constraint.

---

### Task 3: Extract configuration and logging

**Files:**

- Create: `adapters/thesims4/backend/config.py`
- Modify: `adapters/thesims4/backend/ai_sims_server.py`
- Modify: `adapters/thesims4/tests/test_sims4_backend.py`

**Moves:**

- `DEFAULT_CONFIG`
- `deep_update`
- configuration file/environment parsing
- logging-handler setup

- [x] **Step 1: Add focused configuration compatibility tests**

Cover:

- defaults are copied rather than mutated;
- existing environment-variable precedence is unchanged;
- malformed optional config still reports the same error path;
- importing `backend.config` creates no log directory or handler.

- [x] **Step 2: Run the focused tests and verify RED**

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "config_module or configuration_precedence"
```

- [x] **Step 3: Implement inert configuration helpers**

Make paths, environment mappings, and error streams explicit arguments in
`backend.config`. Keep no module-level file read or handler installation.

In the façade:

- keep `CONFIG_PATH`, `CONFIG`, and all derived constants;
- expose compatible `deep_update()`, `load_config()`, and `setup_logging()`;
- initialize named loggers without file handlers at import;
- attach the existing rotating handlers from `run()` exactly once.

- [x] **Step 4: Run focused tests and the full Sims suite**

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "config_module or configuration_precedence or import"
py -3.12 -m pytest -q -p no:cacheprovider tests
```

Expected: all tests pass.

---

### Task 4: Extract agent and queue management

**Files:**

- Create: `adapters/thesims4/backend/agent_manager.py`
- Modify: `adapters/thesims4/backend/ai_sims_server.py`
- Modify: `adapters/thesims4/tests/test_sims4_backend.py`

**Moves:**

- `CognitionQueue`
- `Test10QueueGate`
- `AgentManager`

- [x] **Step 1: Add a late-binding compatibility test**

Prove that:

- importing `backend.agent_manager` starts no worker;
- façade construction starts no worker;
- the first queue submission still starts the configured worker count;
- a façade-level profile callback replacement is observed by `AGENTS`.

- [x] **Step 2: Run the focused tests and verify RED**

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "agent_manager_module or queue_workers"
```

- [x] **Step 3: Move the three classes**

Use constructor callbacks for profile lookup, clock access, and logging only
where the class already depends on façade behavior. Keep:

- the scheduler and queue data structures unchanged;
- lazy worker startup unchanged;
- thread names, daemon status, timeouts, records, and exception propagation
  unchanged.

Construct and re-export `AGENTS`, `COGNITION_QUEUE`, and `TEST10_QUEUE_GATE`
from the façade.

- [x] **Step 4: Run queue tests and the full Sims suite**

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "queue or agent or import"
py -3.12 -m pytest -q -p no:cacheprovider tests
```

Expected: all tests pass.

---

### Task 5: Extract database and memory-session compatibility

**Files:**

- Create: `adapters/thesims4/backend/db.py`
- Modify: `adapters/thesims4/backend/ai_sims_server.py`
- Modify: `adapters/thesims4/tests/test_sims4_backend.py`

**Moves:**

- low-level connection creation
- `init_db` and `ensure_column`
- memory checkpoint backup/restore/create operations
- memory-session JSON read/write and identifier validation

- [x] **Step 1: Add path late-binding and schema compatibility tests**

Verify:

- monkeypatching façade `DB_PATH` and `ACTIVE_DB_PATH` still controls
  `connect_db()`;
- monkeypatching façade `sqlite3.connect` and `init_db` remains effective;
- legacy schema identifier validation is unchanged;
- importing `backend.db` opens no connection and creates no file.

- [x] **Step 2: Run the focused tests and verify RED**

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "database_module or legacy_database or legacy_schema"
```

- [x] **Step 3: Move low-level database functions**

Keep path selection in façade wrappers so existing global monkeypatches are
read at call time. Pass explicit paths into extracted checkpoint/session
helpers. Re-export every existing function through `ai_sims_server`.

Do not change SQL, transaction boundaries, row factories, pragmas, migration
order, exception types, or fallback behavior.

- [x] **Step 4: Run database/session tests and the full Sims suite**

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "database or memory_session or legacy"
py -3.12 -m pytest -q -p no:cacheprovider tests
```

Expected: all tests pass.

---

### Task 6: Extract cognition and response processing

**Files:**

- Create: `adapters/thesims4/backend/cognition.py`
- Modify: `adapters/thesims4/backend/ai_sims_server.py`
- Modify: `adapters/thesims4/tests/test_sims4_backend.py`

**Moves:**

- response schemas and normalization
- JSON extraction and fallback construction
- memory selection and context/prompt construction
- category, role-confusion, grounding, and recall validation
- deterministic reasoning fallback
- `CognitionRuntime`

- [x] **Step 1: Add façade monkeypatch compatibility tests**

Verify that replacing `ai_sims_server.llm_chat` changes
`COGNITION_RUNTIME.dialogue()` and that replacing the singleton's `dialogue`
method changes `chat()`.

- [x] **Step 2: Run focused tests and verify RED against a direct extraction**

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "cognition_module or facade_monkeypatch"
```

- [x] **Step 3: Move the cohesive cognition block**

Keep schemas and pure helpers owned by `backend.cognition`. Supply provider
generation and other mutable façade collaborators through late-bound
callbacks. Re-export existing helper names from `ai_sims_server`.

Do not rewrite or simplify prompts, matching expressions, retry order,
normalization defaults, rejection diagnostics, or fallback text during the
move.

- [x] **Step 4: Run cognition tests and the full Sims suite**

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "dialogue or response or recall or grounding or cognition or prompt"
py -3.12 -m pytest -q -p no:cacheprovider tests
```

Expected: all tests pass.

---

### Task 7: Extract HTTP server and dispatch

**Files:**

- Create: `adapters/thesims4/backend/server.py`
- Modify: `adapters/thesims4/backend/ai_sims_server.py`
- Modify: `adapters/thesims4/tests/test_sims4_backend.py`

**Moves:**

- `EmpneonHTTPServer`
- `Handler`
- authentication, body validation, JSON responses, and route dispatch

- [x] **Step 1: Add dynamic-dispatch compatibility tests**

Verify that handler calls resolve patched façade values at request time,
including `API_TOKEN`, cognition queue diagnostics, and one endpoint function.
Verify importing `backend.server` binds no socket.

- [x] **Step 2: Run focused tests and verify RED**

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "server_module or http or handler"
```

- [x] **Step 3: Move server classes with one late-bound resolver**

Give `Handler` a façade-installed name resolver rather than copying endpoint
globals into `server.py`. Preserve:

- authorization rules and token comparison;
- request-size and content parsing behavior;
- all route names and methods;
- exception-to-status mapping and response bodies;
- `allow_reuse_address`;
- existing logging.

Re-export both classes from `ai_sims_server`.

- [x] **Step 4: Run HTTP tests and the full Sims suite**

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "http or handler or diagnostic"
py -3.12 -m pytest -q -p no:cacheprovider tests
```

Expected: all tests pass.

---

### Task 8: Documentation and complete verification

**Files:**

- Modify: `docs/technical-audit-2026-07-29.md`
- Modify: relevant repository architecture and Sims backend Markdown
- Modify: `docs/superpowers/specs/2026-07-29-sims4-backend-decomposition-design.md`
- Modify: this plan

- [x] **Step 1: Update audit status**

Record:

- F-09 was real as a responsibility/side-effect concentration issue;
- the original audit incorrectly claimed import-time worker and database
  startup;
- the five extracted modules and compatibility façade;
- the cognition-runtime rename;
- verification evidence.

- [x] **Step 2: Update current architecture documentation**

Describe the five module boundaries and keep historical documents factually
correct without the conflicting name.

- [ ] **Step 3: Run static checks**

From repository root:

```powershell
py -3.12 -m ruff check core adapters tests scripts
$env:PYTHONPATH='core\src;adapters\thesims4\src'
py -3.12 -m mypy core\src adapters\thesims4\src adapters\godot\src
py -3.12 -m py_compile adapters\thesims4\backend\ai_sims_server.py adapters\thesims4\backend\config.py adapters\thesims4\backend\db.py adapters\thesims4\backend\agent_manager.py adapters\thesims4\backend\cognition.py adapters\thesims4\backend\server.py
git diff --check
$legacyName = 'her' + 'mes'
git grep -in $legacyName -- '*.py' '*.md'
```

Expected: all checks pass and the final grep has no output.

2026-07-30 result: mypy passed over 52 files, compilation passed for all six backend modules,
`git diff --check` passed, and the conflicting-name grep had no output. Ruff passed for the six
decomposition modules plus the modified Sims test. The broader command above remains open: it
reports 50 findings confined to unchanged `empneon_state.py`, Sims smoke-client, and Python 3.7
game-script files.

- [x] **Step 4: Run all automated suites**

Core:

```powershell
$env:PYTHONPATH='src'
py -3.12 -m pytest -q -p no:cacheprovider tests
```

Sims 4:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests
```

Godot:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests
```

Shared and release:

```powershell
$env:PYTHONPATH='.'
py -3.12 -m pytest -q -p no:cacheprovider tests scripts/test_release.py
```

- [x] **Step 5: Run the existing scenario verification**

Execute the repository's documented one-scenario regression command and verify
`1/1` passes.

- [x] **Step 6: Inspect final scope**

```powershell
git status --short
git diff --stat
git diff -- docs/technical-audit-2026-07-29.md
```

Confirm no unrelated files changed and leave all work uncommitted.
