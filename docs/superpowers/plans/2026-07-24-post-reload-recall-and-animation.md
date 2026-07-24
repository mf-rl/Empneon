# Post-Reload Recall and Waiting Animation Implementation Plan

**Status:** Completed; checklist retained as the original execution record

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve cue-selected time facts after reload and keep waiting animations functional when EA clears the linked social group.

**Architecture:** The recall fix stays inside the Sims adapter's deterministic evidence selector and retains only time-bearing facts for the existing `answers_when` branch. The animation fix preserves the paired native path while a social group exists, then caches an initiator-only mode when it does not; visual construction failures disable later attempts for that waiting interaction without affecting dialogue.

**Tech Stack:** Python 3.12 backend and tests, Python 3.7 Sims script compilation, pytest

## Global Constraints

- Preserve pair scoping, observer privacy, confirmation gating, deduplication, and the three-result recall limit.
- Preserve the existing paired waiting animation path when a social group is available.
- Do not recreate, replace, or mutate EA social groups.
- Dialogue delivery, cancellation, relationship effects, floating headlines, structured provider output, and persistence behavior remain unchanged.
- Add no dependencies, Core gameplay concepts, or provider-specific behavior.
- Do not commit or push until explicitly requested.

---

## File Structure

- Modify `adapters/thesims4/backend/empneon_state.py`: retain time facts selected by `answers_when`.
- Modify `adapters/thesims4/ts4script/ai_sims_agent.py`: select paired or initiator-only animation safely and suppress repeated failures.
- Modify `adapters/thesims4/tests/test_sims4_backend.py`: reproduce the persisted-date evidence loss.
- Modify `adapters/thesims4/tests/test_sims4_mod_autonomy.py`: cover missing-group fallback and one-time failure handling while preserving the paired-path assertions.
- Modify `adapters/thesims4/docs/in-game-core-feature-test-plan.md`: mark automated repair complete and live reload retest pending.
- Modify `adapters/thesims4/docs/in-game-core-feature-test-results.md`: record the persisted evidence, failed response, cause, and automated result.

### Task 1: Retain cue-selected time evidence

**Files:**
- Modify: `adapters/thesims4/backend/empneon_state.py:653-699`
- Test: `adapters/thesims4/tests/test_sims4_backend.py:608-697`

**Interfaces:**
- Consumes: `recalled_memories(conn, actor_id, other_id, query, limit=3)`
- Produces: the same recalled-memory dictionaries, with time-bearing `facts` retained when `answers_when` selected the memory

- [ ] **Step 1: Extend the existing live-shaped recall test**

After the existing message assertions in
`test_when_question_prefers_grounded_time_fact_over_unsupported_replies`, add:

```python
expected_fact = [
    {
        "actor_id": "bernard",
        "statement": "Tonight, 7pm, at my place.",
    }
]
assert recalled[0]["facts"] == expected_fact
assert compound_recalled[0]["facts"] == expected_fact
assert conversational_recalled[0]["facts"] == expected_fact
```

- [ ] **Step 2: Run the test and verify it fails for missing facts**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py::test_when_question_prefers_grounded_time_fact_over_unsupported_replies
```

Expected: FAIL because each selected memory currently contains `facts=[]`.

- [ ] **Step 3: Retain only matching time facts for `answers_when`**

Replace the fact filter inside `recalled_memories()` with:

```python
selected["facts"] = [
    fact
    for fact in facts
    if (
        answers_when
        and _TIME_FACT_CUE.search(str(fact.get("statement") or ""))
    )
    or terms & _recall_terms(str(fact.get("statement") or ""))
]
```

- [ ] **Step 4: Run focused recall coverage**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "recalled_memories or semantic_recall or recall_candidates"
```

Expected: all selected tests pass, including pair scoping, privacy, semantic fallback, deduplication, and the live-shaped date query.

### Task 2: Fall back safely when the listener social group is absent

**Files:**
- Modify: `adapters/thesims4/ts4script/ai_sims_agent.py:1640-1719`
- Test: `adapters/thesims4/tests/test_sims4_mod_autonomy.py:74-1100`

**Interfaces:**
- Consumes: `waiting_conversation_animation(interaction, sequence)`
- Produces: a paired element when the mapped mixer has a linked social group, an initiator-only visual element when it does not, or the original waiting sequence after one visual-construction failure

- [ ] **Step 1: Add the missing-group regression to the existing runtime test**

Immediately after the existing paired-path assertions, create an isolated
mapped mixer whose linked owner has no social group:

```python
missing_group_mixer = FakeMappedInteraction(
    conversation_affordance,
    SimpleNamespace(social_group=None),
)
unsafe_calls = []

def unsafe_basic_elements(_sequence):
    unsafe_calls.append(True)
    raise UnboundLocalError(
        "local variable 'listen_animation_factory' referenced before assignment"
    )

missing_group_mixer.build_basic_elements = unsafe_basic_elements
missing_group_waiting = SimpleNamespace(
    _empneon_waiting_mixer=missing_group_mixer,
)
marker_count = len(selected)

assert agent.waiting_conversation_animation(
    missing_group_waiting, "next-tick"
) == (("visual-outcome", "conversation-animation"), "next-tick")
assert agent.waiting_conversation_animation(
    missing_group_waiting, "next-tick"
) == (("visual-outcome", "conversation-animation"), "next-tick")
assert unsafe_calls == []
assert missing_group_waiting._empneon_animation_mode == "initiator_only"
assert len(selected) == marker_count + 1
assert selected[-1].startswith(
    "Waiting conversation animation using initiator-only fallback:"
)
```

- [ ] **Step 2: Strengthen the existing visual-construction failure assertion**

Call the failure path twice and require only one marker:

```python
marker_count = len(selected)
assert agent.waiting_conversation_animation(waiting, "next-tick") == "next-tick"
assert agent.waiting_conversation_animation(waiting, "next-tick") == "next-tick"
assert len(selected) == marker_count + 1
assert selected[-1].startswith("Waiting conversation animation failed:")
assert waiting._empneon_animation_disabled is True
```

- [ ] **Step 3: Run the mod runtime test and verify both additions fail**

Run:

```powershell
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_mod_autonomy.py::test_conversation_session_and_alarm_submit_without_overlap
```

Expected: the missing-group case returns the idle sequence after calling the unsafe method, and the failure case writes two markers.

- [ ] **Step 4: Add the narrow animation mode selection**

At the start of `waiting_conversation_animation()`:

```python
if getattr(interaction, "_empneon_animation_disabled", False):
    return sequence
```

After `build_outcome_actions(...)`, choose the animation:

```python
visual = build_outcome_actions(mixer, _VisualOutcomeActions(actions))
mode = getattr(interaction, "_empneon_animation_mode", None)
linked_group = getattr(
    getattr(mixer, "super_interaction", None),
    "social_group",
    None,
)
if mode == "initiator_only" or linked_group is None:
    mode = "initiator_only"
    interaction._empneon_animation_mode = mode
    animation = visual
    if not getattr(
        interaction, "_empneon_animation_fallback_diagnostic", False
    ):
        interaction._empneon_animation_fallback_diagnostic = True
        interaction._empneon_animation_diagnostic = True
        write_marker(
            "Waiting conversation animation using initiator-only fallback: "
            "linked social group unavailable"
        )
else:
    animation = mixer.build_basic_elements(visual)
```

Keep the existing paired-path diagnostic and return value. In the exception
handler, disable later attempts before recording the existing failure:

```python
interaction._empneon_animation_disabled = True
write_marker("Waiting conversation animation failed:\n" + traceback.format_exc())
return sequence
```

- [ ] **Step 5: Run all Sims mod tests**

Run:

```powershell
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_mod_autonomy.py
```

Expected: all tests pass, including the unchanged paired animation assertions and the new fallback assertions.

### Task 3: Full regression verification and documentation

**Files:**
- Modify: `adapters/thesims4/docs/in-game-core-feature-test-plan.md`
- Modify: `adapters/thesims4/docs/in-game-core-feature-test-results.md`

**Interfaces:**
- Consumes: Tasks 1 and 2 automated evidence
- Produces: a test record that distinguishes persisted data from failed post-reload recall and leaves live verification pending

- [ ] **Step 1: Run the complete Sims adapter suite and compile changed Python**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests
py -3.12 -m py_compile backend/empneon_state.py
py -3.7 -m py_compile ts4script/ai_sims_agent.py
```

Expected: all tests and both Python versions compile successfully.

- [ ] **Step 2: Run the complete Core suite**

Run:

```powershell
$env:PYTHONPATH='src'
py -3.12 -m pytest -q -p no:cacheprovider tests
```

Expected: all Core tests pass, preserving provider, persistence, identity, relationship, and memory behavior.

- [ ] **Step 3: Build the Python 3.7 Sims mod artifacts**

Run:

```powershell
py -3.12 .\build_mod.py
```

Expected: `Empneon_TheSims4.ts4script` and `Empneon_TheSims4.package` build successfully in `dist`.

- [ ] **Step 4: Update the in-game test record**

Record:

```markdown
- Save/reload data persistence passed: the confirmed date event and attributed
  time fact remained accessible to both actors.
- Post-reload recall failed because deterministic cue selection removed the
  selected time fact after ranking; automated coverage now preserves it.
- Missing EA social-group state caused the listener-factory exception;
  automated coverage now preserves the paired path and uses an initiator-only
  fallback only when that group is absent.
- Live save/reload recall and animation retest remains pending installation and
  restart.
```

- [ ] **Step 5: Check the complete uncommitted diff**

Run:

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors; only intended session files and generated `dist` artifacts are modified. Do not commit or push.
