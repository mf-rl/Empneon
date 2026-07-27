"""Provider- and game-independent recall evidence constraints."""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

TIME_ISSUE = (
    "answer with the supported recalled time without inventing another schedule"
)
LOCATION_ISSUE = "preserve the recalled location owner and speaker perspective"
RELATION_ISSUE = "preserve the recalled relation owner and speaker perspective"

_TIME_QUESTION = re.compile(
    r"\bwhen\b|\b(?:what|which)\s+(?:time|day|date)\b",
    re.IGNORECASE,
)
_LOCATION_QUESTION = re.compile(
    r"\bwhere\b|\b(?:what|which)\s+place\b",
    re.IGNORECASE,
)
_QUESTION_REQUEST = re.compile(r"\?|\b(?:tell|remind)\s+me\b", re.IGNORECASE)
_RECALL_REQUEST = re.compile(
    r"\b(?:remember|recall|did i say)\b",
    re.IGNORECASE,
)
_WH_REQUEST = re.compile(
    r"(?:^|[.!?]\s*)(?:what|when|where|who|which)\b",
    re.IGNORECASE,
)
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
_RELATION = re.compile(
    r"\b(?P<possessive>my|your)\s+"
    r"(?P<relation>sister|brother|sibling)\b",
    re.IGNORECASE,
)
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


def analyze_recall_query(text: str) -> RecallQuery:
    value = str(text or "")
    question = bool(_QUESTION_REQUEST.search(value))
    slots: set[str] = set()
    if question and _TIME_QUESTION.search(value):
        slots.add("time")
    if question and _LOCATION_QUESTION.search(value):
        slots.add("location")
    requested = frozenset(slots)
    explicit = question and bool(
        requested or _RECALL_REQUEST.search(value) or _WH_REQUEST.search(value)
    )
    return RecallQuery(explicit, requested)


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


def fact_supports_query(
    fact: Mapping[str, object],
    query: RecallQuery,
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


def _relation_issue(
    facts: Sequence[Mapping[str, object]],
    response: str,
    speaker_id: str,
    listener_id: str,
) -> str:
    owners_by_relation: dict[str, set[str]] = {}
    for fact in facts:
        actor_id = str(fact.get("actor_id") or "")
        for match in _RELATION.finditer(str(fact.get("statement") or "")):
            if match.group("possessive").casefold() == "my":
                owners_by_relation.setdefault(
                    match.group("relation").casefold(), set()
                ).add(actor_id)
    unquoted = _ATTRIBUTED_QUOTATION.sub("", response)
    for match in _RELATION.finditer(unquoted):
        owners = owners_by_relation.get(
            match.group("relation").casefold(), set()
        )
        if len(owners) != 1:
            continue
        claimed_owner = (
            speaker_id
            if match.group("possessive").casefold() == "my"
            else listener_id
        )
        if claimed_owner != next(iter(owners)):
            return RELATION_ISSUE
    return ""


def validate_recall_response(
    query: RecallQuery,
    facts: Sequence[Mapping[str, object]],
    response: str,
    speaker_id: str,
    listener_id: str,
) -> str:
    value = str(response or "")
    return (
        _time_issue(query, facts, value)
        or _location_issue(
            facts,
            value,
            str(speaker_id),
            str(listener_id),
        )
        or _relation_issue(
            facts,
            value,
            str(speaker_id),
            str(listener_id),
        )
    )
