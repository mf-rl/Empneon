# Sims 4 Action-Result Terminal HTTP Errors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop permanent `/action-result` HTTP client errors after one request while retaining
retries for transient failures.

**Architecture:** Classify `urllib.error.HTTPError` inside the existing action-result worker and
carry one `permanent` boolean through its response queue. The existing response pump pauses a
permanently rejected entry instead of rescheduling it; successful and transient paths keep their
current behavior.

**Tech Stack:** The Sims 4 embedded Python, Python standard-library `urllib`, pytest.

## Global Constraints

- Keep the backend's strict HTTP `400` contract unchanged.
- Treat HTTP `400` through `499` as permanent.
- Keep network errors, timeouts, and HTTP `500` through `599` retryable.
- Log the rejected decision ID, status, and backend response body.
- Do not add dependencies or restructure the adapter.
- Do not commit or push until the user explicitly requests it.

---

### Task 1: Classify and pause permanent action-result failures

**Files:**
- Modify: `adapters/thesims4/ts4script/ai_sims_agent.py:1-8,1169-1258,1530-1556`
- Test: `adapters/thesims4/tests/test_sims4_mod_autonomy.py:1-7,2093-2152`
- Modify: `adapters/thesims4/docs/in-game-core-feature-test-results.md`

**Interfaces:**
- Consumes: `post_json(path, payload, timeout)` and `_ACTION_RESULT_RESPONSES`.
- Produces: response tuples `(outbox_id, error, permanent)` where `permanent` is true only for
  HTTP status codes `400 <= code < 500`.

- [x] **Step 1: Write the failing permanent-error regression**

Import `io` and `urllib.error` in `test_sims4_mod_autonomy.py`. In the existing outbox test, submit
a failed result whose patched `post_json` raises:

```python
urllib.error.HTTPError(
    "/action-result",
    400,
    "Bad Request",
    {},
    io.BytesIO(b'{"error":"unknown or conflicting action proposal"}'),
)
```

Run the response pump several times, then assert:

```python
assert permanent_attempts == ["decision-permanent"]
assert permanent_item["paused"] is True
assert permanent_item["attempts"] == 1
assert any(
    "decision-permanent" in marker
    and "HTTP 400" in marker
    and "unknown or conflicting action proposal" in marker
    for marker in selected
)
```

- [x] **Step 2: Run the focused test and verify RED**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider `
  tests/test_sims4_mod_autonomy.py -k conversation_session_and_alarm_submit_without_overlap
```

Expected: failure because the current worker retries the HTTP `400` and does not pause the entry.

- [x] **Step 3: Implement the minimal transport classification**

Add `import urllib.error` beside `urllib.parse`. In `dispatch_action_result_outbox.worker`, catch
`urllib.error.HTTPError` before the generic exception:

```python
permanent = False
try:
    post_json("/action-result", body, timeout=10)
except urllib.error.HTTPError as exc:
    permanent = 400 <= exc.code < 500
    detail = exc.read().decode("utf-8", errors="replace")
    error = "HTTP {}: {}".format(exc.code, detail or exc.reason)
    if permanent:
        write_marker(
            "Action result rejected permanently: decision_id={} {}".format(
                body.get("decision_id"), error
            )
        )
    else:
        write_marker(traceback.format_exc())
except Exception as exc:
    error = str(exc)
    write_marker(traceback.format_exc())
with _AUTONOMY_RESPONSES_LOCK:
    _ACTION_RESULT_RESPONSES.append((outbox_id, error, permanent))
```

In `process_autonomy_responses`, unpack the boolean. When `error is not None`, increment attempts;
if `permanent`, set `paused = True` and emit the existing `action_confirmation_failed` session
event immediately for a successful player result. Otherwise retain the existing backoff and
three-attempt behavior unchanged.

- [x] **Step 4: Run the focused test and verify GREEN**

Run the Step 2 command.

Expected: `1 passed`.

- [x] **Step 5: Verify existing transient and success behavior**

The same test already exercises two transient failures followed by success and normal successful
removal. Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_mod_autonomy.py
```

Expected: all tests in the module pass.

- [x] **Step 6: Run complete adapter verification**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider
py -3.12 -m py_compile ts4script/ai_sims_agent.py
py -3.12 build_mod.py
git diff --check
```

Expected: all `246` or more Sims adapter tests pass, compilation succeeds, both mod artifacts
build, and `git diff --check` reports no errors.

- [x] **Step 7: Record automated and live-retest status**

Append a concise note to `in-game-core-feature-test-results.md` stating that permanent action-result
HTTP errors now pause after one attempt while transient errors retain backoff. Mark the live check
pending until the rebuilt mod is installed and one backend restart produces at most one `400` for
the rejected decision.

- [x] **Step 8: Leave changes uncommitted**

Run `git status --short` and report every modified file. Do not stage, commit, or push.
