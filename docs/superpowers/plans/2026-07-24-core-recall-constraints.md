# Core Recall Constraints Implementation Plan

**Status:** Completed; checklist retained as the original execution record

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every recall stage use the same question slots and deterministic evidence constraints so repeated questions cannot lose or contradict authoritative time and location facts.

**Architecture:** Add one pure Core module for recall analysis, fact-slot matching, temporal normalization, and response validation. Replace the Sims adapter's duplicated time/location classification with that shared API while preserving its event retrieval, semantic selection, retry, and attributed fallback boundaries.

**Tech Stack:** Python 3.11+, standard-library `dataclasses` and `re`, pytest, SQLite-backed Empneon episodic memory.

## Global Constraints

- Keep Core independent of games, providers, models, prompts, and databases.
- Preserve stored event and attributed-fact schemas.
- Preserve non-question remembrance and ordinary non-recall dialogue.
- Prefer authoritative supporting facts over factless generated recall answers.
- Require the most specific supported time and reject conflicting schedule values.
- Preserve correct, named, quoted, omitted, and symmetric location behavior.
- Do not commit or push until the user explicitly requests it.

---

### Task 1: Add the Core recall-constraint API

**Files:**
- Create: `core/src/empneon/core/memory/recall.py`
- Create: `core/tests/unit/test_recall_constraints.py`

**Interfaces:**
- Produces: `RecallQuery(explicit: bool, requested_slots: frozenset[str])`
- Produces: `TemporalValues(clocks: frozenset[int], relatives: frozenset[str], weekdays: frozenset[str])`
- Produces: `analyze_recall_query(text: str) -> RecallQuery`
- Produces: `temporal_values(text: str) -> TemporalValues`
- Produces: `fact_supports_query(fact: Mapping[str, object], query: RecallQuery) -> bool`
- Produces: `validate_recall_response(query: RecallQuery, facts: Sequence[Mapping[str, object]], response: str, speaker_id: str, listener_id: str) -> str`

- [ ] **Step 1: Write failing Core question-analysis and normalization tests**

Create `core/tests/unit/test_recall_constraints.py`:

```python
import pytest

from empneon.core.memory.recall import (
    RecallQuery,
    TemporalValues,
    analyze_recall_query,
    fact_supports_query,
    temporal_values,
    validate_recall_response,
)


@pytest.mark.parametrize(
    ("message", "slots"),
    [
        ("When is our date?", frozenset({"time"})),
        (
            "I remember our date. What time are we having it?",
            frozenset({"time"}),
        ),
        ("What day is the meeting?", frozenset({"time"})),
        ("What date did we choose?", frozenset({"time"})),
        ("Where are we meeting?", frozenset({"location"})),
        ("I remember our date.", frozenset()),
        ("I am happy today.", frozenset()),
    ],
)
def test_analyze_recall_query_uses_shared_slots(
    message: str, slots: frozenset[str]
) -> None:
    query = analyze_recall_query(message)

    assert query.requested_slots == slots
    assert query.explicit is bool(slots)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Tonight at 7pm.",
            TemporalValues(frozenset({1140}), frozenset({"tonight"}), frozenset()),
        ),
        (
            "At 7:00 p.m.",
            TemporalValues(frozenset({1140}), frozenset(), frozenset()),
        ),
        (
            "Seven o'clock PM on Saturday.",
            TemporalValues(
                frozenset({1140}), frozenset(), frozenset({"saturday"})
            ),
        ),
        (
            "Tomorrow morning.",
            TemporalValues(frozenset(), frozenset({"tomorrow"}), frozenset()),
        ),
    ],
)
def test_temporal_values_normalizes_equivalent_schedule_text(
    text: str, expected: TemporalValues
) -> None:
    assert temporal_values(text) == expected
```

- [ ] **Step 2: Write failing Core fact-matching and validation tests**

Append:

```python
DATE_FACT = {
    "actor_id": "bernard",
    "statement": "Tonight, 7pm, at my place.",
}


def test_temporal_fact_supports_what_time_without_lexical_overlap() -> None:
    query = analyze_recall_query(
        "I remember our date. What time are we having it?"
    )

    assert fact_supports_query(DATE_FACT, query) is True


@pytest.mark.parametrize(
    ("dialogue", "expected_issue"),
    [
        ("Tonight at 7pm, at your place.", ""),
        ("At 7:00 PM.", ""),
        (
            "Tonight at your place.",
            "answer with the supported recalled time without inventing another schedule",
        ),
        (
            "The first Saturday at 10 AM.",
            "answer with the supported recalled time without inventing another schedule",
        ),
        (
            "Tomorrow at 7pm.",
            "answer with the supported recalled time without inventing another schedule",
        ),
    ],
)
def test_validate_recall_response_requires_supported_specific_time(
    dialogue: str, expected_issue: str
) -> None:
    query = analyze_recall_query("What time are we having our date?")

    assert (
        validate_recall_response(
            query, [DATE_FACT], dialogue, "karmine", "bernard"
        )
        == expected_issue
    )


@pytest.mark.parametrize(
    ("fact", "dialogue", "expected_issue"),
    [
        (DATE_FACT, "Tonight at 7pm, at your place.", ""),
        (
            DATE_FACT,
            "Tonight at 7pm, at my place.",
            "preserve the recalled location owner and speaker perspective",
        ),
        (
            DATE_FACT,
            'You told me: "Tonight, 7pm, at my place."',
            "",
        ),
        (
            {
                "actor_id": "karmine",
                "statement": "Tonight, 7pm, at my place.",
            },
            "Tonight at 7pm, at my place.",
            "",
        ),
        (
            {
                "actor_id": "karmine",
                "statement": "Tonight, 7pm, at my place.",
            },
            "Tonight at 7pm, at your place.",
            "preserve the recalled location owner and speaker perspective",
        ),
    ],
)
def test_validate_recall_response_preserves_attributed_location_owner(
    fact: dict[str, str], dialogue: str, expected_issue: str
) -> None:
    query = analyze_recall_query("When is our date?")

    assert (
        validate_recall_response(
            query, [fact], dialogue, "karmine", "bernard"
        )
        == expected_issue
    )
```

- [ ] **Step 3: Run Core tests and verify RED**

Run from `core`:

```powershell
$env:PYTHONPATH='src'; py -3.12 -m pytest -q -p no:cacheprovider tests/unit/test_recall_constraints.py
```

Expected: collection fails because `empneon.core.memory.recall` does not exist.

- [ ] **Step 4: Implement the pure Core module**

Create `core/src/empneon/core/memory/recall.py` with these constants and immutable values:

```python
"""Provider- and game-independent recall evidence constraints."""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

TIME_ISSUE = (
    "answer with the supported recalled time without inventing another schedule"
)
LOCATION_ISSUE = (
    "preserve the recalled location owner and speaker perspective"
)

_TIME_QUESTION = re.compile(
    r"\bwhen\b|\b(?:what|which)\s+(?:time|day|date)\b",
    re.IGNORECASE,
)
_LOCATION_QUESTION = re.compile(
    r"\bwhere\b|\b(?:what|which)\s+place\b",
    re.IGNORECASE,
)
_QUESTION_REQUEST = re.compile(r"\?|\b(?:tell|remind)\s+me\b", re.IGNORECASE)
_NUMERIC_CLOCK = re.compile(
    r"\b(?P<hour>1[0-2]|0?[1-9])"
    r"(?::(?P<minute>[0-5]\d))?\s*"
    r"(?P<period>a\.?m\.?|p\.?m\.?)(?!\w)",
    re.IGNORECASE,
)
_WORD_CLOCK = re.compile(
    r"\b(?P<hour>one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve)\s+o['’]?clock\s*"
    r"(?P<period>a\.?m\.?|p\.?m\.?)(?!\w)",
    re.IGNORECASE,
)
_RELATIVE = re.compile(
    r"\b(today|tonight|tomorrow|yesterday)\b",
    re.IGNORECASE,
)
_WEEKDAY = re.compile(
    r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.IGNORECASE,
)
_LOCATION = re.compile(
    r"\b(?P<possessive>my|your)\s+"
    r"(?P<location>place|home|house)\b",
    re.IGNORECASE,
)
_LOCATION_NOUN = re.compile(r"\b(place|home|house)\b", re.IGNORECASE)
_ATTRIBUTED_QUOTATION = re.compile(
    r"(?:\byou told me|\bi remember saying|\b[^:\n]{1,50}\bsaid)"
    r'\s*:\s*(?:"[^"]*"|“[^”]*”)',
    re.IGNORECASE,
)
_WORD_HOURS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}


@dataclass(frozen=True)
class RecallQuery:
    explicit: bool
    requested_slots: frozenset[str]


@dataclass(frozen=True)
class TemporalValues:
    clocks: frozenset[int]
    relatives: frozenset[str]
    weekdays: frozenset[str]
```

Implement query and temporal analysis:

```python
def analyze_recall_query(text: str) -> RecallQuery:
    value = str(text or "")
    question = bool(_QUESTION_REQUEST.search(value))
    slots = set()
    if question and _TIME_QUESTION.search(value):
        slots.add("time")
    if question and _LOCATION_QUESTION.search(value):
        slots.add("location")
    requested = frozenset(slots)
    return RecallQuery(bool(requested), requested)


def _minutes(hour: int, minute: int, period: str) -> int:
    normalized = hour % 12
    if period.casefold().startswith("p"):
        normalized += 12
    return normalized * 60 + minute


def temporal_values(text: str) -> TemporalValues:
    value = str(text or "")
    clocks = {
        _minutes(
            int(match.group("hour")),
            int(match.group("minute") or 0),
            match.group("period"),
        )
        for match in _NUMERIC_CLOCK.finditer(value)
    }
    clocks.update(
        _minutes(
            _WORD_HOURS[match.group("hour").casefold()],
            0,
            match.group("period"),
        )
        for match in _WORD_CLOCK.finditer(value)
    )
    return TemporalValues(
        frozenset(clocks),
        frozenset(
            match.group(1).casefold() for match in _RELATIVE.finditer(value)
        ),
        frozenset(
            match.group(1).casefold() for match in _WEEKDAY.finditer(value)
        ),
    )
```

Implement fact matching and validation:

```python
def fact_supports_query(
    fact: Mapping[str, object], query: RecallQuery
) -> bool:
    statement = str(fact.get("statement") or "")
    temporal = temporal_values(statement)
    return bool(
        (
            "time" in query.requested_slots
            and (temporal.clocks or temporal.relatives or temporal.weekdays)
        )
        or (
            "location" in query.requested_slots
            and _LOCATION_NOUN.search(statement)
        )
    )


def _time_issue(
    query: RecallQuery,
    facts: Sequence[Mapping[str, object]],
    response: str,
) -> str:
    if "time" not in query.requested_slots:
        return ""
    values = [
        temporal_values(str(fact.get("statement") or "")) for fact in facts
    ]
    clocks = frozenset(item for value in values for item in value.clocks)
    relatives = frozenset(item for value in values for item in value.relatives)
    weekdays = frozenset(item for value in values for item in value.weekdays)
    if not (clocks or relatives or weekdays):
        return ""
    answer = temporal_values(response)
    if clocks and not clocks.intersection(answer.clocks):
        return TIME_ISSUE
    if not clocks and not (
        relatives.intersection(answer.relatives)
        or weekdays.intersection(answer.weekdays)
    ):
        return TIME_ISSUE
    if (
        answer.clocks.difference(clocks)
        or answer.relatives.difference(relatives)
        or answer.weekdays.difference(weekdays)
    ):
        return TIME_ISSUE
    return ""


def _location_issue(
    facts: Sequence[Mapping[str, object]],
    response: str,
    speaker_id: str,
    listener_id: str,
) -> str:
    owners_by_location: dict[str, set[str]] = {}
    for fact in facts:
        actor_id = str(fact.get("actor_id") or "")
        for match in _LOCATION.finditer(str(fact.get("statement") or "")):
            if match.group("possessive").casefold() == "my":
                owners_by_location.setdefault(
                    match.group("location").casefold(), set()
                ).add(actor_id)
    unquoted = _ATTRIBUTED_QUOTATION.sub("", response)
    for match in _LOCATION.finditer(unquoted):
        owners = owners_by_location.get(
            match.group("location").casefold(), set()
        )
        if len(owners) != 1:
            continue
        claimed_owner = (
            speaker_id
            if match.group("possessive").casefold() == "my"
            else listener_id
        )
        if claimed_owner != next(iter(owners)):
            return LOCATION_ISSUE
    return ""


def validate_recall_response(
    query: RecallQuery,
    facts: Sequence[Mapping[str, object]],
    response: str,
    speaker_id: str,
    listener_id: str,
) -> str:
    return _time_issue(query, facts, str(response or "")) or _location_issue(
        facts,
        str(response or ""),
        str(speaker_id),
        str(listener_id),
    )
```

- [ ] **Step 5: Run Core tests and verify GREEN**

Run the command from Step 3.

Expected: all Core recall-constraint tests pass.

- [ ] **Step 6: Run Core static checks**

Run from `core`:

```powershell
py -3.12 -m ruff check src/empneon/core/memory/recall.py tests/unit/test_recall_constraints.py
py -3.12 -m mypy src/empneon/core/memory/recall.py
```

Expected: both commands exit zero.

---

### Task 2: Integrate shared constraints into Sims retrieval and grounding

**Files:**
- Modify: `adapters/thesims4/backend/empneon_state.py:550-760`
- Modify: `adapters/thesims4/backend/ai_sims_server.py:1981-2160`
- Test: `adapters/thesims4/tests/test_sims4_backend.py:680-970`
- Test: `adapters/thesims4/tests/test_sims4_backend.py:1437-1600`

**Interfaces:**
- Consumes all public interfaces from Task 1.
- Preserves: `recall_candidates(...)`, `recalled_memories(...)`, `_supported_recall_facts(...)`, `_supported_recall_issue(...)`, and `HermesRuntime.dialogue(...)`.
- Removes duplicated adapter-only temporal and possessive validation after callers use Core.

- [ ] **Step 1: Add a failing retrieval regression for `what time`**

In the existing date-recall retrieval test, record three newer factless recall
events after the authoritative `Tonight, 7pm, at my place` event, then add:

```python
what_time_recalled = ai_sims_server.empneon_state.recalled_memories(
    conn,
    "karmine",
    "bernard",
    "I'm happy you remember. What time are we having our date?",
)
```

Assert:

```python
assert [item["message"] for item in what_time_recalled] == [
    "Tonight, 7pm, at my place."
]
assert what_time_recalled[0]["facts"] == expected_fact
```

The newer events must use recall questions and `facts: []`, matching the live
failure.

- [ ] **Step 2: Add failing dialogue regressions for completeness and invention**

Beside `_supported_date_recall_context`, add:

```python
@pytest.mark.parametrize(
    ("dialogue", "expected_issue"),
    [
        (
            "That sounds good! Tonight at your place.",
            "answer with the supported recalled time without inventing another schedule",
        ),
        (
            "The first Saturday at 10 AM.",
            "answer with the supported recalled time without inventing another schedule",
        ),
        ("Tonight at 7pm, at your place.", ""),
        ("At 7:00 PM.", ""),
    ],
)
def test_what_time_recall_requires_authoritative_specific_time(
    dialogue, expected_issue
) -> None:
    payload, context = _supported_date_recall_context()
    payload["message"] = (
        "I'm happy you remember. What time are we having our date?"
    )

    assert (
        ai_sims_server._supported_recall_issue(
            payload, {"dialogue": dialogue}, context
        )
        == expected_issue
    )


def test_invented_time_uses_attributed_fallback(monkeypatch) -> None:
    invented = _social_provider_response(
        "Oh, of course! It's the first Saturday at 10 AM.",
        "romance",
    )
    calls = []
    monkeypatch.setattr(
        ai_sims_server,
        "llm_chat",
        lambda *_args, **_kwargs: calls.append(1) or json.dumps(invented),
    )
    monkeypatch.setattr(ai_sims_server, "RESPONSE_REJECTION_ENABLED", False)
    payload, context = _supported_date_recall_context()
    payload["message"] = (
        "I'm happy you remember. What time are we having our date?"
    )

    response = ai_sims_server.HERMES.dialogue(payload, context)

    assert len(calls) == 2
    assert response["dialogue"] == (
        'You told me: "Tonight, 7pm, at my place."'
    )
```

- [ ] **Step 3: Run focused Sims tests and verify RED**

Run from `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "what_time or invented_time"
```

Expected: retrieval returns recent factless replies, partial/invented times
return no issue, and the invented provider response is accepted after one
call.

- [ ] **Step 4: Use Core analysis in deterministic retrieval**

In `empneon_state.py`, import:

```python
from empneon.core.memory.recall import (
    analyze_recall_query,
    fact_supports_query,
)
```

Make `_is_recall_question` delegate:

```python
def _is_recall_question(text: str) -> bool:
    return analyze_recall_query(text).explicit
```

In both `recall_candidates` and `recalled_memories`, analyze once:

```python
recall_query = analyze_recall_query(query)
```

For every authoritative fact list, derive:

```python
supporting_facts = [
    fact for fact in facts if fact_supports_query(fact, recall_query)
]
```

In `recall_candidates`, rank `bool(supporting_facts)` before lexical overlap
and recency.

In `recalled_memories`:

- use `recall_query.explicit`;
- treat `bool(supporting_facts)` as `answers_requested`;
- retain supporting facts even without lexical overlap;
- if any match answers a requested slot, discard factless matches before
  sorting;
- preserve the existing lexical path when no requested slot has supporting
  evidence.

Keep the three-result cap and fact deduplication unchanged.

- [ ] **Step 5: Use Core analysis and validation in dialogue grounding**

In `ai_sims_server.py`, import:

```python
from empneon.core.memory.recall import (
    analyze_recall_query,
    fact_supports_query,
    validate_recall_response,
)
```

Replace `_supported_recall_facts` classification with:

```python
def _supported_recall_facts(message, context):
    query = analyze_recall_query(str(message or ""))
    if not query.explicit:
        return []
    facts = [
        {
            "actor_id": str(fact.get("actor_id") or ""),
            "statement": str(fact.get("statement") or "").strip(),
        }
        for memory in context.get("recalled_memories") or []
        for fact in memory.get("facts") or []
        if isinstance(fact, dict)
        and str(fact.get("statement") or "").strip()
    ]
    supporting = [
        fact for fact in facts if fact_supports_query(fact, query)
    ]
    if supporting or query.requested_slots:
        return supporting
    question_terms = set(_dialogue_words(message, context))
    return [
        fact
        for fact in facts
        if question_terms
        & set(_dialogue_words(fact["statement"], context))
    ]
```

In `_supported_recall_issue`, after uncertainty rejection, call:

```python
    issue = validate_recall_response(
        analyze_recall_query(message),
        facts,
        dialogue,
        str(context.get("speaker_id") or ""),
        str(context.get("listener_id") or ""),
    )
    if issue:
        return issue
```

Remove the adapter-only `_recall_question_cue`, `_time_fact_values`,
`_possessive_location_issue`, and their regex constants after all callers use
Core. Preserve generic lexical grounding for recall questions without
structured requested slots.

- [ ] **Step 6: Run focused Sims tests and verify GREEN**

Run the command from Step 3 plus all existing supported-recall tests:

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "what_time or invented_time or supported_recall"
```

Expected: all selected tests pass.

- [ ] **Step 7: Run complete verification**

From `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests
py -3.12 -m py_compile backend/ai_sims_server.py backend/empneon_state.py
py -3.12 build_mod.py
```

From `core`:

```powershell
$env:PYTHONPATH='src'; py -3.12 -m pytest -q -p no:cacheprovider tests
py -3.12 -m mypy src tests
```

From the repository root:

```powershell
py -3.12 -m ruff check core/src core/tests adapters/thesims4/src adapters/thesims4/tests adapters/godot/src adapters/godot/tests tests scripts/release.py scripts/test_release.py
git diff --check
```

Do not install artifacts, restart processes, commit, or push.
