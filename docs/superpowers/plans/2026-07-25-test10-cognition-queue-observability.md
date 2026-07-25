# Test 10 Cognition Queue Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this
> plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Execution status:** Implemented; automated and live in-game verification complete.

**Goal:** Make the Sims 4 Test 10 priority gate observable and reproducible without changing
scheduler ordering or existing game, memory, provider, and relationship behavior.

**Architecture:** Add passive state tracking around the existing `CognitionQueue`, expose it through
a read-only loopback diagnostic, and use an explicit auto-releasing loopback gate for deterministic
live priority evidence. The scheduler and production cognition requests remain unchanged.

**Tech Stack:** Python 3.12, Python standard library, existing `PriorityScheduler`,
`ThreadingHTTPServer`, and pytest.

## Global Constraints

- Do not modify `PriorityScheduler`, cognition urgency, CLOD routing, prompts, persistence, game
  queues, relationship behavior, animation, or confirmation.
- Add no dependency, database migration, or configuration flag.
- Keep the Test 10 gate loopback-only, explicitly armed, single-run, and auto-releasing.
- Diagnostic data contains identifiers, event type, urgency, lifecycle state, and timestamps only.
- Retain at most 64 completed lifecycle records in memory; backend restart clears them.
- Synthetic harness actor IDs start with `empneon-test10-`.
- Inspect generated reports for sensitive content; retain reviewed reports when documenting live
  acceptance.
- Do not commit or push until the user explicitly requests it.

---

### Task 1: Observe queue state without changing execution order

**Files:**
- Modify: `adapters/thesims4/backend/ai_sims_server.py:1133-1184`
- Modify: `adapters/thesims4/tests/test_sims4_backend.py:1093-1140`

**Interfaces:**
- Produces: `CognitionQueue.snapshot() -> dict[str, object]`
- Produces snapshot keys: `worker_limit`, `running`, `waiting`, and `recent`
- Preserves: `CognitionQueue.run(request, work)` return, exception, timeout, and priority semantics

- [x] **Step 1: Extend the existing priority test with failing snapshot assertions**

Before releasing the blocker, assert:

```python
snapshot = queue.snapshot()
assert snapshot["worker_limit"] == 1
assert [item["actor_id"] for item in snapshot["running"]] == ["blocker"]
assert {item["actor_id"] for item in snapshot["waiting"]} == {
    "ambient",
    "player",
}
assert all(
    set(item)
    == {
        "request_id",
        "actor_id",
        "event_type",
        "urgency",
        "state",
        "submitted_at",
        "started_at",
    }
    for item in snapshot["running"] + snapshot["waiting"]
)
```

After joining all threads, retain the existing:

```python
assert order == ["blocker", "player", "ambient"]
```

and add:

```python
snapshot = queue.snapshot()
assert snapshot["running"] == []
assert snapshot["waiting"] == []
started = [
    item["actor_id"]
    for item in snapshot["recent"]
    if item["state"] == "started"
]
assert started == ["blocker", "player", "ambient"]
```

- [x] **Step 2: Run the focused test and verify RED**

Run from `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py::test_cognition_queue_prioritizes_waiting_player_work
```

Expected: FAIL because `CognitionQueue.snapshot` does not exist.

- [x] **Step 3: Implement passive bounded lifecycle tracking**

Import `deque` from `collections`. In `CognitionQueue.__init__`, retain the worker count and add
`self._states = {}` plus `self._recent = deque(maxlen=64)`.

Add private helpers that build JSON-compatible records from the existing `CognitiveRequest`:

```python
def _request_state(self, request, state):
    return {
        "request_id": request.id,
        "actor_id": request.agent_id,
        "event_type": request.event.type,
        "urgency": request.urgency,
        "state": state,
        "submitted_at": time.time(),
        "started_at": None,
    }

def _record(self, item, state):
    record = dict(item, state=state, recorded_at=time.time())
    self._recent.append(record)
    AGENT_LOG.info(
        "cognition request %s id=%s actor=%s event=%s urgency=%s queue_depth=%s",
        state,
        record["request_id"],
        record["actor_id"],
        record["event_type"],
        record["urgency"],
        len(self._scheduler),
    )
```

Within the existing condition lock:

- add a `waiting` state before scheduler submission;
- change it to `running` immediately after `pop()` and before `work()`;
- remove it and append `completed` or `failed` in the worker `finally`;
- remove it and append `timed_out` when `run()` times out.

Do not change the scheduler calls, worker count, deadlines, or job-result handling.

Implement:

```python
def snapshot(self):
    with self._condition:
        states = [dict(item) for item in self._states.values()]
        return {
            "worker_limit": self._worker_limit,
            "running": [item for item in states if item["state"] == "running"],
            "waiting": [item for item in states if item["state"] == "waiting"],
            "recent": [dict(item) for item in self._recent],
        }
```

- [x] **Step 4: Run the focused test and verify GREEN**

Run the Step 2 command. Expected: PASS with the original execution order unchanged.

- [x] **Step 5: Add and pass error-cleanup coverage**

Add `test_cognition_queue_snapshot_clears_failed_work`, run a job that raises
`RuntimeError("expected")`, assert `run()` raises the same exception, `running` and `waiting` are
empty, and `recent[-1]["state"] == "failed"`.

Run both cognition-queue tests. Expected: PASS.

---

### Task 2: Expose the read-only loopback diagnostic

**Files:**
- Modify: `adapters/thesims4/backend/ai_sims_server.py:2938-2970`
- Modify: `adapters/thesims4/tests/test_sims4_backend.py`

**Interfaces:**
- Consumes: `COGNITION_QUEUE.snapshot()`
- Produces: `GET /diagnostics/cognition-queue`
- Preserves: every existing `/health`, `/agents/active`, and diagnostic response

- [x] **Step 1: Add the failing route test**

Construct a real handler as existing route tests do, set
`handler.path = "/diagnostics/cognition-queue"`, replace `COGNITION_QUEUE.snapshot` with a fixed
approved response, and assert:

```python
assert responses == [
    (
        200,
        {
            "worker_limit": 1,
            "running": [],
            "waiting": [],
            "recent": [],
        },
    )
]
```

Also assert the route does not call `open_db`.

- [x] **Step 2: Run the route test and verify RED**

Run the new test directly. Expected: FAIL because the path is not handled.

- [x] **Step 3: Add the minimum GET branch**

Before database-backed diagnostic dispatch in `Handler.do_GET`, add:

```python
if parsed.path == "/diagnostics/cognition-queue":
    self.send_json(200, COGNITION_QUEUE.snapshot())
    return
```

Do not add query parameters, mutation behavior, or database access.

- [x] **Step 4: Run route and existing diagnostic tests**

Run the new route test plus existing usage and health route tests. Expected: PASS.

---

### Task 3: Add the controlled Test 10 concurrency harness

**Files:**
- Create: `adapters/thesims4/scripts/test10_priority_harness.py`
- Create: `adapters/thesims4/tests/test_test10_priority_harness.py`
- Modify: `adapters/thesims4/docs/in-game-core-feature-test-plan.md:283-297`

**Interfaces:**
- Produces: `request_json(method, url, payload=None, timeout=120) -> dict`
- Produces: `evaluate_lifecycle(recent, synthetic_actor_ids) -> dict[str, object]`
- Produces: CLI arguments `--base-url`, `--output`, `--setup-timeout`, and `--completion-timeout`
- Consumes: `/diagnostics/cognition-queue`, the loopback Test 10 gate, and a real in-game
  `player_conversation`

- [x] **Step 1: Write failing lifecycle-evaluation tests**

Cover:

```python
result = evaluate_lifecycle(
    [
        {"actor_id": "empneon-test10-blocker", "state": "started"},
        {"actor_id": "empneon-test10-waiting", "state": "submitted"},
        {"actor_id": "real-player", "event_type": "player_conversation", "state": "submitted"},
        {"actor_id": "empneon-test10-blocker", "state": "completed"},
        {"actor_id": "real-player", "event_type": "player_conversation", "state": "started"},
        {"actor_id": "empneon-test10-waiting", "state": "started"},
    ],
    {"empneon-test10-blocker", "empneon-test10-waiting"},
)
assert result["passed"] is True
```

Add separate cases where the waiting ambient request started before the player and where no
waiting ambient submission was observed; both return `passed=False` with a non-empty reason.

- [x] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
py -3.12 -m pytest -q -p no:cacheprovider tests/test_test10_priority_harness.py
```

Expected: collection fails because the harness module does not exist.

- [x] **Step 3: Implement the pure evaluator and HTTP helper**

Use only `argparse`, `json`, `time`, `urllib.request`, `uuid`, and `pathlib`.
`evaluate_lifecycle` must require:

1. the blocker started;
2. the second synthetic ambient request was submitted before the player;
3. the player was submitted before the second ambient request started;
4. the player started before the second ambient request started.

Return the relevant indices and a concise failure reason; do not inspect dialogue.

- [x] **Step 4: Implement orchestration through existing routes**

Arm the loopback Test 10 gate with a unique run ID. It starts one controlled blocker and queues one
lower-priority `critical_need` request. The blocker releases explicitly after the real player
request is observed or automatically after 60 seconds.

The CLI:

1. verifies `/health` reports `active_agent_limit == 1`;
2. asks the operator to open Empneon Social and prepare, but not submit, the message;
3. arms the gate, which establishes the running blocker and waiting ambient request;
4. asks the operator to submit the prepared message immediately;
5. polls `recent` until a non-synthetic `player_conversation` is submitted;
6. releases the gate and waits until ordering is observable;
7. evaluates the lifecycle and writes an indented JSON report.

If either initial state disappears before the next state is established, return an inconclusive
report and exit `2`. Return `0` for pass and `1` for observed priority failure.

- [x] **Step 5: Run harness unit tests and syntax checks**

Run:

```powershell
py -3.12 -m pytest -q -p no:cacheprovider tests/test_test10_priority_harness.py
py -3.12 -m py_compile scripts/test10_priority_harness.py
```

Expected: PASS.

- [x] **Step 6: Document the exact Test 10 procedure**

Update Test 10 with the harness command:

```powershell
py -3.12 .\scripts\test10_priority_harness.py
```

Document exit codes `0` pass, `1` observed ordering failure, and `2` inconclusive setup. Require
retaining the reviewed JSON report and restarting the backend before the persistence check.

---

### Task 4: Regression verification

**Files:**
- Verify all files changed by Tasks 1-3

**Interfaces:**
- Produces: evidence that observability did not change existing behavior

- [x] **Step 1: Run complete Sims adapter tests**

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests
```

- [x] **Step 2: Run complete Core tests**

From `core`:

```powershell
$env:PYTHONPATH='src'
py -3.12 -m pytest -q -p no:cacheprovider tests
```

- [x] **Step 3: Run static verification**

From repository root:

```powershell
py -3.12 -m ruff check core/src core/tests adapters/thesims4/src adapters/thesims4/tests adapters/godot/src adapters/godot/tests tests
py -3.12 -m mypy core/src adapters/thesims4/src adapters/godot/src
py -3.12 -m py_compile adapters/thesims4/backend/ai_sims_server.py adapters/thesims4/scripts/test10_priority_harness.py
git diff --check
```

- [x] **Step 4: Inspect the uncommitted result**

Run `git status --short`. Confirm only the approved spec, plan, implementation, tests, and Test 10
documentation changed. Do not commit or push.
