# Sims 4 Neutral Factual-Recall Outcomes Implementation Plan

**Execution status:** Completed; automated checks and neutral live outcomes passed.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent supported factual-recall answers from causing relationship outcomes or native social actions while preserving their dialogue and all normal social behavior.

**Architecture:** Reuse `_supported_recall_facts()` as the existing explicit, grounded recall boundary. After model normalization in `HermesRuntime.dialogue()`, clear only the response's relationship outcome and executable actions when supported recall evidence exists.

**Tech Stack:** Python 3.12, pytest, Sims 4 adapter backend

## Global Constraints

- Preserve generated recall dialogue, emotion, intent, category, tone, trust, and memory.
- Preserve normal romance initiation, subtle reciprocation, rejection, and outcomes.
- Preserve all non-recall social categories and existing recall grounding.
- Do not change Core contracts, prompts, schemas, databases, or Sims script-mod code.
- Leave all changes uncommitted and unpushed.

---

### Task 1: Neutralize Supported Recall Side Effects

**Files:**
- Modify: `adapters/thesims4/backend/ai_sims_server.py:2480-2500`
- Test: `adapters/thesims4/tests/test_sims4_backend.py:1619`

**Interfaces:**
- Consumes: `_supported_recall_facts(message, context) -> list[dict]`.
- Produces: `HermesRuntime.dialogue()` responses with supported recall dialogue intact and `relationship_outcome`, `suggested_action`, and `animation` set to `none`.

- [x] **Step 1: Add the failing supported-recall regression**

Add a provider response matching the live failure:

```python
def test_supported_recall_is_relationship_and_action_neutral(monkeypatch) -> None:
    provider_response = {
        "dialogue": "TEST14-A-731? That's it! It's a secret code word for us.",
        "expressed_emotion": "playful",
        "intent": "accept_playfully",
        "response_category": "romance",
        "tone_tags": ["playful", "romantic"],
        "trust_delta": 1,
        "relationship_outcome": "romance_positive",
        "memory": {"importance": 0.5, "summary": ""},
    }
    monkeypatch.setattr(
        ai_sims_server,
        "llm_chat",
        lambda *_args, **_kwargs: json.dumps(provider_response),
    )
    payload = {
        "speaker": {},
        "listener": {},
        "message": "What is our code word?",
        "available_response_categories": ["friendly", "romance"],
    }
    context = ai_sims_server.build_context(
        payload,
        {"name": "Sim B"},
        {"name": "Sim A"},
        {},
        {},
        [{
            "facts": [{
                "actor_id": "sim-a",
                "statement": "Our secret code word is TEST14-A-731.",
            }]
        }],
    )
    context.update(conversation=[], speaker_id="sim-b", listener_id="sim-a")

    response = ai_sims_server.HERMES.dialogue(payload, context)

    assert response["dialogue"] == provider_response["dialogue"]
    assert response["response_category"] == "romance"
    assert response["trust_delta"] == 1
    assert response["relationship_outcome"] == "none"
    assert response["suggested_action"] == "none"
    assert response["animation"] == "none"
```

- [x] **Step 2: Add the compatibility regression**

Use an ordinary romantic prompt and no recalled facts:

```python
def test_normal_romance_remains_actionable(monkeypatch) -> None:
    provider_response = {
        "dialogue": "Yes, I feel the same. I would love to be together.",
        "expressed_emotion": "playful",
        "intent": "accept_playfully",
        "response_category": "romance",
        "tone_tags": ["playful", "romantic"],
        "trust_delta": 1,
        "relationship_outcome": "romance_positive",
        "memory": {"importance": 0.5, "summary": ""},
    }
    monkeypatch.setattr(
        ai_sims_server,
        "llm_chat",
        lambda *_args, **_kwargs: json.dumps(provider_response),
    )
    monkeypatch.setattr(
        ai_sims_server, "RESPONSE_REJECTION_ENABLED", False
    )
    payload = {
        "speaker": {},
        "listener": {},
        "message": "I love you. Do you feel the same?",
        "available_response_categories": ["friendly", "romance"],
    }
    context = ai_sims_server.build_context(
        payload,
        {"name": "Sim B"},
        {"name": "Sim A"},
        {},
        {},
        [],
    )
    context.update(conversation=[], speaker_id="sim-b", listener_id="sim-a")

    response = ai_sims_server.HERMES.dialogue(payload, context)

    assert response["relationship_outcome"] == "romance_positive"
    assert response["suggested_action"] == "social.romance"
    assert response["animation"] == "social.romance"
```

- [x] **Step 3: Run both tests and verify RED**

From `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py `
  -k "supported_recall_is_relationship_and_action_neutral or normal_romance_remains_actionable"
```

Expected: the supported-recall test fails with
`relationship_outcome == "romance_positive"` while the normal-romance
compatibility test passes.

- [x] **Step 4: Implement the response-boundary guard**

Immediately after the `normalize_response()` / `fallback_response()` block in
`HermesRuntime.dialogue()`:

```python
if supported_facts:
    response["relationship_outcome"] = "none"
    response["suggested_action"] = response["animation"] = "none"
```

- [x] **Step 5: Run focused tests and verify GREEN**

Repeat the Step 3 command. Expected: both tests pass.

- [x] **Step 6: Run complete verification**

Run the full Sims adapter, Core, Godot, and shared pytest suites, compile
`ai_sims_server.py` and `empneon_state.py`, then run `git diff --check`.
Expected: zero failures and exit code `0` for every command.

- [x] **Step 7: Update Test 14 records**

Record:

- owner-aware live recall passed with B for `your` and A for `our`;
- both turns incorrectly applied `romance +5`;
- the response-boundary fix is automated-pass and requires a backend-restart
  live confirmation that recall no longer changes romance.

Keep Test 14 `PARTIAL`. Do not stage, commit, or push.
