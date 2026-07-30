"""Capture live resource evidence for one player-triggered Empneon Social."""

import argparse
import csv
import json
import math
import shutil
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil  # type: ignore[import-untyped]
from simulate_http_interactions import request_json

PROCESS_NAMES = {"sims": "ts4_x64.exe", "provider": "llama-server.exe"}


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        raise ValueError("values are required")
    ordered = sorted(float(value) for value in values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def parse_presentmon(
    path: Path,
    *,
    start_seconds: float | None = None,
    end_seconds: float | None = None,
) -> list[float]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = csv.DictReader(handle)
        if "msBetweenDisplayChange" not in (rows.fieldnames or ()):
            raise ValueError("PresentMon output lacks msBetweenDisplayChange")
        if (start_seconds is not None or end_seconds is not None) and "TimeInSeconds" not in (
            rows.fieldnames or ()
        ):
            raise ValueError("PresentMon output lacks TimeInSeconds")
        values = []
        for row in rows:
            frame_time = float(row["msBetweenDisplayChange"] or 0)
            captured_at = float(row.get("TimeInSeconds") or 0)
            if frame_time <= 0:
                continue
            if start_seconds is not None and captured_at < start_seconds:
                continue
            if end_seconds is not None and captured_at > end_seconds:
                continue
            values.append(frame_time)
    if not values:
        raise ValueError("PresentMon produced no positive displayed-frame samples")
    return values


def summarize(samples: list[dict[str, Any]], frame_times: list[float]) -> dict[str, object]:
    if not samples:
        raise ValueError("resource samples are required")

    def peak(path: tuple[str, ...]) -> float:
        values = []
        for sample in samples:
            value: Any = sample
            for key in path:
                value = value[key]
            values.append(float(value))
        return max(values)

    return {
        "sample_count": len(samples),
        "system": {
            "peak_cpu_percent": peak(("system", "cpu_percent")),
            "peak_ram_mb": peak(("system", "ram_mb")),
        },
        "gpu": {
            "peak_memory_used_mb": peak(("gpu", "memory_used_mb")),
            "peak_utilization_percent": peak(("gpu", "utilization_percent")),
        },
        "processes": {
            role: {
                "peak_cpu_percent": peak(("processes", role, "cpu_percent")),
                "peak_ram_mb": peak(("processes", role, "ram_mb")),
            }
            for role in ("sims", "backend", "provider")
        },
        "frames": {
            "sample_count": len(frame_times),
            "p50_ms": percentile(frame_times, 0.50),
            "p95_ms": percentile(frame_times, 0.95),
            "peak_ms": max(frame_times),
        },
    }


def discover_processes(backend_pid: int | None = None) -> dict[str, psutil.Process]:
    candidates: dict[str, list[psutil.Process]] = {
        "sims": [],
        "backend": [],
        "provider": [],
    }
    for process in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = process.name().casefold()
            command = " ".join(process.cmdline()).casefold()
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
        for role, expected in PROCESS_NAMES.items():
            if name == expected:
                candidates[role].append(process)
        if name.startswith("python") and "ai_sims_server.py" in command and (
            backend_pid is None or process.pid == backend_pid
        ):
            candidates["backend"].append(process)

    result = {}
    for role, matches in candidates.items():
        if not matches:
            raise RuntimeError(f"{role} process is not running")
        if len(matches) > 1:
            raise RuntimeError(f"multiple {role} processes found")
        result[role] = matches[0]
    return result


def gpu_sample() -> dict[str, float]:
    output = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=memory.used,utilization.gpu",
            "--format=csv,noheader,nounits",
        ],
        text=True,
        timeout=10,
    )
    fields = [field.strip() for field in output.splitlines()[0].split(",")]
    if len(fields) != 2:
        raise ValueError("nvidia-smi returned an unexpected GPU row")
    values = [float(field) for field in fields]
    if any(not math.isfinite(value) or value < 0 for value in values):
        raise ValueError("nvidia-smi returned invalid GPU values")
    return {
        "memory_used_mb": values[0],
        "utilization_percent": values[1],
    }


def tool_versions() -> dict[str, str]:
    presentmon = shutil.which("presentmon")
    if presentmon is None:
        raise RuntimeError("PresentMon is not available")
    presentmon_result = subprocess.run(
        [presentmon, "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    driver_result = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=driver_version",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    presentmon_lines = (presentmon_result.stdout or presentmon_result.stderr).splitlines()
    driver_lines = (driver_result.stdout or driver_result.stderr).splitlines()
    presentmon_version = presentmon_lines[0].strip() if presentmon_lines else ""
    driver_version = driver_lines[0].strip() if driver_lines else ""
    if not presentmon_version or not driver_version:
        raise RuntimeError("telemetry tool version detection failed")
    return {
        "presentmon": presentmon_version,
        "nvidia_driver": driver_version,
        "psutil": str(psutil.__version__),
    }


def resource_sample(processes: dict[str, psutil.Process]) -> dict[str, object]:
    return {
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


def start_presentmon(
    sims_pid: int, csv_path: Path
) -> tuple[subprocess.Popen[str], str]:
    executable = shutil.which("presentmon")
    if executable is None:
        raise RuntimeError("PresentMon is not available")
    session = f"Empneon-{uuid.uuid4().hex}"
    process = subprocess.Popen(
        [
            executable,
            "--process_id",
            str(sims_pid),
            "--output_file",
            str(csv_path),
            "--v1_metrics",
            "--exclude_dropped",
            "--no_console_stats",
            "--session_name",
            session,
        ],
        text=True,
    )
    return process, session


def stop_presentmon(process: subprocess.Popen[str], session: str) -> None:
    executable = shutil.which("presentmon")
    if executable is not None:
        try:
            subprocess.run(
                [
                    executable,
                    "--session_name",
                    session,
                    "--terminate_existing_session",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            process.terminate()
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def capture(
    base_url: str,
    csv_path: Path,
    *,
    interval: float = 0.25,
    timeout: float = 180,
    backend_pid: int | None = None,
) -> dict[str, object]:
    base_url = base_url.rstrip("/")
    health_url = base_url + "/health"
    queue_url = base_url + "/diagnostics/cognition-queue"
    initial_health = request_json("GET", health_url, timeout=10)
    if initial_health.get("status") != "ok":
        raise RuntimeError("backend health check failed")
    if initial_health.get("active_agents"):
        raise RuntimeError("backend must be inactive before capture")
    if initial_health.get("active_agent_limit") != 1:
        raise RuntimeError("active_agent_limit must be 1")
    initial_queue = request_json("GET", queue_url, timeout=10)
    if initial_queue.get("running") or initial_queue.get("waiting"):
        raise RuntimeError("cognition queue must be idle before capture")
    baseline_ids = {
        str(item.get("request_id"))
        for item in initial_queue.get("recent") or []
        if item.get("request_id")
    }

    processes = discover_processes(backend_pid)
    psutil.cpu_percent()
    for process in processes.values():
        process.cpu_percent()

    presentmon, session = start_presentmon(processes["sims"].pid, csv_path)
    samples: list[dict[str, object]] = []
    started = time.monotonic()
    deadline = started + timeout
    request_started: float | None = None
    request_sample_index: int | None = None
    request_id = ""
    try:
        time.sleep(0.1)
        if presentmon.poll() is not None:
            raise RuntimeError(
                "PresentMon exited during startup; run capture from an elevated terminal"
            )
        print("ARMED: trigger one Empneon Social and wait for its reply.", flush=True)
        while time.monotonic() < deadline:
            queue = request_json("GET", queue_url, timeout=10)
            recent = queue.get("recent") or []
            new_player_ids = {
                str(item["request_id"])
                for item in recent
                if item.get("event_type") == "player_conversation"
                and item.get("request_id")
                and str(item["request_id"]) not in baseline_ids
            }
            if len(new_player_ids) > 1:
                raise RuntimeError("multiple Empneon Social requests observed")
            sample = resource_sample(processes)
            sample["elapsed_ms"] = round((time.monotonic() - started) * 1000, 3)
            samples.append(sample)
            if request_started is None:
                entry = next(
                    (
                        item
                        for item in recent
                        if item.get("event_type") == "player_conversation"
                        and item.get("state") in {"submitted", "started"}
                        and str(item.get("request_id") or "") not in baseline_ids
                    ),
                    None,
                )
                if entry is not None:
                    request_started = time.monotonic()
                    request_sample_index = len(samples) - 1
                    request_id = str(entry["request_id"])
            completed_entry = next(
                (
                    item
                    for item in recent
                    if request_id
                    and item.get("request_id") == request_id
                    and item.get("state") == "completed"
                ),
                None,
            )
            if request_started is not None and completed_entry is not None:
                completed = time.monotonic()
                break
            time.sleep(interval)
        else:
            if request_started is None:
                raise TimeoutError("no Empneon Social began before timeout")
            raise TimeoutError("Empneon Social did not complete before timeout")
    finally:
        stop_presentmon(presentmon, session)

    frame_times = parse_presentmon(
        csv_path,
        start_seconds=request_started - started,
        end_seconds=completed - started,
    )
    request_samples = samples[request_sample_index:]
    return {
        "status": "passed",
        "captured_at": datetime.now(UTC).isoformat(),
        "initial_health": {
            key: initial_health.get(key)
            for key in ("status", "provider", "model", "active_agent_limit")
        },
        "configuration": {
            "base_url": base_url.rstrip("/"),
            "sample_interval_seconds": interval,
            "timeout_seconds": timeout,
            "provider": initial_health.get("provider"),
            "model": initial_health.get("model"),
            "active_agent_limit": initial_health.get("active_agent_limit"),
        },
        "processes": {
            role: {"pid": process.pid, "name": process.name()}
            for role, process in processes.items()
        },
        "request": {
            "request_id": request_id,
            "started_ms": round((request_started - started) * 1000, 3),
            "completed_ms": round((completed - started) * 1000, 3),
            "duration_ms": round((completed - request_started) * 1000, 3),
        },
        "samples": samples,
        "summary": summarize(request_samples, frame_times),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--sample-interval", type=float, default=0.25)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--backend-pid", type=int)
    args = parser.parse_args(argv)

    if args.sample_interval <= 0 or args.timeout <= 0:
        print("sample interval and timeout must be positive", file=sys.stderr)
        return 1
    output = args.output or Path(
        "output/live-resource-capture-{}.json".format(
            datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        )
    )
    csv_path = output.with_suffix(".presentmon.csv")
    failed_output = output.with_name(f"{output.stem}.failed.json")
    failed_csv = output.with_name(f"{output.stem}.failed.presentmon.csv")
    temporary_output = output.with_suffix(output.suffix + ".tmp")
    if any(
        path.exists()
        for path in (output, csv_path, failed_output, failed_csv, temporary_output)
    ):
        print("refusing to overwrite existing evidence", file=sys.stderr)
        return 1
    output.parent.mkdir(parents=True, exist_ok=True)

    try:
        report = capture(
            args.base_url,
            csv_path,
            interval=args.sample_interval,
            timeout=args.timeout,
            backend_pid=args.backend_pid,
        )
        report["artifacts"] = {"presentmon_csv": str(csv_path)}
        report["tools"] = tool_versions()
        temporary_output.write_text(
            json.dumps(report, indent=2),
            encoding="utf-8",
        )
        temporary_output.replace(output)
    except Exception as exc:
        temporary_output.unlink(missing_ok=True)
        if csv_path.exists():
            csv_path.replace(failed_csv)
        failed_output.write_text(
            json.dumps(
                {
                    "status": "failed",
                    "error": {
                        "type": type(exc).__name__,
                        "message": str(exc),
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"capture failed: {exc}", file=sys.stderr)
        return 1

    print(f"Report: {output}")
    print(f"PresentMon: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
