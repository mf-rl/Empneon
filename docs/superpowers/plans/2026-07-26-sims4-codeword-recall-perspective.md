# Sims 4 Code-Word Recall Perspective Implementation Plan

**Execution status:** Completed; automated checks and first-person live recall passed.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Sim B answer a supported `your code word` question as `my code word` while preserving owner selection, shared recall, and unrelated dialogue.

**Architecture:** Parse identifier-bearing code-word facts at the Sims response boundary. Reuse that parser to render owner-aware prompt evidence, enforce first-person grounding, and produce a correct deterministic fallback.

**Tech Stack:** Python 3.12, `re`, pytest, Sims 4 adapter backend

## Global Constraints

- Preserve Test 14 A/B fact selection and save-slot isolation.
- Preserve `our code word` as shared first-person plural.
- Preserve relationship-outcome sanitization and normal romance.
- Do not mutate databases/checkpoints or change Core, provider schemas, or Sims mod code.
- Leave all changes uncommitted and unpushed.

---

### Task 1: Enforce Code-Word Owner Perspective

**Files:**
- Modify: `adapters/thesims4/backend/ai_sims_server.py:2199-2285,2343`
- Test: `adapters/thesims4/tests/test_sims4_backend.py:3820-3910`

**Interfaces:**
- Produces: `_codeword_fact_parts(fact) -> tuple[str, str] | None`, returning `(possessive, identifier)`.
- Consumes: `empneon_state.codeword_recall_owner_id(query, responding_id, message_author_id)`.

- [x] **Step 1: Add failing evidence and grounding regressions**

```python
def test_codeword_recall_evidence_uses_owner_not_source_pronoun() -> None:
    context = {
        "speaker_id": "sim-b",
        "listener_id": "sim-a",
        "speaker": {"name": "Sim B"},
        "listener": {"name": "Sim A"},
    }
    fact = {
        "actor_id": "sim-b",
        "statement": "Your secret code word is TEST14-B-731.",
    }

    assert ai_sims_server._attributed_fact_text(fact, context) == (
        "Sim B's code word is TEST14-B-731."
    )


def test_supported_codeword_recall_requires_first_person_owner() -> None:
    payload = {"message": "What is your code word?"}
    context = ai_sims_server.build_context(
        payload,
        {"name": "Sim B"},
        {"name": "Sim A"},
        {},
        {},
        [{
            "facts": [{
                "actor_id": "sim-b",
                "statement": "Your secret code word is TEST14-B-731.",
            }]
        }],
    )
    context.update(conversation=[], speaker_id="sim-b", listener_id="sim-a")

    assert ai_sims_server._supported_recall_issue(
        payload,
        {"dialogue": "Your code word is TEST14-B-731."},
        context,
    ) == "refer to the Speaker-owned code word in first person as my code word"
    assert ai_sims_server._supported_recall_issue(
        payload,
        {"dialogue": "My code word is TEST14-B-731."},
        context,
    ) == ""
```

- [x] **Step 2: Tighten the existing fallback regression**

Extend `test_reasoning_fallback_recalls_possessive_codeword` with an expected
dialogue parameter:

```python
(
    "Our secret code word is TEST14-A-731.",
    "What is our code word?",
    "sim-a",
    "Our code word is TEST14-A-731.",
),
(
    "Your secret code word is TEST14-B-731.",
    "What is your code word?",
    "sim-b",
    "My code word is TEST14-B-731.",
),
```

Assert `response["dialogue"] == expected_dialogue` while retaining the
existing grounding and fact-attribution assertions.

- [x] **Step 3: Run the tests and verify RED**

From `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py `
  -k "codeword_recall_evidence_uses_owner_not_source_pronoun or supported_codeword_recall_requires_first_person_owner or reasoning_fallback_recalls_possessive_codeword"
```

Expected: evidence still says `Sim B said: Your...`, wrong-person grounding
returns no issue, and fallback does not produce the required `My`/`Our`
sentences.

- [x] **Step 4: Add the narrow fact parser**

In `ai_sims_server.py`:

```python
_CODEWORD_FACT = re.compile(
    r"\b(?P<possessive>my|our|your)\s+(?:secret\s+)?code\s*word\s+"
    r"(?:is|are)\s+(?P<identifier>(?=[A-Z0-9-]*\d)"
    r"[A-Z0-9]+(?:-[A-Z0-9]+)+)\b",
    re.IGNORECASE,
)


def _codeword_fact_parts(fact):
    match = _CODEWORD_FACT.search(str(fact.get("statement") or ""))
    if match is None:
        return None
    return match.group("possessive").casefold(), match.group("identifier")
```

- [x] **Step 5: Render evidence by ownership**

At the start of `_attributed_fact_text()`:

```python
parts = _codeword_fact_parts(fact)
if parts is not None:
    possessive, identifier = parts
    if possessive == "our":
        return "The shared code word is {}.".format(identifier)
    return "{}'s code word is {}.".format(actor, identifier)
```

Compute `actor` before this branch using the existing ID-to-name mapping.

- [x] **Step 6: Enforce first-person grounding**

After Core recall validation in `_supported_recall_issue()`:

```python
owner_id = empneon_state.codeword_recall_owner_id(
    message,
    str(context.get("speaker_id") or ""),
    str(context.get("listener_id") or ""),
)
if (
    owner_id == str(context.get("speaker_id") or "")
    and any(_codeword_fact_parts(fact) is not None for fact in facts)
    and not re.search(
        r"\bmy\s+(?:secret\s+)?code\s*word\b",
        dialogue,
        re.IGNORECASE,
    )
):
    return (
        "refer to the Speaker-owned code word in first person "
        "as my code word"
    )
```

- [x] **Step 7: Make deterministic fallback perspective-correct**

Change `_recalled_fact_dialogue(fact, context)` to accept `message=""`.
Before its existing attribution branches:

```python
parts = _codeword_fact_parts(fact)
owner_id = empneon_state.codeword_recall_owner_id(
    message,
    str(context.get("speaker_id") or ""),
    str(context.get("listener_id") or ""),
)
if parts is not None and owner_id is not None:
    identifier = parts[1]
    pronoun = (
        "My"
        if owner_id == str(context.get("speaker_id") or "")
        else "Our"
    )
    return "{} code word is {}.".format(pronoun, identifier)
```

Pass `message` from `reasoning_fallback_response()` into this function.

- [x] **Step 8: Run focused tests and verify GREEN**

Repeat Step 3. Expected: all selected tests pass.

- [x] **Step 9: Run complete verification and update records**

Run all Sims adapter, Core, Godot, and shared tests; compile the two changed
backend modules; run `git diff --check`. Update Test 14 documentation with
the live perspective failure, automated fix, and backend-restart retest.
Keep Test 14 `PARTIAL`; do not stage, commit, or push.
