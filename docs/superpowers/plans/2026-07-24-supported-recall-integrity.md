# Supported Recall Integrity Implementation Plan

**Status:** Completed; checklist retained as the original execution record

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure a model uses selected attributed facts when answering naturally phrased recall questions without enabling broad response rejection.

**Architecture:** Keep memory retrieval unchanged and add one narrow validation path at Sims dialogue generation. It detects recall clauses anywhere in a question, derives answer-bearing terms from selected facts, retries only an ignored supported recall, and uses the existing grounded fallback after a second failure.

**Tech Stack:** Python 3.12 backend and pytest, Python 3.7 Sims script build

## Global Constraints

- Keep `response_rejection_enabled=false` behavior unchanged for non-recall dialogue.
- Preserve pair scoping, privacy, confirmation gating, semantic selection, persistence, categories, relationship effects, animation, and provider transports.
- Require factual answers only when selected attributed evidence supports the question.
- Keep the rule provider- and model-agnostic.
- Add no dependency or Core gameplay concept.
- Do not commit or push until explicitly requested.

---

## File Structure

- Modify `adapters/thesims4/backend/empneon_state.py`: expose the existing time-fact cue for reuse; do not change its matching behavior.
- Modify `adapters/thesims4/backend/ai_sims_server.py`: detect supported recall questions and enforce the narrow retry/fallback path.
- Modify `adapters/thesims4/tests/test_sims4_backend.py`: reproduce the exact live failure and protect ordinary/unsupported dialogue.
- Modify `adapters/thesims4/docs/in-game-core-feature-test-plan.md`: record the automated repair and live retest.
- Modify `adapters/thesims4/docs/in-game-core-feature-test-results.md`: append the tracked failure, root cause, and verification.

### Task 1: Reproduce supported recall being ignored

**Files:**
- Test: `adapters/thesims4/tests/test_sims4_backend.py`

**Interfaces:**
- Consumes: `CognitionRuntime.dialogue(payload, context)`
- Produces: regression coverage for the always-on supported-recall contract

- [ ] **Step 1: Add a live-shaped retry test**

Create a context with an explicit attributed fact:

```python
recalled = [
    {
        "speaker_id": "karmine",
        "listener_id": "bernard",
        "message": "Tonight, 7pm, at my place.",
        "facts": [
            {
                "actor_id": "bernard",
                "statement": "Tonight, 7pm, at my place.",
            }
        ],
        "explicit": True,
    }
]
payload = {
    "speaker": {},
    "listener": {},
    "message": (
        "Hey, my sweet baby. When are we going on our date? "
        "Can you tell me?"
    ),
    "available_response_categories": ["friendly", "romance"],
}
```

Stub `llm_chat` with two schema-valid responses: first
`That sounds good! So, when are we going on our date?`, then
`Tonight at 7 pm, at your place. I'm looking forward to it.` Set
`RESPONSE_REJECTION_ENABLED=False`. Assert:

```python
assert len(calls) == 2
assert response["dialogue"] == corrected_dialogue
assert "Tonight, 7pm, at my place." in calls[1][0][1]["content"]
```

- [ ] **Step 2: Add a failed-retry fallback test**

Return the same ignored-recall response twice. Assert the provider is called
twice and the resulting dialogue contains the known time rather than declining
the date or asking the question back:

```python
assert len(calls) == 2
assert "tonight" in response["dialogue"].casefold()
assert "7pm" in response["dialogue"].casefold()
assert "rather stay friends" not in response["dialogue"].casefold()
```

- [ ] **Step 3: Protect unsupported and non-recall behavior**

Retain `test_disabled_response_rejection_accepts_first_normalized_response`.
Add an unsupported recall assertion with no facts and a first provider response
of `I don't remember that.`:

```python
assert len(calls) == 1
assert response["dialogue"] == "I don't remember that."
```

- [ ] **Step 4: Add the supported-recall provider-failure test**

Make `llm_chat` raise `ProviderError("offline")` with the supported date
context. Assert the grounded result still uses the selected fact:

```python
assert "tonight" in response["dialogue"].casefold()
assert "7pm" in response["dialogue"].casefold()
```

Do not catch provider failures when the context has no supported recall fact.

- [ ] **Step 5: Run the focused tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "supported_recall or disabled_response_rejection"
```

Expected: the retry tests fail because only one provider call is made and the
ignored response is returned; the provider-failure test raises instead of
falling back. Existing non-recall behavior passes.

### Task 2: Add the narrow recall-integrity boundary

**Files:**
- Modify: `adapters/thesims4/backend/empneon_state.py:550-565`
- Modify: `adapters/thesims4/backend/ai_sims_server.py:1930-2195`
- Test: `adapters/thesims4/tests/test_sims4_backend.py`

**Interfaces:**
- Consumes: selected `context["recalled_memories"]`
- Produces: `_supported_recall_facts(message, context) -> list[str]` and `_supported_recall_issue(payload, response, context) -> str`

- [ ] **Step 1: Reuse the existing time cue**

Rename `_TIME_FACT_CUE` to `TIME_FACT_CUE` in `empneon_state.py` and update its
two local references. Do not alter the regular expression.

- [ ] **Step 2: Detect supported recall facts**

Add helpers beside `_memory_supports_question()`:

```python
def _recall_question_cue(message):
    value = str(message or "").casefold()
    if "?" not in value:
        return ""
    match = re.search(r"\b(when|where|who|what)\b", value)
    if match:
        return match.group(1)
    if "remember" in value or "did i say" in value:
        return "recall"
    return ""


def _supported_recall_facts(message, context):
    cue = _recall_question_cue(message)
    if not cue:
        return []
    facts = [
        str(fact.get("statement") or "").strip()
        for memory in context.get("recalled_memories") or []
        for fact in memory.get("facts") or []
        if isinstance(fact, dict) and str(fact.get("statement") or "").strip()
    ]
    if cue == "when":
        return [fact for fact in facts if empneon_state.TIME_FACT_CUE.search(fact)]
    question_terms = set(_dialogue_words(message, context))
    return [
        fact
        for fact in facts
        if question_terms & set(_dialogue_words(fact, context))
    ]
```

Update `_memory_supports_question()` to return `True` immediately when
`_supported_recall_facts()` is non-empty, preserving its existing lexical
fallback for older explicit exchanges without structured facts.

- [ ] **Step 3: Validate only selected answers**

Add:

```python
def _supported_recall_issue(payload, response, context):
    message = str(payload.get("message") or "")
    facts = _supported_recall_facts(message, context)
    if not facts:
        return ""
    dialogue = str(response.get("dialogue") or "")
    lowered = dialogue.casefold()
    if any(
        phrase in lowered
        for phrase in (
            "don't know",
            "do not know",
            "not sure",
            "don't remember",
            "do not remember",
            "what are you talking",
        )
    ):
        return "use the supporting memory instead of denying it"
    cue = _recall_question_cue(message)
    if cue == "when" and empneon_state.TIME_FACT_CUE.search(dialogue):
        return ""
    question_terms = set(_dialogue_words(message, context))
    ignored = {
        "about", "can", "did", "does", "good", "going", "know", "remember",
        "said", "say", "sound", "sounds", "tell", "that", "the", "this",
        "what", "when", "where", "which", "who", "with", "would", "you",
    }
    answer_terms = set().union(
        *(
            set(_dialogue_words(fact, context)) - question_terms - ignored
            for fact in facts
        )
    )
    if answer_terms and answer_terms & set(_dialogue_words(dialogue, context)):
        return ""
    return "answer the recall question with the selected attributed fact"
```

Call this helper from `response_grounding_issue()` so broad rejection mode
also uses the same rule. Preserve unsupported-memory uncertainty behavior.

- [ ] **Step 4: Enforce only recall integrity when broad rejection is off**

In `CognitionRuntime.dialogue()`, compute `recall_issue` after normalization.
Return immediately under `RESPONSE_REJECTION_ENABLED=False` only when it is
empty. When it is non-empty, use the existing second attempt and append the
exact selected facts:

```python
facts = _supported_recall_facts(payload.get("message"), context)
prompt += (
    "\nCorrection: Answer the recall question using this attributed evidence: "
    + " | ".join(facts)
)
```

Do not apply role, repetition, category, or other grounding rejection while
the broad flag is off.

- [ ] **Step 5: Keep the fallback grounded**

In `reasoning_fallback_response()`, place the existing supported-question
branch before `interaction_kind == "romantic_invitation"`. This ensures
`When are we going on our date?` recalls the selected plan rather than
declining a new invitation.

If a provider error occurs while selected supported facts exist, return this
same grounded fallback. Preserve the existing exception behavior when there is
no supported recall evidence.

- [ ] **Step 6: Run focused coverage and verify GREEN**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "supported_recall or grounding_rejects_memory or dialogue_fallback or disabled_response_rejection"
```

Expected: all selected tests pass. The live-shaped case retries, the second
response is accepted, the failed retry uses the date fact, and ordinary
rejection-disabled dialogue remains a single call.

### Task 3: Full verification, build, and live-test record

**Files:**
- Modify: `adapters/thesims4/docs/in-game-core-feature-test-plan.md`
- Modify: `adapters/thesims4/docs/in-game-core-feature-test-results.md`

**Interfaces:**
- Consumes: Tasks 1 and 2 verification
- Produces: rebuilt artifacts and an accurate pending live-test handoff

- [ ] **Step 1: Run the complete Sims adapter suite and compile the backend**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests
py -3.12 -m py_compile backend/ai_sims_server.py backend/empneon_state.py
```

Expected: all Sims tests and compilation pass.

- [ ] **Step 2: Run the complete Core suite**

Run:

```powershell
$env:PYTHONPATH='src'
py -3.12 -m pytest -q -p no:cacheprovider tests
```

Expected: all Core tests pass.

- [ ] **Step 3: Build the Sims mod**

Run:

```powershell
py -3.12 .\build_mod.py
```

Expected: both `Empneon_TheSims4.ts4script` and
`Empneon_TheSims4.package` build successfully in `dist`.

- [ ] **Step 4: Update the test documents**

Record the exact failed response, confirmation that attributed evidence
reached the prompt, the narrow always-on validation boundary, automated test
counts, and that live verification requires only repeating the existing date
question after installation and restart.

- [ ] **Step 5: Review the uncommitted diff**

Run:

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors and only intended session files. Do not commit,
push, install, or restart the running game/backend.
