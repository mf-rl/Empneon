# Sims 4 In-Game Test Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix every actionable defect recorded in in-game Tests 3 through 7 before Test 8 begins.

**Architecture:** Extend the existing game-boundary probes, private-memory retrieval, and shared dialogue validator rather than adding new layers. Keep the LLM expressive, but reject ungrounded output and use the existing deterministic fallback after two failed attempts.

**Tech Stack:** Python 3.11+, The Sims 4 script API, SQLite/sqlite-vec, Empneon Core, pytest.

## Global Constraints

- Preserve the single active `empneon_core_memory.sqlite3` database.
- Preserve observation-based memory privacy and native-action confirmation gating.
- Apply only consequences reported by a completed native interaction.
- Add no dependencies or persistence formats.
- Do not automatically retry `FinishingType.OBJECT_CHANGED`.
- Keep Tests 4 through 7 partial/failed until a new release passes the in-game retest.

---

### Task 1: Read the active aspiration across game API variants

**Files:**
- Modify: `adapters/thesims4/ts4script/ai_sims_agent.py:346`
- Test: `adapters/thesims4/tests/test_sims4_mod_autonomy.py:293`

**Interfaces:**
- Consumes: `sim_info.aspiration_tracker` and `short_trait_name(value)`.
- Produces: `sim_aspiration(sim_info) -> str`, returning a tuning name or `"unknown"`.

- [ ] **Step 1: Add a failing method-based tracker test**

```python
method_info = SimpleNamespace(
    aspiration_tracker=SimpleNamespace(
        get_primary_aspiration=lambda: type("Bodybuilder", (), {})
    )
)
assert agent.sim_aspiration(method_info) == "Bodybuilder"
```

- [ ] **Step 2: Run the focused test and observe the failure**

Run from `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_mod_autonomy.py
```

Expected: FAIL because only `active_aspiration` and `primary_aspiration` attributes are read.

- [ ] **Step 3: Probe existing attributes and the primary-aspiration method**

```python
def sim_aspiration(sim_info):
    tracker = getattr(sim_info, "aspiration_tracker", None)
    for attr in ("active_aspiration", "primary_aspiration"):
        name = short_trait_name(getattr(tracker, attr, None))
        if name:
            return name
    try:
        name = short_trait_name(tracker.get_primary_aspiration())
        if name:
            return name
    except Exception:
        pass
    return "unknown"
```

- [ ] **Step 4: Rerun the script-mod test and confirm PASS**

- [ ] **Step 5: Commit the independently verified boundary fix**

```powershell
git add adapters/thesims4/ts4script/ai_sims_agent.py adapters/thesims4/tests/test_sims4_mod_autonomy.py
git commit -m "fix(sims4): ingest active aspiration"
```

### Task 2: Prevent accessible memories from being crowded out

**Files:**
- Modify: `adapters/thesims4/backend/empneon_state.py:474`
- Modify: `adapters/thesims4/backend/ai_sims_server.py:866`
- Test: `adapters/thesims4/tests/test_sims4_backend.py:272`

**Interfaces:**
- Consumes: the existing observation IDs and `VectorMemoryStore.search()`.
- Produces: `relevant_memories()` ranked only from observable candidates; `memories_for_pair()` filters the complete observable ranking by exact participant pair.

- [ ] **Step 1: Add a failing crowding/privacy test**

Create confirmed observable events for one agent across more than twenty pairs, put the target
`PRIVATE-GARDEN-731` event outside the old global top-twenty window, and assert:

```python
found = ai_sims_server.memories_for_pair(
    "karmine", "bernard", query="Where is the garden code item?"
)
assert found[0]["summary"] == "PRIVATE-GARDEN-731 is under the blue bench"
assert ai_sims_server.memories_for_pair(
    "billie", "bernard", query="Where is the garden code item?"
) == []
```

- [ ] **Step 2: Run the focused backend test and observe the missing target memory**

Run from `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "crowd or vector"
```

- [ ] **Step 3: Rank the full observable candidate set before limiting**

In `relevant_memories`, request `len(observed)` vector candidates, filter them by `observed`, append
any observable events absent from the vector index, then apply `[:limit]`. In `memories_for_pair`,
request the complete observable ranking before applying the existing exact-pair filter and caller
limit. Keep the existing bounded-world `ponytail:` comment documenting the linear scan ceiling.

- [ ] **Step 4: Rerun the focused test and confirm retrieval plus privacy PASS**

- [ ] **Step 5: Commit the retrieval fix**

```powershell
git add adapters/thesims4/backend/empneon_state.py adapters/thesims4/backend/ai_sims_server.py adapters/thesims4/tests/test_sims4_backend.py
git commit -m "fix(sims4): preserve relevant private memory"
```

### Task 3: Ground factual, need, and romantic dialogue

**Files:**
- Modify: `adapters/thesims4/backend/ai_sims_server.py:1199-1534`
- Test: `adapters/thesims4/tests/test_sims4_backend.py:436`
- Test: `adapters/thesims4/tests/test_adapter.py`

**Interfaces:**
- Consumes: current game-state needs, query-relevant pair memories, and normalized model output.
- Produces: `response_grounding_issue(...) -> str`, `reasoning_fallback_response(...) -> dict`, and an intent that the existing `Sims4Adapter.action_for()` maps to a native action.

- [ ] **Step 1: Add failing response-contract tests**

Cover these assertions with normalized responses and a context containing
`PRIVATE-GARDEN-731 is under the blue bench`:

```python
assert "supporting memory" in ai_sims_server.response_grounding_issue(
    {"message": "Where is the garden code item?"},
    {"dialogue": "What are you talking about?", "intent": "clarify", "relationship": {}},
    context,
)
assert ai_sims_server.response_grounding_issue(
    {"message": "Would you like to go on a date?"},
    {"dialogue": "My hunger is critical.", "intent": "agree", "relationship": {}},
    context,
)
assert ai_sims_server.response_grounding_issue(
    {"message": "Would you like to go on a date?"},
    {"dialogue": "No, I would rather stay friends.", "intent": "set_boundary", "relationship": {}},
    context,
) == ""
```

Also assert that a response claiming `hunger is critical` is rejected when current hunger is above
25, that an accepted date requires `intent == "flirt"` plus a positive `romance_delta`, and that an
explicit decline keeps romance at zero.

- [ ] **Step 2: Add failing fallback tests**

```python
recall = ai_sims_server.reasoning_fallback_response(
    {"message": "Where is the garden code item?"}, context
)
assert "under the blue bench" in recall["dialogue"]

fallback = ai_sims_server.reasoning_fallback_response(
    {"message": "Hello there"}, context_without_memories
)
assert fallback["memory"]["summary"] != "The conversation needed a careful response."
assert "Hello there" in fallback["memory"]["summary"]
```

- [ ] **Step 3: Run focused tests and confirm the current validator accepts bad output**

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py tests/test_adapter.py -k "grounding or fallback or romantic"
```

- [ ] **Step 4: Use only query-relevant memories in the prompt summary**

In `chat`, replace the unfiltered `memory_summary(speaker_id, listener_id)` passed to
`build_context` with:

```python
summary = {"summary": "; ".join(item["summary"] for item in memories[:4])}
```

Keep the persisted `memory_summary` returned to diagnostics unchanged.

- [ ] **Step 5: Extend the shared validator minimally**

Add checks for stale critical-need claims, supported-memory uncertainty, and direct romantic
acceptance/decline. Treat `agree`, `accept`, and `flirt` as acceptance only when dialogue addresses
the invitation; require positive `romance_delta` and `intent == "flirt"`. Allow explicit decline
phrases with zero romance.

- [ ] **Step 6: Make fallback recall and summaries concrete**

When `_memory_supports_question()` succeeds, return the first relevant memory summary as dialogue.
For the romantic branch, return an explicit decline with `intent="set_boundary"`,
`animation="awkward_chat"`, and `romance_delta=0` when both model attempts fail grounding. For every
branch, set summary to:

```python
"{} {}".format(payload.get("message") or "", dialogue).strip()
```

- [ ] **Step 7: Run focused tests and confirm PASS**

- [ ] **Step 8: Commit the grounded-dialogue fix**

```powershell
git add adapters/thesims4/backend/ai_sims_server.py adapters/thesims4/tests/test_sims4_backend.py adapters/thesims4/tests/test_adapter.py
git commit -m "fix(sims4): ground social responses"
```

### Task 4: Full verification and retest handoff

**Files:**
- Modify if evidence changes: `adapters/thesims4/docs/in-game-core-feature-test-results.md`
- Verify: all changed source and test files

**Interfaces:**
- Produces: a pushed feature branch ready to build a release for in-game Tests 4 through 7.

- [ ] **Step 1: Run all automated suites**

From the repository root:

```powershell
$env:PYTHONPATH='core\src;adapters\thesims4\src'; py -3.12 -m pytest -q -p no:cacheprovider core adapters/thesims4 tests scripts/test_release.py
py -3.12 -m ruff check core/src core/tests adapters/thesims4/src adapters/thesims4/tests adapters/thesims4/backend adapters/thesims4/ts4script tests scripts
py -3.12 -m mypy core/src adapters/thesims4/src
py -3.12 -m py_compile adapters/thesims4/backend/ai_sims_server.py adapters/thesims4/backend/empneon_state.py adapters/thesims4/ts4script/ai_sims_agent.py
```

Expected: every command exits 0.

- [ ] **Step 2: Verify the release contract**

```powershell
$env:PYTHONPATH='.'; py -3.12 -m pytest -q -p no:cacheprovider scripts/test_release.py
```

Expected: PASS and the Sims release still contains the built `.package` and `.ts4script` artifacts.

- [ ] **Step 3: Review the complete branch diff and status**

```powershell
git diff origin/feature/sims4-core-integration...HEAD --check
git status --short
```

Expected: no whitespace errors and a clean worktree after commits.

- [ ] **Step 4: Push the requested branch**

```powershell
git push origin feature/sims4-core-integration
```

- [ ] **Step 5: Hand off only the required in-game retests**

Retest Test 4 aspiration ingestion, Test 5 relevant accept/decline and confirmed romance behavior,
Test 6 contradiction-free exact recall, and Test 7 paraphrased recall/privacy after installing a
new release. Do not begin Test 8 until those results are logged.
