"""Smoke test: the recall benchmark runs end to end on a tiny store."""

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).with_name("bench_recall.py")


def test_bench_recall_smoke(tmp_path: Path) -> None:
    out = tmp_path / "report.json"
    subprocess.run(  # noqa: S603 - fixed argv, our own script
        [sys.executable, str(SCRIPT), "--sizes", "200", "--repeat", "1", "--json", str(out)],
        check=True,
        capture_output=True,
    )
    run = json.loads(out.read_text())["runs"][0]
    assert run["events"] == 200
    assert "sims.recall_event_rows[rare.hot]" in run["results"]
    assert "fts5.pair_rows[rare.hot]" in run["results"]
