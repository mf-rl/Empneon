import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import capture_live_resources as capture  # noqa: E402

SAMPLE = {
    "system": {"cpu_percent": 10.0, "ram_mb": 100.0},
    "gpu": {"memory_used_mb": 200.0, "utilization_percent": 30.0},
    "processes": {
        "sims": {"cpu_percent": 4.0, "ram_mb": 40.0},
        "backend": {"cpu_percent": 1.0, "ram_mb": 10.0},
        "provider": {"cpu_percent": 5.0, "ram_mb": 50.0},
    },
}


class FakeProcess:
    def __init__(
        self,
        pid: int,
        name: str,
        cmdline: list[str],
        *,
        cpu_percent: float = 0.0,
        rss: int = 0,
    ) -> None:
        self.pid = pid
        self._name = name
        self._cmdline = cmdline
        self._cpu_percent = cpu_percent
        self._rss = rss

    def name(self) -> str:
        return self._name

    def cmdline(self) -> list[str]:
        return self._cmdline

    def cpu_percent(self) -> float:
        return self._cpu_percent

    def memory_info(self) -> SimpleNamespace:
        return SimpleNamespace(rss=self._rss)


class FakePresentMon:
    def __init__(self, returncode: int | None = None) -> None:
        self.stopped = False
        self.returncode = returncode

    def stop(self) -> None:
        self.stopped = True

    def poll(self) -> int | None:
        return self.returncode


class StubbornPresentMon:
    def __init__(self) -> None:
        self.waits = 0
        self.terminated = False
        self.killed = False

    def wait(self, timeout: int) -> int:
        self.waits += 1
        if self.waits < 3:
            raise capture.subprocess.TimeoutExpired("presentmon", timeout)
        return 0

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True


def test_parse_presentmon_keeps_positive_displayed_frames() -> None:
    csv_path = Path(__file__).with_name(".presentmon-test.csv")
    try:
        csv_path.write_text(
            "Application,msBetweenDisplayChange,Dropped\n"
            "TS4_x64.exe,10.0,0\n"
            "TS4_x64.exe,0,0\n"
            "TS4_x64.exe,30.0,0\n",
            encoding="utf-8",
        )

        assert capture.parse_presentmon(csv_path) == [10.0, 30.0]
    finally:
        csv_path.unlink(missing_ok=True)


def test_parse_presentmon_limits_frames_to_request_window() -> None:
    csv_path = Path(__file__).with_name(".presentmon-window-test.csv")
    try:
        csv_path.write_text(
            "Application,TimeInSeconds,msBetweenDisplayChange\n"
            "TS4_x64.exe,1.0,10.0\n"
            "TS4_x64.exe,2.0,20.0\n"
            "TS4_x64.exe,3.0,30.0\n",
            encoding="utf-8",
        )

        assert capture.parse_presentmon(
            csv_path,
            start_seconds=1.5,
            end_seconds=2.5,
        ) == [20.0]
    finally:
        csv_path.unlink(missing_ok=True)


def test_summarize_retains_raw_peaks_and_percentiles() -> None:
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


def test_discover_processes_finds_sims_backend_and_provider(monkeypatch) -> None:
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


def test_discover_processes_requires_backend_pid_when_ambiguous(monkeypatch) -> None:
    monkeypatch.setattr(
        capture.psutil,
        "process_iter",
        lambda _attrs: iter(
            [
                FakeProcess(1, "TS4_x64.exe", []),
                FakeProcess(2, "python.exe", ["python", "ai_sims_server.py"]),
                FakeProcess(3, "python.exe", ["python", "ai_sims_server.py"]),
                FakeProcess(4, "llama-server.exe", []),
            ]
        ),
    )

    with pytest.raises(RuntimeError, match="multiple backend processes"):
        capture.discover_processes()


def test_discover_processes_ignores_python_launcher(monkeypatch) -> None:
    monkeypatch.setattr(
        capture.psutil,
        "process_iter",
        lambda _attrs: iter(
            [
                FakeProcess(1, "TS4_x64.exe", []),
                FakeProcess(2, "py.exe", ["py", "backend/ai_sims_server.py"]),
                FakeProcess(3, "python.exe", ["python", "backend/ai_sims_server.py"]),
                FakeProcess(4, "llama-server.exe", []),
            ]
        ),
    )

    assert capture.discover_processes()["backend"].pid == 3


def test_resource_sample_reports_process_rss_in_mebibytes(monkeypatch) -> None:
    processes = {
        "sims": FakeProcess(1, "TS4_x64.exe", [], cpu_percent=4.0, rss=40 * 1024**2),
        "backend": FakeProcess(2, "python.exe", [], cpu_percent=1.0, rss=10 * 1024**2),
        "provider": FakeProcess(
            3, "llama-server.exe", [], cpu_percent=5.0, rss=50 * 1024**2
        ),
    }
    monkeypatch.setattr(capture.psutil, "cpu_percent", lambda: 10.0)
    monkeypatch.setattr(
        capture.psutil,
        "virtual_memory",
        lambda: SimpleNamespace(used=100 * 1024**2),
    )
    monkeypatch.setattr(
        capture,
        "gpu_sample",
        lambda: {"memory_used_mb": 200.0, "utilization_percent": 30.0},
    )

    result = capture.resource_sample(processes)

    assert result == SAMPLE


def test_gpu_sample_parses_memory_and_utilization(monkeypatch) -> None:
    monkeypatch.setattr(
        capture.subprocess,
        "check_output",
        lambda *_args, **_kwargs: "4416, 30\n",
    )

    assert capture.gpu_sample() == {
        "memory_used_mb": 4416.0,
        "utilization_percent": 30.0,
    }


def test_tool_versions_records_presentmon_and_nvidia_driver(monkeypatch) -> None:
    def fake_run(command, **_kwargs):
        if command[0] == "presentmon.exe":
            return SimpleNamespace(
                stdout="",
                stderr="PresentMon 2.5.1\nCapture Target Options:\n",
            )
        if command[0] == "nvidia-smi":
            return SimpleNamespace(stdout="576.88\n", stderr="")
        raise AssertionError(command)

    monkeypatch.setattr(capture.shutil, "which", lambda _name: "presentmon.exe")
    monkeypatch.setattr(capture.subprocess, "run", fake_run)

    result = capture.tool_versions()

    assert result["presentmon"] == "PresentMon 2.5.1"
    assert result["nvidia_driver"] == "576.88"
    assert result["psutil"]


def test_stop_presentmon_kills_process_when_graceful_cleanup_times_out(
    monkeypatch,
) -> None:
    process = StubbornPresentMon()
    monkeypatch.setattr(capture.shutil, "which", lambda _name: "presentmon.exe")
    monkeypatch.setattr(
        capture.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            capture.subprocess.TimeoutExpired("presentmon", 10)
        ),
    )

    capture.stop_presentmon(process, "test-session")

    assert process.terminated is True
    assert process.killed is True
    assert process.waits == 3


def test_capture_detects_one_submitted_started_completed_player_request(monkeypatch) -> None:
    queue = iter(
        [
            {
                "running": [],
                "waiting": [],
                "recent": [],
            },
            {
                "running": [],
                "waiting": [],
                "recent": [],
            },
            {
                "running": [{"request_id": "request-a"}],
                "waiting": [],
                "recent": [
                    {
                        "request_id": "request-a",
                        "actor_id": "sim-a",
                        "event_type": "player_conversation",
                        "state": "submitted",
                    },
                    {
                        "request_id": "request-a",
                        "actor_id": "sim-a",
                        "event_type": "player_conversation",
                        "state": "started",
                    },
                ],
            },
            {
                "running": [],
                "waiting": [],
                "recent": [
                    {
                        "request_id": "request-a",
                        "actor_id": "sim-a",
                        "event_type": "player_conversation",
                        "state": "completed",
                    }
                ],
            },
        ]
    )

    def fake_request(_method, url, **_kwargs):
        if url.endswith("/health"):
            return {"status": "ok", "active_agents": [], "active_agent_limit": 1}
        if url.endswith("/diagnostics/cognition-queue"):
            return next(queue)
        raise AssertionError(url)

    presentmon = FakePresentMon()
    monkeypatch.setattr(capture, "request_json", fake_request)
    monkeypatch.setattr(capture, "resource_sample", lambda _processes: SAMPLE)
    monkeypatch.setattr(
        capture,
        "parse_presentmon",
        lambda _path, **_kwargs: [10.0, 20.0],
    )
    monkeypatch.setattr(
        capture,
        "start_presentmon",
        lambda *_args: (presentmon, "test-session"),
    )
    monkeypatch.setattr(
        capture,
        "stop_presentmon",
        lambda process, _session: process.stop(),
    )
    monkeypatch.setattr(capture, "discover_processes", lambda _pid=None: {
        "sims": FakeProcess(1, "TS4_x64.exe", []),
        "backend": FakeProcess(2, "python.exe", []),
        "provider": FakeProcess(3, "llama-server.exe", []),
    })
    monkeypatch.setattr(capture.time, "sleep", lambda _seconds: None)

    result = capture.capture("http://example.test", Path("frames.csv"), timeout=1)

    assert result["status"] == "passed"
    assert result["initial_health"] == {
        "status": "ok",
        "provider": None,
        "model": None,
        "active_agent_limit": 1,
    }
    assert result["request"]["request_id"] == "request-a"
    assert "actor_ids" not in result["request"]
    assert len(result["samples"]) == 3
    assert result["summary"]["sample_count"] == 2
    assert presentmon.stopped is True


def test_capture_rejects_a_second_player_request(monkeypatch) -> None:
    queue = iter(
        [
            {"running": [], "waiting": [], "recent": []},
            {
                "running": [{"request_id": "request-a"}],
                "waiting": [],
                "recent": [
                    {
                        "request_id": "request-a",
                        "event_type": "player_conversation",
                        "state": "submitted",
                    }
                ],
            },
            {
                "running": [{"request_id": "request-a"}],
                "waiting": [{"request_id": "request-b"}],
                "recent": [
                    {
                        "request_id": "request-a",
                        "event_type": "player_conversation",
                        "state": "started",
                    },
                    {
                        "request_id": "request-b",
                        "event_type": "player_conversation",
                        "state": "submitted",
                    },
                ],
            },
        ]
    )

    def fake_request(_method, url, **_kwargs):
        if url.endswith("/health"):
            return {"status": "ok", "active_agents": [], "active_agent_limit": 1}
        return next(queue)

    presentmon = FakePresentMon()
    monkeypatch.setattr(capture, "request_json", fake_request)
    monkeypatch.setattr(capture, "resource_sample", lambda _processes: SAMPLE)
    monkeypatch.setattr(capture, "discover_processes", lambda _pid=None: {
        "sims": FakeProcess(1, "TS4_x64.exe", []),
        "backend": FakeProcess(2, "python.exe", []),
        "provider": FakeProcess(3, "llama-server.exe", []),
    })
    monkeypatch.setattr(
        capture,
        "start_presentmon",
        lambda *_args: (presentmon, "test-session"),
    )
    monkeypatch.setattr(
        capture,
        "stop_presentmon",
        lambda process, _session: process.stop(),
    )
    monkeypatch.setattr(capture.time, "sleep", lambda _seconds: None)

    with pytest.raises(RuntimeError, match="multiple Empneon Social requests observed"):
        capture.capture("http://example.test", Path("frames.csv"), timeout=1)

    assert presentmon.stopped is True


def test_capture_classifies_completion_timeout(monkeypatch) -> None:
    queue_calls = 0

    def fake_request(_method, url, **_kwargs):
        nonlocal queue_calls
        if url.endswith("/health"):
            return {"status": "ok", "active_agents": [], "active_agent_limit": 1}
        queue_calls += 1
        if queue_calls == 1:
            return {"running": [], "waiting": [], "recent": []}
        return {
            "running": [{"request_id": "request-a"}],
            "waiting": [],
            "recent": [
                {
                    "request_id": "request-a",
                    "event_type": "player_conversation",
                    "state": "started",
                }
            ],
        }

    presentmon = FakePresentMon()
    clock = iter([0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
    monkeypatch.setattr(capture, "request_json", fake_request)
    monkeypatch.setattr(capture, "resource_sample", lambda _processes: SAMPLE)
    monkeypatch.setattr(capture, "discover_processes", lambda _pid=None: {
        "sims": FakeProcess(1, "TS4_x64.exe", []),
        "backend": FakeProcess(2, "python.exe", []),
        "provider": FakeProcess(3, "llama-server.exe", []),
    })
    monkeypatch.setattr(
        capture,
        "start_presentmon",
        lambda *_args: (presentmon, "test-session"),
    )
    monkeypatch.setattr(
        capture,
        "stop_presentmon",
        lambda process, _session: process.stop(),
    )
    monkeypatch.setattr(capture.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(capture.time, "sleep", lambda _seconds: None)

    with pytest.raises(TimeoutError, match="Empneon Social did not complete"):
        capture.capture("http://example.test", Path("frames.csv"), timeout=0.5)

    assert presentmon.stopped is True


def test_capture_rejects_active_backend_before_start(monkeypatch) -> None:
    monkeypatch.setattr(
        capture,
        "request_json",
        lambda *_args, **_kwargs: {
            "status": "ok",
            "active_agents": [{"sim_id": "busy"}],
            "active_agent_limit": 1,
        },
    )

    with pytest.raises(RuntimeError, match="backend must be inactive before capture"):
        capture.capture("http://example.test", Path("frames.csv"))


def test_capture_rejects_presentmon_startup_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        capture,
        "request_json",
        lambda *_args, **_kwargs: {
            "status": "ok",
            "active_agents": [],
            "active_agent_limit": 1,
        },
    )
    monkeypatch.setattr(capture, "discover_processes", lambda _pid=None: {
        "sims": FakeProcess(1, "TS4_x64.exe", []),
        "backend": FakeProcess(2, "python.exe", []),
        "provider": FakeProcess(3, "llama-server.exe", []),
    })
    presentmon = FakePresentMon(returncode=1)
    monkeypatch.setattr(
        capture,
        "start_presentmon",
        lambda *_args: (presentmon, "test-session"),
    )
    monkeypatch.setattr(
        capture,
        "stop_presentmon",
        lambda process, _session: process.stop(),
    )
    monkeypatch.setattr(capture.time, "sleep", lambda _seconds: None)

    with pytest.raises(RuntimeError, match="PresentMon exited during startup"):
        capture.capture("http://example.test", Path("frames.csv"), timeout=0)

    assert presentmon.stopped is True


def test_capture_classifies_start_timeout(monkeypatch) -> None:
    monkeypatch.setattr(
        capture,
        "request_json",
        lambda *_args, **_kwargs: {
            "status": "ok",
            "active_agents": [],
            "active_agent_limit": 1,
        },
    )
    monkeypatch.setattr(capture, "discover_processes", lambda _pid=None: {
        "sims": FakeProcess(1, "TS4_x64.exe", []),
        "backend": FakeProcess(2, "python.exe", []),
        "provider": FakeProcess(3, "llama-server.exe", []),
    })
    presentmon = FakePresentMon()
    monkeypatch.setattr(
        capture,
        "start_presentmon",
        lambda *_args: (presentmon, "test-session"),
    )
    monkeypatch.setattr(
        capture,
        "stop_presentmon",
        lambda process, _session: process.stop(),
    )

    with pytest.raises(TimeoutError, match="no Empneon Social began before timeout"):
        capture.capture("http://example.test", Path("frames.csv"), timeout=0)

    assert presentmon.stopped is True


def test_main_writes_report_and_refuses_overwrite(monkeypatch) -> None:
    output = Path(__file__).with_name(".live-capture-cli-test.json")
    csv_path = output.with_suffix(".presentmon.csv")
    try:
        monkeypatch.setattr(
            capture,
            "capture",
            lambda *_args, **_kwargs: {"status": "passed", "samples": [SAMPLE]},
        )
        monkeypatch.setattr(
            capture,
            "tool_versions",
            lambda: {
                "presentmon": "PresentMon 2.5.1",
                "nvidia_driver": "576.88",
                "psutil": "7.0.0",
            },
        )

        assert capture.main(["--output", str(output)]) == 0
        report = json.loads(output.read_text(encoding="utf-8"))
        assert report["status"] == "passed"
        assert report["tools"]["presentmon"] == "PresentMon 2.5.1"
        assert capture.main(["--output", str(output)]) == 1
    finally:
        output.unlink(missing_ok=True)
        csv_path.unlink(missing_ok=True)


def test_main_preserves_partial_presentmon_evidence_on_failure(monkeypatch) -> None:
    output = Path(__file__).with_name(".live-capture-failure-test.json")
    csv_path = output.with_suffix(".presentmon.csv")
    failed_output = output.with_name(f"{output.stem}.failed.json")
    failed_csv = output.with_name(f"{output.stem}.failed.presentmon.csv")

    def fail_after_csv(_base_url, path, **_kwargs):
        path.write_text("partial frame evidence", encoding="utf-8")
        raise RuntimeError("capture failed")

    try:
        monkeypatch.setattr(capture, "capture", fail_after_csv)

        assert capture.main(["--output", str(output)]) == 1
        assert not output.exists()
        assert not csv_path.exists()
        assert failed_csv.read_text(encoding="utf-8") == "partial frame evidence"
        failure = json.loads(failed_output.read_text(encoding="utf-8"))
        assert failure["error"] == {
            "type": "RuntimeError",
            "message": "capture failed",
        }
    finally:
        for path in (output, csv_path, failed_output, failed_csv):
            path.unlink(missing_ok=True)


def test_main_preserves_evidence_when_metadata_collection_fails(monkeypatch) -> None:
    output = Path(__file__).with_name(".live-capture-metadata-test.json")
    csv_path = output.with_suffix(".presentmon.csv")
    failed_output = output.with_name(f"{output.stem}.failed.json")
    failed_csv = output.with_name(f"{output.stem}.failed.presentmon.csv")

    def successful_capture(_base_url, path, **_kwargs):
        path.write_text("frame evidence", encoding="utf-8")
        return {"status": "passed", "samples": [SAMPLE]}

    try:
        monkeypatch.setattr(capture, "capture", successful_capture)
        monkeypatch.setattr(
            capture,
            "tool_versions",
            lambda: (_ for _ in ()).throw(RuntimeError("version probe failed")),
        )

        assert capture.main(["--output", str(output)]) == 1
        assert not output.exists()
        assert not csv_path.exists()
        assert failed_csv.read_text(encoding="utf-8") == "frame evidence"
        failure = json.loads(failed_output.read_text(encoding="utf-8"))
        assert failure["error"]["message"] == "version probe failed"
    finally:
        for path in (output, csv_path, failed_output, failed_csv):
            path.unlink(missing_ok=True)


def test_main_refuses_existing_failure_artifacts(monkeypatch) -> None:
    output = Path(__file__).with_name(".live-capture-collision-test.json")
    failed_output = output.with_name(f"{output.stem}.failed.json")
    called = False

    def unexpected_capture(*_args, **_kwargs):
        nonlocal called
        called = True
        return {}

    try:
        failed_output.write_text("existing evidence", encoding="utf-8")
        monkeypatch.setattr(capture, "capture", unexpected_capture)

        assert capture.main(["--output", str(output)]) == 1
        assert called is False
        assert failed_output.read_text(encoding="utf-8") == "existing evidence"
    finally:
        output.unlink(missing_ok=True)
        failed_output.unlink(missing_ok=True)
