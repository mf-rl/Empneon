# Sims 4 Response Rejection Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist both exhausted dialogue-rejection reasons and expose them on the matching Sims
timeline decision without storing prompts or raw model replies.

**Execution status:** Complete; automated verification and live funny/mischief capture passed.

**Review hardening:** Persistence and timeline exposure independently project exactly two ordered
integer attempts to `attempt` and `reason`; malformed types or ordering and corrupt JSON are
ignored.

**Architecture:** `CognitionRuntime.dialogue()` returns exhausted rejection reasons as private,
request-local response metadata. `chat()` removes and persists that metadata in the existing
`DocumentMemoryStore`, while a Sims-only timeline wrapper decorates Core decision entries.

**Tech Stack:** Python 3.12, SQLite, existing `DocumentMemoryStore`, pytest.

## Global Constraints

- Do not commit or push until the user explicitly requests it.
- Persist only one-based attempt numbers and normalized rejection reasons.
- Do not persist prompts, raw model replies, schemas, conversation text, or credentials.
- Do not change Core contracts, database schemas, provider APIs, configuration, or the Sims mod.
- Preserve current validation, retry, fallback, relationship, action, and usage behavior.

---

### Task 1: Carry Exhausted Rejection Reasons to Chat Orchestration

**Files:**
- Modify: `adapters/thesims4/backend/ai_sims_server.py:2671-2766`
- Test: `adapters/thesims4/tests/test_sims4_backend.py`

**Interfaces:**
- Consumes: existing grounding, category, and role-confusion issue strings.
- Produces: private fallback field `_response_rejections: list[dict[str, object]]`.

- [x] **Step 1: Write the failing exhausted-attempt test**

Add a focused test that returns two distinct model replies, rejects each for a static reason, and
allows the deterministic fallback:

```python
def test_dialogue_fallback_carries_only_exhausted_rejection_reasons(monkeypatch) -> None:
    replies = iter(
        (
            json.dumps(_social_provider_response("RAW-FIRST", "funny")),
            json.dumps(_social_provider_response("RAW-SECOND", "mischief")),
        )
    )
    monkeypatch.setattr(ai_sims_server, "llm_chat", lambda *_args, **_kwargs: next(replies))
    monkeypatch.setattr(
        ai_sims_server,
        "response_grounding_issue",
        lambda _payload, response, _context: {
            "RAW-FIRST": "first normalized reason",
            "RAW-SECOND": "second normalized reason",
        }.get(response["dialogue"], ""),
    )
    monkeypatch.setattr(
        ai_sims_server,
        "response_has_role_confusion",
        lambda _response, _context: False,
    )
    payload = {
        "speaker": {},
        "listener": {},
        "message": "Tell me something funny.",
        "available_response_categories": list(ai_sims_server.SOCIAL_CATEGORIES),
    }
    context = ai_sims_server.build_context(
        payload, {"name": "Karmine"}, {"name": "Bernard"}, {}, {}, []
    )
    context.update(conversation=[], speaker_id="karmine", listener_id="bernard")

    response = ai_sims_server.COGNITION_RUNTIME.dialogue(payload, context)

    assert response["_response_rejections"] == [
        {"attempt": 1, "reason": "first normalized reason"},
        {"attempt": 2, "reason": "second normalized reason"},
    ]
    assert "RAW-FIRST" not in json.dumps(response["_response_rejections"])
    assert "RAW-SECOND" not in json.dumps(response["_response_rejections"])
```

- [x] **Step 2: Write the accepted-retry regression**

Use the same setup, but make the second response pass grounding:

```python
def test_accepted_dialogue_retry_carries_no_rejection_diagnostic(monkeypatch) -> None:
    replies = iter(
        (
            json.dumps(_social_provider_response("RAW-FIRST", "funny")),
            json.dumps(_social_provider_response("Accepted reply.", "funny")),
        )
    )
    monkeypatch.setattr(ai_sims_server, "llm_chat", lambda *_args, **_kwargs: next(replies))
    monkeypatch.setattr(
        ai_sims_server,
        "response_grounding_issue",
        lambda _payload, response, _context: (
            "first normalized reason" if response["dialogue"] == "RAW-FIRST" else ""
        ),
    )
    monkeypatch.setattr(
        ai_sims_server,
        "response_has_role_confusion",
        lambda _response, _context: False,
    )
    payload = {
        "speaker": {},
        "listener": {},
        "message": "Tell me something funny.",
        "available_response_categories": list(ai_sims_server.SOCIAL_CATEGORIES),
    }
    context = ai_sims_server.build_context(
        payload, {"name": "Karmine"}, {"name": "Bernard"}, {}, {}, []
    )
    context.update(conversation=[], speaker_id="karmine", listener_id="bernard")

    response = ai_sims_server.COGNITION_RUNTIME.dialogue(payload, context)

    assert response["dialogue"] == "Accepted reply."
    assert "_response_rejections" not in response
```

- [x] **Step 3: Run both focused tests and verify RED**

Run from `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider `
  tests/test_sims4_backend.py::test_dialogue_fallback_carries_only_exhausted_rejection_reasons `
  tests/test_sims4_backend.py::test_accepted_dialogue_retry_carries_no_rejection_diagnostic
```

Expected: the exhausted-attempt test fails because `_response_rejections` is absent; the accepted
retry test passes.

- [x] **Step 4: Add the minimal request-local collection**

Initialize `rejections = []` before the attempt loop. Replace the duplicated log expression with:

```python
reason = issue or category_issue or "speaker/listener confusion"
PROVIDER_LOG.warning(
    "model response failed grounding (%s); retrying=%s",
    reason,
    attempt == 0,
)
rejections.append({"attempt": attempt + 1, "reason": reason})
```

After both attempts fail:

```python
fallback = reasoning_fallback_response(payload, context)
fallback["suggested_action"] = fallback["animation"] = "none"
fallback["_response_rejections"] = rejections
return fallback
```

- [x] **Step 5: Re-run both focused tests and verify GREEN**

Repeat Step 3. Expected: both tests pass.

---

### Task 2: Persist and Expose Decision Diagnostics

**Files:**
- Modify: `adapters/thesims4/backend/ai_sims_server.py:2794-2975`
- Modify: `adapters/thesims4/backend/ai_sims_server.py:3384-3427`
- Test: `adapters/thesims4/tests/test_sims4_backend.py`

**Interfaces:**
- Consumes: private `_response_rejections` returned by the selected dialogue resolver.
- Produces: `thesims4.response-rejections` document keyed by decision ID.
- Produces: `sims_timeline(conn, agent_id) -> dict[str, object]`.

- [x] **Step 1: Write the failing persistence and timeline test**

Add an end-to-end adapter test based on `test_chat_waits_for_native_game_confirmation`. Patch
`COGNITION_RUNTIME.dialogue()` to return ordinary fallback fields plus:

```python
"_response_rejections": [
    {"attempt": 1, "reason": "first normalized reason"},
    {"attempt": 2, "reason": "second normalized reason"},
],
```

Call `chat()`, assert `_response_rejections` is absent from its returned dictionary, then confirm
dialogue delivery. Reopen the database and assert:

```python
stored = DocumentMemoryStore(conn).get(
    "thesims4.response-rejections", result["decision_id"]
)
assert stored == {
    "response_rejections": [
        {"attempt": 1, "reason": "first normalized reason"},
        {"attempt": 2, "reason": "second normalized reason"},
    ]
}
timeline = ai_sims_server.sims_timeline(conn, "bella")
decision = next(
    entry for entry in timeline["entries"]
    if entry["id"] == result["decision_id"]
)
assert decision["data"]["diagnostics"] == stored
assert "RAW-" not in json.dumps(stored)
```

- [x] **Step 2: Write the malformed-document regression**

Create a completed decision for an agent, store an invalid document such as
`{"response_rejections": [{"attempt": "one", "reason": ""}]}`, and assert
`sims_timeline()` returns the decision without a `diagnostics` key.

- [x] **Step 3: Run both focused tests and verify RED**

Run from `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider `
  tests/test_sims4_backend.py::test_exhausted_rejections_persist_on_completed_timeline_decision `
  tests/test_sims4_backend.py::test_sims_timeline_ignores_malformed_rejection_diagnostics
```

Expected: both tests fail because persistence and `sims_timeline()` do not exist.

- [x] **Step 4: Capture and persist private diagnostics**

Add `response_rejections = []` beside the `selected` request-local state. In the resolver, before
converting the response to a decision:

```python
response_rejections.extend(response.pop("_response_rejections", []))
```

After `actions.propose(...)`, persist only exhausted diagnostics:

```python
if response_rejections:
    DocumentMemoryStore(conn).set(
        "thesims4.response-rejections",
        decision.id,
        {"response_rejections": response_rejections},
    )
```

The `pop()` prevents the private field from reaching player-facing response conversion.

- [x] **Step 5: Add the Sims timeline decorator**

Add:

```python
def sims_timeline(conn, agent_id):
    timeline = agent_timeline(conn, agent_id)
    documents = DocumentMemoryStore(conn)
    for entry in timeline["entries"]:
        if entry["type"] != "decision":
            continue
        stored = documents.get("thesims4.response-rejections", entry["id"])
        if not isinstance(stored, dict):
            continue
        rejections = stored.get("response_rejections")
        if not isinstance(rejections, list) or not rejections:
            continue
        if not all(
            isinstance(item, dict)
            and isinstance(item.get("attempt"), int)
            and not isinstance(item.get("attempt"), bool)
            and item["attempt"] > 0
            and isinstance(item.get("reason"), str)
            and bool(item["reason"].strip())
            for item in rejections
        ):
            continue
        entry["data"]["diagnostics"] = {"response_rejections": rejections}
    return timeline
```

Change only the Sims diagnostic route:

```python
elif path == "/diagnostics/timeline":
    body = sims_timeline(conn, identifier)
```

- [x] **Step 6: Re-run both focused tests and verify GREEN**

Repeat Step 3. Expected: both tests pass.

---

### Task 3: Verify and Record the Diagnostic Handoff

**Files:**
- Modify: `docs/roadmap.md`
- Modify: `adapters/thesims4/docs/in-game-core-feature-test-results.md`
- Modify: `docs/superpowers/specs/2026-07-27-sims4-response-rejection-diagnostics-design.md`
- Modify: `docs/superpowers/plans/2026-07-27-sims4-response-rejection-diagnostics.md`

**Interfaces:**
- Consumes: passing Tasks 1 and 2.
- Produces: accurate automated status and a bounded live funny/mischief retest handoff.

- [x] **Step 1: Run focused rejection and timeline coverage**

From `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py `
  -k "rejection or timeline"
```

Expected: all selected tests pass.

- [x] **Step 2: Run complete verification**

From the repository root:

```powershell
$env:PYTHONPATH='core\src;adapters\thesims4\src'
py -3.12 -m pytest -q -p no:cacheprovider adapters/thesims4/tests
py -3.12 -m pytest -q -p no:cacheprovider core/tests
py -3.12 -m pytest -q -p no:cacheprovider adapters/godot/tests
py -3.12 -m pytest -q -p no:cacheprovider tests
py -3.12 -m py_compile adapters/thesims4/backend/ai_sims_server.py
git diff --check
```

Expected: every suite, compilation, and whitespace check passes.

- [x] **Step 3: Update documentation without claiming live diagnosis**

Record:

- rejection reasons now persist without prompts or raw replies;
- the Sims timeline exposes them after completed fallback decisions and database reopen;
- automated test counts and checks;
- the actual LM Studio funny/mischief reasons remain pending a rebuilt-backend live retest.

Update the roadmap gate to: rebuild/restart, repeat funny and mischief prompts, inspect the
matching timeline decisions, and use the captured reasons to decide whether response acceptance
needs a separate fix.

- [x] **Step 4: Mark the spec and plan automated status**

Set the design status and this plan's execution status to implemented and automated-verified,
with live funny/mischief diagnosis explicitly pending.

- [x] **Step 5: Inspect the uncommitted result**

Run:

```powershell
git diff --check
git diff --stat
git status --short
```

Expected changed files:

- `adapters/thesims4/backend/ai_sims_server.py`
- `adapters/thesims4/tests/test_sims4_backend.py`
- `adapters/thesims4/docs/in-game-core-feature-test-results.md`
- `docs/roadmap.md`
- the approved design and this implementation plan

Do not commit or push.
