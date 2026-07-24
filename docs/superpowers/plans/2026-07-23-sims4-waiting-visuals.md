# Sims 4 Waiting Visuals Implementation Plan

**Status (2026-07-23): Implemented; waiting animation live-confirmed.** The original raw
`animation_ref` approach produced only staring. The final implementation uses the native outcome
builder for visual assembly while neutralizing gameplay fields and replacing its normal outcome
element. Dual-portrait order and exact floating symbols remain open live checks.

> **For agentic workers:** Execute inline on the existing `main` worktree. Do not create a
> worktree, branch, subagent, commit, or push.

**Goal:** Add cosmetic conversation animation, dual-portrait notifications, and explicit native
relationship headlines to the existing single-turn Empneon Social flow.

**Architecture:** Keep the current queue and relationship lifecycle unchanged. The script mod
creates a non-queued friendly mixer only as the owner of a native visual outcome sequence. Loot,
continuations, events, cancellation, extras, parameterized autonomy, and relationship scoring are
disabled. The mod also adds the native secondary notification icon and explicitly sends the
relationship track's tuned headline after a nonzero observed delta. No response-derived social or
custom visual UI is added.

**Tech Stack:** Python 3.7 script mod, The Sims 4 native animation/notification/headline APIs,
existing pytest fakes, standard library only.

## Global Constraints

- Continue on the existing `main` worktree.
- Do not commit or push until the user explicitly requests it.
- Do not queue a native response-derived social or add another visible interaction.
- Build only the EA tuning's visual outcome sequence; never run its normal outcome, loot,
  continuations, events, extras, sentiments, milestones, moods, or relationship scoring.
- Preserve relationship application and Core reporting if visual headline dispatch fails.
- Keep stronger `+++` and milestone effects deferred.

---

### Task 1: Show Both Sims in Dialogue Notifications

**Files:**
- Modify: `adapters/thesims4/tests/test_sims4_mod_autonomy.py`
- Modify: `adapters/thesims4/ts4script/ai_sims_agent.py`

**Interfaces:**
- Changes: `show_empneon_notification(owner, title, text, secondary_owner=None) -> bool`
- Submitted dialogue: Sim A primary, Sim B secondary
- Returned dialogue: Sim B primary, Sim A secondary

- [ ] **Step 1: Add failing portrait-order assertions**

Extend the existing submitted- and returned-notification assertions:

```python
assert submitted_notification.show_kwargs["icon_override"].obj_instance is actor
assert (
    submitted_notification.show_kwargs["secondary_icon_override"].obj_instance
    is pie_interaction.target
)

assert (
    response_notification.show_kwargs["icon_override"].obj_instance
    is pie_interaction.target
)
assert (
    response_notification.show_kwargs["secondary_icon_override"].obj_instance
    is pie_interaction.sim
)
```

Also retain one error-notification assertion proving `secondary_icon_override` is absent.

- [ ] **Step 2: Run the focused test and verify RED**

From `adapters/thesims4` run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_mod_autonomy.py::test_conversation_session_and_alarm_submit_without_overlap
```

Expected: FAIL because current notifications only pass `icon_override`.

- [ ] **Step 3: Add the native secondary icon**

Change the helper without introducing a second notification path:

```python
def show_empneon_notification(owner, title, text, secondary_owner=None):
    if owner is None:
        return False
    try:
        notification = UiDialogNotification.TunableFactory().default(
            owner,
            title=raw_text(title),
            text=raw_text(text),
        )
        show_kwargs = {"icon_override": IconInfoData(obj_instance=owner)}
        if secondary_owner is not None:
            show_kwargs["secondary_icon_override"] = IconInfoData(
                obj_instance=secondary_owner
            )
        notification.show_dialog(**show_kwargs)
        return True
    except Exception:
        write_marker(traceback.format_exc())
        return False
```

Pass `target` as the fourth argument when showing Sim A's submitted dialogue, and pass `actor` when
showing Sim B's returned dialogue. Leave error calls unchanged.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run the Step 2 command again.

Expected: PASS.

---

### Task 2: Dispatch Native Relationship Headlines Above Both Sims

**Files:**
- Modify: `adapters/thesims4/tests/test_sims4_mod_autonomy.py`
- Modify: `adapters/thesims4/ts4script/ai_sims_agent.py`

**Interfaces:**
- Consumes: the selected relationship track's tuned `headline`
- Consumes: the already-observed nonzero relationship delta
- Preserves: successful relationship result and observed Core consequence if the visual call fails

- [ ] **Step 1: Add failing headline assertions**

Give the fake romance track a recording headline:

```python
headline_calls = []
romance_track.headline = SimpleNamespace(
    send_headline_message=lambda sim_info, value: headline_calls.append(
        (sim_info, value)
    )
)
```

After the existing `+5` romance assertion, require exactly one explicit headline for each Sim:

```python
assert headline_calls == [
    (romance_session.target.sim_info, 5),
    (romance_session.actor.sim_info, 5),
]
```

Add compact cases beside it proving that zero observed delta sends nothing and that a raising
headline logs the visual failure while `apply_relationship_outcome` still returns the observed
change with no relationship error.

- [ ] **Step 2: Run the focused test and verify RED**

Run the command from Task 1, Step 2.

Expected: FAIL because `apply_relationship_outcome` does not explicitly dispatch the tuned
headline.

- [ ] **Step 3: Add one visual-only helper**

Add this beside the relationship helpers:

```python
def show_relationship_headlines(track, source_info, target_info, observed):
    if not observed:
        return
    send = getattr(getattr(track, "headline", None), "send_headline_message", None)
    if not callable(send):
        write_marker("Native relationship headline unavailable")
        return
    for sim_info in (source_info, target_info):
        try:
            send(sim_info, observed)
        except Exception:
            write_marker("Relationship headline failed:\n" + traceback.format_exc())
```

In `apply_relationship_outcome`, call it once after computing a nonzero `observed` value and before
returning `changes`:

```python
if observed:
    show_relationship_headlines(track, source_info, target_info, observed)
```

Do not return a relationship error from this helper.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run the Task 1, Step 2 command again.

Expected: PASS, including two-Sim dispatch, zero suppression, and visual-only failure handling.

---

### Task 3: Play Only the EA Conversation Animation While Waiting

**Files:**
- Modify: `adapters/thesims4/tests/test_sims4_mod_autonomy.py`
- Modify: `adapters/thesims4/ts4script/ai_sims_agent.py`

**Interfaces:**
- Reuses: `find_action_affordance("friendly_chat")`
- Reuses: `affordance.basic_content.animation_ref(interaction, sequence=...)`
- Preserves: the current waiting interaction as the only queued interaction

- [ ] **Step 1: Add a failing animation-only lifecycle test**

Configure the fake friendly-chat affordance so invoking its complete basic content fails, while its
animation reference records use:

```python
animation_calls = []

class FakeBasicContent:
    def __call__(self, *_args, **_kwargs):
        raise AssertionError("full native social content must not run")

    def animation_ref(self, interaction, sequence):
        animation_calls.append((interaction, sequence))
        return ("conversation-animation", sequence)

mixer.basic_content = FakeBasicContent()
```

Update the waiting runner assertions so its first yielded child is the animation tuple and confirm:

```python
mapped_aop_count = len(mapped_aops)
waiting_runner = waiting._run_interaction_gen("timeline")
assert next(waiting_runner) == ("conversation-animation", "next-tick")
assert animation_calls == [(waiting, "next-tick")]
assert len(queued_waiting) == 1
assert len(mapped_aops) == mapped_aop_count
```

Keep the existing response and cancellation completion assertions. Add one unavailable-participant
case and one missing/raising `animation_ref` case; both must close or continue safely without
queueing another interaction or applying a consequence. Give the waiting fake a recording
`cancel(...)` method and assert a displayed backend response cancels it with
`FinishingType.NATURAL`, so a running animation is interrupted rather than allowed to finish after
the answer appears.

- [ ] **Step 2: Run the focused test and verify RED**

Run the command from Task 1, Step 2.

Expected: FAIL because the waiting loop currently yields only `next-tick`.

- [ ] **Step 3: Add the minimal animation-only wrapper**

Add one helper beside `find_action_affordance`:

```python
def waiting_conversation_animation(interaction, sequence):
    try:
        affordance = find_action_affordance("friendly_chat")
        basic_content = getattr(affordance, "basic_content", None)
        animation_ref = getattr(basic_content, "animation_ref", None)
        if not callable(animation_ref):
            return sequence
        return animation_ref(interaction, sequence=sequence)
    except Exception:
        write_marker("Waiting conversation animation failed:\n" + traceback.format_exc())
        return sequence
```

Wrap only the existing one-tick child inside `EmpneonWaitingInteraction._run_interaction_gen`:

```python
child = element_utils.sleep_until_next_tick_element()
child = waiting_conversation_animation(self, child)
yield from element_utils.run_child(timeline, child)
```

Import `FinishingType` from `interactions.interaction_finisher`. In
`show_empneon_chat_result`, set `session.response_received` first, then interrupt the waiting
interaction after the response notification is displayed:

```python
session.response_received = displayed
if displayed:
    cancel = getattr(session.interaction, "cancel", None)
    if callable(cancel):
        cancel(
            FinishingType.NATURAL,
            cancel_reason_msg="Empneon response received",
        )
```

The loop already closes canceled or unavailable sessions. Do not instantiate the native
affordance, construct an AOP, invoke `basic_content(...)`, or push anything onto either Sim's
queue.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run the Task 1, Step 2 command again.

Expected: PASS, with the animation reference invoked and no full native social content.

---

### Task 4: Document and Verify the Source Build

**Files:**
- Modify: `adapters/thesims4/docs/in-game-core-feature-test-plan.md`
- Modify: `adapters/thesims4/docs/in-game-core-feature-test-results.md`
- Modify: `docs/superpowers/specs/2026-07-23-sims4-single-turn-social-design.md`

- [ ] **Step 1: Update live verification**

Record the three new checks:

- submitted and response notifications show the approved primary/secondary portrait order;
- both Sims visibly animate only while **Waiting for response** is active;
- each nonzero friendship/romance result shows the tuned native headline above both Sims.

Retain the explicit deferral of stronger `+++` and milestone effects. Record that the waiting
animation is live-confirmed while dual-portrait order and exact floating symbols remain open.

- [ ] **Step 2: Run complete Sims adapter verification**

From `adapters/thesims4` run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests
py -3.7 build_mod.py
```

Expected: all Sims adapter tests pass and both mod artifacts rebuild successfully.

- [ ] **Step 3: Inspect without committing**

From the repository root run:

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors; all changes remain uncommitted on `main`.

- [ ] **Step 4: Hand off the live test**

Ask the user to install the rebuilt source mod, restart The Sims 4 so the `.ts4script` reloads, and
run the updated Test 5. Record observed portrait order, animation behavior, and exact friendship or
romance headline symbols before calling the feature complete.
