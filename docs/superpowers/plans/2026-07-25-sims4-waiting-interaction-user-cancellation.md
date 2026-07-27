# Sims 4 Waiting Interaction User-Cancellation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep `Waiting for response` active until the backend reply unless the player explicitly cancels it.

**Architecture:** Split queueing the visible waiting interaction from submitting the backend request. Route both the finishing callback and generator cleanup through one finish handler that closes only for `FinishingType.USER_CANCEL`; any other pending finish requeues the same session without submitting again.

**Tech Stack:** Python 3.7-compatible Sims 4 script, pytest, existing Sims 4 test fakes, existing mod builder.

**Status:** Implemented; automated checks and the live Test 14 branch matrix passed.

## Global Constraints

- Only an explicit player cancellation closes the session as canceled.
- A non-user finish requeues the same session and never submits another backend request.
- A response is marked received before the active waiting interaction ends naturally.
- Requeue failure is reported as a delivery failure, not as user cancellation.
- Existing response delivery, error handling, action results, autonomy, and save-slot behavior remain unchanged.
- Do not modify runtime configuration, logs, databases, or checkpoint artifacts.
- Do not commit or push until the user explicitly requests it.

---

### Task 1: Protect the waiting-interaction lifecycle

**Files:**
- Modify: `adapters/thesims4/tests/test_sims4_mod_autonomy.py:170,1142-1249`
- Modify: `adapters/thesims4/ts4script/ai_sims_agent.py:304-360,2002-2040`

**Interfaces:**
- Produces: `queue_waiting_interaction(session) -> bool`, which queues and registers one waiting interaction without starting a backend request.
- Produces: `waiting_interaction_finished(session, interaction) -> None`, which ignores closed/responded/stale interactions, closes an explicit user cancellation, and otherwise requeues.
- Preserves: `queue_awaiting_answer(session, message) -> bool`, which queues once, begins one turn, and calls `submit_empneon_chat` once.

- [x] **Step 1: Write the failing regression**

Extend the existing conversation-session test with `FinishingType.USER_CANCEL = "user_cancel"` and observable interaction instances. Cover these literal outcomes:

```python
assert agent.queue_awaiting_answer(race_session, "Wait for the reply.")
assert submitted == [(race_session, "Wait for the reply.")]

first_waiting = race_session.interaction
first_waiting.finishing_type = "displaced"
first_waiting.finishing_callback(first_waiting)

replacement = race_session.interaction
assert replacement is not first_waiting
assert replacement._empneon_session_id == race_session.id
assert race_session.closed is False
assert submitted == [(race_session, "Wait for the reply.")]

first_waiting.finishing_callback(first_waiting)
assert race_session.interaction is replacement

replacement.finishing_type = agent.FinishingType.USER_CANCEL
replacement.finishing_callback(replacement)
assert race_session.closed is True
assert race_session.canceled is True
```

Keep the existing late-result assertion so an explicit cancellation still suppresses display and calls `report_canceled_proposal`. Update the generator-close case to expect a replacement for a non-user finish, and add an explicit `USER_CANCEL` case that still closes.

- [x] **Step 2: Run the regression and verify RED**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_mod_autonomy.py -k conversation_session_and_alarm_submit_without_overlap
```

Expected: FAIL because the current finishing callback closes `race_session` for `"displaced"` instead of requeueing it.

- [x] **Step 3: Implement the minimal lifecycle split**

Add a queue-only helper by moving the existing affordance lookup, context creation, push, session binding, and callback registration out of `queue_awaiting_answer`:

```python
def queue_waiting_interaction(session):
    affordance = services.affordance_manager().get(EMPNEON_WAITING_INTERACTION_ID)
    if affordance is None or session.actor is None or session.target is None:
        session.fail("Could not queue Waiting for response.")
        return False
    try:
        context = InteractionContext(
            session.actor,
            InteractionContext.SOURCE_SCRIPT_WITH_USER_INTENT,
            Priority.High,
        )
        result = session.actor.push_super_affordance(
            affordance,
            session.target,
            context,
        )
        interaction = getattr(result, "interaction", None)
    except Exception:
        write_marker(traceback.format_exc())
        interaction = None
    if interaction is None:
        session.fail("Could not queue Waiting for response.")
        return False
    interaction._empneon_session_id = session.id
    session.interaction = interaction
    register_finished = getattr(interaction, "register_on_finishing_callback", None)
    if not callable(register_finished):
        session.fail("Waiting for response has no completion callback.")
        return False
    register_finished(
        lambda completed: waiting_interaction_finished(session, completed)
    )
    return True
```

Add the shared finish gate:

```python
def waiting_interaction_finished(session, interaction):
    if (
        session.closed
        or session.response_received
        or session.interaction is not interaction
    ):
        return
    if getattr(interaction, "finishing_type", None) == FinishingType.USER_CANCEL:
        write_marker("Empneon Social waiting task canceled by user")
        session.close(canceled=True)
        return
    write_marker("Empneon Social waiting task restarted")
    queue_waiting_interaction(session)
```

Make `queue_awaiting_answer` call `queue_waiting_interaction`, then preserve the existing `begin_turn` and single `submit_empneon_chat` call. Replace the generator's unconditional `finally` cancellation with `waiting_interaction_finished(session, self)`. Change missing-participant handling from `session.close(canceled=True)` to `session.fail("Could not continue Waiting for response.")`.

- [x] **Step 4: Run the focused test and verify GREEN**

Run the command from Step 2.

Expected: PASS; the non-user finish produces one replacement, the stale callback does nothing, the explicit user finish cancels, and only one backend submission is recorded.

- [x] **Step 5: Run the whole lifecycle test module**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_mod_autonomy.py
```

Expected: PASS with no changed expectations outside waiting-interaction lifecycle behavior.

### Task 2: Verify adapter compatibility and build the mod

**Files:**
- Verify: `adapters/thesims4/ts4script/ai_sims_agent.py`
- Verify: `adapters/thesims4/tests/`
- Build output: existing Sims 4 mod artifact produced by `build_mod.py`

**Interfaces:**
- Consumes: the lifecycle behavior from Task 1.
- Produces: a verified mod build ready for live Test 14.

- [x] **Step 1: Run the full Sims 4 adapter suite**

Run from `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider
```

Expected: all tests pass, including cancellation persistence, delivery, action results, autonomy, and save-slot tests.

- [x] **Step 2: Compile the changed production module**

Run:

```powershell
py -3.12 -m py_compile ts4script/ai_sims_agent.py
```

Expected: exit code 0.

- [x] **Step 3: Build the Sims 4 mod**

Run:

```powershell
py -3.12 build_mod.py
```

Expected: exit code 0 and the normal mod artifact is rebuilt.

- [x] **Step 4: Check the final diff and workspace**

Run from the repository root:

```powershell
git diff --check
git diff -- adapters/thesims4/ts4script/ai_sims_agent.py adapters/thesims4/tests/test_sims4_mod_autonomy.py
git status --short
```

Expected: no whitespace errors; only the planned source, test, spec, plan, and normal build output changes belong to this task. The existing config, logs, database, and checkpoint artifacts remain untouched. Do not commit or push.
