# Sims 4 Autonomous Sim-Payload Compatibility Implementation Plan

**Execution status:** Completed; automated checks and the live Test 15 retest passed.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing sim-only `aiautonomous` request complete through provider-free CLOD 1 while preserving scheduled speaker/listener autonomy.

**Architecture:** Normalize the actor only at the `/autonomous` persistence boundary: prefer `speaker`, then fall back to `sim`. Keep strict actor identity validation and persist an optional listener only when it has an ID.

**Tech Stack:** Python 3.12, SQLite, pytest, Empneon Core identity and usage stores.

## Global Constraints

- Do not weaken `empneon_state.sync_sim` identity validation.
- Do not change event creation, decisions, action mapping, scheduling, or usage accounting.
- Preserve scheduled `{speaker, listener}` behavior.
- Do not stage, commit, or push until the user explicitly requests it.

---

### Task 1: Accept and persist sim-only autonomous requests

**Files:**
- Modify: `adapters/thesims4/tests/test_sims4_backend.py`
- Modify: `adapters/thesims4/backend/ai_sims_server.py:2843-2871`

**Interfaces:**
- Consumes: `autonomous_action(payload: dict) -> dict`
- Produces: compatibility for both `{sim}` and `{speaker, listener}` payloads

- [x] **Step 1: Write the failing sim-only regression**

Add near the existing autonomous-action tests:

```python
def test_autonomous_action_accepts_sim_only_payload(tmp_path, monkeypatch) -> None:
    core_db = str(tmp_path / "core.sqlite3")
    monkeypatch.setattr(ai_sims_server, "CORE_DB_PATH", core_db)

    proposal = ai_sims_server.autonomous_action(
        {"sim": {"id": "bella", "name": "Bella"}}
    )

    with open_db(core_db) as conn:
        agent = AgentStore(conn).get("bella")
        usage = UsageStore(conn).telemetry("bella")

    assert agent.name == "Bella"
    assert proposal["selected_clod"] == 1
    assert proposal["suggested_action"] == "idle"
    assert usage["by_clod"] == {"1": 1}
    assert usage["by_provider"] == {"core-rules": 1}
    assert usage["actual"]["prompt_tokens"] == 0
    assert usage["actual"]["completion_tokens"] == 0
```

- [x] **Step 2: Run the regression and verify RED**

From `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py::test_autonomous_action_accepts_sim_only_payload
```

Expected: FAIL with `ValueError: observed Sim id is required` from the empty
`speaker` persistence attempt.

- [x] **Step 3: Implement the minimal persistence normalization**

Replace the unconditional participant loop in `autonomous_action` with:

```python
actor = payload.get("speaker") or payload.get("sim") or {}
persist_core_agent(conn, actor)
listener = payload.get("listener")
if isinstance(listener, dict) and listener.get("id"):
    persist_core_agent(conn, listener)
```

This preserves strict actor validation, preserves scheduled speaker precedence,
and ignores only an absent or unidentified optional listener.

- [x] **Step 4: Run the regression and scheduled-autonomy checks**

From `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py::test_autonomous_action_accepts_sim_only_payload tests/test_sims4_backend.py::test_confirmed_friendship_updates_core_relationship tests/test_sims4_mod_autonomy.py
```

Expected: all selected tests PASS.

- [x] **Step 5: Run complete automated verification**

Run the full Sims adapter suite:

```powershell
Set-Location adapters/thesims4
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests
```

Run the full Core suite:

```powershell
Set-Location ../../core
$env:PYTHONPATH='src'
py -3.12 -m pytest -q -p no:cacheprovider tests
```

Run the Godot suite:

```powershell
Set-Location ../adapters/godot
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests
```

Run the shared cross-adapter suite:

```powershell
Set-Location ../..
$env:PYTHONPATH='core\src;adapters\thesims4\src;adapters\godot\src'
py -3.12 -m pytest -q -p no:cacheprovider tests
```

Compile the changed backend and check the diff:

```powershell
Set-Location adapters/thesims4
py -3.12 -m py_compile backend/ai_sims_server.py
Set-Location ../..
git diff --check
```

Expected: every suite passes, compilation succeeds, and `git diff --check`
prints nothing.

- [x] **Step 6: Perform the live Test 15 retest**

Restart the backend with LM Studio still stopped. In the Sims cheat console run:

```text
aiautonomous
empneon.usage
```

Expected: `aiautonomous` reports `Core proposed autonomous action`; usage gains
one CLOD 1 `core-rules` request with zero prompt and completion tokens.

- [x] **Step 7: Record evidence without committing**

Update the Test 15 sections in:

- `adapters/thesims4/docs/in-game-core-feature-test-plan.md`
- `adapters/thesims4/docs/in-game-core-feature-test-results.md`

Record the original HTTP 500, the regression fix, automated verification, and
the live retest result. Keep Test 15 partial until its player-dialogue fallback
and provider-recovery checks also pass. Do not stage, commit, or push.
