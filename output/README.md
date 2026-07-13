# Published Stage 3 Evidence

These files support the preliminary SocietyBench results recorded on 2026-07-13. They use
synthetic agent IDs and contain no credentials, user paths, save data, or real Sim identities.

## Configuration

- Hardware: Ryzen 7 4800H, RTX 2060 Laptop 6 GB, 16 GB RAM
- OS: Windows 11
- Game: The Sims 4 `1.121.361.1020`, foreground and unpaused
- Provider: LM Studio at `http://127.0.0.1:1234/v1`
- Model: `gemma-4-e4b-it-uncensored`, 7.5B, Q4_K_M
- Scenario: deterministic 20-agent `social-ring`
- Provider baseline: sequential calls, temperature `0`, maximum `16` tokens, 60-second
  timeout
- Fixed baseline: provider-free CLOD 1
- Believability run: temperature `0.2`, maximum `16` tokens, seed `20260713`
- Frame metric: positive PresentMon `msBetweenDisplayChange` samples

The provider baseline can be regenerated while The Sims 4 is running:

```powershell
py -3.12 -m empneon.benchmarks.live `
  --base-url http://127.0.0.1:1234/v1 `
  --model gemma-4-e4b-it-uncensored `
  --output output/stage3-baseline-foreground-20260713.json
```

The blinded packet can be regenerated and scored with:

```powershell
py -3.12 -m empneon.benchmarks.believability generate `
  --model gemma-4-e4b-it-uncensored --seed 20260713 `
  --packet output/stage3-believability-blind-20260713.json `
  --key output/stage3-believability-key-20260713.json

py -3.12 -m empneon.benchmarks.believability score `
  --packet output/stage3-believability-blind-20260713.json `
  --key output/stage3-believability-key-20260713.json `
  --result output/stage3-believability-result-20260713.json
```

## Artifacts

| File | Purpose | SHA-256 |
|---|---|---|
| `stage3-baseline-foreground-20260713.json` | 20 provider observations and fixed-CLOD counts | `20ee127a4ef4183a38fe96460eac2eb5c08f2ea6c46bb845c704954256da430e` |
| `stage3-presentmon-foreground-20260713.csv` | 3,218 raw PresentMon rows; 3,216 positive display-change samples | `6c0aaec55a86e322963e4110958156de93f6c10ff4c64ad88c8e536ba9787369` |
| `stage3-believability-blind-20260713.json` | Rated 20-pair blind packet | `f4f02b4e9409d781f091d72a856264c38c40f477c5ee379001f958daa013f4ac` |
| `stage3-believability-key-20260713.json` | Post-evaluation strategy key | `b7bc85f64a2e4877d87ea51efdd4ac238c5ed3c8814a148502a8db58d6492497` |
| `stage3-believability-result-20260713.json` | Revealed aggregate score | `67bc528492f98cf02a0855ce6086bb436cca466d06d5a5e1d91a18cd1d32a412` |

## Limitations

- This is one run on one laptop, game build, model, and quantization.
- Provider calls were sequential and used short synthetic prompts.
- CPU and RAM are system-wide samples; VRAM is total device usage from `nvidia-smi`.
- Resource samples were taken after provider calls, not continuously, and fixed CLOD 1 has
  no equivalent resource-sample series.
- PresentMon process IDs and swap-chain addresses are ephemeral. The exact capture command
  and PresentMon version were not preserved, so the CSV is auditable but the capture setup
  is not exactly reproducible.
- Frame timing overlapped the provider workload but does not isolate Empneon's contribution
  from the game, other mods, or background processes.
- The believability result has one assistant evaluator, minimal synthetic context, and no
  player ratings. Candidate styles were recognizable despite hidden A/B strategy labels.
- Several model candidates violated the requested plain two-to-six-word format with emoji
  or numbering.
- These artifacts support no scalability, acceptable-performance, or player-quality claim.
