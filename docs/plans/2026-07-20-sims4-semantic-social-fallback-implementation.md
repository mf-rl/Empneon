# Sims 4 Semantic Social Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the model classify Sims social meaning in its existing response, remove contaminated history on repetition retries, and return relevant deterministic Sims dialogue when the model is unavailable.

**Architecture:** Add one structured `player_interaction_kind` field to the existing model response and a conservative local classifier for explicit invitations and offline fallback. Keep Core routing and confirmation unchanged; the Sims backend substitutes an adapter-specific deterministic decision only when Core degrades to CLOD 1.

**Tech Stack:** Python 3.11+, standard-library `difflib` and `re`, Empneon Core CLOD routing, The Sims 4 adapter backend, pytest.

## Global Constraints

- Use one model generation call per attempt; do not add a classifier request or second model.
- Preserve model freedom over wording, tone, emotion, acceptance, rejection, and proposed consequences.
- Keep privacy, consent, role, factual-grounding, and native-confirmation guards.
- Offline dialogue may be conservative but must be relevant to the interaction category.
- Add no dependency, database, API, provider, or persistence-format change.
- Do not retry native game-action failures automatically.
- Follow RED-GREEN TDD for every production change.

---

### Task 1: Classify player interaction meaning

**Files:**
- Modify: `adapters/thesims4/backend/ai_sims_server.py:220-270,900-970,1380-1570`
- Test: `adapters/thesims4/tests/test_sims4_backend.py:540-675`

**Interfaces:**
- Produces: `classify_player_interaction(message: object) -> str`.
- Produces: normalized response key `player_interaction_kind` with one of `friendly`, `romantic_compliment`, `romantic_invitation`, `hostile`, `informational`, or `neutral`.
- Consumes: the normalized kind in `response_grounding_issue` and `reasoning_fallback_response`.

- [x] **Step 1: Add failing classification and validation tests**

```python
@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Would you go out with me?", "romantic_invitation"),
        ("Let's be girlfriends.", "romantic_invitation"),
        ("I'm very attracted to you. You are really hot.", "romantic_compliment"),
        ("You are very nice. Let's be friends!", "friendly"),
        ("Where is PRIVATE-GARDEN-731?", "informational"),
        ("I hate you.", "hostile"),
        ("The weather changed.", "neutral"),
    ],
)
def test_local_social_classifier(message, expected) -> None:
    assert ai_sims_server.classify_player_interaction(message) == expected
```

Add a romantic-compliment response to the existing grounding test:

```python
compliment = ai_sims_server.normalize_response(
    {
        "dialogue": "That is flattering. I appreciate your honesty.",
        "player_interaction_kind": "romantic_compliment",
        "intent": "respond",
        "relationship": {"romance_delta": 0},
    }
)
assert ai_sims_server.response_grounding_issue(
    {"message": "I'm very attracted to you. You are really hot."},
    compliment,
    context,
) == ""
```

- [x] **Step 2: Run focused tests and verify RED**

From `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "local_social_classifier or grounding_rejects"
```

Expected: FAIL because the classifier and response field do not exist.

- [x] **Step 3: Implement the local classifier and schema field**

Add `player_interaction_kind` to `DIALOGUE_SCHEMA.properties`, its six-value enum, and the schema's
required list. Add it to `SYSTEM_PROMPT` and to `normalize_response`, defaulting to
`classify_player_interaction("")` only when absent.

Implement the classifier with ordered rules:

```python
INTERACTION_KINDS = (
    "friendly",
    "romantic_compliment",
    "romantic_invitation",
    "hostile",
    "informational",
    "neutral",
)


def classify_player_interaction(message):
    value = str(message or "").casefold()
    if re.search(
        r"\b(go(?:ing)? out|date|be my (?:girl|boy)friend|"
        r"be (?:girl|boy)friends|kiss me|marry me)\b",
        value,
    ):
        return "romantic_invitation"
    if re.search(
        r"\b(attract(?:ed|ive)?|hot|beautiful|handsome|cute|sexy|"
        r"love you|crush)\b",
        value,
    ):
        return "romantic_compliment"
    if re.search(r"\b(hate|stupid|idiot|ugly|despise)\b", value):
        return "hostile"
    if "?" in value or re.match(r"\s*(who|what|when|where|why|how)\b", value):
        return "informational"
    if re.search(r"\b(friend|friends|nice|hello|hey|thanks|thank you)\b", value):
        return "friendly"
    return "neutral"
```

In `response_grounding_issue`, use the model's normalized kind except that a local
`romantic_invitation` always wins as the consent safety boundary. Apply direct accept/decline rules
only to the effective `romantic_invitation` kind. In `reasoning_fallback_response`, use the local
kind after existing needs and factual-memory branches; return a polite boundary for invitations,
a distinct acknowledgment for compliments, a boundary for hostile input, and a friendly
acknowledgment for friendly/neutral input.

- [x] **Step 4: Run focused tests and verify GREEN**

Run the Step 2 command. Expected: all selected tests PASS.

- [x] **Step 5: Commit classification and fallback behavior**

```powershell
git add adapters/thesims4/backend/ai_sims_server.py adapters/thesims4/tests/test_sims4_backend.py
git commit -m "fix(sims4): classify social interactions"
```

### Task 2: Detect near-copies and retry without conversation history

**Files:**
- Modify: `adapters/thesims4/backend/ai_sims_server.py:1-20,1380-1630`
- Test: `adapters/thesims4/tests/test_sims4_backend.py:590-675`

**Interfaces:**
- Consumes: `_dialogue_words(value, context) -> list[str]`.
- Produces: `_dialogue_similarity(left, right) -> float` using `difflib.SequenceMatcher`.
- Changes: `HermesRuntime.dialogue` rebuilds only the repetition retry prompt with `conversation=[]`.

- [x] **Step 1: Add failing near-copy and clean-retry tests**

Change the echo regression to Karmine's observed near-copy:

```python
echoed = ai_sims_server.normalize_response(
    {
        "dialogue": "It's just looking at you, baby. You really make my world spin.",
        "player_interaction_kind": "romantic_compliment",
        "intent": "agree",
    }
)
assert "copy" in ai_sims_server.response_grounding_issue(
    {"message": "Just looking at you, baby. You really make my world spin"},
    echoed,
    copy_context,
)
```

Add a retry prompt test:

```python
def test_repetition_retry_removes_conversation_history(monkeypatch) -> None:
    prompts = []
    responses = iter(
        [
            {"dialogue": "You have a very kind presence.", "player_interaction_kind": "friendly"},
            {"dialogue": "That means a lot to me.", "player_interaction_kind": "friendly"},
        ]
    )

    def generate(messages, **_kwargs):
        prompts.append(messages[1]["content"])
        return json.dumps(next(responses))

    monkeypatch.setattr(ai_sims_server, "llm_chat", generate)
    payload = {"speaker": {}, "listener": {}, "message": "Thank you for being here."}
    context = ai_sims_server.build_context(
        payload, {"name": "Karmine"}, {"name": "Bernard"}, {}, {}, [], {}
    )
    context.update(
        speaker_id="karmine",
        listener_id="bernard",
        conversation=[
            {
                "speaker_id": "karmine",
                "message": "Hello.",
                "dialogue": "You have a very kind presence.",
            }
        ],
    )

    result = ai_sims_server.HERMES.dialogue(payload, context)

    assert result["dialogue"] == "That means a lot to me."
    assert "You have a very kind presence." in prompts[0]
    assert "Recent conversation:\nNone yet" in prompts[1]
```

- [x] **Step 2: Run focused tests and verify RED**

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "grounding_rejects or repetition_retry"
```

Expected: FAIL because the one-word near-copy is not rejected and the retry retains history.

- [x] **Step 3: Implement similarity and clean retry**

Import `SequenceMatcher` from `difflib`. Implement:

```python
def _dialogue_similarity(left, right):
    return SequenceMatcher(None, left, right, autojunk=False).ratio()
```

For at least six meaningful message words, reject similarity `>= 0.8`. Use the same comparison for
prior replies of at least four words. In `HermesRuntime.dialogue`, if the first issue contains
`copy` or `previous reply`, rebuild the retry prompt with `dict(context, conversation=[])`, then
append the correction. Continue validating the second response against the original context.

- [x] **Step 4: Run backend tests and verify GREEN**

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py
```

Expected: all backend tests PASS.

- [x] **Step 5: Commit retry isolation**

```powershell
git add adapters/thesims4/backend/ai_sims_server.py adapters/thesims4/tests/test_sims4_backend.py
git commit -m "fix(sims4): isolate repeated dialogue retries"
```

### Task 3: Return relevant Sims fallback dialogue at CLOD 1

**Files:**
- Modify: `adapters/thesims4/backend/ai_sims_server.py:1660-1775`
- Test: `adapters/thesims4/tests/test_sims4_backend.py:730-820`

**Interfaces:**
- Consumes: `reasoning_fallback_response(payload, context) -> dict[str, object]`.
- Produces: an adapter `Decision` through `Sims4Adapter.decision_from_response` when provider routing returns CLOD 1.
- Preserves: Core usage provider `core-rules`, selected CLOD `1`, action proposal, and native confirmation gating.

- [x] **Step 1: Add a failing provider-unavailable integration test**

Reuse the existing test Router shape, but make `generate_result` raise `ProviderError("offline")`.
Call `chat` with Karmine as speaker, Bernard as listener, message
`I'm very attracted to you. You are really hot.`, and `available_actions=["friendly_chat"]`.
Assert:

```python
assert result["selected_clod"] == 1
assert "language model is unavailable" not in result["dialogue"].casefold()
assert "attracted" not in result["dialogue"].casefold()
assert result["relationship"]["romance_delta"] == 0
with open_db(core_db) as conn:
    assert UsageStore(conn).telemetry("karmine")["by_provider"] == {"core-rules": 1}
```

- [x] **Step 2: Run the integration test and verify RED**

Run the new test directly. Expected: FAIL because `Sims4Adapter.response_for` returns the generic
model-unavailable dialogue for Core's CLOD 1 decision.

- [x] **Step 3: Substitute the adapter fallback before proposal storage**

Immediately after `runtime.decide_dynamic` returns, when `selected["clod"] == 1`, replace the generic
decision with:

```python
decision = adapter.decision_from_response(
    reasoning_fallback_response(payload, context),
    event.id,
)
```

Then use the existing action selection, event persistence, action proposal, usage record, response
serialization, and native-confirmation path unchanged.

- [x] **Step 4: Run the complete Sims 4 suite and verify GREEN**

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider
```

Expected: all Sims 4 tests PASS.

- [x] **Step 5: Commit CLOD 1 adapter fallback**

```powershell
git add adapters/thesims4/backend/ai_sims_server.py adapters/thesims4/tests/test_sims4_backend.py
git commit -m "fix(sims4): ground offline social fallback"
```

### Task 4: Verify, document, and push

**Files:**
- Modify: `adapters/thesims4/docs/in-game-core-feature-test-plan.md`
- Modify: `adapters/thesims4/docs/in-game-core-feature-test-results.md`
- Add: `docs/plans/2026-07-20-sims4-semantic-social-fallback-implementation.md`

**Interfaces:**
- Produces: a clean, pushed `feature/sims4-core-integration` branch ready for another Test 5 release retest.

- [x] **Step 1: Run all verification suites from their package roots**

Run Core, Sims 4, Godot, repository integration, and release-contract pytest suites. Run the CI
Ruff command, `mypy core/src adapters/thesims4/src`, and `py_compile` for the Sims backend,
Empneon state bridge, and script mod. Expected: every command exits `0`.

- [x] **Step 2: Update Test 5 evidence without marking it passed**

Record Karmine's observed near-copy, the two `previous reply` provider-log rejections, the generic
fallback root cause, and the automated semantic/offline remediation. Keep Test 5 `PARTIAL` until a
release proves distinct dialogue and a confirmed native romance consequence.

- [x] **Step 3: Commit documentation and plan**

```powershell
git add adapters/thesims4/docs/in-game-core-feature-test-plan.md adapters/thesims4/docs/in-game-core-feature-test-results.md docs/plans/2026-07-20-sims4-semantic-social-fallback-implementation.md
git commit -m "docs(sims4): prepare semantic fallback retest"
```

- [x] **Step 4: Push the existing PR branch**

```powershell
git push origin feature/sims4-core-integration
```

Expected: PR #5 advances to the final documentation commit; preserve the worktree.
