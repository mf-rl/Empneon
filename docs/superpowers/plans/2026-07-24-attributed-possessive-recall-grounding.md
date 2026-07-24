# Attributed Possessive Recall Grounding Implementation Plan

**Status:** Completed; checklist retained as the original execution record

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reject recalled responses that invert an attributed location's owner while preserving correct, quoted, omitted, and non-recall responses.

**Architecture:** Extend the existing deterministic `_supported_recall_issue` boundary with one small ownership check. Derive the location owner from attributed facts, ignore explicitly attributed quoted text, and let the existing retry and safe fallback paths handle conflicts.

**Tech Stack:** Python 3.11+, standard-library `re`, pytest, Empneon attributed episodic memory.

## Global Constraints

- Do not rewrite, migrate, or delete stored memories.
- Do not change Core attribution, persistence, or provider routing.
- Do not require a response to mention location.
- Preserve valid quotations and symmetric speaker/listener ownership.
- Limit deterministic location vocabulary to `place`, `home`, and `house`.
- Do not commit or push until the user explicitly requests it.

---

### Task 1: Enforce attributed possessive location perspective

**Files:**
- Modify: `adapters/thesims4/backend/ai_sims_server.py:2003-2075`
- Test: `adapters/thesims4/tests/test_sims4_backend.py:1437-1550`

**Interfaces:**
- Consumes: supported facts shaped as `{"actor_id": str, "statement": str}` plus dialogue context containing `speaker_id`, `listener_id`, `speaker`, and `listener`.
- Produces: `_possessive_location_issue(facts, dialogue, context) -> str`.
- Integrates with: `_supported_recall_issue(payload, response, context) -> str`.

- [x] **Step 1: Add failing ownership regression tests**

Add the following tests beside the existing supported-recall tests:

```python
@pytest.mark.parametrize(
    ("dialogue", "expected_issue"),
    [
        (
            "Oh, of course! It's tonight at 7pm, right at my place.",
            "preserve the recalled location owner and speaker perspective",
        ),
        ("Tonight at 7pm, at your place.", ""),
        ("Tonight at 7pm, at Bernard's place.", ""),
        ('You told me: "Tonight, 7pm, at my place."', ""),
        ("Tonight at 7pm.", ""),
    ],
)
def test_supported_recall_preserves_listener_owned_location_perspective(
    dialogue, expected_issue
) -> None:
    payload, context = _supported_date_recall_context()

    issue = ai_sims_server._supported_recall_issue(
        payload,
        {"dialogue": dialogue},
        context,
    )

    assert issue == expected_issue


@pytest.mark.parametrize(
    ("dialogue", "expected_issue"),
    [
        ("Tonight at 7pm, at my place.", ""),
        (
            "Tonight at 7pm, at your place.",
            "preserve the recalled location owner and speaker perspective",
        ),
        ('I remember saying: "Tonight, 7pm, at my place."', ""),
    ],
)
def test_supported_recall_preserves_speaker_owned_location_perspective(
    dialogue, expected_issue
) -> None:
    payload, context = _supported_date_recall_context()
    context["recalled_memories"][0]["facts"][0]["actor_id"] = "karmine"

    issue = ai_sims_server._supported_recall_issue(
        payload,
        {"dialogue": dialogue},
        context,
    )

    assert issue == expected_issue


def test_supported_recall_uses_attributed_fallback_after_location_inversion(
    monkeypatch,
) -> None:
    inverted = _social_provider_response(
        "Oh, of course! It's tonight at 7pm, right at my place.",
        "romance",
    )
    calls = []
    monkeypatch.setattr(
        ai_sims_server,
        "llm_chat",
        lambda *_args, **_kwargs: calls.append(1) or json.dumps(inverted),
    )
    monkeypatch.setattr(ai_sims_server, "RESPONSE_REJECTION_ENABLED", False)
    payload, context = _supported_date_recall_context()

    response = ai_sims_server.HERMES.dialogue(payload, context)

    assert len(calls) == 2
    assert response["dialogue"] == (
        'You told me: "Tonight, 7pm, at my place."'
    )
```

- [x] **Step 2: Run focused tests and verify RED**

Run from `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py::test_supported_recall_preserves_listener_owned_location_perspective tests/test_sims4_backend.py::test_supported_recall_preserves_speaker_owned_location_perspective tests/test_sims4_backend.py::test_supported_recall_uses_attributed_fallback_after_location_inversion
```

Expected: invalid `my place`/`your place` cases return no issue, and the live-shaped model response is accepted instead of reaching fallback.

- [x] **Step 3: Add the minimal attribution-aware helper**

Add beside `_supported_recall_facts`:

```python
_POSSESSIVE_LOCATION_CUE = re.compile(
    r"\b(?P<possessive>my|your)\s+(?P<location>place|home|house)\b",
    re.IGNORECASE,
)
_ATTRIBUTED_QUOTATION = re.compile(
    r"(?:\byou told me|\bi remember saying|\b[^:\n]{1,50}\bsaid)"
    r"\s*:\s*(?:\"[^\"]*\"|“[^”]*”)",
    re.IGNORECASE,
)


def _possessive_location_issue(facts, dialogue, context):
    owners_by_location = {}
    for fact in facts:
        actor_id = str(fact.get("actor_id") or "")
        for match in _POSSESSIVE_LOCATION_CUE.finditer(
            str(fact.get("statement") or "")
        ):
            if match.group("possessive").casefold() == "my":
                owners_by_location.setdefault(
                    match.group("location").casefold(), set()
                ).add(actor_id)
    unquoted = _ATTRIBUTED_QUOTATION.sub("", str(dialogue or ""))
    speaker_id = str(context.get("speaker_id") or "")
    listener_id = str(context.get("listener_id") or "")
    for match in _POSSESSIVE_LOCATION_CUE.finditer(unquoted):
        owners = owners_by_location.get(match.group("location").casefold(), set())
        if len(owners) != 1:
            continue
        expected_owner = next(iter(owners))
        claimed_owner = (
            speaker_id
            if match.group("possessive").casefold() == "my"
            else listener_id
        )
        if expected_owner and claimed_owner != expected_owner:
            return "preserve the recalled location owner and speaker perspective"
    return ""
```

- [x] **Step 4: Invoke ownership validation before time-only success**

In `_supported_recall_issue`, after uncertainty rejection and before the
`when` branch accepts a matching time, add:

```python
    ownership_issue = _possessive_location_issue(facts, dialogue, context)
    if ownership_issue:
        return ownership_issue
```

This ordering ensures a correct time cannot hide an incorrect location owner.

- [x] **Step 5: Run focused tests and verify GREEN**

Run the command from Step 2.

Expected: all parameter cases and the fallback test pass.

- [x] **Step 6: Run complete regression verification**

From `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests
py -3.12 -m py_compile backend/ai_sims_server.py
py -3.12 build_mod.py
```

From `core`:

```powershell
$env:PYTHONPATH='src'; py -3.12 -m pytest -q -p no:cacheprovider tests
```

From the repository root:

```powershell
py -3.12 -m ruff check core/src core/tests adapters/thesims4/src adapters/thesims4/tests adapters/godot/src adapters/godot/tests tests scripts/release.py scripts/test_release.py
git diff --check
```

Do not install the built artifact, restart processes, commit, or push.
