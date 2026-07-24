# Sims 4 Fresh Recalled Response Implementation Plan

**Status:** Completed; checklist retained as the original execution record

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ground Sims dialogue in recalled facts without exposing an earlier generated reply for reuse, while allowing optional relationship-appropriate terms of endearment.

**Architecture:** Change only the shared recalled-history prompt renderer and its prompt guidance. Selected memories retain the original player statement and confirmed attributed facts, but omit stored generated dialogue before the main model call.

**Tech Stack:** Python 3.12, Python standard library, pytest.

## Global Constraints

- Work on the existing `main` worktree.
- Do not commit or push until the user explicitly requests it.
- Do not add another model request or enable response rejection.
- Do not change semantic selection, pair scoping, retrieval ranking, stored memories, or similarity thresholds.
- Terms of endearment remain optional model expression; do not add a hardcoded term list or injection subsystem.

---

### Task 1: Render Recalled Exchanges as Evidence

**Files:**
- Modify: `adapters/thesims4/tests/test_sims4_backend.py`
- Modify: `adapters/thesims4/backend/ai_sims_server.py`

**Interfaces:**
- Consumes: `_recalled_memory_text(context) -> str`, selected memory dictionaries from `semantic_recalled_memories()`
- Produces: recalled prompt text containing original player statements and attributed facts but no stored generated dialogue

- [ ] **Step 1: Add failing date and unrelated-memory assertions**

Extend `test_semantic_recall_exposes_only_selected_support` so each case includes the selected
memory's old generated reply:

```python
@pytest.mark.parametrize(
    ("query", "selected_id", "supported_text", "unsupported_text", "old_reply"),
    [
        (
            "Hey, baby. When are we going on a date?",
            "date-plan",
            "Tonight, 7pm, at my place.",
            "Next Saturday at the museum.",
            "That sounds perfect! Tonight at 7 pm at your place is lovely. "
            "You have such a charming way of making things feel like heaven.",
        ),
        (
            "Any idea where I put the thing that opens the garden?",
            "garden-key",
            "The garden key is beneath the blue bench.",
            "The garden key is in the kitchen.",
            "I will remember that.",
        ),
    ],
)
def test_semantic_recall_exposes_only_selected_support(
    monkeypatch,
    query,
    selected_id,
    supported_text,
    unsupported_text,
    old_reply,
) -> None:
```

Use the date `old_reply` as the `date-plan` candidate dialogue. After building the prompt, assert:

```python
assert supported_text in prompt
assert unsupported_text not in prompt
assert old_reply not in prompt
```

Update `test_actor_prompt_separates_recalled_history_from_current_session`:

```python
assert "Robin said: Let's meet for pizza tomorrow at 7 PM." in prompt
assert "Pizza sounds good, let's plan it." not in prompt
assert "Robin: How has your day been?" in prompt
assert "Travis: Busy, but good." in prompt
assert "may inspire a fresh, natural term of endearment" in prompt
assert "but never require one" in prompt
```

The current-session reply stays visible; only recalled generated dialogue disappears.

- [ ] **Step 2: Run the focused tests and verify RED**

Run from `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "semantic_recall_exposes_only_selected_support or actor_prompt_separates_recalled_history"
```

Expected: both tests fail because `_recalled_memory_text()` renders explicit memories through
`_exchange_text()`, which includes the stored generated reply.

- [ ] **Step 3: Render explicit recalled messages without their generated replies**

Replace the explicit-memory branch in `_recalled_memory_text()` with:

```python
        if memory.get("explicit"):
            asker_id = (
                context.get("listener_id")
                if memory.get("speaker_id") == context.get("speaker_id")
                else context.get("speaker_id")
            )
            message = str(memory.get("message") or "").strip()
            if message:
                lines.append("{} said: {}".format(names.get(asker_id, asker_id), message))
```

Remove the branch's `continue` so confirmed attributed facts are still rendered by the existing
fact loop. Do not change `_exchange_text()` because current-session conversation still needs both
sides of each exchange.

- [ ] **Step 4: Add optional endearment guidance**

Add these grounding rules in `build_chat_prompt()` after the relationship-attraction guidance:

```text
- A close or romantic relationship and compatible traits may inspire a fresh, natural term of
  endearment, but never require one.
- Do not use a term of endearment for neutral or hostile relationships, rejected romance, or when
  identity or context makes it inappropriate.
```

- [ ] **Step 5: Run the focused tests and verify GREEN**

Run the Step 2 command again.

Expected: all selected tests pass.

- [ ] **Step 6: Run the complete Sims adapter suite**

Run from `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests
py -3.12 -m py_compile backend/ai_sims_server.py
```

Expected: all Sims adapter tests pass and compilation exits `0`.

- [ ] **Step 7: Inspect without committing**

Run from the repository root:

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors. The implementation, tests, design, and plan remain uncommitted.

- [ ] **Step 8: Hand off the live retest**

Restart the backend and ask:

```text
Hey, baby. When are we going on a date?
```

Expected: Sim B preserves `Tonight at 7 pm at your place` but does not repeat the stored
`That sounds perfect!...` reply. A relationship-appropriate term of endearment may appear but is
not required. Repeat with the stored garden-key memory and record both results before changing the
in-game test status.
