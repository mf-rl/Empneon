# Sims 4 Possessive Code-Word Recall Implementation Plan

**Execution status:** Completed; automated checks and the live Test 14 retest passed.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recall confirmed `our` and `your` identifier assignments with correct attribution and return safe uncertainty instead of HTTP `500` for unsupported explicit recall.

**Architecture:** Extend the existing confirmed-event fact boundary with one narrow possessive identifier parser. Reuse Core's existing explicit-recall classifier in the deterministic fallback rather than maintaining a second incomplete question list.

**Tech Stack:** Python 3.12 backend and tests, Python 3.7-compatible Sims script unchanged, pytest, SQLite

## Global Constraints

- Preserve existing identifier-first and `my ... is ...` durable facts.
- Preserve actor attribution, pair privacy, time/location constraints, save-slot behavior, provider usage, cancellation, and action-result behavior.
- Do not change schemas, configuration, HTTP contracts, or Sims script-mod code.
- Do not modify or migrate the existing slot 14 and slot 15 checkpoint files.
- Leave every change uncommitted and unpushed until the user explicitly requests otherwise.

---

### Task 1: Attribute Possessive Identifier Assignments

**Files:**
- Modify: `adapters/thesims4/backend/empneon_state.py:549-615`
- Test: `adapters/thesims4/tests/test_sims4_backend.py:2584`

**Interfaces:**
- Consumes: confirmed interaction dictionaries with `speaker_id`, `listener_id`, `message`, and `facts`.
- Produces: `_authoritative_facts(data: dict[str, object]) -> list[dict[str, object]]` entries whose `actor_id` is the message author for `my`/`our` and the addressed Sim for `your`.

- [x] **Step 1: Add the failing attribution regression**

Add beside `test_legacy_confirmed_identifier_assignment_is_authoritative`:

```python
@pytest.mark.parametrize(
    ("message", "actor_id"),
    (
        ("Our secret code word is TEST14-A-731.", "sim-a"),
        ("Your secret code word is TEST14-B-731.", "sim-b"),
    ),
)
def test_possessive_identifier_assignment_is_authoritative(
    message: str,
    actor_id: str,
) -> None:
    assert ai_sims_server.empneon_state._authoritative_facts(
        {
            "speaker_id": "sim-b",
            "listener_id": "sim-a",
            "message": message,
            "dialogue": "Acknowledged.",
            "facts": [],
        }
    ) == [{"actor_id": actor_id, "statement": message}]
```

- [x] **Step 2: Run the test and verify RED**

Run from `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py::test_possessive_identifier_assignment_is_authoritative
```

Expected: both rows fail because `_authoritative_facts()` returns `[]`.

- [x] **Step 3: Implement the narrow assignment parser**

In `empneon_state.py`, add a compiled pattern that requires `my`, `our`, or `your`, a bounded property phrase, `is`/`are`, and the existing hyphenated identifier shape:

```python
_POSSESSIVE_IDENTIFIER_ASSIGNMENT = re.compile(
    r"\b(?P<possessive>my|our|your)\s+[a-z][a-z -]{0,30}\s+"
    r"(?:is|are)\s+(?=[A-Z0-9-]*\d)[A-Z0-9]+(?:-[A-Z0-9]+)+\b",
    re.IGNORECASE,
)
```

Add:

```python
def _possessive_identifier_fact(
    data: dict[str, object],
) -> dict[str, str] | None:
    statement = " ".join(str(data.get("message") or "").split())
    match = _POSSESSIVE_IDENTIFIER_ASSIGNMENT.search(statement)
    if not statement or statement.endswith("?") or match is None:
        return None
    actor_id = (
        str(data.get("speaker_id") or "")
        if match.group("possessive").casefold() == "your"
        else str(data.get("listener_id") or "")
    )
    return {"actor_id": actor_id, "statement": statement}
```

In `_authoritative_facts()`, append this fact for non-recall messages before the legacy fact, using the existing membership check to avoid duplicating `my` facts.

- [x] **Step 4: Run attribution and existing fact tests and verify GREEN**

```powershell
py -3.12 -m pytest -q -p no:cacheprovider `
  tests/test_sims4_backend.py::test_possessive_identifier_assignment_is_authoritative `
  tests/test_sims4_backend.py::test_legacy_confirmed_identifier_assignment_is_authoritative `
  tests/test_sims4_backend.py::test_confirmed_identifier_fact_is_required_for_explicit_recall
```

Expected: all pass.

---

### Task 2: Make Explicit Recall Fallback Total

**Files:**
- Modify: `adapters/thesims4/backend/ai_sims_server.py:2435-2449`
- Test: `adapters/thesims4/tests/test_sims4_backend.py:3592`

**Interfaces:**
- Consumes: `analyze_recall_query(message) -> RecallQuery`.
- Produces: `reasoning_fallback_response(payload, context) -> dict[str, object]` for every explicit recall question, including unsupported `What is ...?` forms.

- [x] **Step 1: Add failing exact-live and unsupported-fallback regressions**

Add:

```python
@pytest.mark.parametrize(
    ("statement", "question", "actor_id", "identifier"),
    (
        (
            "Our secret code word is TEST14-A-731.",
            "What is our code word?",
            "sim-a",
            "TEST14-A-731",
        ),
        (
            "Your secret code word is TEST14-B-731.",
            "What is your code word?",
            "sim-b",
            "TEST14-B-731",
        ),
    ),
)
def test_reasoning_fallback_recalls_possessive_codeword(
    statement: str,
    question: str,
    actor_id: str,
    identifier: str,
) -> None:
    facts = ai_sims_server.empneon_state._authoritative_facts(
        {
            "speaker_id": "sim-b",
            "listener_id": "sim-a",
            "message": statement,
            "facts": [],
        }
    )
    context = ai_sims_server.build_context(
        {"id": "sim-b"},
        {"id": "sim-a"},
        {"name": "Sim B"},
        {"name": "Sim A"},
        {},
        [
            {
                "speaker_id": "sim-b",
                "listener_id": "sim-a",
                "message": statement,
                "dialogue": "Acknowledged.",
                "facts": facts,
            }
        ],
    )
    context.update(
        conversation=[],
        speaker_id="sim-b",
        listener_id="sim-a",
    )

    response = ai_sims_server.reasoning_fallback_response(
        {"message": question},
        context,
    )

    assert identifier in response["dialogue"]
    assert ai_sims_server.response_grounding_issue(
        {"message": question},
        response,
        context,
    ) == ""
    assert facts == [{"actor_id": actor_id, "statement": statement}]


def test_reasoning_fallback_returns_uncertainty_for_unsupported_what_question() -> None:
    context = ai_sims_server.build_context(
        {"id": "sim-b"},
        {"id": "sim-a"},
        {"name": "Sim B"},
        {"name": "Sim A"},
        {},
        [],
    )
    context.update(
        conversation=[],
        speaker_id="sim-b",
        listener_id="sim-a",
    )

    response = ai_sims_server.reasoning_fallback_response(
        {"message": "What is our code word?"},
        context,
    )

    assert response["intent"] == "admit_uncertainty"
    assert "don't know" in response["dialogue"].casefold()
```

- [x] **Step 2: Run the regressions and verify RED**

```powershell
py -3.12 -m pytest -q -p no:cacheprovider `
  tests/test_sims4_backend.py::test_reasoning_fallback_recalls_possessive_codeword `
  tests/test_sims4_backend.py::test_reasoning_fallback_returns_uncertainty_for_unsupported_what_question
```

Expected after Task 1: supported rows pass, while the unsupported question raises `RuntimeError: could not build a grounded dialogue fallback`.

- [x] **Step 3: Reuse the shared explicit-recall classifier**

In the fallback candidate selection, replace the incomplete prefix/keyword condition with:

```python
elif analyze_recall_query(message).explicit:
    candidates.append("I'm not sure; I don't remember enough to answer that.")
```

Keep the supported-memory branch before it so authoritative answers retain precedence.

- [x] **Step 4: Run focused recall tests and verify GREEN**

```powershell
py -3.12 -m pytest -q -p no:cacheprovider `
  tests/test_sims4_backend.py::test_reasoning_fallback_recalls_possessive_codeword `
  tests/test_sims4_backend.py::test_reasoning_fallback_returns_uncertainty_for_unsupported_what_question `
  tests/test_sims4_backend.py::test_reasoning_fallback_recalls_supported_fact_and_uses_concrete_summary
```

Expected: all pass and no fallback raises.

---

### Task 3: Regression Verification and Test 14 Record

**Files:**
- Modify: `docs/superpowers/specs/2026-07-26-sims4-possessive-codeword-recall-design.md`
- Modify: `adapters/thesims4/docs/in-game-core-feature-test-results.md:1121-1146`
- Modify: `docs/roadmap.md:44-51`
- Verify: `adapters/thesims4/backend/empneon_state.py`
- Verify: `adapters/thesims4/backend/ai_sims_server.py`
- Verify: `adapters/thesims4/tests/test_sims4_backend.py`

**Interfaces:**
- Consumes: green focused regressions from Tasks 1 and 2.
- Produces: automated compatibility evidence and an accurate live-retest handoff.

- [x] **Step 1: Run the complete Sims adapter suite**

From `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider
```

Expected: all Sims tests pass.

- [x] **Step 2: Run the complete Core suite**

From `core`:

```powershell
$env:PYTHONPATH='src'
py -3.12 -m pytest -q -p no:cacheprovider
```

Expected: all Core tests pass.

- [x] **Step 3: Compile changed production modules**

From the repository root:

```powershell
py -3.12 -m py_compile `
  adapters/thesims4/backend/empneon_state.py `
  adapters/thesims4/backend/ai_sims_server.py
```

Expected: exit code `0`.

- [x] **Step 4: Update the acceptance record**

Set the design status to implemented and automated-verified. Record that slots 14 and 15 already prove checkpoint separation, the exact live recall failure now has regressions, and a rebuilt backend live retest remains required. Keep Test 14 `PARTIAL` until both Save A and Save B answers are delivered in game after full restarts.

- [x] **Step 5: Inspect the final uncommitted result**

```powershell
git diff --check
git status --short
git diff --stat
```

Expected: only the approved backend, tests, spec, plan, results, and roadmap files are changed. Do not stage, commit, or push.
