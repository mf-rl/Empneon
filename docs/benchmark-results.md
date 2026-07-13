# SocietyBench Results

## Baseline hardware run: 2026-07-13

This preliminary Stage 3 run executed the deterministic 20-agent social-ring workload
while The Sims 4 remained foregrounded and unpaused on the baseline Ryzen 7 4800H,
RTX 2060 Laptop 6 GB, and 16 GB RAM system. LM Studio served
`gemma-4-e4b-it-uncensored` (7.5B, Q4_K_M). PresentMon captured displayed frame timing.

| Measurement | Result |
|---|---:|
| One-call-per-agent provider calls | 20 |
| Fixed-CLOD 1 decisions / provider calls | 20 / 0 |
| Prompt / completion tokens | 320 / 320 |
| Provider latency p50 / p95 | 18,821 / 33,701.65 ms |
| Peak system CPU | 76.5% |
| Peak system RAM used | 15,705.23 MiB |
| Peak GPU memory used | 5,918 MiB |
| Captured Sims frames | 3,216 |
| Sims frame time p50 / p95 | 87.37 / 229.27 ms |
| Peak Sims frame time | 932.06 ms |

This is evidence of severe baseline pressure, not acceptable-performance validation.
The run used short synthetic prompts and sequential calls; it did not compare alternative
models, context sizes, concurrency policies, or player-rated believability. Raw provider
and PresentMon evidence is published with its configuration, checksums, and limitations in
the [Stage 3 artifact manifest](../output/README.md).

## Blinded believability run: 2026-07-13

The deterministic social-ring scenario produced 20 paired candidates from the fixed CLOD 1
resolver and `gemma-4-e4b-it-uncensored`, with option order randomized using seed `20260713`.
The evaluator saw the event, actors, and A/B candidates but not the separate strategy key.

| Measurement | Result |
|---|---:|
| Evaluated pairs | 20 |
| One-call-per-agent wins | 19 (95%) |
| Fixed-CLOD 1 wins | 1 (5%) |
| Ties | 0 |
| Deeper-reasoning net preference | +0.90 |

The evaluator favored concrete nods or greetings over the abstract `acknowledge` intent.
Fixed CLOD 1 won when the model introduced an unsupported threat assessment into a neutral
social event. This is preliminary evidence from one assistant evaluator and synthetic,
minimal contexts—not a player study. Candidate styles were recognizable, and several model
responses violated the requested plain two-to-six-word format with numbering or emoji. The
[blind packet](../output/stage3-believability-blind-20260713.json),
[answer key](../output/stage3-believability-key-20260713.json), and
[scored result](../output/stage3-believability-result-20260713.json) are published with the
other Stage 3 artifacts.

## Stage 5 comparison collection: 2026-07-13

SocietyBench now exposes a validated comparison record for every request, pairing the
provider-free fixed-CLOD 1 decision with the one-call provider decision while retaining the
request and strategy labels. Missing strategies, incomplete result sets, and decisions for
the wrong agent are rejected. The blinded evaluator now consumes these records directly.

The initial collection is the existing 20-pair social-ring run above. Reusing it avoids
presenting another execution of the same workload as independent evidence. These records
support the value estimate below; collection alone makes no claim about player-visible
benefit or an adaptive scheduler.

## Stage 5 preliminary value estimate: 2026-07-13

The score now reports `(deeper-reasoning wins - cheap-reasoning wins) / evaluated pairs`.
It ranges from `-1` when every comparison favors cheap reasoning to `+1` when every
comparison favors deeper reasoning. The 19-to-1 blind result produces `+0.90`.

This signed preference is a reproducible player-visible value proxy, not measured player
utility. It captures contextual fit, social plausibility, and specificity under the published
rubric, but it comes from one synthetic evaluator and one model run.

## Stage 5 archetype decision gate: 2026-07-13

Archetype approximation is not justified by the published evidence and was not implemented.
The hardware run shows severe pressure, but it compares only one-call-per-agent with fixed
CLOD 1. It does not measure an archetype or pooled-policy path, resource savings attributable
to pooling, identity or contradiction regressions, believability loss, or promotion criteria.

The `+0.90` deeper-reasoning preference is evidence that decision quality can be visible, not
evidence that agents can safely share an approximation. Reconsideration requires a controlled
SocietyBench arm showing lower cost or latency while meeting predefined identity-continuity,
contradiction, and believability thresholds.

## Stage 5 adaptive replay against Stage 3: 2026-07-13

The first adaptive policy was replayed over the published 20-sample social-ring evidence. The
comparison fixed the minimum preference-retention threshold at 90% before scoring. With global
deeper-reasoning value `0.90` and uniform Stage 3 urgency `0.50`, every selection score was
`0.45`, below the policy threshold `0.50`; all requests therefore selected CLOD 1.

| Measurement | Result |
|---|---:|
| One-call baseline provider calls / preference | 20 / 95% |
| Fixed-CLOD 1 provider calls / preference | 0 / 5% |
| Adaptive provider calls / reduction | 0 / 100% |
| Adaptive preference | 5% |
| Preference retention versus one-call | 5.26% |
| Required preference retention | 90% |
| Consistency re-evaluated | No |
| Stage 5 exit gate | Failed |

The result exposes a cost-quality failure, not a scheduler win. Uniform urgency gives this
policy no basis for mixed routing: it can select all provider cognition or all deterministic
cognition, but cannot preserve expensive reasoning where it matters. The replay used existing
synthetic decisions and single-evaluator ratings; it did not perform another provider or
in-game hardware run. See the
[comparison artifact](../output/stage5-adaptive-comparison-20260713.json).

## Stage 5 differentiated workload design: 2026-07-13

The remediation workload contains 20 deterministic agent requests whose routing inputs are
fixed before generation or evaluation. Event semantics are divided into 8 low-value routine
events, 6 medium-value social events, and 6 high-value conflict or disclosure events. Each
request declares urgency, consequence, novelty, and social complexity. Expected value is the
unweighted mean of the three value features, and the selection score remains urgency times
expected value.

| Declared tier | Cases | Urgency | Expected value | Selection score | Planned route |
|---|---:|---:|---:|---:|---|
| Low | 8 | 0.25 | 0.20 | 0.05 | CLOD 1 |
| Medium | 6 | 0.75 | 0.70 | 0.525 | Provider |
| High | 6 | 0.95 | 0.90 | 0.855 | Provider |

The existing threshold is `0.50`, so the design plans 8 cheap and 12 provider selections.
These are workload properties only. No provider cost, consistency, or blinded-believability
result is claimed until the next comparison is executed and scored.

## Stage 5 differentiated adaptive validation: 2026-07-13

The 20-case differentiated workload was generated with the same local model as Stage 3.
Candidate order was seeded and blinded; the assistant evaluator fixed all preferences before
the separate key was revealed. Thresholds were fixed in that key before scoring: at least
90% preference retention, 100% identity continuity, 0% contradictions, and a positive
provider-call reduction.

| Measurement | Result |
|---|---:|
| Adaptive provider calls / reduction | 12 / 40% |
| One-call / adaptive selected-call tokens | 913 / 545 |
| Token reduction | 40.31% |
| One-call / adaptive selected-call latency sum | 26,324 / 14,450 ms |
| Summed latency reduction | 45.11% |
| One-call-or-tie / adaptive preference | 90% / 85% |
| Preference retention / minimum | 94.44% / 90% |
| Identity continuity / minimum | 100% / 100% |
| Contradiction rate / maximum | 0% / 0% |
| Stage 5 exit gate | Passed |

Stage 5 is complete. This is a single synthetic run with one assistant evaluator. The
consistency arm observes one target claim per agent, so it is a routing integrity check, not
a longitudinal contradiction test. The Sims was not running; no frame timing, system RAM,
CPU, or VRAM was measured. Adaptive token and latency totals select the 12 routed calls from
the paired 20-call evidence; they are not a separately timed adaptive execution. Model
formatting violations also remained visible in several candidates. The packet, key, and
scored result are published in the
[artifact manifest](../output/README.md).
