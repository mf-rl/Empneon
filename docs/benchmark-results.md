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
