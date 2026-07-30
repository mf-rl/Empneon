# Sims 4 Funny State Safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent friendly or funny provider replies to funny interactions from mutating relationship state.

**Architecture:** Add one bounded guard inside `CognitionRuntime.dialogue`, the
existing boundary that holds both incoming and outgoing social categories.
Leave normalization, category independence, and adapter mappings unchanged.

**Tech Stack:** Python 3.11+, pytest

**Execution status:** Complete; `286` Sims adapter tests and the rebuilt-backend
live retest passed.

## Global Constraints

- Preserve dialogue and outgoing response category.
- Do not change non-funny incoming interactions.
- Do not change mean, mischief, or romance outgoing responses.
- Do not commit or push until the user requests it.

---

### Task 1: Neutralize warm responses to incoming funny interactions

**Files:**
- Modify: `adapters/thesims4/tests/test_sims4_backend.py`
- Modify: `adapters/thesims4/backend/ai_sims_server.py:2724-2737`
- Modify: `adapters/thesims4/README.md`
- Modify: `adapters/thesims4/docs/in-game-core-feature-test-results.md`
- Modify: `docs/roadmap.md`

**Interfaces:**
- Consumes: `payload["incoming_category"]` and normalized provider response
- Produces: State-neutral `friendly` or `funny` response to incoming `funny`

- [x] **Step 1: Write the exact live regression**

Mock only `llm_chat`, returning:

```python
{
    "dialogue": (
        "Here's one! It's about a llama who decided to become an artist "
        "and paint with its own wool."
    ),
    "expressed_emotion": "playful",
    "intent": "accept_playfully",
    "response_category": "friendly",
    "tone_tags": ["playful", "friendly"],
    "trust_delta": 1,
    "relationship_outcome": "friendship_positive",
    "memory": {"importance": 0.5, "summary": ""},
}
```

Pass `incoming_category="funny"` and assert that dialogue and `friendly`
category remain unchanged while trust, outcome, suggested action, and animation
are neutral.

- [x] **Step 2: Verify RED**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py::test_funny_incoming_friendly_reply_is_state_neutral
```

Expected: FAIL because trust remains `1` and the outcome remains
`friendship_positive`.

- [x] **Step 3: Add the bounded runtime guard**

After explicit response recategorization:

```python
if (
    payload.get("incoming_category") == "funny"
    and response["response_category"] in ("friendly", "funny")
):
    response["trust_delta"] = 0
    response["relationship_outcome"] = "none"
    response["suggested_action"] = response["animation"] = "none"
```

- [x] **Step 4: Verify GREEN and regression safety**

Run the focused test, all Sims adapter tests, all Core tests, all Godot tests,
all shared tests, scoped test lint, backend byte-compilation, and
`git diff --check`.

- [x] **Step 5: Update handoff status**

Record automated completion and make rebuilt-backend live confirmation the next
roadmap gate. Leave all files uncommitted and unpushed.
