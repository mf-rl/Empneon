# Sims 4 Live Resource Capture Design

**Status:** Complete; focused verification, one initial capture, and a three-request
thinking-disabled neutral/recall matrix passed

## Goal

Measure one normal player-triggered Empneon Social on the documented baseline machine while The
Sims 4, the Empneon backend, and LM Studio are running. Preserve raw samples and reproducible frame
timing so later routing calibration can use observed evidence rather than estimates.

## Scope

The capture covers one request from the backend's inactive state through an active agent and back
to inactivity. It records:

- system CPU and used RAM;
- CPU and resident RAM for The Sims 4, the Empneon backend, and LM Studio's `llama-server`;
- total NVIDIA GPU memory use and GPU utilization;
- displayed Sims frame timing from PresentMon;
- request start, completion, duration, configured provider/model, and active-agent limit.

It does not change runtime routing, infer safe budgets from one run, send a chat request, inspect
conversation content, retain a Sim identifier, or modify the Core database.

## Approach

Add one Windows-oriented script under `adapters/thesims4/scripts`. Reuse the adapter's existing
development dependency on `psutil`, Windows `nvidia-smi`, PresentMon, and the backend `/health`
endpoint. Add no dependency and do not alter the existing synthetic SocietyBench runner.

The script discovers exactly one `TS4_x64`, backend Python process, and `llama-server`. An explicit
PID option may resolve an ambiguous backend process; missing or ambiguous required processes fail
before capture. The script also verifies backend health, an idle cognition queue, NVIDIA
telemetry, and PresentMon before reporting `ARMED`.

## Capture Flow

1. Validate the output paths and refuse to overwrite existing evidence.
2. Discover the required processes and record their names and IDs.
3. Start PresentMon for the Sims process with a unique session and CSV output.
4. Poll `/diagnostics/cognition-queue` and resource sources every 250 milliseconds.
5. Print `ARMED`; the player then starts one normal Empneon Social.
6. Mark request start from a new player-conversation `submitted` or `started` queue record.
7. Mark completion from the matching durable `completed` queue record.
8. Stop PresentMon, parse its displayed positive frame-time samples, and write the JSON report.
9. Exit nonzero on preflight failure, timeout, missing samples, or incomplete request lifecycle.

Cleanup always terminates only the PresentMon process started by the capture. It never terminates
The Sims 4, LM Studio, or the Empneon backend.

## Evidence Format

The JSON report contains:

- capture configuration and timestamps;
- process identities and backend health metadata;
- every timestamped resource sample, with summaries limited to the request window;
- request start, completion, and elapsed time;
- per-source CPU/RAM peaks;
- system CPU/RAM peaks;
- GPU-memory and GPU-utilization peaks;
- Sims frame-time sample count, p50, p95, and peak;
- paths and tool versions needed to reproduce the run.

The PresentMon CSV remains the raw frame evidence beside the JSON report. Neither artifact is
committed automatically because timing data may contain machine-specific process information.

## Error Handling

- A non-empty backend at startup is rejected so the measured request boundary is unambiguous.
- A health or telemetry sample failure ends the run and writes no successful report.
- A timeout after arming reports whether no request began or whether an active request never
  completed.
- PresentMon startup or parsing failure makes the run fail rather than silently omitting frame
  timing.
- Partial raw files are retained with a failure suffix when they contain useful diagnostic
  evidence.

## Verification

Focused tests replace process discovery, HTTP health reads, telemetry commands, clocks, and
PresentMon with deterministic fakes. They verify:

- inactive-to-active-to-inactive lifecycle detection;
- refusal to start while an agent is already active;
- timeout classification;
- percentile and peak summaries;
- output overwrite protection;
- PresentMon cleanup after success and failure.

The live acceptance run must:

1. print `ARMED`;
2. capture one completed Empneon Social;
3. produce non-empty raw resource and frame samples;
4. preserve the game, backend, provider, and database state;
5. record enough configuration to repeat the command.

One successful run updates benchmark documentation as measured evidence but does not justify
changing resource budgets or increasing concurrency.
