# Sims 4 Single-Turn Empneon Social Implementation Plan

**Status (2026-07-23): Implemented; core flow and waiting animation live-confirmed.** Exact
dual-portrait layout and floating relationship symbols remain open visual checks.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the held multi-turn Empneon Social with one cancelable request/answer transaction that uses portrait notifications and applies one bounded, observable native Sims relationship outcome without queueing a second social.

**Architecture:** The backend adds a validated semantic `relationship_outcome` to the existing model response and the Sims adapter converts it into the proposal's adapter action. The script mod reuses its existing tuned affordance for two short queue phases, displays speaker-owned notifications, applies a fixed native friendship or romance score only after dialogue delivery, and confirms only the observed game delta to Core.

**Tech Stack:** Python 3.7 script mod, Python 3.11+ backend/Core, The Sims 4 native interaction and relationship APIs, SQLite, existing pytest fakes, standard library only.

## Global Constraints

- Each player-triggered Empneon Social carries exactly one player message and one answer.
- Keep the pie-menu entry named **Empneon Social**.
- Show **Start conversation** while routing and **Waiting for response** while the provider request
  is pending.
- A later message requires selecting Empneon Social again and receives a new conversation ID.
- Cancellation suppresses late dialogue, delivery confirmation, memory, trust, relationship loot, and Core consequences.
- Do not queue a response-derived Sims social.
- Apply at most one fixed mild relationship outcome per decision ID.
- The model chooses only a bounded semantic outcome, never a tuning ID or number.
- Report only observed Sims friendship or romance changes to Core.
- Add no dependency, database migration, provider request, or new persistence format.
- Keep stronger `+++` and milestone effects deferred.
- Do not commit until the user explicitly requests it.

---

## File Structure

- `adapters/thesims4/backend/ai_sims_server.py`
  - Extend and validate the existing structured dialogue response.
  - Keep safe fallbacks relationship-neutral.
- `adapters/thesims4/src/empneon_thesims4/adapter.py`
  - Persist the semantic outcome in the decision and expose it as the adapter action.
- `adapters/thesims4/ts4script/ai_sims_agent.py`
  - Replace the held multi-turn session with two short queue phases.
  - Show portrait notifications.
  - Apply and observe native relationship outcomes.
- `adapters/thesims4/tests/test_sims4_backend.py`
  - Cover response schema, semantic validation, fallbacks, and proposal output.
- `adapters/thesims4/tests/test_adapter.py`
  - Cover decision/action round trips for every outcome.
- `adapters/thesims4/tests/test_sims4_mod_autonomy.py`
  - Cover queue lifecycle, cancellation, notifications, native relationship mutation, and idempotence.
- `adapters/thesims4/docs/in-game-core-feature-test-plan.md`
  - Replace the obsolete held multi-turn Test 5 procedure with the single-turn live matrix.
- `adapters/thesims4/docs/in-game-core-feature-test-results.md`
  - Record the implementation handoff without claiming unobserved in-game results.

---

### Task 1: Add the bounded relationship-outcome response contract

**Files:**
- Modify: `adapters/thesims4/backend/ai_sims_server.py:205-291,911-979,1690-1702,1812-1919`
- Test: `adapters/thesims4/tests/test_sims4_backend.py`

**Interfaces:**
- Produces: `RELATIONSHIP_OUTCOMES: tuple[str, ...]`
- Produces: `validated_relationship_outcome(response: Mapping[str, object]) -> str`
- Changes: `normalize_response(...)` always returns `relationship_outcome`
- Preserves: one provider generation per attempt and existing response-category validation

- [ ] **Step 1: Add failing schema and normalization tests**

Add tests beside the existing response-category tests:

```python
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            {
                "dialogue": "I enjoy talking with you too.",
                "response_category": "friendly",
                "relationship_outcome": "friendship_positive",
            },
            "friendship_positive",
        ),
        (
            {
                "dialogue": "Please leave me alone.",
                "response_category": "mean",
                "relationship_outcome": "friendship_negative",
            },
            "friendship_negative",
        ),
        (
            {
                "dialogue": "Yes, I would love to date you.",
                "response_category": "romance",
                "relationship_outcome": "romance_positive",
            },
            "romance_positive",
        ),
        (
            {
                "dialogue": "No, I would rather stay friends.",
                "response_category": "romance",
                "relationship_outcome": "romance_negative",
            },
            "romance_negative",
        ),
        (
            {
                "dialogue": "The weather changed.",
                "response_category": "friendly",
                "relationship_outcome": "friendship_lifetime",
            },
            "none",
        ),
    ],
)
def test_relationship_outcome_is_bounded_and_grounded(raw, expected) -> None:
    response = ai_sims_server.normalize_response(raw)
    assert response["relationship_outcome"] == expected


def test_dialogue_schema_requires_relationship_outcome() -> None:
    field = ai_sims_server.DIALOGUE_SCHEMA["properties"]["relationship_outcome"]
    assert field == {
        "type": "string",
        "enum": [
            "friendship_positive",
            "friendship_negative",
            "romance_positive",
            "romance_negative",
            "none",
        ],
    }
    assert "relationship_outcome" in ai_sims_server.DIALOGUE_SCHEMA["required"]
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run from `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k relationship_outcome
```

Expected: failures because the schema and normalized field do not exist.

- [ ] **Step 3: Add the schema field and semantic validator**

Add near `DIALOGUE_SCHEMA`:

```python
RELATIONSHIP_OUTCOMES = (
    "friendship_positive",
    "friendship_negative",
    "romance_positive",
    "romance_negative",
    "none",
)
ROMANTIC_RECIPROCATION = re.compile(
    r"\b(yes|i would love|i'd love|me too|feel the same|date sounds|be together)\b"
)
ROMANTIC_REJECTION = re.compile(
    r"\b(no|not interested|rather stay friends|do not want|don't want|cannot|can't)\b"
)


def validated_relationship_outcome(response):
    value = str(response.get("relationship_outcome") or "none")
    dialogue = str(response.get("dialogue") or "").casefold()
    category = str(response.get("response_category") or "")
    if value not in RELATIONSHIP_OUTCOMES:
        return "none"
    if value == "friendship_positive" and category not in ("friendly", "funny"):
        return "none"
    if value == "friendship_negative" and category not in ("mean", "mischief"):
        return "none"
    if value == "romance_positive" and (
        category != "romance" or not ROMANTIC_RECIPROCATION.search(dialogue)
    ):
        return "none"
    if value == "romance_negative" and (
        category != "romance" or not ROMANTIC_REJECTION.search(dialogue)
    ):
        return "none"
    return value
```

Add this property and required key to `DIALOGUE_SCHEMA`:

```python
"relationship_outcome": {
    "type": "string",
    "enum": list(RELATIONSHIP_OUTCOMES),
},
```

After constructing `response` in `normalize_response`, set:

```python
response["relationship_outcome"] = validated_relationship_outcome(
    dict(response, relationship_outcome=raw.get("relationship_outcome"))
)
```

- [ ] **Step 4: Update the prompt and relationship-neutral fallback**

Change the response example to include:

```json
"relationship_outcome": "romance_positive"
```

Add these prompt rules:

```text
Choose one relationship_outcome. Use friendship_positive only for a warm or funny response,
friendship_negative only for a mean or hostile response, romance_positive only when the Speaker
clearly reciprocates romance, romance_negative only for an explicit romantic rejection, and none
otherwise. Never return a numeric relationship change.
```

Replace the existing blanket prohibition on friendship and romance fields with:

```text
Do not return numeric friendship, romance, attraction, tuning, or action fields; the adapter and
game own them.
```

Set every `reasoning_fallback_response` input to:

```python
"relationship_outcome": "none",
```

- [ ] **Step 5: Add inconsistency and fallback tests**

```python
@pytest.mark.parametrize(
    "raw",
    [
        {
            "dialogue": "That is kind of you.",
            "response_category": "friendly",
            "relationship_outcome": "romance_positive",
        },
        {
            "dialogue": "No, I would rather stay friends.",
            "response_category": "romance",
            "relationship_outcome": "romance_positive",
        },
        {
            "dialogue": "Yes, I would love to date you.",
            "response_category": "romance",
            "relationship_outcome": "romance_negative",
        },
    ],
)
def test_inconsistent_relationship_outcome_degrades_to_none(raw) -> None:
    assert ai_sims_server.normalize_response(raw)["relationship_outcome"] == "none"


def test_reasoning_fallback_has_no_relationship_outcome() -> None:
    response = ai_sims_server.reasoning_fallback_response(
        {"message": "Would you date me?"},
        {"recalled_memories": [], "conversation": [], "emotions": {}},
    )
    assert response["relationship_outcome"] == "none"
```

- [ ] **Step 6: Run the backend tests and verify GREEN**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py
```

Expected: all backend tests pass.

- [ ] **Step 7: Prepare the commit only when authorized**

```powershell
git add adapters/thesims4/backend/ai_sims_server.py adapters/thesims4/tests/test_sims4_backend.py
git commit -m "feat(sims4): classify relationship outcomes"
```

Do not run this step until the user requests commits.

---

### Task 2: Make the relationship outcome the adapter action

**Files:**
- Modify: `adapters/thesims4/src/empneon_thesims4/adapter.py:250-380`
- Test: `adapters/thesims4/tests/test_adapter.py`
- Test: `adapters/thesims4/tests/test_sims4_backend.py`

**Interfaces:**
- Consumes: `response["relationship_outcome"]`
- Produces: adapter actions `relationship.friendship_positive`, `relationship.friendship_negative`, `relationship.romance_positive`, `relationship.romance_negative`, or `none`
- Produces: decision delta `StateDelta("social.relationship_outcome", "set", outcome)`
- Removes: response-category-derived `social.<category>` action authority for player dialogue

- [ ] **Step 1: Add failing adapter round-trip tests**

```python
@pytest.mark.parametrize(
    ("outcome", "action"),
    [
        ("friendship_positive", "relationship.friendship_positive"),
        ("friendship_negative", "relationship.friendship_negative"),
        ("romance_positive", "relationship.romance_positive"),
        ("romance_negative", "relationship.romance_negative"),
        ("none", "none"),
    ],
)
def test_relationship_outcome_is_the_player_dialogue_action(outcome, action) -> None:
    adapter = Sims4Adapter(
        {
            "speaker": {"id": "b", "name": "B"},
            "listener": {"id": "a", "name": "A"},
            "message": "hello",
        }
    )
    decision = adapter.decision_from_response(
        {
            "dialogue": "A grounded response.",
            "response_category": "friendly",
            "tone_tags": [],
            "trust_delta": 0,
            "relationship_outcome": outcome,
        },
        "event-1",
    )
    assert adapter.action_for(decision) == action
    assert adapter.response_for(decision)["relationship_outcome"] == outcome
```

- [ ] **Step 2: Run the focused adapter tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_adapter.py -k relationship_outcome
```

Expected: failure because the decision still derives `social.<category>`.

- [ ] **Step 3: Implement the outcome/action mapping**

Add module constants:

```python
RELATIONSHIP_OUTCOMES = (
    "friendship_positive",
    "friendship_negative",
    "romance_positive",
    "romance_negative",
    "none",
)
RELATIONSHIP_ACTIONS = {
    outcome: "relationship." + outcome
    for outcome in RELATIONSHIP_OUTCOMES
    if outcome != "none"
}
```

In `decision_from_response`, normalize the outcome and append its state delta:

```python
outcome = str(response.get("relationship_outcome") or "none")
if outcome not in RELATIONSHIP_OUTCOMES:
    outcome = "none"
changes.extend(
    (
        StateDelta("social.response_category", "set", category),
        StateDelta("social.tone_tags", "set", _items(response.get("tone_tags"))),
        StateDelta("social.relationship_outcome", "set", outcome),
        StateDelta(
            "animation",
            "set",
            RELATIONSHIP_ACTIONS.get(outcome, "none"),
        ),
    )
)
```

In `action_for`, accept relationship actions before checking configured native socials:

```python
if action in RELATIONSHIP_ACTIONS.values() or action == "none":
    return action
```

In `response_for`, default and restore the semantic field:

```python
"relationship_outcome": "none",
```

```python
elif change.path == "social.relationship_outcome":
    response["relationship_outcome"] = change.value
```

- [ ] **Step 4: Update backend proposal assertions**

Change player-dialogue tests that currently expect `social.romance` or another category action:

```python
assert response["response_category"] == "romance"
assert response["relationship_outcome"] == "romance_positive"
assert response["suggested_action"] == "relationship.romance_positive"
```

Keep autonomous-action tests unchanged; they still use mapped native socials.

- [ ] **Step 5: Run adapter and backend suites**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_adapter.py tests/test_sims4_backend.py
```

Expected: all selected tests pass.

- [ ] **Step 6: Prepare the commit only when authorized**

```powershell
git add adapters/thesims4/src/empneon_thesims4/adapter.py adapters/thesims4/tests/test_adapter.py adapters/thesims4/tests/test_sims4_backend.py
git commit -m "feat(sims4): propose relationship loot"
```

Do not run this step until the user requests commits.

---

### Task 3: Replace the held multi-turn session with two short queue phases

**Files:**
- Modify: `adapters/thesims4/ts4script/ai_sims_agent.py:147-315,1041-1087,1632-1767,1826-1907`
- Test: `adapters/thesims4/tests/test_sims4_mod_autonomy.py`

**Interfaces:**
- Produces: `queue_awaiting_answer(session: EmpneonConversationSession, message: str) -> bool`
- Produces: `show_dialogue_notification(sim: object, dialogue: str) -> bool`
- Reuses: `EmpneonSocialInteraction` and its existing tuning resource
- Changes: `EmpneonSocialInteraction.get_name` returns pie label or **Start conversation**;
  `EmpneonWaitingInteraction.get_name` returns **Waiting for response**

- [ ] **Step 1: Add a failing single-turn lifecycle test**

Add a focused test using the existing fake game modules:

```python
def test_empneon_social_is_one_cancelable_turn(monkeypatch) -> None:
    # Add this focused block inside the existing loaded-mod test, reusing its
    # pie_interaction, dialogs, notifications, and submitted collections.
    submitted = []
    pushed = []
    actor = pie_interaction.sim
    target = pie_interaction.target
    waiting = agent.EmpneonSocialInteraction()
    waiting.sim = actor
    waiting.target = target

    monkeypatch.setattr(
        actor,
        "push_super_affordance",
        lambda affordance, queued_target, context: pushed.append(
            SimpleNamespace(
                affordance=affordance,
                target=queued_target,
                context=context,
                interaction=waiting,
            )
        ) or pushed[-1],
    )
    monkeypatch.setattr(
        agent,
        "submit_empneon_chat",
        lambda session, message: submitted.append((session, message)),
    )
    monkeypatch.setattr(
        agent,
        "show_dialogue_notification",
        lambda sim, dialogue: notifications.append((sim, dialogue)) or True,
    )

    runner = pie_interaction._run_interaction_gen(SimpleNamespace())
    with pytest.raises(StopIteration):
        next(runner)
    session = agent._CONVERSATION_SESSIONS[str(actor.sim_info.sim_id)]
    assert pie_interaction.get_name() == "Start conversation"

    dialog = dialogs[-1]
    dialog.accepted = True
    dialog.text_input_responses = {"message": "Hello, Karmine."}
    dialog.listener(dialog)

    assert notifications == [(actor, "Hello, Karmine.")]
    assert waiting.get_name() == "Waiting for response"
    assert submitted == [(session, "Hello, Karmine.")]
    assert session.phase == "waiting_for_backend"
```

Use the existing fake `UiDialogTextInputOkCancel`, interaction context, and queued-interaction
helpers rather than adding a second test framework.

- [ ] **Step 2: Run the lifecycle test and verify RED**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_mod_autonomy.py -k one_cancelable_turn
```

Expected: failure because the original interaction remains in its tick loop and no waiting task is pushed.

- [ ] **Step 3: Make queue names instance-aware**

Replace the simple name method with:

```python
@flexmethod
def get_name(cls, inst, *args, **kwargs):
    if inst is None:
        label = "Empneon Social"
    else:
        label = getattr(inst, "_empneon_queue_name", "Start conversation")
    return LocalizationHelperTuning.get_raw_text(label)
```

Set `_empneon_queue_name = "Start conversation"` on a selected instance and
the separate **Waiting for response** affordance on the programmatically pushed instance.

- [ ] **Step 4: End Start conversation after opening input**

Replace the held loop in `_run_interaction_gen` with two explicit branches:

```python
def _run_interaction_gen(self, timeline):
    if getattr(self, "_empneon_waiting", False):
        return (yield from self._run_waiting_gen(timeline))
    actor = getattr(self, "sim", None)
    target = getattr(self, "target", None)
    actor_id = str(getattr(getattr(actor, "sim_info", None), "sim_id", ""))
    if not actor_id or target is None or actor_id in _CONVERSATION_SESSIONS:
        return False
    self._empneon_queue_name = "Start conversation"
    session = EmpneonConversationSession(self, actor, target)
    _CONVERSATION_SESSIONS[actor_id] = session
    show_empneon_message_dialog(session)
    return True
```

Because the start interaction no longer owns a long-running `finally` block, make
`EmpneonConversationSession.close()` unregister itself:

```python
def close(self, canceled=False):
    if self.closed:
        return
    self.closed = True
    self.canceled = bool(canceled)
    self.phase = "closed"
    actor_id = str(getattr(getattr(self.actor, "sim_info", None), "sim_id", ""))
    if _CONVERSATION_SESSIONS.get(actor_id) is self:
        _CONVERSATION_SESSIONS.pop(actor_id, None)
```

Keep the existing failed-proposal report when `pending_decision` exists, but remove the direct
`native_interaction.cancel()` call: player sessions no longer own a response-derived native
interaction, and the waiting generator exits from the closed phase.

Add the waiting branch:

```python
def _run_waiting_gen(self, timeline):
    session = find_conversation_session(getattr(self, "_empneon_session_id", None))
    if session is None:
        return False
    session.waiting_interaction = self
    try:
        while not session.closed and session.phase == "waiting_for_backend":
            yield from element_utils.run_child(
                timeline, element_utils.sleep_until_next_tick_element()
            )
        return not session.canceled
    finally:
        if not session.closed and session.phase == "waiting_for_backend":
            session.close(canceled=True)
```

Do not launch a normal Sims social or animation here. The first implementation leaves the Sims
visually idle inside the waiting task, which is the consequence-free fallback approved by the
design.

- [ ] **Step 5: Queue Waiting for response before starting provider work**

Add:

```python
def queue_awaiting_answer(session, message):
    actor = session.actor
    target = session.target
    affordance = services.affordance_manager().get(EMPNEON_SOCIAL_INTERACTION_ID)
    context = InteractionContext(
        actor,
        InteractionContext.SOURCE_SCRIPT_WITH_USER_INTENT,
        Priority.High,
    )
    result = actor.push_super_affordance(affordance, target, context)
    waiting = getattr(result, "interaction", None)
    if waiting is None:
        session.close(canceled=True)
        show_empneon_notification(actor, "Empneon error", "Could not await the answer.")
        return False
    waiting._empneon_waiting = True
    waiting._empneon_session_id = session.id
    session.waiting_interaction = waiting
    turn_id = session.begin_turn()
    if turn_id is None:
        session.close(canceled=True)
        return False
    submit_empneon_chat(session, message)
    return True
```

In the input callback, replace direct submission with:

```python
show_dialogue_notification(actor, message)
queue_awaiting_answer(session, message)
```

- [ ] **Step 6: Replace transcript dialogs with portrait notifications**

Add:

```python
def show_dialogue_notification(sim, dialogue):
    try:
        name = sim_full_name(getattr(sim, "sim_info", sim))
        notification = UiDialogNotification.TunableFactory().default(
            sim,
            title=raw_text(name),
            text=raw_text(dialogue),
        )
        notification.show_dialog()
        return True
    except Exception:
        write_marker(traceback.format_exc())
        return False
```

On a successful backend response:

```python
if not show_dialogue_notification(session.target, str(data.get("dialogue") or "...")):
    report_canceled_proposal(data)
    session.close(canceled=True)
    return False
session.response_data = data
session.phase = "confirming_dialogue"
report_dialogue_delivery(
    session.actor,
    data.get("_empneon_payload"),
    data,
    queue_native=False,
    session_id=session.id,
    turn_id=session.turn_id,
)
```

Remove the response text-input dialog, transcript continuation, `next_message`, and
`finish_displayed_turn`/`continue_displayed_turn` path for player sessions.

For the player submission, start no request when its notification cannot be displayed:

```python
if not show_dialogue_notification(actor, message):
    session.close(canceled=True)
    show_empneon_notification(actor, "Empneon error", "Could not display the message.")
    return
queue_awaiting_answer(session, message)
```

- [ ] **Step 7: Add cancellation and late-result assertions**

```python
def test_canceling_awaiting_answer_discards_late_result(monkeypatch) -> None:
    reports = []
    shown = []
    session = agent.EmpneonConversationSession(
        pie_interaction, pie_interaction.sim, pie_interaction.target
    )
    session.turn_id = 1
    session.phase = "waiting_for_backend"
    waiting = agent.EmpneonSocialInteraction()
    session.waiting_interaction = waiting
    monkeypatch.setattr(
        agent, "report_canceled_proposal", lambda data: reports.append(data)
    )
    monkeypatch.setattr(
        agent,
        "show_dialogue_notification",
        lambda sim, dialogue: shown.append((sim, dialogue)) or True,
    )
    session.close(canceled=True)

    late = {
        "decision_id": "late-decision",
        "suggested_action": "relationship.friendship_positive",
        "dialogue": "Late answer.",
    }
    accepted = session.accept_backend_result(
        session.turn_id,
        late,
        None,
    )

    assert accepted is False
    assert session.canceled is True
    assert shown == []
    assert reports == [late]
```

Also assert that closing the input dialog before submission creates no backend request and no
waiting task. Add a notification-failure case asserting no `/dialogue-result`, relationship
mutation, or confirmed memory is produced.

- [ ] **Step 8: Run the complete script-mod suite**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_mod_autonomy.py
```

Expected: all script-mod tests pass with obsolete multi-turn assertions replaced by single-turn
queue assertions.

- [ ] **Step 9: Prepare the commit only when authorized**

```powershell
git add adapters/thesims4/ts4script/ai_sims_agent.py adapters/thesims4/tests/test_sims4_mod_autonomy.py
git commit -m "fix(sims4): make Empneon Social single turn"
```

Do not run this step until the user requests commits.

---

### Task 4: Apply and confirm one observed native relationship outcome

**Files:**
- Modify: `adapters/thesims4/ts4script/ai_sims_agent.py:852-921,1041-1136,1360-1498`
- Test: `adapters/thesims4/tests/test_sims4_mod_autonomy.py`
- Test: `adapters/thesims4/tests/test_sims4_backend.py`

**Interfaces:**
- Produces: `find_relationship_track(name: str) -> object | None`
- Produces: `apply_relationship_loot(session: EmpneonConversationSession, data: dict) -> list[dict]`
- Produces: `complete_delivered_turn(session: EmpneonConversationSession) -> None`
- Uses fixed mild magnitude: `5` relationship points
- Confirms: `/action-result` with the exact proposed relationship action and observed delta

- [ ] **Step 1: Extract relationship-track lookup and add failing loot tests**

Refactor the existing lookup inside `relationship_payload` into:

```python
def find_relationship_track(name):
    for resource_name in ("STATISTIC", "RELATIONSHIP_TRACK"):
        resource_type = getattr(sims4.resources.Types, resource_name, None)
        if resource_type is None:
            continue
        manager = services.get_instance_manager(resource_type)
        track = next(
            (
                tuning
                for tuning in manager.types.values()
                if getattr(tuning, "__name__", "") == name
            ),
            None,
        )
        if track is not None:
            return track
    return None
```

Add a parameterized test:

```python
@pytest.mark.parametrize(
    ("outcome", "track_name", "delta", "path"),
    [
        ("friendship_positive", "LTR_Friendship_Main", 5, "relationship.friendship"),
        ("friendship_negative", "LTR_Friendship_Main", -5, "relationship.friendship"),
        ("romance_positive", "LTR_Romance_Main", 5, "relationship.romance"),
        ("romance_negative", "LTR_Romance_Main", -5, "relationship.romance"),
    ],
)
def test_relationship_loot_reports_only_observed_change(
    monkeypatch, outcome, track_name, delta, path
) -> None:
    source_tracker = SimpleNamespace()
    source_info = SimpleNamespace(sim_id="b", relationship_tracker=source_tracker)
    target_info = SimpleNamespace(sim_id="a")
    session = agent.EmpneonConversationSession(
        pie_interaction,
        SimpleNamespace(sim_info=target_info),
        SimpleNamespace(sim_info=source_info),
    )
    before = {"friendship": 10, "romance": 10}
    after = dict(before)
    after["friendship" if track_name == "LTR_Friendship_Main" else "romance"] += 3
    scores = iter((before, after))
    calls = []
    track = type(track_name, (), {})

    monkeypatch.setattr(agent, "find_relationship_track", lambda name: track)
    monkeypatch.setattr(
        source_tracker,
        "add_relationship_score",
        lambda target_id, amount, selected_track: calls.append(
            (target_id, amount, selected_track)
        ),
    )
    monkeypatch.setattr(
        agent,
        "relationship_payload",
        lambda _source, _target: next(scores),
    )

    changes = agent.apply_relationship_loot(
        session,
        {
            "decision_id": "decision-1",
            "relationship_outcome": outcome,
            "suggested_action": "relationship." + outcome,
        },
    )

    assert calls == [(session.actor.sim_info.sim_id, delta, track)]
    assert changes == [{"path": path, "operation": "increment", "value": 3}]
```

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_mod_autonomy.py -k relationship_loot
```

Expected: failure because the helper does not exist.

- [ ] **Step 3: Implement the native relationship mutation boundary**

Add:

```python
RELATIONSHIP_LOOT = {
    "friendship_positive": ("friendship", "LTR_Friendship_Main", 5),
    "friendship_negative": ("friendship", "LTR_Friendship_Main", -5),
    "romance_positive": ("romance", "LTR_Romance_Main", 5),
    "romance_negative": ("romance", "LTR_Romance_Main", -5),
}


def apply_relationship_loot(session, data):
    outcome = str(data.get("relationship_outcome") or "none")
    configured = RELATIONSHIP_LOOT.get(outcome)
    if configured is None:
        return []
    key, track_name, amount = configured
    source_info = getattr(session.target, "sim_info", None)
    target_info = getattr(session.actor, "sim_info", None)
    track = find_relationship_track(track_name)
    tracker = getattr(source_info, "relationship_tracker", None)
    add_score = getattr(tracker, "add_relationship_score", None)
    if track is None or target_info is None or not callable(add_score):
        raise RuntimeError("native relationship loot unavailable for {}".format(outcome))
    before = relationship_payload(source_info, target_info)
    add_score(target_info.sim_id, amount, track)
    after = relationship_payload(source_info, target_info)
    observed = int(after.get(key, 0)) - int(before.get(key, 0))
    write_marker(
        "Empneon relationship outcome {}: {} -> {} observed {:+d}".format(
            outcome,
            source_info.sim_id,
            target_info.sim_id,
            observed,
        )
    )
    if not observed:
        return []
    return [
        {
            "path": "relationship." + key,
            "operation": "increment",
            "value": observed,
        }
    ]
```

This calls the game's native relationship tracker so the game remains authoritative and sends its
normal relationship update to the client. The live test, not the unit test, determines which
headline symbols the current build displays.

- [ ] **Step 4: Apply loot only after dialogue delivery acknowledgement**

Replace the old `continue_displayed_turn` event handling:

```python
def complete_delivered_turn(session):
    if session.closed or session.relationship_outcome_applied:
        return
    session.relationship_outcome_applied = True
    data = session.response_data or {}
    action = str(data.get("suggested_action") or "none")
    try:
        changes = apply_relationship_loot(session, data)
    except Exception as exc:
        write_marker("Empneon relationship loot failed: {!r}".format(exc))
        changes = []
    if action == "none":
        session.close()
    else:
        report_action_result(
            data["decision_id"],
            action,
            "succeeded",
            changes=changes,
            session_id=session.id,
            turn_id=session.turn_id,
        )
        session.close()
```

Initialize `session.relationship_outcome_applied = False` in
`EmpneonConversationSession.__init__`, then call `complete_delivered_turn(session)` only for the
matching `dialogue_displayed` event.

Do not execute loot in `accept_backend_result`; that method only displays the answer notification
and starts dialogue-delivery confirmation.

- [ ] **Step 5: Add idempotence, zero-delta, and failure tests**

```python
def test_relationship_loot_is_not_applied_twice(monkeypatch) -> None:
    session = agent.EmpneonConversationSession(
        pie_interaction, pie_interaction.sim, pie_interaction.target
    )
    session.turn_id = 1
    session.phase = "confirming_dialogue"
    session.response_data = {
        "decision_id": "decision-once",
        "suggested_action": "relationship.friendship_positive",
    }
    applied = []
    monkeypatch.setattr(
        agent,
        "apply_relationship_loot",
        lambda _session, _data: applied.append("once") or [],
    )
    monkeypatch.setattr(agent, "report_action_result", lambda *args, **kwargs: None)
    agent.complete_delivered_turn(session)
    agent.complete_delivered_turn(session)
    assert applied == ["once"]


def test_missing_relationship_track_preserves_dialogue_without_consequence(monkeypatch) -> None:
    session = agent.EmpneonConversationSession(
        pie_interaction, pie_interaction.sim, pie_interaction.target
    )
    session.turn_id = 1
    session.phase = "confirming_dialogue"
    session.response_data = {
        "decision_id": "decision-no-track",
        "suggested_action": "relationship.romance_positive",
        "relationship_outcome": "romance_positive",
    }
    reports = []
    monkeypatch.setattr(agent, "find_relationship_track", lambda _name: None)
    monkeypatch.setattr(
        agent,
        "report_action_result",
        lambda decision_id, action, status, reason=None, changes=None, **kwargs: reports.append(
            {
                "decision_id": decision_id,
                "action": action,
                "status": status,
                "reason": reason,
                "changes": changes or [],
            }
        ),
    )
    agent.complete_delivered_turn(session)
    body = reports[-1]
    assert body["status"] == "succeeded"
    assert body["changes"] == []
    assert session.closed is True
```

Also test `relationship_outcome == "none"` performs no tracker call and relies on
`/dialogue-result` to confirm the `none` proposal.

- [ ] **Step 6: Verify Core accepts observed relationship consequences**

Extend the existing `/action-result` backend test:

```python
result = ai_sims_server.confirm_action(
    {
        "decision_id": decision_id,
        "action": "relationship.romance_positive",
        "status": "succeeded",
        "changes": [
            {
                "path": "relationship.romance",
                "operation": "increment",
                "value": 3,
            }
        ],
    }
)
assert result["status"] == "succeeded"
assert result["consequences"] == 2  # action marker plus observed romance delta
```

Assert a mismatched action or duplicate conflicting result still returns HTTP 400.

- [ ] **Step 7: Run Sims adapter tests**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider
```

Expected: all Sims adapter tests pass.

- [ ] **Step 8: Prepare the commit only when authorized**

```powershell
git add adapters/thesims4/ts4script/ai_sims_agent.py adapters/thesims4/tests/test_sims4_mod_autonomy.py adapters/thesims4/tests/test_sims4_backend.py
git commit -m "feat(sims4): apply native relationship outcomes"
```

Do not run this step until the user requests commits.

---

### Task 5: Document, build, and hand off the live Test 5 matrix

**Files:**
- Modify: `adapters/thesims4/docs/in-game-core-feature-test-plan.md:118-190`
- Modify: `adapters/thesims4/docs/in-game-core-feature-test-results.md:394-500`
- Verify: `adapters/thesims4/build_mod.py`
- Verify: `adapters/thesims4/dist/Empneon_TheSims4.ts4script`
- Verify: `adapters/thesims4/dist/Empneon_TheSims4.package`

**Interfaces:**
- Produces: source-built mod ready for the single-turn in-game test
- Preserves: uncommitted SQLite `-wal` and `-shm` runtime files
- Defers: stronger `+++` and relationship milestone effects

- [ ] **Step 1: Replace the Test 5 procedure**

Document this exact live matrix:

| Player message | Required validated outcome |
|---|---|
| “I enjoy talking with you.” | `friendship_positive` or `none`, matching the answer |
| “I hate you. Go away.” | `friendship_negative` or `none`, matching the answer |
| “Would you like to go on a date with me?” with clear reciprocation | `romance_positive` |
| The same invitation with explicit rejection | `romance_negative` |
| “Where did we agree to meet?” | `none` |

For every row, record:

- **Start conversation** and **Waiting for response** queue transitions;
- Sim A and Sim B notification portraits;
- exact answer and relationship outcome;
- friendship and romance immediately before and after;
- floating relationship symbols, if any;
- Core timeline/replay changes;
- absence of a response-derived social in either queue.

Add a cancellation row requiring no late notification, memory, trust, loot, or relationship
change.

- [ ] **Step 2: Record deferred effects explicitly**

Add to both the plan and results handoff:

```text
This implementation uses one mild outcome tier. Stronger +++ feedback and milestone effects such
as best-friend events, confessions, first kisses, and proposals remain deferred until ordinary
friendship and romance outcomes are verified in the current game build.
```

Keep Test 5 `PARTIAL` until the live matrix passes.

- [ ] **Step 3: Run all automated verification**

From the repository root:

```powershell
$env:PYTHONPATH='core\src;adapters\thesims4\src'
py -3.12 -m pytest -q -p no:cacheprovider core adapters/thesims4 tests scripts/test_release.py
py -3.12 -m ruff check core/src core/tests adapters/thesims4/src adapters/thesims4/tests adapters/thesims4/backend adapters/thesims4/ts4script tests scripts
py -3.12 -m mypy core/src adapters/thesims4/src
py -3.12 -m py_compile adapters/thesims4/backend/ai_sims_server.py adapters/thesims4/backend/empneon_state.py adapters/thesims4/ts4script/ai_sims_agent.py
empneon-regress core/scenarios/clod1-regressions.json
git diff --check
```

Expected: every command exits `0`. If full Ruff exposes unrelated legacy rules outside the current
CI scope, use the repository's documented CI Ruff command and record the distinction without
changing unrelated files.

- [ ] **Step 4: Build and install the source artifacts**

From `adapters/thesims4`:

```powershell
py -3.12 .\build_mod.py
.\install_mod.ps1
Get-FileHash -Algorithm SHA256 .\dist\Empneon_TheSims4.ts4script
Get-FileHash -Algorithm SHA256 .\dist\Empneon_TheSims4.package
```

Expected: both artifacts build, install, and have recorded hashes. Do not start or leave a backend
process running at handoff.

- [ ] **Step 5: Perform the live source-build retest**

The user starts the source backend and fully restarts The Sims 4. Execute the five-row matrix plus
manual cancellation. The gate passes only if:

- queue transitions do not deadlock;
- the waiting task can be canceled;
- portraits identify the actual speaker;
- cancellation suppresses every late effect;
- native friendship and romance outcomes match observed deltas;
- the current game build shows and records its actual floating feedback;
- no response-derived native social is queued;
- save/reload preserves confirmed memory and relationship state.

- [ ] **Step 6: Update results from observed evidence**

Record the exact game version, source commit, provider/model, artifact hashes, messages, answers,
outcomes, before/after relationship values, floating symbols, cancellation result, and
save/reload result. Do not claim exact `++`, hearts, broken hearts, or milestone behavior that was
not observed.

- [ ] **Step 7: Prepare the documentation commit only when authorized**

```powershell
git add adapters/thesims4/docs/in-game-core-feature-test-plan.md adapters/thesims4/docs/in-game-core-feature-test-results.md docs/superpowers/specs/2026-07-23-sims4-single-turn-social-design.md docs/superpowers/plans/2026-07-23-sims4-single-turn-social.md
git commit -m "docs(sims4): record single-turn social validation"
```

Do not run this step until the user requests commits.
