import json
from pathlib import Path

import pytest

from empneon.benchmarks.regression import main, run_regressions

FIXTURE = Path(__file__).parents[2] / "scenarios" / "clod1-regressions.json"


def test_canonical_regression_fixture_passes() -> None:
    report = run_regressions(json.loads(FIXTURE.read_text(encoding="utf-8")))

    assert report["passed"] is True
    assert (report["passed_cases"], report["failed_cases"]) == (1, 0)


def test_regression_report_exposes_expected_and_actual_mismatch() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["cases"][0]["expected"]["intent"] = "avoid"

    report = run_regressions(payload)

    assert report["passed"] is False
    assert report["results"][0]["mismatches"]["intent"] == {
        "expected": "avoid",
        "actual": "acknowledge",
    }


def test_cli_returns_failure_for_regression(tmp_path: Path) -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["cases"][0]["expected"]["target_id"] = "someone-else"
    fixture = tmp_path / "failing.json"
    fixture.write_text(json.dumps(payload), encoding="utf-8")

    assert main([str(fixture)]) == 1

def test_runner_rejects_invalid_fixture() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["cases"][0]["request"]["event"]["id"] = None

    with pytest.raises(ValueError, match="event id"):
        run_regressions(payload)
