# Cross-Adapter Needs and Dialogue Continuity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Normalize game-owned need severity for both conversation actors, let the model use it without forced dialogue replacement, and retain conversation context during anti-repetition retries.

**Architecture:** Extend the existing `AgentStateSnapshot.needs` entries with a validated semantic status while leaving each adapter responsible for native scales and thresholds. The Sims adapter will preserve `-100..100` motives and build the existing normalized snapshot for each actor; the backend will prompt from both snapshots, remove need-omission rejection, and keep recent dialogue on retry.

**Tech Stack:** Python 3.12, pytest, standard-library dataclasses/JSON, existing Empneon Core contracts and Sims 4 adapter.

## Global Constraints

- `level` and `urgency` remain normalized to `0.0..1.0` for every game.
- `status` is exactly `satisfied`, `low`, or `critical`.
- Each adapter owns its native scale conversion and severity thresholds.
- The Sims 4 native motive range is preserved as `-100..100`.
- Sims bands are `-25..100` satisfied, `-50..-26` low, and `-100..-51` critical.
- Both actors' normalized identity, traits, affect, needs, and effects reach the model.
- Need omission alone never rejects or replaces a valid model response.
- Recent player inputs and model replies remain present during a repetition retry.
- Add no dependency, database migration, configurable threshold system, embeddings, or generated phrase library.
- Do not stage or delete SQLite `-wal` or `-shm` sidecars.
- Do not start the backend for unit tests; if a later manual check requires it, stop it before handoff.

---

### Task 1: Validate the common need status

**Files:**
- Modify: `core/src/empneon/core/contracts.py:60-63`
- Modify: `core/docs/adapter-development.md:14-23`
- Test: `core/tests/unit/test_contracts.py`

**Interfaces:**
- Consumes: existing `AgentStateSnapshot.needs: dict[str, object]` entries.
- Produces: optional need entry field `status: Literal["satisfied", "low", "critical"]`, validated at runtime without changing schema version 1.

- [ ] **Step 1: Write failing common-contract tests**

Add these tests to `core/tests/unit/test_contracts.py`:

```python
def test_agent_state_snapshot_accepts_common_need_status_and_native_scale() -> None:
    snapshot = AgentStateSnapshot.from_mapping(
        {
            "schema_version": 1,
            "adapter": "example-game",
            "agent_id": "alice",
            "needs": {
                "energy": {
                    "level": 0.4,
                    "urgency": 0.6,
                    "status": "low",
                    "native": {"value": 40, "minimum": 0, "maximum": 100},
                }
            },
        }
    )

    assert snapshot.needs["energy"]["status"] == "low"
    assert snapshot.needs["energy"]["native"]["minimum"] == 0


def test_agent_state_snapshot_rejects_unknown_need_status() -> None:
    with pytest.raises(ValueError, match="need status"):
        AgentStateSnapshot.from_mapping(
            {
                "schema_version": 1,
                "adapter": "test",
                "agent_id": "alice",
                "needs": {
                    "energy": {
                        "level": 0.5,
                        "urgency": 0.5,
                        "status": "orange",
                    }
                },
            }
        )
```

- [ ] **Step 2: Run the focused tests and verify the invalid status is accepted incorrectly**

Run from the repository root:

```powershell
$env:PYTHONPATH='core\src'; py -3.12 -m pytest -q -p no:cacheprovider core/tests/unit/test_contracts.py
```

Expected: `test_agent_state_snapshot_rejects_unknown_need_status` fails because no `ValueError` is raised.

- [ ] **Step 3: Add the minimal runtime validation**

In `AgentStateSnapshot.__post_init__`, extend the existing need loop to:

```python
        for need in self.needs.values():
            if isinstance(need, Mapping):
                _bounded(need, "level", 0.0, 1.0)
                _bounded(need, "urgency", 0.0, 1.0)
                status = need.get("status")
                if status is not None and status not in (
                    "satisfied",
                    "low",
                    "critical",
                ):
                    raise ValueError("agent state need status is invalid")
```

- [ ] **Step 4: Document the cross-adapter need fields**

Document the optional common fields in `core/docs/adapter-development.md` immediately after the
existing normalized range description:

```markdown
Each normalized need may include `status` as `satisfied`, `low`, or `critical`. The adapter owns
the native thresholds and may preserve its source value and bounds under the need's `native`
mapping. Core consumers use normalized `level`, `urgency`, and `status`; they do not infer severity
from a game-specific number.
```

- [ ] **Step 5: Run the focused Core tests**

Run:

```powershell
$env:PYTHONPATH='core\src'; py -3.12 -m pytest -q -p no:cacheprovider core/tests/unit/test_contracts.py
```

Expected: all tests in `test_contracts.py` pass.

- [ ] **Step 6: Commit the common contract**

```powershell
git add core/src/empneon/core/contracts.py core/docs/adapter-development.md core/tests/unit/test_contracts.py
git commit -m "feat(core): validate normalized need status"
```

---

### Task 2: Preserve and normalize Sims motives

**Files:**
- Modify: `adapters/thesims4/ts4script/ai_sims_agent.py:494-525`
- Modify: `adapters/thesims4/src/empneon_thesims4/adapter.py:104-131`
- Test: `adapters/thesims4/tests/test_sims4_mod_autonomy.py`
- Test: `adapters/thesims4/tests/test_adapter.py`

**Interfaces:**
- Consumes: Sims commodity values returned by `stat.get_value()` in the native `-100..100` range.
- Produces: `_need_state(value: int | float) -> dict[str, object]` with normalized `level`, inverse `urgency`, semantic `status`, and native range metadata.

- [ ] **Step 1: Write failing native-extraction tests**

In `test_sims4_mod_autonomy.py`, change the rich fixture's hunger value from `18` to `-40` and its assertion to:

```python
    hunger = SimpleNamespace(
        stat_type=type("motive_Hunger", (), {}),
        get_value=lambda: -40,
    )
```

```python
    assert rich_payload["needs"] == {"hunger": -40}
```

Add a boundary assertion near the same test:

```python
    starving = SimpleNamespace(
        stat_type=type("motive_Hunger", (), {}),
        get_value=lambda: -120,
    )
    assert agent.sim_needs(
        SimpleNamespace(
            commodity_tracker=SimpleNamespace(
                get_all_commodities=lambda: [starving]
            )
        )
    ) == {"hunger": -100}
```

- [ ] **Step 2: Write failing normalized-band tests**

In `test_adapter.py`, replace the old `0..100` need expectations (`0.63/0.37`) with expectations for the full Sims scale, then add:

```python
@pytest.mark.parametrize(
    "native,status,level",
    [
        (-100, "critical", 0.0),
        (-51, "critical", 0.245),
        (-50, "low", 0.25),
        (-26, "low", 0.37),
        (-25, "satisfied", 0.375),
        (100, "satisfied", 1.0),
    ],
)
def test_sims_need_scale_maps_to_common_status(
    native: int, status: str, level: float
) -> None:
    state = Sims4Adapter(
        {"speaker": {"id": "bella", "needs": {"hunger": native}}}
    ).agent_state()

    assert state.needs["hunger"] == {
        "level": pytest.approx(level),
        "urgency": pytest.approx(1 - level),
        "status": status,
        "native": {"value": native, "minimum": -100, "maximum": 100},
    }
```

For the existing payload with `needs: {"hunger": 63}`, assert `level == pytest.approx(0.815)`, `urgency == pytest.approx(0.185)`, `status == "satisfied"`, and the native metadata. Make the equivalent change for the existing energy `63` assertion.

- [ ] **Step 3: Run focused Sims tests and verify they fail**

Run from `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_mod_autonomy.py tests/test_adapter.py
```

Expected: the negative motive extraction and normalized-band assertions fail under the current zero clamp and `value / 100` conversion.

- [ ] **Step 4: Preserve native motive values at the game boundary**

In `ai_sims_agent.py`, make `_stat_values` return rounded source values without applying a need-specific scale:

```python
def _stat_values(tracker):
    result = {}
    for stat in _tracker_items(tracker):
        try:
            name = short_trait_name(getattr(stat, "stat_type", stat))
            getter = getattr(stat, "get_value", None)
            value = getter() if callable(getter) else getattr(stat, "value", None)
            if name and isinstance(value, (int, float)):
                result[name] = int(round(value))
        except Exception:
            pass
    return result
```

Keep the scale rule in `sim_needs`, where all callers pass through:

```python
        if name in allowed:
            needs[name] = max(-100, min(100, value))
```

- [ ] **Step 5: Normalize Sims needs in one adapter helper**

Add above `Sims4Adapter` in `adapter.py`:

```python
def _need_state(value: int | float) -> dict[str, object]:
    native = max(-100.0, min(100.0, float(value)))
    level = (native + 100.0) / 200.0
    status = "critical" if native < -50 else "low" if native < -25 else "satisfied"
    return {
        "level": level,
        "urgency": 1.0 - level,
        "status": status,
        "native": {
            "value": int(native) if native.is_integer() else native,
            "minimum": -100,
            "maximum": 100,
        },
    }
```

Replace the need comprehension in `agent_state` with:

```python
        needs: dict[str, object] = {
            str(name): _need_state(value)
            for name, value in _mapping(speaker.get("needs")).items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }
```

- [ ] **Step 6: Run the focused Sims tests**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_mod_autonomy.py tests/test_adapter.py
```

Expected: both test files pass.

- [ ] **Step 7: Commit Sims need normalization**

```powershell
git add adapters/thesims4/ts4script/ai_sims_agent.py adapters/thesims4/src/empneon_thesims4/adapter.py adapters/thesims4/tests/test_sims4_mod_autonomy.py adapters/thesims4/tests/test_adapter.py
git commit -m "fix(sims4): preserve native motive severity"
```

---

### Task 3: Give the model normalized state for both actors

**Files:**
- Modify: `adapters/thesims4/backend/ai_sims_server.py:1270-1465`
- Test: `adapters/thesims4/tests/test_sims4_backend.py`

**Interfaces:**
- Consumes: `Sims4Adapter(payload).agent_state()` and the Task 2 normalized need entries.
- Produces: `_actor_snapshot(payload: dict, role: str) -> dict` plus `context["speaker_state"]` and `context["listener_state"]` used by `build_chat_prompt`.

- [ ] **Step 1: Write a failing both-actor prompt test**

Replace `test_rich_game_state_is_grounded_in_dialogue_prompt` with a payload containing both actors and these assertions:

```python
def test_both_actor_states_are_grounded_in_dialogue_prompt() -> None:
    payload = {
        "speaker": {
            "id": "karmine",
            "current_mood": "uncomfortable",
            "needs": {"hunger": -40},
            "effects": [{"kind": "moodlet", "label": "Peckish"}],
            "aspiration": "MasterChef",
            "career": "Painter",
            "skills": {"Cooking": 7},
            "household": {"name": "Luna Household"},
        },
        "listener": {
            "id": "bernard",
            "current_mood": "happy",
            "needs": {"social": -60},
            "effects": [{"kind": "moodlet", "label": "GreatConversation"}],
        },
        "message": "How are you?",
    }
    context = ai_sims_server.build_context(
        payload,
        {"name": "Karmine"},
        {"name": "Bernard"},
        {},
        {},
        [],
        {},
    )
    context.update(
        conversation=[], speaker_id="karmine", listener_id="bernard"
    )

    prompt = ai_sims_server.build_chat_prompt(payload, context)

    assert '"hunger": {"level": 0.3' in prompt
    assert '"status": "low"' in prompt
    assert '"social": {"level": 0.2' in prompt
    assert '"status": "critical"' in prompt
    assert "Peckish" in prompt
    assert "GreatConversation" in prompt
    assert "Speaker current state:" in prompt
    assert "Listener current state:" in prompt
    assert "Do not recite need names, status labels, or numeric values" in prompt
```

- [ ] **Step 2: Run the prompt test and verify it fails**

Run from `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py::test_both_actor_states_are_grounded_in_dialogue_prompt
```

Expected: failure because only the Speaker has a normalized snapshot and the Listener's needs/effects are absent.

- [ ] **Step 3: Build snapshots through the existing adapter**

Add immediately before `build_context`:

```python
def _actor_snapshot(payload, role):
    other = "listener" if role == "speaker" else "speaker"
    actor_payload = dict(payload)
    actor_payload.pop("sim", None)
    actor_payload["speaker"] = payload.get(role) or {}
    actor_payload["listener"] = payload.get(other) or {}
    if role == "listener":
        actor_payload["relationship"] = {}
    return dataclasses.asdict(Sims4Adapter(actor_payload).agent_state())
```

At the beginning of `build_context`, compute both snapshots and include them in the returned mapping:

```python
    speaker_state = _actor_snapshot(payload, "speaker")
    listener_state = _actor_snapshot(payload, "listener")
```

```python
        "speaker_state": speaker_state,
        "listener_state": listener_state,
```

Keep the existing `game_state` mapping for aspiration, career, skills, household, and compatibility with current callers.

- [ ] **Step 4: Label both snapshots and add model-first need guidance**

In `build_chat_prompt`, remove the local one-sided `snapshot = ...` assignment. Replace the one-sided `Current normalized snapshot` and `Native state` prompt fields with:

```text
Speaker current state:
{speaker_state}

Listener current state:
{listener_state}
```

Pass both formatted values:

```python
        speaker_state=dumps(context["speaker_state"]),
        listener_state=dumps(context["listener_state"]),
```

Replace the critical-need grounding rule with:

```text
- Needs are context, not required topics. A satisfied need is normally silent; a low need may
  motivate a gentle suggestion; a critical need should strongly influence urgency and may redirect
  the conversation, but the Speaker may still continue the current topic.
- Express needs naturally in-world. Do not recite need names, status labels, or numeric values.
```

- [ ] **Step 5: Run prompt and identity tests**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "actor_states or identity or rich_game_state"
```

Expected: the both-actor and existing identity prompt tests pass.

- [ ] **Step 6: Commit both-actor model context**

```powershell
git add adapters/thesims4/backend/ai_sims_server.py adapters/thesims4/tests/test_sims4_backend.py
git commit -m "feat(sims4): prompt with both actor states"
```

---

### Task 4: Stop need overrides and retain repetition context

**Files:**
- Modify: `adapters/thesims4/backend/ai_sims_server.py:1655-1945`
- Test: `adapters/thesims4/tests/test_sims4_backend.py`

**Interfaces:**
- Consumes: existing `response_grounding_issue`, `reasoning_fallback_response`, and `HermesRuntime.dialogue` flow.
- Produces: model-first acceptance when a need is omitted and a retry prompt that still contains recent dialogue plus a concrete novelty correction.

- [ ] **Step 1: Replace the forced-need fallback test with model-first acceptance**

Replace `test_dialogue_fallback_mentions_critical_need_and_refuses_unsupported_fact` with two focused tests. Keep the unsupported-memory half as its own existing behavior test, and add:

```python
def test_valid_model_reply_is_not_replaced_for_omitting_a_critical_need(
    monkeypatch,
) -> None:
    calls = []

    def fake_llm(*_args, **_kwargs):
        calls.append(1)
        return json.dumps(
            {
                "dialogue": "I'm glad you asked. I want to keep talking this through with you.",
                "emotion": "thoughtful",
                "intent": "respond",
                "relationship": {},
                "memory": {},
            }
        )

    monkeypatch.setattr(ai_sims_server, "llm_chat", fake_llm)
    payload = {
        "speaker": {"id": "karmine", "needs": {"hunger": -80}},
        "listener": {"id": "bernard"},
        "message": "How are you feeling?",
    }
    context = ai_sims_server.build_context(
        payload,
        {"name": "Karmine"},
        {"name": "Bernard"},
        {},
        {"current_mood": "uncomfortable"},
        [],
        {},
    )
    context.update(
        conversation=[], speaker_id="karmine", listener_id="bernard"
    )

    response = ai_sims_server.HERMES.dialogue(payload, context)

    assert len(calls) == 1
    assert response["dialogue"].startswith("I'm glad you asked")
```

Add a direct fallback check:

```python
def test_provider_failure_fallback_stays_on_current_topic_despite_need() -> None:
    payload = {
        "speaker": {"id": "karmine", "needs": {"hunger": -80}},
        "listener": {"id": "bernard"},
        "message": "Would you like to go on a date with me?",
    }
    context = ai_sims_server.build_context(
        payload,
        {"name": "Karmine"},
        {"name": "Bernard"},
        {},
        {},
        [],
        {},
    )
    context.update(
        conversation=[], speaker_id="karmine", listener_id="bernard"
    )

    response = ai_sims_server.reasoning_fallback_response(payload, context)

    assert response["player_interaction_kind"] == "romantic_invitation"
    assert "need" not in response["dialogue"].casefold()
    assert "critical" not in response["dialogue"].casefold()
```

- [ ] **Step 2: Change the repetition retry test expectation**

Rename `test_repetition_retry_removes_recent_conversation_history` to `test_repetition_retry_keeps_history_and_requests_new_direction`. Replace its final assertions with:

```python
    assert response["dialogue"] == "Thank you. I enjoy spending time with you too."
    assert "You have a very kind presence." in prompts[0]
    assert "You have a very kind presence." in prompts[1]
    assert "advance the conversation with a new reaction, detail, question, or decision" in prompts[1]
```

- [ ] **Step 3: Run the focused tests and verify current behavior fails**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "omitting_a_critical_need or fallback_stays_on_current_topic or repetition_retry_keeps"
```

Expected: forced need grounding causes an extra call or need fallback, and the repetition retry removes the previous reply.

- [ ] **Step 4: Remove need-omission rejection and forced need fallbacks**

In `response_grounding_issue`, delete only the `needs`, `critical`, `stale`, missing-critical, and non-critical-need blocks. Leave current/previous message similarity, previous reply similarity, memory evidence, and role checks unchanged.

In `reasoning_fallback_response`, delete the `needs`/`critical` construction and the first branch that emits `"I'm uncomfortable because my ... need is critical."`. Make `romantic_invitation` the first branch. Delete the `if critical:` candidate that emits `"Before we continue..."`; let the existing topical and neutral candidates remain.

- [ ] **Step 5: Keep history and issue one precise novelty correction**

In `HermesRuntime.dialogue`, delete:

```python
            if issue and ("copy" in issue or "previous reply" in issue):
                prompt = build_chat_prompt(payload, dict(context, conversation=[]))
```

After the existing issue correction, add:

```python
            if issue and ("copy" in issue or "previous reply" in issue):
                prompt += (
                    "\nCorrection: Keep the facts and conversational continuity, but advance the "
                    "conversation with a new reaction, detail, question, or decision. Do not reuse "
                    "an earlier opening or sentence frame."
                )
```

Also add the same positive instruction once to the initial Grounding rules:

```text
- Advance the conversation with a new reaction, detail, question, or decision instead of reusing
  an earlier opening or sentence frame.
```

- [ ] **Step 6: Remove or rewrite obsolete critical-need tests**

Delete `test_mirroring_critical_need_fallback_stays_grounded` and `test_grounding_reasoning_fallback_direct_call_handles_critical_need`, which assert the behavior being removed. Keep the general current-message mirroring and neutral grounded-fallback tests; together with the new provider-failure test they cover the remaining behavior.

- [ ] **Step 7: Run the complete Sims backend test file**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py
```

Expected: all backend tests pass.

- [ ] **Step 8: Commit model-first dialogue continuity**

```powershell
git add adapters/thesims4/backend/ai_sims_server.py adapters/thesims4/tests/test_sims4_backend.py
git commit -m "fix(sims4): keep need-aware dialogue model-first"
```

---

### Task 5: Document and verify the Test 5 remediation

**Files:**
- Modify: `adapters/thesims4/docs/in-game-core-feature-test-plan.md:118-150`
- Test: repository Core and Sims suites

**Interfaces:**
- Consumes: the completed common contract, Sims extraction, both-actor prompt, and model-first retry behavior.
- Produces: updated live Test 5 instructions without claiming a live pass before the user verifies it.

- [ ] **Step 1: Update the partial Test 5 record**

Extend the existing `PARTIAL` status paragraph with:

```markdown
Automated coverage also preserves the Sims `-100..100` motive scale, maps it to common
`satisfied`/`low`/`critical` states, prompts with both actors' normalized current state, accepts
valid model dialogue that omits a need, and retains recent dialogue during repetition retries.
Live source-build evidence is still required; Test 5 is not passed.
```

Add these focused live assertions under Test 5:

```markdown
- Focused need/continuity assertions: capture Karmine's and Bernard's visible mood/need state before
  the conversation. Green needs do not force a need report; orange/red needs may influence natural
  wording without exposing numeric values or replacing a valid model reply. Continue enough turns
  to confirm replies introduce a new reaction, detail, question, or decision instead of recycling
  earlier inputs or replies.
```

- [ ] **Step 2: Run the complete Core suite**

Run from the repository root:

```powershell
$env:PYTHONPATH='core\src'; py -3.12 -m pytest -q -p no:cacheprovider core/tests
```

Expected: all Core tests pass.

- [ ] **Step 3: Run the complete Sims adapter suite**

Run from `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests
```

Expected: all Sims adapter tests pass.

- [ ] **Step 4: Run static repository checks**

Run from the repository root:

```powershell
git diff --check
git status --short
```

Expected: `git diff --check` exits 0; status lists only intended tracked changes plus the pre-existing untracked SQLite `-wal` and `-shm` sidecars.

- [ ] **Step 5: Confirm the backend is stopped**

Run:

```powershell
$listener = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
if ($listener) { throw "Backend is still listening on port 8765" }
```

Expected: exits 0 with no listener.

- [ ] **Step 6: Commit documentation and any final test-only corrections**

```powershell
git add adapters/thesims4/docs/in-game-core-feature-test-plan.md
git commit -m "docs(sims4): extend Test 5 need checks"
```

- [ ] **Step 7: Inspect the final branch without pushing**

Run:

```powershell
git status --short --branch
git log -5 --oneline
```

Expected: branch remains `feature/sims4-core-integration`, is ahead of its remote, and is not pushed until live Test 5 passes.
