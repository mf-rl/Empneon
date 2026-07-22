# Cross-Adapter Identity and Dialogue Variety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give dialogue models normalized gender, game-defined age, and trait context for both actors while deterministically rejecting replies that mirror current or previous conversation text.

**Architecture:** Add a JSON-compatible `identity` section to the existing Core `AgentStateSnapshot`; game adapters populate it and retain raw values under `native.identity`. The Sims backend renders both identities into the role prompt and extends its existing word-sequence grounding validator, avoiding embeddings, new dependencies, or a Sims-specific identity ontology in Core.

**Tech Stack:** Python 3.12 backend/tests, Python 3.7-compatible Sims script source, dataclasses, stdlib `difflib.SequenceMatcher`, pytest, Ruff, mypy.

## Global Constraints

- The normalized identity format is shared by every adapter: `gender`, `age`, and `traits` records live under `AgentStateSnapshot.identity`.
- The Sims 4 age is a life stage, never an invented year count or enum ordinal presented as years.
- Preserve original game values under `native.identity`.
- Unknown gender or age stays `unknown`; the model must not infer it.
- Traits influence roleplay but must not be named mechanically or caricatured.
- Reject mirroring of the current input, prior inputs, and prior model replies, including romantic requests.
- Keep necessary repeated facts such as names, places, and dates valid when the rest of the response is distinct.
- Do not add dependencies or semantic-embedding calls.
- Keep held Empneon Social requests actionless; autonomous Sims decisions retain native actions.
- Do not apply model-proposed Sims friendship or romance directly.
- Do not stage SQLite `-shm` or `-wal` sidecars.
- Do not push until the focused live Test 5 retest passes and its evidence is recorded.

## File Structure

- `core/src/empneon/core/contracts.py`: owns the provider-independent snapshot shape and JSON validation.
- `core/tests/unit/test_contracts.py`: locks snapshot identity serialization and validation.
- `adapters/thesims4/ts4script/ai_sims_agent.py`: extracts Sims gender, age stage, traits, and raw native identity.
- `adapters/thesims4/tests/test_sims4_mod_autonomy.py`: exercises extraction with Sims API fakes and malformed modded traits.
- `adapters/thesims4/src/empneon_thesims4/adapter.py`: transfers normalized identity into the Core snapshot.
- `adapters/thesims4/tests/test_adapter.py`: verifies adapter normalization and native preservation.
- `adapters/thesims4/backend/ai_sims_server.py`: builds identity-aware prompts and validates dialogue variety.
- `adapters/thesims4/tests/test_sims4_backend.py`: covers role identity, trait guidance, and anti-mirroring behavior.
- `adapters/thesims4/docs/in-game-core-feature-test-plan.md`: states the focused live assertions.
- `adapters/thesims4/docs/in-game-core-feature-test-results.md`: records the latest partial/pass evidence.

---

### Task 1: Core normalized identity contract

**Files:**
- Modify: `core/src/empneon/core/contracts.py:38-90`
- Test: `core/tests/unit/test_contracts.py:13-35`

**Interfaces:**
- Produces: `AgentStateSnapshot.identity: dict[str, object]`.
- Produces: `AgentStateSnapshot.from_mapping()` reconstruction of the optional identity mapping.
- Preserves: schema version `1` and existing callers that omit identity.

- [ ] **Step 1: Write the failing Core contract test**

Extend `test_agent_state_snapshot_is_json_compatible_and_embedded_in_event` with:

```python
"identity": {
    "gender": {"key": "female", "label": "Female"},
    "age": {"kind": "life_stage", "value": "adult", "label": "Adult"},
    "traits": [{"id": "outgoing", "label": "Outgoing"}],
},
```

and assert:

```python
assert encoded["agent_state"]["identity"] == {
    "gender": {"key": "female", "label": "Female"},
    "age": {"kind": "life_stage", "value": "adult", "label": "Adult"},
    "traits": [{"id": "outgoing", "label": "Outgoing"}],
}
```

Add a malformed-identity JSON test:

```python
def test_agent_state_snapshot_rejects_non_json_identity() -> None:
    with pytest.raises(ValueError, match="JSON-compatible"):
        AgentStateSnapshot(
            1,
            "test",
            "alice",
            identity={"traits": [{"id": object()}]},
        )
```

- [ ] **Step 2: Run the Core tests to verify RED**

Run from `core`:

```powershell
$env:PYTHONPATH='src'; py -3.12 -m pytest -q -p no:cacheprovider tests/unit/test_contracts.py
```

Expected: FAIL because `AgentStateSnapshot` does not accept or serialize `identity`.

- [ ] **Step 3: Add the minimum snapshot field and parser entry**

Append the new field after `native` so existing positional construction remains compatible:

```python
identity: dict[str, object] = field(default_factory=dict)
```

In `from_mapping`, add:

```python
identity=_mapping(value.get("identity")),
```

No separate identity validator is needed: the existing `json.dumps(dataclasses.asdict(self), allow_nan=False)` boundary validates the complete nested record.

- [ ] **Step 4: Verify the Core contract and full Core suite**

Run from `core`:

```powershell
$env:PYTHONPATH='src'; py -3.12 -m pytest -q -p no:cacheprovider tests/unit/test_contracts.py
$env:PYTHONPATH='src'; py -3.12 -m pytest -q -p no:cacheprovider tests
```

Expected: focused tests and the full Core suite pass.

- [ ] **Step 5: Commit the Core contract**

```powershell
git add core/src/empneon/core/contracts.py core/tests/unit/test_contracts.py
git commit -m "feat(core): add normalized agent identity"
```

---

### Task 2: Extract Sims identity without inventing age

**Files:**
- Modify: `adapters/thesims4/ts4script/ai_sims_agent.py:350-475,610-645`
- Test: `adapters/thesims4/tests/test_sims4_mod_autonomy.py:300-430`

**Interfaces:**
- Produces: `sim_identity(sim_info) -> dict[str, object]`.
- Produces: `sim_info_payload(sim_info)["identity"]` in the Core common format.
- Produces: `sim_info_payload(sim_info)["native"]["identity"]` with raw enum text.
- Preserves: top-level `traits` labels for existing backend/profile compatibility.

- [ ] **Step 1: Write failing Sims extraction assertions**

In the existing rich Sim fixture, add:

```python
gender=SimpleNamespace(name="FEMALE", value=1),
age=SimpleNamespace(name="YOUNGADULT", value=5),
```

Give `Outgoing` a stable ID and description:

```python
outgoing = SimpleNamespace(
    name="Outgoing",
    guid64=101,
    trait_description="Enjoys socializing and speaks confidently.",
)
rich_info.trait_tracker = SimpleNamespace(equipped_traits=[outgoing])
```

Assert:

```python
assert rich_payload["identity"] == {
    "gender": {"key": "female", "label": "Female"},
    "age": {
        "kind": "life_stage",
        "value": "young_adult",
        "label": "Young Adult",
    },
    "traits": [
        {
            "id": "101",
            "label": "Outgoing",
            "description": "Enjoys socializing and speaks confidently.",
        }
    ],
}
assert rich_payload["native"]["identity"] == {
    "gender": "FEMALE",
    "age": "YOUNGADULT",
}
assert rich_payload.get("age") is None
```

Add an unknown/modded case whose broken description raises, and assert gender/age become `unknown` while valid trait labels remain.

- [ ] **Step 2: Run the focused Sims script test to verify RED**

Run from `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_mod_autonomy.py::test_conversation_session_and_alarm_submit_without_overlap
```

Expected: FAIL because the payload has no normalized identity.

- [ ] **Step 3: Implement enum, trait, and identity extraction**

Add these Python 3.7-compatible helpers near `sim_traits`:

```python
def enum_key(value):
    raw = getattr(value, "name", None)
    text = str(raw or value or "").rsplit(".", 1)[-1].strip().casefold()
    return text.replace("youngadult", "young_adult") or "unknown"


def identity_value(key, label=None):
    return {
        "key": key,
        "label": label or key.replace("_", " ").title(),
    }


def sim_trait_records(sim_info):
    records = []
    tracker = getattr(sim_info, "trait_tracker", None)
    try:
        equipped = getattr(tracker, "equipped_traits", None)
        equipped = equipped() if callable(equipped) else equipped
        for trait in equipped or ():
            try:
                label = short_trait_name(trait)
                if not label:
                    continue
                record = {
                    "id": str(getattr(trait, "guid64", None) or label),
                    "label": label,
                }
                description = text_value(
                    getattr(trait, "trait_description", None)
                    or getattr(trait, "description", None),
                    "",
                )
                if description:
                    record["description"] = description
                records.append(record)
            except Exception:
                pass
    except Exception:
        pass
    return records


def sim_identity(sim_info):
    gender = enum_key(getattr(sim_info, "gender", None))
    if gender not in ("male", "female"):
        gender = "unknown"
    age = enum_key(getattr(sim_info, "age", None))
    known_ages = (
        "baby", "infant", "toddler", "child", "teen",
        "young_adult", "adult", "elder",
    )
    if age not in known_ages:
        age = "unknown"
    return {
        "gender": identity_value(gender),
        "age": {
            "kind": "life_stage",
            "value": age,
            "label": age.replace("_", " ").title(),
        },
        "traits": sim_trait_records(sim_info),
    }
```

Make `sim_traits` return labels from `sim_trait_records`. In `sim_info_payload`, set `identity = sim_identity(sim_info)`, return `"age": None`, return `"identity": identity`, and add:

```python
"identity": {
    "gender": str(getattr(getattr(sim_info, "gender", None), "name", "unknown")),
    "age": str(getattr(getattr(sim_info, "age", None), "name", "unknown")),
},
```

inside the existing `native` mapping.

- [ ] **Step 4: Verify focused and full Sims script tests**

Run from `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_mod_autonomy.py
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests
```

Expected: all Sims tests pass; existing age assertions are updated to the normalized life-stage assertions above.

- [ ] **Step 5: Commit Sims extraction**

```powershell
git add adapters/thesims4/ts4script/ai_sims_agent.py adapters/thesims4/tests/test_sims4_mod_autonomy.py
git commit -m "feat(sims4): extract normalized Sim identity"
```

---

### Task 3: Carry identity through the adapter and prompt

**Files:**
- Modify: `adapters/thesims4/src/empneon_thesims4/adapter.py:105-160`
- Modify: `adapters/thesims4/backend/ai_sims_server.py:1262-1430`
- Test: `adapters/thesims4/tests/test_adapter.py:55-105`
- Test: `adapters/thesims4/tests/test_sims4_backend.py:430-510`

**Interfaces:**
- Consumes: `AgentStateSnapshot.identity` from Task 1 and payload identity from Task 2.
- Produces: identity-bearing Sims `WorldEvent.agent_state`.
- Produces: `build_context()` keys `speaker_identity` and `listener_identity`.
- Produces: explicit Speaker/Listener identity and trait behavior rules in `build_chat_prompt()`.

- [ ] **Step 1: Write failing adapter and prompt tests**

Extend `test_sims_payload_becomes_normalized_agent_state_without_losing_native_values`:

```python
"identity": {
    "gender": {"key": "female", "label": "Female"},
    "age": {"kind": "life_stage", "value": "adult", "label": "Adult"},
    "traits": [{"id": "good", "label": "Good"}],
},
```

Then assert:

```python
assert event.agent_state.identity["gender"]["key"] == "female"
assert event.agent_state.identity["age"]["value"] == "adult"
assert event.agent_state.identity["traits"] == [{"id": "good", "label": "Good"}]
```

Add a backend prompt test using Karmine as a female young adult with an outgoing trait and Bernard as a male adult. Assert the prompt contains serialized identity for both roles and these instructions:

```python
assert "Use the Speaker's traits to shape tone, preferences, confidence, boundaries, and choices" in prompt
assert "Do not guess gender or age when identity is unknown" in prompt
assert "Do not merely name or caricature traits" in prompt
```

- [ ] **Step 2: Run focused tests to verify RED**

Run from `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_adapter.py tests/test_sims4_backend.py -k "identity or rich_game_state"
```

Expected: FAIL because the adapter and prompt omit normalized identity.

- [ ] **Step 3: Transfer identity into the snapshot and dialogue context**

In `Sims4Adapter.agent_state`, read:

```python
identity = _mapping(speaker.get("identity"))
```

and pass `identity=identity` to `AgentStateSnapshot`.

In `build_context`, add:

```python
"speaker_identity": speaker.get("identity") or {},
"listener_identity": listener.get("identity") or {},
```

In `build_chat_prompt`, add sections:

```text
Speaker identity: {speaker_identity}
Listener identity: {listener_identity}
```

and grounding rules:

```text
- Use the Speaker's traits to shape tone, preferences, confidence, boundaries, and choices.
- Combine traits with current mood, needs, relationship, memories, and the current message.
- Do not merely name or caricature traits.
- Use gendered relationship terms only when supported by supplied identity.
- Do not guess gender or age when identity is unknown.
```

Supply both identity mappings through the existing `.format(...)` call with `dumps(...)`.

- [ ] **Step 4: Verify adapter and backend suites**

Run from `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_adapter.py tests/test_sims4_backend.py
```

Expected: both files pass.

- [ ] **Step 5: Commit identity propagation**

```powershell
git add adapters/thesims4/src/empneon_thesims4/adapter.py adapters/thesims4/backend/ai_sims_server.py adapters/thesims4/tests/test_adapter.py adapters/thesims4/tests/test_sims4_backend.py
git commit -m "feat(sims4): ground dialogue in actor identity"
```

---

### Task 4: Reject current and historical dialogue mirroring

**Files:**
- Modify: `adapters/thesims4/backend/ai_sims_server.py:1288-1430,1439-1558,1717-1755`
- Test: `adapters/thesims4/tests/test_sims4_backend.py:570-740`

**Interfaces:**
- Produces: `_dialogue_similarity(left: list[str], right: list[str]) -> float` with acceptance limit `0.72` at its callers.
- Produces: `response_grounding_issue()` issues for current input copy, previous input copy, and previous reply reuse.
- Preserves: the existing one-retry `HermesRuntime.dialogue()` flow and grounded fallback.

- [ ] **Step 1: Add failing regressions from the live Bernard/Karmine conversation**

Add this exact current-input mirror:

```python
message = (
    "You make me happier than I ever expected, and I don't want to wonder "
    "what this could be anymore. I want us to be together. Will you be my girlfriend?"
)
response = ai_sims_server.normalize_response(
    {
        "dialogue": (
            "That's wonderful to hear! You make me happier than I ever expected, "
            "and it makes you wonder what this could be anymore. You are the most "
            "beautiful flower, Bernard. Would you be my girlfriend?"
        )
    }
)
assert "copy" in ai_sims_server.response_grounding_issue(
    {"message": message}, response, context
)
```

Add a previous-player-input mirror and a previous-model-reply mirror to `context["conversation"]`, asserting the respective issue contains `copy` and `previous reply`.

Add a legitimate fact reuse case:

```python
distinct = ai_sims_server.normalize_response(
    {"dialogue": "Saturday sounds perfect. Where would you like to go?"}
)
assert ai_sims_server.response_grounding_issue(
    {"message": "How about Saturday evening? I know a place I'd love to take you."},
    distinct,
    context,
) == ""
```

- [ ] **Step 2: Run focused grounding tests to verify RED**

Run from `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "grounding or mirror or conversation"
```

Expected: the romantic mirror and prior-input mirror are accepted, so the test fails.

- [ ] **Step 3: Apply one deterministic comparison policy**

In the prompt grounding rules add:

```text
- Answer the current message without restating or closely paraphrasing it.
- Keep the reply distinct from every recent player input and Speaker reply.
```

In `response_grounding_issue`, remove the `classify_player_interaction(message) != "romantic_invitation"` exemption and use `0.72` for meaningful comparisons. Compare the generated dialogue against each prior turn's `message` before comparing its `dialogue`:

```python
if (
    len(message_words) >= 6
    and len(dialogue_words) >= 4
    and _dialogue_similarity(message_words, dialogue_words) >= 0.72
):
    return "respond naturally; do not copy the player's message"

for turn in context.get("conversation") or []:
    previous_message = _dialogue_words(turn.get("message"), context)
    if (
        len(previous_message) >= 6
        and len(dialogue_words) >= 4
        and _dialogue_similarity(dialogue_words, previous_message) >= 0.72
    ):
        return "do not copy a previous player message"
    previous_reply = _dialogue_words(turn.get("dialogue"), context)
    if (
        len(previous_reply) >= 4
        and len(dialogue_words) >= 4
        and _dialogue_similarity(dialogue_words, previous_reply) >= 0.72
    ):
        return "do not reuse a previous reply for a different message"
```

Keep name removal in `_dialogue_words`. The existing retry branch already removes conversation context when an issue contains `copy` or `previous reply`; retain that behavior.

- [ ] **Step 4: Verify retry and fallback behavior**

Add a two-response provider test where the first response mirrors Bernard and the second is distinct. Assert two provider calls and return of the second response. Add a persistent-mirror case and assert the grounded fallback is distinct from the input.

Run from `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py
```

Expected: all backend tests pass, including exact live regression text.

- [ ] **Step 5: Commit anti-mirroring behavior**

```powershell
git add adapters/thesims4/backend/ai_sims_server.py adapters/thesims4/tests/test_sims4_backend.py
git commit -m "fix(sims4): prevent dialogue mirroring"
```

---

### Task 5: Document, verify, build, and retest Test 5

**Files:**
- Modify: `adapters/thesims4/docs/in-game-core-feature-test-plan.md`
- Modify: `adapters/thesims4/docs/in-game-core-feature-test-results.md`

**Interfaces:**
- Consumes: all prior tasks.
- Produces: reproducible automated evidence, installed game artifacts, and focused live Test 5 evidence.

- [ ] **Step 1: Update the Test 5 checklist without marking it passed**

Record these required observations:

- Karmine's response is distinct from Bernard's current and earlier messages and from her earlier replies.
- Karmine uses `boyfriend` or neutral wording for male Bernard, never `girlfriend` for him.
- Dialogue respects Karmine's reported life stage and traits without reciting trait labels.
- Exact dates such as `Saturday` remain usable when the surrounding response is distinct.
- Held Empneon Social remains actionless and does not deadlock; autonomous decisions still retain native actions.
- Sims friendship/romance come only from game-observed behavior; Empneon trust changes on delivered dialogue.

- [ ] **Step 2: Run all automated verification**

Run from repository worktree root unless a different directory is noted:

```powershell
$env:PYTHONPATH='core\src'; py -3.12 -m pytest -q -p no:cacheprovider core/tests
$env:PYTHONPATH='core\src;adapters\thesims4\src'; py -3.12 -m pytest -q -p no:cacheprovider adapters/thesims4/tests
$env:PYTHONPATH='core\src;adapters\godot\src'; py -3.12 -m pytest -q -p no:cacheprovider adapters/godot/tests
$env:PYTHONPATH='core\src;adapters\thesims4\src'; py -3.12 -m mypy core/src adapters/thesims4/src adapters/thesims4/backend
py -3.12 -m ruff check --select E9,F63,F7,F82 core adapters tests
py -3.12 -m py_compile core/src/empneon/core/contracts.py adapters/thesims4/src/empneon_thesims4/adapter.py adapters/thesims4/backend/ai_sims_server.py adapters/thesims4/ts4script/ai_sims_agent.py
git diff --check
```

Expected: every command exits `0`. Use the repository's existing scoped Ruff policy; do not expand this task into legacy lint cleanup.

- [ ] **Step 3: Build and install the mod**

Run from `adapters/thesims4` after fully closing The Sims 4:

```powershell
py -3.12 .\build_mod.py
.\install_mod.ps1
```

Expected: `dist/Empneon_TheSims4.ts4script` and `dist/Empneon_TheSims4.package` build and install successfully. Confirm installed SHA-256 hashes equal the `dist` artifacts.

- [ ] **Step 4: Run the backend from source and perform focused Test 5**

Start the existing source-backend command documented in `adapters/thesims4/docs/setup.md`, confirm `http://127.0.0.1:8765/health`, then fully restart The Sims 4. Use Bernard and Karmine and repeat the live conversation that produced the recorded mirror. Capture exact inputs, replies, life stages, genders, traits, `ai.relationship` before/after, queue behavior, and decision IDs.

Expected: no mirrored dialogue, no role/gender confusion, no held-session deadlock, and identity-consistent roleplay. Keep Test 5 partial if any assertion fails.

- [ ] **Step 5: Record evidence and commit documentation**

Only after the live assertions pass, mark Test 5 passed and record the exact evidence in the results document:

```powershell
git add adapters/thesims4/docs/in-game-core-feature-test-plan.md adapters/thesims4/docs/in-game-core-feature-test-results.md
git commit -m "docs(sims4): record identity-aware Test 5"
```

- [ ] **Step 6: Review branch and push after the live gate**

Review the complete diff from `origin/feature/sims4-core-integration`, rerun any reviewer-requested checks, verify only the two live SQLite sidecars remain untracked, then push:

```powershell
git status --short --branch
git diff --check origin/feature/sims4-core-integration...HEAD
git push origin feature/sims4-core-integration
```

Expected: push occurs only after Test 5 is recorded as passed.
