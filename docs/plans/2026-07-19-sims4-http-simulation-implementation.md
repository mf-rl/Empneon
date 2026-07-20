# Sims 4 HTTP Simulation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run a standard-library harness that reproduces Empneon Social HTTP traffic and verifies Core state through diagnostics.

**Architecture:** One Python script owns payload construction, HTTP calls, assertions, database counts, and JSON reporting. Tests replace its HTTP function with a deterministic fake; the live run targets the installed backend and current database.

**Tech Stack:** Python 3.11, `urllib.request`, `sqlite3`, `json`, existing `pytest`.

## Global Constraints

- Run live tests against `http://127.0.0.1:8765` and `C:\Users\mauri\Downloads\Empneon-TheSims4-0.3.0\empneon_core_memory.sqlite3`.
- Mutate state only through public HTTP endpoints; direct database access is read-only.
- Prefix synthetic IDs and names with `empneon-test-`; never delete existing records.
- Use a unique run ID so repeated runs do not collide.
- Never collect configuration, API keys, save files, or legacy databases.
- Keep actual Sims API extraction, native execution, and game save/load as manual tests.

---

### Task 1: HTTP contract and report primitives

**Files:**
- Create: `adapters/thesims4/scripts/simulate_http_interactions.py`
- Create: `adapters/thesims4/tests/test_http_simulation.py`

**Interfaces:**
- Produces: `request_json(method: str, url: str, payload: dict | None = None, timeout: int = 120) -> dict`
- Produces: `sim_payload(run_id: str, role: str, *, mood: str = "fine", needs: dict | None = None) -> dict`
- Produces: `chat_payload(run_id: str, speaker: dict, listener: dict, message: str) -> dict`
- Produces: `confirmation_payload(chat_response: dict, status: str, reason: str = "") -> dict`
- Produces: `database_counts(path: Path) -> dict[str, int]`

- [ ] **Step 1: Write failing contract tests**

```python
from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import simulate_http_interactions as simulation


def test_chat_payload_matches_mod_contract() -> None:
    speaker = simulation.sim_payload("run-1", "b", mood="uncomfortable", needs={"bladder": 10})
    listener = simulation.sim_payload("run-1", "a")
    payload = simulation.chat_payload("run-1", speaker, listener, "The code is BLUE-731")

    assert payload["speaker"] == speaker
    assert payload["listener"] == listener
    assert payload["event"] == {"type": "player_conversation", "source": "http_simulation"}
    assert payload["available_actions"]
    assert payload["message"] == "The code is BLUE-731"


def test_confirmation_uses_proposed_decision_and_action() -> None:
    payload = simulation.confirmation_payload(
        {"decision_id": "decision-1", "animation": "friendly_chat"}, "succeeded"
    )
    assert payload == {
        "decision_id": "decision-1",
        "action": "friendly_chat",
        "status": "succeeded",
        "reason": "",
        "changes": [],
    }
```

- [ ] **Step 2: Run the contract tests and verify they fail**

Run: `py -3.12 -m pytest -q -p no:cacheprovider tests/test_http_simulation.py`

Expected: collection fails because `simulate_http_interactions` does not exist.

- [ ] **Step 3: Implement the minimal primitives**

Create the script with `AVAILABLE_ACTIONS` copied from the mod, `urllib.request.Request` for JSON
I/O, deterministic synthetic payload fields, validation that confirmation has both decision and
action, and read-only counts for these existing tables:

```python
COUNT_TABLES = (
    "agents",
    "events",
    "beliefs",
    "action_proposals",
    "action_results",
    "cognition_usage",
)


def confirmation_payload(response: dict, status: str, reason: str = "") -> dict:
    decision_id = str(response.get("decision_id") or "")
    action = str(response.get("suggested_action") or response.get("animation") or "")
    if not decision_id or not action:
        raise ValueError("chat response lacks decision or action")
    return {
        "decision_id": decision_id,
        "action": action,
        "status": status,
        "reason": reason,
        "changes": [],
    }
```

- [ ] **Step 4: Run focused tests**

Run: `py -3.12 -m pytest -q -p no:cacheprovider tests/test_http_simulation.py`

Expected: all contract tests pass.

- [ ] **Step 5: Commit the contract layer**

```powershell
git add adapters/thesims4/scripts/simulate_http_interactions.py adapters/thesims4/tests/test_http_simulation.py
git commit -m "test(sims4): add HTTP simulation contract"
```

### Task 2: End-to-end scenarios

**Files:**
- Modify: `adapters/thesims4/scripts/simulate_http_interactions.py`
- Modify: `adapters/thesims4/tests/test_http_simulation.py`

**Interfaces:**
- Consumes: all Task 1 functions.
- Produces: `run_scenarios(base_url: str, database: Path) -> dict`
- Produces: process exit code `0` only when every scenario passes.

- [ ] **Step 1: Write failing scenario tests**

Use `monkeypatch.setattr(simulation, "request_json", fake_request)` with a stateful fake that
returns health, chat proposals, confirmations, diagnostics, replay, identity, and autonomy. Assert
that:

```python
report = simulation.run_scenarios("http://example.test", database)
assert report["passed"] is True
assert [item["name"] for item in report["scenarios"]] == [
    "health",
    "canonical_state",
    "successful_confirmation",
    "failed_confirmation",
    "private_fact",
    "topical_retrieval",
    "usage",
    "timeline_and_replay",
    "identity_round_trip",
]
assert report["database"]["before"]["agents"] <= report["database"]["after"]["agents"]
```

Add one failure test where `/health` raises `URLError`; assert the report marks `health` failed,
contains the exception text, and does not issue mutation requests.

- [ ] **Step 2: Run scenario tests and verify they fail**

Run: `py -3.12 -m pytest -q -p no:cacheprovider tests/test_http_simulation.py`

Expected: failures report that `run_scenarios` is missing.

- [ ] **Step 3: Implement sequential scenarios**

Implement one `record(name, callable)` helper inside `run_scenarios`. It captures start/end time,
response evidence, and exceptions without adding a class hierarchy. Use three synthetic Sims:
`a` as listener/player, `b` as the informed responder, and `c` as the uninformed responder.

For every chat, call `/chat`, then confirm the returned decision through `/action-result`.
Successful confirmation sends `status="succeeded"`; the failure scenario sends
`status="failed"` and `reason="simulated native cancellation"`. Validate:

- B's low bladder produces an active `Restore bladder` goal and normalized uncomfortable emotion.
- Success replay has `consequence_integrity: true` and a succeeded result.
- Failure replay has no applied changes and a failed result.
- After confirming `PRIVATE-GARDEN-<run>` to B, B has matching belief/memory while C does not.
- A paraphrased question to B produces a proposal and leaves the original fact accessible.
- B usage includes a provider-backed request; `/autonomous` adds provider `core-rules`, CLOD 1.
- Timeline contains events and decisions created by the run.
- Export, import, and second export preserve agent ID and canonical identity fields.

- [ ] **Step 4: Add CLI and JSON output**

Use `argparse` with:

```text
--base-url  default http://127.0.0.1:8765
--database  required for the live run
--output    optional; default output/http-simulation-<UTC timestamp>.json
```

Write the report with `json.dump(..., indent=2)`, print one line per scenario plus the report path,
and return exit code `1` when any scenario failed.

- [ ] **Step 5: Run focused tests**

Run: `py -3.12 -m pytest -q -p no:cacheprovider tests/test_http_simulation.py`

Expected: all HTTP simulation tests pass.

- [ ] **Step 6: Commit the scenario runner**

```powershell
git add adapters/thesims4/scripts/simulate_http_interactions.py adapters/thesims4/tests/test_http_simulation.py
git commit -m "test(sims4): automate Core HTTP scenarios"
```

### Task 3: Documentation, regression checks, and live run

**Files:**
- Modify: `adapters/thesims4/docs/in-game-core-feature-test-plan.md`
- Generated, untracked: `adapters/thesims4/output/http-simulation-*.json`

**Interfaces:**
- Consumes: Task 2 CLI.
- Produces: a live JSON evidence report and a reduced manual-test list.

- [ ] **Step 1: Document the automated command**

Add an `Automated backend preflight` section with this exact command:

```powershell
py -3.12 .\scripts\simulate_http_interactions.py `
  --database 'C:\Users\mauri\Downloads\Empneon-TheSims4-0.3.0\empneon_core_memory.sqlite3'
```

State that it adds `empneon-test-*` records, requires the backend and provider, and does not
replace the four remaining in-game checks listed in the design.

- [ ] **Step 2: Run adapter and release regression checks**

Run from `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider
py -3.12 -m ruff check .
py -3.12 -m mypy src backend
```

Run from the repository root:

```powershell
$env:PYTHONPATH='.'
py -3.12 -m pytest -q -p no:cacheprovider scripts/test_release.py
```

Expected: every command exits `0`.

- [ ] **Step 3: Run against the installed backend and current database**

Run from `adapters/thesims4`:

```powershell
py -3.12 .\scripts\simulate_http_interactions.py `
  --database 'C:\Users\mauri\Downloads\Empneon-TheSims4-0.3.0\empneon_core_memory.sqlite3'
```

Expected: exit `0`, nine passing scenarios, and a report under `output/`. If an assertion fails,
preserve its response in the report and diagnose the backend before changing the assertion.

- [ ] **Step 4: Inspect database evidence read-only**

Run:

```powershell
sqlite3 'C:\Users\mauri\Downloads\Empneon-TheSims4-0.3.0\empneon_core_memory.sqlite3' `
  "select id,name from agents where id like 'empneon-test-%' order by id;"
```

Expected: only synthetic IDs created by the harness are returned; existing game agents remain.

- [ ] **Step 5: Commit documentation and final verification state**

```powershell
git add adapters/thesims4/docs/in-game-core-feature-test-plan.md
git commit -m "docs(sims4): add backend simulation preflight"
```

Do not commit the live JSON report because it can contain generated dialogue.
