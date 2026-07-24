# Grounded Semantic Recall Precedence Implementation Plan

**Status:** Completed; checklist retained as the original execution record

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent factless semantic recall from replacing deterministic recall that contains attributed evidence.

**Architecture:** Keep both selectors unchanged and add one evidence-precedence guard where their results merge. Grounded semantic results remain authoritative, while factless semantic results remain usable only when deterministic recall is also factless.

**Tech Stack:** Python 3.12, pytest, Python 3.7 Sims source build

## Global Constraints

- Do not change candidate construction, selector prompts, provider calls, persistence, pair scoping, privacy, confirmation gating, or result limits.
- Preserve grounded semantic selection.
- Preserve factless semantic selection when no grounded deterministic result exists.
- Do not change dialogue validation, categories, relationships, animation, or provider transports.
- Add no dependency or Core gameplay concept.
- Do not commit or push until explicitly requested.

---

## File Structure

- Modify `adapters/thesims4/backend/ai_sims_server.py`: add the precedence guard inside `semantic_recalled_memories()`.
- Modify `adapters/thesims4/tests/test_sims4_backend.py`: cover grounded fallback precedence and factless semantic compatibility.
- Modify `adapters/thesims4/docs/in-game-core-feature-test-plan.md`: update the current Test 5 live handoff.
- Modify `adapters/thesims4/docs/in-game-core-feature-test-results.md`: record the fabricated-date failure and automated repair.

### Task 1: Guard grounded deterministic recall

**Files:**
- Modify: `adapters/thesims4/backend/ai_sims_server.py:1369-1380`
- Test: `adapters/thesims4/tests/test_sims4_backend.py:350-520`

**Interfaces:**
- Consumes: `semantic_recalled_memories(query, candidates, fallback)`
- Produces: the same list of recalled-memory dictionaries with grounded evidence precedence

- [x] **Step 1: Add the failing live-shaped precedence test**

```python
def test_semantic_recall_keeps_grounded_fallback_over_factless_selection(
    monkeypatch,
) -> None:
    grounded = [
        {
            "event_id": "date-plan",
            "message": "Tonight, 7pm, at my place.",
            "facts": [
                {
                    "actor_id": "bernard",
                    "statement": "Tonight, 7pm, at my place.",
                }
            ],
        }
    ]
    factless = [
        {
            "event_id": "prior-question",
            "message": "When is our date?",
            "dialogue": "It was the 15th.",
            "facts": [],
            "explicit": True,
        }
    ]
    monkeypatch.setattr(
        ai_sims_server,
        "select_recalled_memories",
        lambda _query, _candidates: factless,
    )

    recalled = ai_sims_server.semantic_recalled_memories(
        "Can you tell me when is our date?",
        factless + grounded,
        grounded,
    )

    assert recalled == grounded
```

- [x] **Step 2: Add the factless compatibility test**

```python
def test_semantic_recall_keeps_factless_selection_without_grounded_fallback(
    monkeypatch,
) -> None:
    fallback = [{"event_id": "literal", "message": "Old wording.", "facts": []}]
    selected = [
        {
            "event_id": "semantic",
            "message": "Meaning-matched wording.",
            "facts": [],
            "explicit": True,
        }
    ]
    monkeypatch.setattr(
        ai_sims_server,
        "select_recalled_memories",
        lambda _query, _candidates: selected,
    )

    recalled = ai_sims_server.semantic_recalled_memories(
        "What did we discuss?",
        selected,
        fallback,
    )

    assert recalled == selected
```

The existing `test_semantic_recall_exposes_only_selected_support` protects
grounded semantic selection, while the existing empty/provider-failure tests
protect fallback behavior.

- [x] **Step 3: Run focused tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "semantic_recall"
```

Expected: the grounded-fallback precedence test fails because the current
function returns the non-empty factless semantic selection. Existing and
factless-compatibility tests pass.

- [x] **Step 4: Add the minimal precedence guard**

Replace the final return in `semantic_recalled_memories()` with:

```python
    if (
        any(item.get("facts") for item in fallback)
        and not any(item.get("facts") for item in selected)
    ):
        return fallback
    return selected or fallback
```

- [x] **Step 5: Run focused tests and verify GREEN**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "semantic_recall"
```

Expected: every semantic-recall test passes.

### Task 2: Full verification and test handoff

**Files:**
- Modify: `adapters/thesims4/docs/in-game-core-feature-test-plan.md`
- Modify: `adapters/thesims4/docs/in-game-core-feature-test-results.md`

**Interfaces:**
- Consumes: Task 1 automated result
- Produces: verified source and an accurate live-retest instruction

- [x] **Step 1: Run the complete Sims adapter suite and compile the backend**

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests
py -3.12 -m py_compile backend/ai_sims_server.py backend/empneon_state.py
```

- [x] **Step 2: Run the complete Core suite**

```powershell
$env:PYTHONPATH='src'
py -3.12 -m pytest -q -p no:cacheprovider tests
```

- [x] **Step 3: Build the Sims source artifacts**

```powershell
py -3.12 .\build_mod.py
```

- [x] **Step 4: Update the test record**

Record the exact live question, fabricated `15th` response, confirmed
factless semantic override, evidence-precedence guard, automated test counts,
and that only the source backend must be restarted before repeating the
existing question.

- [x] **Step 5: Review the uncommitted diff**

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors and only intended session files. Do not commit,
push, install, or restart the running game/backend.
