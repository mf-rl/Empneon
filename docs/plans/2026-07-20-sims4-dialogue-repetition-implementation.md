# Sims 4 Dialogue Repetition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop copied or recycled Sims dialogue, recognize common romantic invitations, and make `ai.relationship <name>` query the correct numeric Sim ID.

**Architecture:** Extend the existing shared response validator and deterministic fallback instead of constraining generation in the prompt. Resolve relationship command names through the existing game-side `find_sim_info_by_name` lookup; preserve raw numeric-ID input as the fallback.

**Tech Stack:** Python 3.11+, The Sims 4 script API, Empneon Core, pytest, standard library only.

## Global Constraints

- Preserve model freedom over natural wording, tone, personality, emotion, acceptance, and rejection.
- Reject only integrity failures: copied input, stale reused output, ignored romantic invitations, and ungrounded facts.
- Add no dependency, API, database, or persistence-format change.
- Do not change or automatically retry native social selection failures.
- Follow RED-GREEN TDD for each production change.

---

### Task 1: Reject repeated dialogue and recognize romantic phrasing

**Files:**
- Modify: `adapters/thesims4/backend/ai_sims_server.py:1356-1536`
- Test: `adapters/thesims4/tests/test_sims4_backend.py:540-620`

**Interfaces:**
- Consumes: `payload["message"]`, `context["conversation"]`, and normalized model responses.
- Produces: `_is_romantic_request(message: str) -> bool` and validation messages from `response_grounding_issue`.

- [ ] **Step 1: Add failing regression tests**

Extend the existing grounding tests with these cases:

```python
for message in (
    "Would you go out with me sometime?",
    "Let's be girlfriends.",
    "Would you be my boyfriend?",
):
    assert ai_sims_server.response_grounding_issue(
        {"message": message}, ignored, context
    ) == "directly accept or decline the romantic invitation"

echoed = ai_sims_server.normalize_response(
    {
        "dialogue": "It's nice to meet you too, Bernard. Meeting you today has made my day very happy.",
        "intent": "agree",
    }
)
assert "copy" in ai_sims_server.response_grounding_issue(
    {
        "message": "It's nice to meet you too, Billie. Meeting you today has made my day very happy."
    },
    echoed,
    context,
)

context["conversation"] = [
    {
        "speaker_id": "billie",
        "message": "It is nice to meet you.",
        "dialogue": "You have a very kind presence.",
    }
]
reused = ai_sims_server.normalize_response(
    {"dialogue": "You have a very kind presence.", "intent": "recall"}
)
assert "previous reply" in ai_sims_server.response_grounding_issue(
    {"message": "Would you go out with me sometime?"}, reused, context
)

fallback = ai_sims_server.reasoning_fallback_response(
    {"message": "Would you go out with me sometime?"}, context
)
assert fallback["intent"] == "set_boundary"
assert fallback["relationship"]["romance_delta"] == 0
```

- [ ] **Step 2: Run the focused backend tests and verify RED**

Run from `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py
```

Expected: FAIL because `go out`, `girlfriend`, and `boyfriend` are not romantic triggers and no echo/reuse validation exists.

- [ ] **Step 3: Implement the minimum shared validation**

Add `_is_romantic_request` using the existing `re` dependency:

```python
def _is_romantic_request(message):
    value = str(message or "").casefold()
    return bool(
        re.search(r"\b(date|love|romance|romantic|kiss|girlfriend|boyfriend)\b", value)
        or re.search(r"\bgo(?:ing)? out\b|\bbe together\b", value)
    )
```

Normalize dialogue words with `re.findall`, excluding both Sims' name tokens. In
`response_grounding_issue`, reject a current-message copy when at least six normalized words are
present and the ordered word lists are equal. Reject a previous reply when its normalized words
equal the proposed dialogue but its associated player message differs from the current message.
Replace both romantic regex checks in `response_grounding_issue` and
`reasoning_fallback_response` with `_is_romantic_request(message)`.

- [ ] **Step 4: Run the focused backend tests and verify GREEN**

Run the Step 2 command. Expected: all backend tests PASS.

- [ ] **Step 5: Commit the backend fix**

```powershell
git add adapters/thesims4/backend/ai_sims_server.py adapters/thesims4/tests/test_sims4_backend.py
git commit -m "fix(sims4): reject repeated social dialogue"
```

### Task 2: Resolve relationship display names to numeric IDs

**Files:**
- Modify: `adapters/thesims4/ts4script/ai_sims_agent.py:1340-1364`
- Test: `adapters/thesims4/tests/test_sims4_mod_autonomy.py:255-350`

**Interfaces:**
- Consumes: existing `find_sim_info_by_name(name)` and `sim_info.sim_id`.
- Produces: `/relationship` query parameters with the resolved numeric `sim_id`; unresolved input remains unchanged for numeric-ID compatibility.

- [ ] **Step 1: Add a failing command regression test**

Inside the existing loaded-mod test, add:

```python
relationship_queries = []
monkeypatch.setattr(agent, "active_sim", lambda _connection: SimpleNamespace(sim_info=rich_info))
monkeypatch.setattr(
    agent,
    "find_sim_info_by_name",
    lambda name: SimpleNamespace(sim_id="cam-id", full_name="Cam Sadya")
    if name == "Cam Sadya"
    else None,
)
monkeypatch.setattr(
    agent,
    "query_json",
    lambda path, query: relationship_queries.append((path, query))
    or {"relationship": {}},
)
agent.ai_relationship("Cam", "Sadya")
assert relationship_queries == [
    ("/relationship", {"sim_id": "cam-id", "target_id": "bella"})
]
```

- [ ] **Step 2: Run the script-mod test and verify RED**

Run from `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_mod_autonomy.py
```

Expected: FAIL because the command sends `"Cam Sadya"` as `sim_id`.

- [ ] **Step 3: Resolve the name before querying Core**

In `ai_relationship`, reuse the existing lookup:

```python
target_info = find_sim_info_by_name(target)
target_id = str(getattr(target_info, "sim_id", target))
target_label = sim_full_name(target_info) if target_info is not None else target
data = query_json("/relationship", {"sim_id": target_id, "target_id": active["id"]})
```

Use `target_label` in console output. Do not add another resolver or backend endpoint.

- [ ] **Step 4: Run the script-mod test and verify GREEN**

Run the Step 2 command. Expected: PASS.

- [ ] **Step 5: Commit the command fix**

```powershell
git add adapters/thesims4/ts4script/ai_sims_agent.py adapters/thesims4/tests/test_sims4_mod_autonomy.py
git commit -m "fix(sims4): resolve relationship names"
```

### Task 3: Verify and publish the retest build source

**Files:**
- Modify: `adapters/thesims4/docs/in-game-core-feature-test-plan.md`
- Modify: `adapters/thesims4/docs/in-game-core-feature-test-results.md`
- Verify: all repository test and quality suites.

**Interfaces:**
- Produces: a pushed `feature/sims4-core-integration` branch ready for a new adapter release and Test 5 retest.

- [ ] **Step 1: Run all automated checks**

From repository root:

```powershell
$env:PYTHONPATH='core\src;adapters\thesims4\src'; py -3.12 -m pytest -q -p no:cacheprovider core adapters/thesims4 tests scripts/test_release.py
py -3.12 -m ruff check core/src core/tests adapters/thesims4/src adapters/thesims4/tests adapters/thesims4/backend adapters/thesims4/ts4script tests scripts
py -3.12 -m mypy core/src adapters/thesims4/src
py -3.12 -m py_compile adapters/thesims4/backend/ai_sims_server.py adapters/thesims4/backend/empneon_state.py adapters/thesims4/ts4script/ai_sims_agent.py
```

Expected: every command exits 0.

- [ ] **Step 2: Update the Test 5 log without marking it passed**

Record the confirmed root causes and automated remediation. Keep Test 5 `PARTIAL` until a release
proves both relevant dialogue and a confirmed native romance consequence in game.

- [ ] **Step 3: Check and commit documentation**

```powershell
git diff --check
git add adapters/thesims4/docs/in-game-core-feature-test-plan.md adapters/thesims4/docs/in-game-core-feature-test-results.md docs/plans/2026-07-20-sims4-dialogue-repetition-implementation.md
git commit -m "docs(sims4): prepare dialogue retest"
```

- [ ] **Step 4: Push the current feature branch**

```powershell
git push origin feature/sims4-core-integration
```

Expected: the remote branch advances to the final documentation commit.
