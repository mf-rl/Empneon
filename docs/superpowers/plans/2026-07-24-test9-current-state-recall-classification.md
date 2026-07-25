# Test 9 Current-State Recall Classification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent current-state questions from being misclassified as unsupported memory recall without weakening existing recall safeguards.

**Architecture:** Keep recall classification in the shared Core helper. Narrow only the generic WH-question regular expression to sentence boundaries; leave explicit recall markers and time/location slot detection unchanged.

**Tech Stack:** Python 3.12, `re`, pytest

## Global Constraints

- Preserve explicit `remember`, `recall`, and `did I say` detection.
- Preserve time and location recall detection.
- Preserve sentence-leading generic WH-question detection.
- Do not change provider routing, Sims fallback behavior, fact selection, or privacy filtering.
- Do not commit until the user explicitly requests it.

---

### Task 1: Correct generic WH recall classification

**Files:**
- Modify: `core/tests/unit/test_recall_constraints.py`
- Modify: `core/src/empneon/core/memory/recall.py`

**Interfaces:**
- Consumes: `analyze_recall_query(text: str) -> RecallQuery`
- Produces: unchanged `analyze_recall_query` interface with corrected classification

- [x] **Step 1: Add the exact failing Test 9 regression**

Add this row to `test_analyze_recall_query_uses_shared_slots`:

```python
(
    "How are you feeling right now, and what do you want to do?",
    False,
    frozenset(),
),
```

- [x] **Step 2: Verify RED**

Run:

```powershell
$env:PYTHONPATH='src'
py -3.12 -m pytest -q -p no:cacheprovider tests/unit/test_recall_constraints.py
```

Working directory: `core`

Expected: one failure showing `RecallQuery(explicit=True, ...)` instead of `explicit=False`.

- [x] **Step 3: Make the minimal classifier change**

Replace the generic WH pattern with sentence-boundary matching:

```python
_WH_REQUEST = re.compile(
    r"(?:^|[.!?]\s*)(?:what|when|where|who|which)\b",
    re.IGNORECASE,
)
```

Do not modify `_TIME_QUESTION`, `_LOCATION_QUESTION`, `_QUESTION_REQUEST`, or
`_RECALL_REQUEST`.

- [x] **Step 4: Verify focused GREEN**

Rerun the focused command from Step 2.

Expected: all recall-constraint tests pass.

- [x] **Step 5: Run Core regression suite**

Run from `core`:

```powershell
$env:PYTHONPATH='src'
py -3.12 -m pytest -q -p no:cacheprovider
```

Expected: complete Core suite passes.

- [x] **Step 6: Run Sims 4 regression suite**

Run from `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider
```

Expected: complete Sims 4 adapter suite passes.

- [x] **Step 7: Check the diff**

Run:

```powershell
git diff --check
git diff -- core/src/empneon/core/memory/recall.py core/tests/unit/test_recall_constraints.py
```

Expected: only the focused regression and WH-pattern simplification, with no whitespace errors.

- [x] **Step 8: Leave changes uncommitted**

Report the focused and complete-suite results. The user will perform the final live Test 9
interaction and will explicitly request any later commit or push.

## Execution record

- The exact regression failed with `RecallQuery(explicit=True)` before the implementation change.
- Focused recall constraints passed `29` tests after the change.
- The complete Core and Sims 4 adapter suites passed `225` and `235` tests.
- Live Test 9 returned grounded CLOD 3 dialogue and persisted its request, token, and latency
  telemetry after backend restart.
