# Sims 4 Live Resource Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this
> plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Complete and published; original checklist retained as the execution plan

**Goal:** Capture reproducible process, system, GPU, request-lifecycle, and Sims frame-time
measurements for one normal player-triggered Empneon Social.

**Architecture:** Add one Windows-only script beside the existing Sims diagnostic harnesses. It
uses the installed `psutil`, `nvidia-smi`, PresentMon, backend health, and the existing cognition
queue diagnostic. It detects one new player request through its durable submitted/started/completed
records and writes raw samples plus summaries without touching runtime routing or the database.

**Tech Stack:** Python 3.11+, standard library, existing `psutil>=7`, NVIDIA `nvidia-smi`,
PresentMon 2.x, pytest.

## Global Constraints

- Add no dependency and do not modify the existing synthetic SocietyBench runner.
- Measure exactly one normal player-triggered Empneon Social.
- Sample every `0.25` seconds by default.
- Refuse to overwrite evidence files.
- Never terminate The Sims 4, LM Studio, `llama-server`, or the Empneon backend.
- Do not inspect or persist conversation content.
- Do not modify resource budgets, routing, or concurrency from one run.
- Do not commit or push until the user explicitly requests it.

---

### Task 1: Resource and frame-summary primitives

**Files:**
- Create: `adapters/thesims4/scripts/capture_live_resources.py`
- Create: `adapters/thesims4/tests/test_live_resource_capture.py`

**Interfaces:**
- Produces: `percentile(values: list[float], quantile: float) -> float`
- Produces: `parse_presentmon(path: Path) -> list[float]`
- Produces: `summarize(samples: list[dict], frame_times: list[float]) -> dict`

- [ ] **Step 1: Write failing summary tests**

Insert the scripts directory into `sys.path` using the existing harness-test pattern, then add:

```python
def test_parse_presentmon_keeps_positive_displayed_frames(tmp_path):
    csv_path = tmp_path / "frames.csv"
    csv_path.write_text(
        "Application,msBetweenDisplayChange,Dropped\n"
        "TS4_x64.exe,10.0,0\n"
        "TS4_x64.exe,0,0\n"
        "TS4_x64.exe,30.0,0\n",
        encoding="utf-8",
    )

    assert capture.parse_presentmon(csv_path) == [10.0, 30.0]


def test_summarize_retains_raw_peaks_and_percentiles():
    samples = [
        {
            "system": {"cpu_percent": 10.0, "ram_mb": 100.0},
            "gpu": {"memory_used_mb": 200.0, "utilization_percent": 30.0},
            "processes": {
                "sims": {"cpu_percent": 4.0, "ram_mb": 40.0},
                "backend": {"cpu_percent": 1.0, "ram_mb": 10.0},
                "provider": {"cpu_percent": 5.0, "ram_mb": 50.0},
            },
        },
        {
            "system": {"cpu_percent": 20.0, "ram_mb": 110.0},
            "gpu": {"memory_used_mb": 220.0, "utilization_percent": 40.0},
            "processes": {
                "sims": {"cpu_percent": 8.0, "ram_mb": 45.0},
                "backend": {"cpu_percent": 2.0, "ram_mb": 11.0},
                "provider": {"cpu_percent": 9.0, "ram_mb": 55.0},
            },
        },
    ]

    result = capture.summarize(samples, [10.0, 20.0, 30.0])

    assert result["sample_count"] == 2
    assert result["system"]["peak_cpu_percent"] == 20.0
    assert result["processes"]["provider"]["peak_ram_mb"] == 55.0
    assert result["gpu"]["peak_memory_used_mb"] == 220.0
    assert result["frames"] == {
        "sample_count": 3,
        "p50_ms": 20.0,
        "p95_ms": 29.0,
        "peak_ms": 30.0,
    }
```

- [ ] **Step 2: Run the tests and verify RED**

Run from `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_live_resource_capture.py
```

Expected: collection fails because `capture_live_resources` does not exist.

- [ ] **Step 3: Implement the pure primitives**

Create the script with these imports and functions:

```python
import csv
from pathlib import Path


def percentile(values, quantile):
    if not values:
        raise ValueError("values are required")
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def parse_presentmon(path):
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        rows = csv.DictReader(handle)
        if "msBetweenDisplayChange" not in (rows.fieldnames or ()):
            raise ValueError("PresentMon output lacks msBetweenDisplayChange")
        values = [
            float(row["msBetweenDisplayChange"])
            for row in rows
            if float(row["msBetweenDisplayChange"] or 0) > 0
        ]
    if not values:
        raise ValueError("PresentMon produced no positive displayed-frame samples")
    return values
```

Implement `summarize` with direct `max` calls over the fixed `system`, `gpu`, and `processes`
fields. Do not add dataclasses or a generic metrics framework.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run the Step 2 command.

Expected: both tests pass.

---

### Task 2: Process discovery and request lifecycle

**Files:**
- Modify: `adapters/thesims4/scripts/capture_live_resources.py`
- Modify: `adapters/thesims4/tests/test_live_resource_capture.py`

**Interfaces:**
- Consumes: `summarize(...)` and `parse_presentmon(...)`
- Produces: `discover_processes(backend_pid: int | None = None) -> dict[str, psutil.Process]`
- Produces: `gpu_sample() -> dict[str, float]`
- Produces: `resource_sample(processes: dict[str, psutil.Process]) -> dict`
- Produces: `start_presentmon(sims_pid: int, csv_path: Path) ->
  tuple[subprocess.Popen[str], str]`
- Produces: `stop_presentmon(process: subprocess.Popen[str], session: str) -> None`
- Produces: `capture(base_url: str, csv_path: Path, *, interval: float = 0.25,
  timeout: float = 180, backend_pid: int | None = None) -> dict`

- [ ] **Step 1: Write failing process and lifecycle tests**

Use small fake processes exposing `pid`, `name()`, `cmdline()`, `cpu_percent()`, and
`memory_info().rss`. Monkeypatch `psutil.process_iter`, `request_json`, `resource_sample`,
`start_presentmon`, `stop_presentmon`, `parse_presentmon`, `time.monotonic`, and `time.sleep`.

Add assertions for:

```python
def test_discover_processes_finds_sims_backend_and_provider(monkeypatch):
    monkeypatch.setattr(
        capture.psutil,
        "process_iter",
        lambda _attrs: iter(
            [
                FakeProcess(1, "TS4_x64.exe", []),
                FakeProcess(2, "python.exe", ["python", "backend/ai_sims_server.py"]),
                FakeProcess(3, "llama-server.exe", []),
            ]
        ),
    )

    result = capture.discover_processes()

    assert {name: process.pid for name, process in result.items()} == {
        "sims": 1,
        "backend": 2,
        "provider": 3,
    }


def test_capture_detects_one_inactive_active_inactive_request(monkeypatch, tmp_path):
    health = iter(
        [
            {"status": "ok", "active_agents": [], "active_agent_limit": 1},
            {"status": "ok", "active_agents": [{"sim_id": "sim-a"}], "active_agent_limit": 1},
            {"status": "ok", "active_agents": [], "active_agent_limit": 1},
        ]
    )
    monkeypatch.setattr(capture, "request_json", lambda *_args, **_kwargs: next(health))
    monkeypatch.setattr(capture, "resource_sample", lambda _processes: SAMPLE)
    monkeypatch.setattr(capture, "parse_presentmon", lambda _path: [10.0, 20.0])
    monkeypatch.setattr(
        capture,
        "start_presentmon",
        lambda *_args: (FakePresentMon(), "test-session"),
    )
    monkeypatch.setattr(capture, "stop_presentmon", lambda process, _session: process.stop())
    monkeypatch.setattr(capture, "discover_processes", lambda _pid=None: PROCESSES)
    monkeypatch.setattr(capture.time, "sleep", lambda _seconds: None)

    result = capture.capture("http://example.test", tmp_path / "frames.csv")

    assert result["status"] == "passed"
    assert result["request"]["actor_ids"] == ["sim-a"]
    assert len(result["samples"]) == 2
```

Also add:

- startup health containing an active agent raises
  `RuntimeError("backend must be inactive before capture")`;
- no observed active agent raises `TimeoutError("no Empneon Social began before timeout")`;
- an agent that never returns inactive raises
  `TimeoutError("Empneon Social did not complete before timeout")`;
- multiple backend candidates require `backend_pid`;
- `resource_sample` reports RSS in MiB and calls each process's primed `cpu_percent()`;
- `gpu_sample` parses the two numeric `nvidia-smi` columns.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_live_resource_capture.py
```

Expected: failures report the missing discovery, sampling, lifecycle, and PresentMon functions.

- [ ] **Step 3: Implement process discovery and sampling**

Use `psutil.process_iter(["pid", "name", "cmdline"])`. Match names case-insensitively:

```python
PROCESS_NAMES = {"sims": "ts4_x64.exe", "provider": "llama-server.exe"}
```

The backend candidate is a Python process whose command line contains `ai_sims_server.py`. If
`backend_pid` is supplied, use only that PID and verify its command line. Require exactly one
candidate for every role.

Prime `psutil.cpu_percent()` and each process's `cpu_percent()` once before the loop. Store
timestamps relative to capture start:

```python
{
    "elapsed_ms": round((time.monotonic() - capture_started) * 1000, 3),
    "system": {
        "cpu_percent": psutil.cpu_percent(),
        "ram_mb": psutil.virtual_memory().used / 1024**2,
    },
    "gpu": gpu_sample(),
    "processes": {
        role: {
            "cpu_percent": process.cpu_percent(),
            "ram_mb": process.memory_info().rss / 1024**2,
        }
        for role, process in processes.items()
    },
}
```

Run `nvidia-smi` with:

```text
--query-gpu=memory.used,utilization.gpu
--format=csv,noheader,nounits
```

Require exactly two finite, nonnegative values from the first GPU row.

- [ ] **Step 4: Implement PresentMon lifecycle**

`start_presentmon` creates a unique session name and runs:

```text
presentmon
--process_id <TS4 PID>
--output_file <CSV path>
--v1_metrics
--exclude_dropped
--no_console_stats
--session_name <unique session>
```

`stop_presentmon` invokes the same executable with
`--session_name <unique session> --terminate_existing_session`, waits up to ten seconds for the
capture process, and terminates only that PresentMon process if it does not exit.

Wrap sampling in `try/finally` so `stop_presentmon` runs exactly once after every successful
`start_presentmon`.

- [ ] **Step 5: Implement lifecycle detection**

Before `ARMED`, GET `/health`, require:

```python
health.get("status") == "ok"
not health.get("active_agents")
health.get("active_agent_limit") == 1
```

Also GET `/diagnostics/cognition-queue`, require empty `running` and `waiting` lists, and retain its
existing request IDs as the baseline. Print
`ARMED: trigger one Empneon Social and wait for its reply.` Start sampling immediately. Mark the
first new player-conversation `submitted` or `started` record as request start and stop on the
matching `completed` record. Retain the request UUID for diagnostic correlation but do not persist
its actor ID. Use `time.monotonic()` for both the global timeout and observed elapsed duration.
Preserve all raw samples while limiting peak and percentile summaries to the observed request
window.

Return the initial health metadata, process IDs/names, request timestamps, raw samples, and
`summarize(...)`. Do not include prompts, replies, Sim IDs, Sim names, or database contents.

- [ ] **Step 6: Run focused tests and verify GREEN**

Run the Step 2 command.

Expected: all live-capture unit tests pass.

---

### Task 3: CLI, failure evidence, and operator documentation

**Files:**
- Modify: `adapters/thesims4/scripts/capture_live_resources.py`
- Modify: `adapters/thesims4/tests/test_live_resource_capture.py`
- Modify: `adapters/thesims4/docs/setup.md`

**Interfaces:**
- Consumes: `capture(...)`
- Produces: `main(argv: list[str] | None = None) -> int`
- Produces: `output/live-resource-capture-<UTC>.json`
- Produces: `output/live-resource-capture-<UTC>.presentmon.csv`

- [ ] **Step 1: Write failing CLI tests**

Add tests that call `main([...])` with a monkeypatched `capture`:

```python
def test_main_writes_report_and_refuses_overwrite(monkeypatch, tmp_path):
    output = tmp_path / "capture.json"
    monkeypatch.setattr(
        capture,
        "capture",
        lambda *_args, **_kwargs: {"status": "passed", "samples": [SAMPLE]},
    )

    assert capture.main(["--output", str(output)]) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "passed"
    assert capture.main(["--output", str(output)]) == 1
```

Add a failure test where `capture` raises after creating the CSV. Assert that the CLI returns `1`,
renames the CSV to `<stem>.failed.presentmon.csv`, writes `<stem>.failed.json` with the exception
type/message, and leaves no successful JSON.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_live_resource_capture.py
```

Expected: failures report that `main` and failure-artifact handling are missing.

- [ ] **Step 3: Implement the minimal CLI**

Use `argparse` options:

```text
--base-url       default http://127.0.0.1:8765
--output         optional JSON path
--sample-interval default 0.25
--timeout        default 180
--backend-pid    optional integer
```

When `--output` is omitted, generate
`output/live-resource-capture-<UTC YYYYMMDDTHHMMSSZ>.json`. Derive the CSV by replacing `.json`
with `.presentmon.csv`. Validate `sample_interval > 0`, `timeout > 0`, and non-existing JSON/CSV
paths before starting any external process.

Write JSON with `indent=2`. Return `0` only for a completed report. On error, print the concise
reason, preserve partial evidence with `.failed` names, and return `1`.

- [ ] **Step 4: Document the exact live command**

Add a `Live resource capture` section to `adapters/thesims4/docs/setup.md`:

```powershell
cd .\adapters\thesims4
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 .\scripts\capture_live_resources.py
```

State that The Sims 4, the backend, LM Studio, `nvidia-smi`, and PresentMon must already be
running/available; the backend must be idle; the player starts exactly one Empneon Social after
`ARMED`; raw artifacts are not automatically committed; and one run must not change budgets or
concurrency.

- [ ] **Step 5: Run focused and package verification**

From `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_live_resource_capture.py
py -3.12 -m ruff check scripts/capture_live_resources.py tests/test_live_resource_capture.py
py -3.12 -m mypy scripts/capture_live_resources.py
py -3.12 -m py_compile scripts/capture_live_resources.py
```

Expected: every command exits `0`.

---

### Task 4: Live evidence run and documentation

**Files:**
- Generated, untracked: `adapters/thesims4/output/live-resource-capture-*.json`
- Generated, untracked: `adapters/thesims4/output/live-resource-capture-*.presentmon.csv`
- Modify after a passing run: `adapters/thesims4/docs/benchmark-results.md`
- Modify after a passing run: `adapters/thesims4/output/README.md`
- Modify after a passing run: `docs/roadmap.md`

**Interfaces:**
- Consumes: Task 3 CLI and one player-triggered Empneon Social
- Produces: one passing raw evidence pair and a documented baseline result

- [ ] **Step 1: Confirm the live preconditions**

Verify read-only:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8765/health' | ConvertTo-Json -Depth 5
Get-Process TS4_x64,python,llama-server
nvidia-smi --query-gpu=name,memory.total,memory.used,utilization.gpu --format=csv,noheader,nounits
presentmon --help
```

Expected: backend `status` is `ok`, `active_agent_limit` is `1`, `active_agents` is empty, all
three processes exist, and both telemetry executables respond.

- [ ] **Step 2: Start the capture**

Run from `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 .\scripts\capture_live_resources.py
```

Wait for `ARMED`.

- [ ] **Step 3: Trigger exactly one normal Empneon Social**

In The Sims 4, select another Sim, start **Empneon Social**, submit a representative message, and
wait until the reply is delivered and **Waiting for response** ends. Do not start another Empneon
interaction during the capture.

- [ ] **Step 4: Validate the artifacts**

Confirm the CLI exits `0`. Inspect the JSON and CSV read-only. Require:

- request start and completion timestamps;
- at least two resource samples;
- positive process/system/GPU values;
- at least one positive displayed frame-time sample;
- frame p50, p95, and peak;
- no prompt, dialogue, Sim name, or database content.

- [ ] **Step 5: Record measured evidence without tuning**

Add a dated section to `benchmark-results.md` containing the machine, game/provider/model
configuration, request duration, process/system/GPU peaks, and frame p50/p95/peak. Add artifact
names, checksums, reproduction command, and limitations to `output/README.md`.

In `docs/roadmap.md`, mark the single-request baseline capture as measured but leave safe-budget
definition and routing calibration open. State explicitly that one request is insufficient to
change concurrency or claim acceptable performance.

- [ ] **Step 6: Run documentation and diff checks**

Run from the repository root:

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors; source, tests, docs, spec, and plan are uncommitted; generated
evidence remains untracked until the user decides whether it is safe and useful to publish.
