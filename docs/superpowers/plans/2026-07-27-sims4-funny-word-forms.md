# Sims 4 Funny Word Forms Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correctly classify the observed funny word forms without changing working social behavior.

**Architecture:** Extend the existing funny branch in the shared
`explicit_social_category()` classifier. Existing callers will continue to
handle recategorization, relationship validation, fallbacks, and player
interaction classification.

**Tech Stack:** Python 3.11+, `re`, pytest

**Execution status:** Complete; `285` Sims adapter tests passed. A live retest
returned a marker-free joke as `friendly`, exposing a separate defect outside
this plan's lexical scope.

## Global Constraints

- Do not add dependencies or abstractions.
- Do not change non-funny category patterns.
- Do not commit or push until the user requests it.

---

### Task 1: Recognize the observed funny word forms

**Files:**
- Modify: `adapters/thesims4/tests/test_sims4_backend.py`
- Modify: `adapters/thesims4/backend/ai_sims_server.py:2043-2061`

**Interfaces:**
- Consumes: `explicit_social_category(message) -> str | None`
- Produces: Existing runtime recategorization for `jokes` and `funniest`

- [x] **Step 1: Change the existing recategorization test dialogue**

Use the exact live provider reply:

```python
"Here is one of my funniest llama jokes! It's about a very grumpy llama who loves to eat hay."
```

Keep its assertions that the response is `funny`, has relationship outcome
`none`, suggested action `none`, and requires only one provider call.

- [x] **Step 2: Run the focused test and verify RED**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py::test_explicit_category_contradiction_is_recategorized_without_retry
```

Expected: FAIL because the response remains `friendly`.

- [x] **Step 3: Extend only the funny regex**

```python
("funny", r"\b(jokes?|funn(?:y|ier|iest)|hilarious|laugh|pun|comedy)\b"),
```

- [x] **Step 4: Verify GREEN and regressions**

Run the focused test, the complete Sims 4 suite, Ruff on both changed Python
files, and `git diff --check`. All commands must exit successfully.

- [x] **Step 5: Leave changes uncommitted**

Report the changed files and verification results. Do not stage, commit, or
push.
