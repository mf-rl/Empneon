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
and PresentMon files remain local under `output/` until the roadmap publication task adds
configuration, sanitization, and limitations alongside them.
