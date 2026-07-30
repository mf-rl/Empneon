# Sims 4 Conservative Resource Budget Proposal

**Status:** Accepted and documented; no runtime or configuration changes

## Goal

Translate the published baseline-hardware capture matrix into the smallest defensible resource
budget proposal. Preserve the current single-request operating limit and distinguish measured
whole-machine pressure from Core's incremental per-request reservations.

## Evidence

The proposal uses the four July 29 captures on the documented Ryzen 7 4800H, RTX 2060 Laptop
6 GB, and 16 GB RAM baseline with The Sims 4, the Empneon backend, and LM Studio running.
The three thinking-disabled requests are the primary comparison matrix; the earlier request is
supporting evidence because it used a different model-thinking configuration.

| Measurement | Observed range |
|---|---:|
| Request duration, thinking disabled | 18,422-25,328 ms |
| Peak system RAM used, thinking disabled | 14,899.73-14,985.24 MiB |
| Request-window system RAM range | 137-269 MiB |
| Peak provider RAM, thinking disabled | 2,787.71-2,982.83 MiB |
| Request-window provider RAM range | 34-70 MiB |
| Peak total GPU memory, thinking disabled | 4,678-4,693 MiB |
| Request-window total GPU-memory range | 54-59 MiB |
| Sims frame-time p95, thinking disabled | 55.71-65.35 ms |

These values are observed peaks and within-window ranges, not capacity limits. System RAM and GPU
measurements include the game, loaded model, and other active workloads. Windows WDDM did not
provide provider-attributable VRAM.

## Proposed Baseline Budget

Keep the current values as conservative candidates:

| Setting | Candidate | Interpretation |
|---|---:|---|
| `active_agent_limit` / concurrent requests | `1` | Only measured operating mode |
| Core `max_ram_mb` | `256` | Incremental request-reservation ceiling, not total process RAM |
| Core `max_vram_mb` | `0` | VRAM admission remains unenforced because route estimates are unattributed |
| Small-route RAM estimate | `64 MiB` | Existing estimate retained; not calibrated by whole-request process data |
| Large-route RAM estimate | `128 MiB` | Conservative headroom; not separately calibrated by this matrix |
| Small-route latency estimate | `30,000 ms` | Covers the observed thinking-disabled requests with limited margin |
| Large-route latency estimate | `90,000 ms` | Existing fallback estimate; not validated by this matrix |
| Small/large VRAM estimates | `0 MiB` | Means unknown and unenforced, not zero consumption |

Retain the existing `2,048`/`4,096` context-token and `120`/`300` completion-token estimates.
The captures do not isolate token limits as a resource-pressure cause, so changing them would not
be evidence-based.

## Rationale

The captures cannot calibrate an individual route estimate: a player request can run semantic
selection and dialogue generation in sequence, while the provider process retains a loaded model
throughout the window. One request's provider range also reached `70 MiB`, slightly above the
existing `64 MiB` small-route estimate. Retaining `64 MiB` and `128 MiB` avoids inventing a new
mapping from whole-process data; neither value should be described as measured. The `256 MiB` Core
ceiling admits one current route but does not imply that 256 MiB of free system memory is
sufficient.

Absolute pressure is the limiting evidence. The thinking-disabled matrix reached roughly
14.9 GiB used RAM on a 16 GiB machine, 4.69 GiB total GPU memory on a 6 GiB GPU, and frame-time
p95 above 55 ms. Those results do not support another concurrent request, a recommended hardware
profile, or tighter live admission thresholds.

The observed request durations fit below the existing 30-second small-route estimate, but the
25.33-second maximum leaves little evidence-based margin. Preserve the estimate rather than
reducing it. The 90-second large-route estimate remains an uncalibrated compatibility value.

## Safety Boundaries

- Do not change runtime budgets, route estimates, routing, token limits, or concurrency from this
  proposal.
- Do not interpret `vram_mb = 0` as measured zero use.
- Do not derive free-RAM or free-VRAM admission thresholds from four runs.
- Do not claim acceptable performance, broad hardware support, or scalability.
- Keep provider-free CLOD 1 fallback available when a configured route is not admitted or fails.

## Evidence Required for a Change

Collect more evidence only when a proposed change creates a specific gap:

- Before increasing concurrency, capture a controlled concurrent in-game run and define failure
  criteria for RAM exhaustion, GPU pressure, request latency, and frame time.
- Before enforcing VRAM admission, obtain provider-attributable GPU memory or a controlled
  loaded/unloaded provider delta that separates the game and provider.
- Before changing RAM estimates, repeat the same neutral and recall cases enough to characterize
  request-window variance.
- Before generalizing the budget, repeat captures for each supported hardware profile, materially
  different model size, or provider execution boundary.
- Before reducing latency estimates, measure repeated tail latency rather than relying on the
  current maximum.

## July 29 Completion Record

- The proposal was accepted and summarized in the project README, Sims adapter README, setup
  guide, artifact manifest, benchmark results, and roadmap.
- All four successful capture reports were re-read to verify their duration, RAM, GPU, and
  frame-time summaries.
- Fresh verification passed `225` Core tests, `306` Sims adapter tests, `4` Godot adapter tests,
  and `5` shared contract tests.
- `active_agent_limit`, Core budgets, route estimates, token limits, routing, and capture
  artifacts remained unchanged.

## Acceptance

This proposal is complete when the measured evidence, candidate values, limitations, and
change-triggering evidence are documented. Completion does not authorize applying the candidates
to runtime configuration.
