# Sims 4 Private Fact Recall Integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make confirmed identifier assignments authoritative recall evidence and prevent earlier unsupported questions or generated answers from masquerading as knowledge.

**Architecture:** Keep Core recall constraints unchanged. Narrowly extend Sims player-message fact extraction, use topic overlap only across authoritative facts when specialized slot matching has no result, and require authoritative facts for explicit recall support.

**Tech Stack:** Python 3.12, existing SQLite memory stores, pytest, Ruff, mypy

## Global Constraints

- Preserve pair scoping, confirmation gating, attribution, deterministic fallback, and recall-answer fact protection.
- Do not broaden generated-model dialogue fact extraction.
- Add no dependency, schema, migration, or Core API change.
- Preserve the user's `response_rejection_enabled: true` configuration change and align the
  shipped fallback, setup guide, and baseline test with that accepted state.
- Commit and push after the user requests final integration.

---

### Task 1: Reproduce authoritative and unsupported private recall

**Files:**
- Modify: `adapters/thesims4/tests/test_sims4_backend.py`
- Test: `adapters/thesims4/tests/test_sims4_backend.py`

**Interfaces:**
- Consumes: `empneon_state.recalled_memories`, `response_grounding_issue`, and `reasoning_fallback_response`.
- Produces: regression coverage for confirmed identifier facts and evidence-free prior questions.

- [x] **Step 1: Add a confirmed-fact assertion**

Extend the existing delivered-memory test for
`PRIVATE-GARDEN-731 is under the blue bench.` to assert that its recalled record contains:

```python
[
    {
        "actor_id": "mortimer",
        "statement": "PRIVATE-GARDEN-731 is under the blue bench.",
    }
]
```

- [x] **Step 2: Add informed/uninformed grounding coverage**

Build two real context dictionaries. The informed context contains the attributed fact; the
uninformed context contains only an earlier question and unsupported answer with `facts=[]`.
Assert:

```python
assert "selected attributed fact" in response_grounding_issue(
    payload, {"dialogue": "It's in the private garden."}, informed
)
assert "under the blue bench" in reasoning_fallback_response(payload, informed)["dialogue"]
assert "no supporting memory" in response_grounding_issue(
    payload, {"dialogue": "It sounds good! What about it?"}, uninformed
)
assert "don't know" in reasoning_fallback_response(payload, uninformed)["dialogue"].casefold()
```

- [x] **Step 3: Run the two focused tests and verify RED**

Run from `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "confirmed_identifier_fact or provider_usage_and_only_confirms_memory"
```

Expected: FAIL because the identifier assignment has no authoritative fact, the informed generic
answer is not rejected, and the uninformed prior question is treated as evidence.

### Task 2: Correct the Sims evidence boundary

**Files:**
- Modify: `adapters/thesims4/backend/empneon_state.py`
- Modify: `adapters/thesims4/backend/ai_sims_server.py`
- Test: `adapters/thesims4/tests/test_sims4_backend.py`

**Interfaces:**
- Changes: `_durable_fact(actor_id, text, *, allow_identifier_assignment=False)`.
- Preserves: all existing call sites except confirmed player-message extraction opts into the new flag.

- [x] **Step 1: Recognize concrete identifier assignments only for player messages**

Add a narrow uppercase, hyphenated, digit-bearing identifier assignment pattern. Let
`_durable_fact` accept it only when `allow_identifier_assignment=True`. Pass that flag only for
the confirmed incoming player message in `record_delivered_experience`; generated dialogue keeps
the existing rules.

- [x] **Step 2: Fall back to authoritative-fact term overlap**

In `_supported_recall_facts`, return specialized slot matches first. When none exist, compare
meaningful question terms against authoritative fact statements even when the question requests a
location slot.

- [x] **Step 3: Require authoritative facts for explicit recall support**

In `_memory_supports_question`, return whether `_supported_recall_facts` is non-empty whenever
`analyze_recall_query(message).explicit` is true. Retain raw-text overlap only for non-explicit
memory use.

- [x] **Step 4: Run the focused tests and verify GREEN**

Run the Task 1 command. Expected: PASS.

- [x] **Step 5: Run existing recall-focused coverage**

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "recall or memory or grounding"
```

Expected: PASS.

### Task 3: Verify regression safety

**Files:**
- Verify: `adapters/thesims4/backend/empneon_state.py`
- Verify: `adapters/thesims4/backend/ai_sims_server.py`
- Verify: `adapters/thesims4/tests/test_sims4_backend.py`

**Interfaces:**
- Produces: fresh evidence that the targeted fix preserves existing Core and Sims behavior.

- [x] **Step 1: Run the complete Sims adapter suite**

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider
```

- [x] **Step 2: Run the complete Core suite**

From `core`:

```powershell
$env:PYTHONPATH='src'
py -3.12 -m pytest -q -p no:cacheprovider
```

- [x] **Step 3: Run static verification**

From the repository root:

```powershell
py -3.12 -m ruff check core/src core/tests adapters/thesims4/src adapters/thesims4/tests adapters/godot/src adapters/godot/tests tests
py -3.12 -m mypy core/src adapters/thesims4/src adapters/godot/src
py -3.12 -m py_compile adapters/thesims4/backend/ai_sims_server.py adapters/thesims4/backend/empneon_state.py
git diff --check
```

- [x] **Step 4: Inspect final status**

Confirm only the user's configuration change, the approved spec/plan, and the targeted source/test
files are modified.

### Task 4: Close the live false-positive gap

**Files:**
- Modify: `adapters/thesims4/backend/ai_sims_server.py`
- Modify: `adapters/thesims4/tests/test_sims4_backend.py`
- Verify: `adapters/thesims4/docs/in-game-core-feature-test-results.md`

- [x] **Step 1: Reproduce the unrelated-location false positive**

Add Billie's actual unrelated fact, `Tonight, 7 PM, at my place`, to the uninformed context and
verify that it incorrectly satisfies `Where is PRIVATE-GARDEN-731?`.

- [x] **Step 2: Require identifier identity at the evidence boundary**

When an explicit query contains a hyphenated digit-bearing identifier, filter recalled facts to the
same identifier before applying generic slot matching. Keep existing date, possessive-location,
and non-identifier recall behavior unchanged.

- [x] **Step 3: Verify automated behavior**

The regression passed after failing for the expected reason. The live database replay produced no
supporting facts, the `state uncertainty because no supporting memory exists` rejection reason,
and `I don't know or remember that.` as deterministic fallback. The full suites and static checks
passed.

- [x] **Step 4: Verify live acceptance**

With `response_rejection_enabled: true`, the informed Sim recalled `under the blue bench`. The
uninformed Sim's fabricated `private garden` response was rejected and the game displayed
`I don't know or remember that.` Test 6 is closed as PASS; Test 7's non-date paraphrase is next.
