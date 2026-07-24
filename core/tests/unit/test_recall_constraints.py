import pytest

from empneon.core.memory.recall import (
    LOCATION_ISSUE,
    TIME_ISSUE,
    RecallQuery,
    TemporalValues,
    analyze_recall_query,
    fact_supports_query,
    temporal_values,
    validate_recall_response,
)


@pytest.mark.parametrize(
    ("message", "explicit", "slots"),
    [
        ("When is our date?", True, frozenset({"time"})),
        (
            "I remember our date. What time are we having it?",
            True,
            frozenset({"time"}),
        ),
        ("What day is the meeting?", True, frozenset({"time"})),
        ("What date did we choose?", True, frozenset({"time"})),
        ("Where are we meeting?", True, frozenset({"location"})),
        ("Do you remember roses?", True, frozenset()),
        ("What flowers do you prefer?", True, frozenset()),
        (
            "I wonder what this could be. Will you be my girlfriend?",
            False,
            frozenset(),
        ),
        ("I remember our date.", False, frozenset()),
        ("I am happy today.", False, frozenset()),
    ],
)
def test_analyze_recall_query_uses_shared_slots(
    message: str,
    explicit: bool,
    slots: frozenset[str],
) -> None:
    assert analyze_recall_query(message) == RecallQuery(explicit, slots)


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
    text: str,
    expected: TemporalValues,
) -> None:
    assert temporal_values(text) == expected


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
        ("Tonight at your place.", TIME_ISSUE),
        ("The first Saturday at 10 AM.", TIME_ISSUE),
        ("Tomorrow at 7pm.", TIME_ISSUE),
    ],
)
def test_validate_recall_response_requires_supported_specific_time(
    dialogue: str,
    expected_issue: str,
) -> None:
    query = analyze_recall_query("What time are we having our date?")

    assert (
        validate_recall_response(
            query, [DATE_FACT], dialogue, "karmine", "bernard"
        )
        == expected_issue
    )


def test_relative_only_time_requires_the_supported_relative() -> None:
    query = analyze_recall_query("When is our date?")
    fact = {"actor_id": "bernard", "statement": "Tomorrow."}

    assert validate_recall_response(
        query, [fact], "Tomorrow.", "karmine", "bernard"
    ) == ""
    assert validate_recall_response(
        query, [fact], "Tonight.", "karmine", "bernard"
    ) == TIME_ISSUE


@pytest.mark.parametrize(
    ("fact", "dialogue", "expected_issue"),
    [
        (DATE_FACT, "Tonight at 7pm, at your place.", ""),
        (DATE_FACT, "Tonight at 7pm, at my place.", LOCATION_ISSUE),
        (DATE_FACT, 'You told me: "Tonight, 7pm, at my place."', ""),
        (DATE_FACT, "Tonight at 7pm, at Bernard's place.", ""),
        (DATE_FACT, "Tonight at 7pm.", ""),
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
            LOCATION_ISSUE,
        ),
    ],
)
def test_validate_recall_response_preserves_attributed_location_owner(
    fact: dict[str, str],
    dialogue: str,
    expected_issue: str,
) -> None:
    query = analyze_recall_query("When is our date?")

    assert (
        validate_recall_response(
            query, [fact], dialogue, "karmine", "bernard"
        )
        == expected_issue
    )
