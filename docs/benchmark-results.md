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

The evaluator favored concrete nods or greetings over the abstract `acknowledge` intent.
Fixed CLOD 1 won when the model introduced an unsupported threat assessment into a neutral
social event. This is preliminary evidence from one assistant evaluator and synthetic,
minimal contexts—not a player study. Candidate styles were recognizable, and several model
responses violated the requested plain two-to-six-word format with numbering or emoji. The
[blind packet](../output/stage3-believability-blind-20260713.json),
[answer key](../output/stage3-believability-key-20260713.json), and
[scored result](../output/stage3-believability-result-20260713.json) are published with the
other Stage 3 artifacts.
