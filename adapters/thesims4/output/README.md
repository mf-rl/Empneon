# Published Benchmark Evidence

These files support the preliminary Stage 3 and Stage 5 SocietyBench results recorded on
2026-07-13. They use synthetic agent IDs and contain no credentials, user paths, save data,
or real Sim identities.

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
py -3.12 -m empneon_thesims4.benchmark `
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

The differentiated Stage 5 validation can be regenerated and scored with:

```powershell
py -3.12 -m empneon.benchmarks.believability generate --adaptive `
  --model gemma-4-e4b-it-uncensored --seed 20260713 `
  --packet output/stage5-adaptive-believability-blind-20260713.json `
  --key output/stage5-adaptive-believability-key-20260713.json

py -3.12 -m empneon.benchmarks.believability score `
  --packet output/stage5-adaptive-believability-blind-20260713.json `
  --key output/stage5-adaptive-believability-key-20260713.json `
  --result output/stage5-adaptive-validation-20260713.json
```

## Artifacts

| File | Purpose | SHA-256 |
|---|---|---|
| `stage3-baseline-foreground-20260713.json` | 20 provider observations and fixed-CLOD counts | `20ee127a4ef4183a38fe96460eac2eb5c08f2ea6c46bb845c704954256da430e` |
| `stage3-presentmon-foreground-20260713.csv` | 3,218 raw PresentMon rows; 3,216 positive display-change samples | `6c0aaec55a86e322963e4110958156de93f6c10ff4c64ad88c8e536ba9787369` |
| `stage3-believability-blind-20260713.json` | Rated 20-pair blind packet | `f4f02b4e9409d781f091d72a856264c38c40f477c5ee379001f958daa013f4ac` |
| `stage3-believability-key-20260713.json` | Post-evaluation strategy key | `b7bc85f64a2e4877d87ea51efdd4ac238c5ed3c8814a148502a8db58d6492497` |
| `stage3-believability-result-20260713.json` | Revealed score and net preference | `4bbcef23962cf3154d877edd2d1e2219a73eee6133f6f6be511ea7fde6910cd9` |
| `stage5-adaptive-comparison-20260713.json` | Adaptive replay and failed exit gate | `d2dfedd9e9f10f3bda932301f1b0cecdfdd4ddc609f5a68df6d193dcf7e04ad2` |
| `stage5-adaptive-believability-blind-20260713.json` | Rated differentiated blind packet | `cf31d0ccfbf92aeb98c7938e8f82da4d42301519a6f5533a7e8eeadf70821fb4` |
| `stage5-adaptive-believability-key-20260713.json` | Routing, thresholds, observations, and answer key | `713a283ee892a6b48b334d4ff3518eec8896903ab725e9b1662276c44778c47f` |
| `stage5-adaptive-validation-20260713.json` | Passing adaptive cost, consistency, and preference score | `2e785fe343f6ec378b4359a7452e19aae3aa5703cb6356deb3512145a49483eb` |

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
- The Stage 5 comparison replays existing decisions and ratings; it is not a new hardware run.
- The differentiated Stage 5 run records provider tokens and latency but no Sims frame time,
  CPU, RAM, or VRAM because the game was not running.
- Adaptive token and latency totals select the 12 routed calls from the paired 20-call run;
  they are not a separately timed adaptive execution.
- Its consistency arm has one target claim per agent and cannot establish longitudinal
  contradiction resistance.

## Live resource captures

Run one request-scoped capture from `adapters/thesims4` with:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 .\scripts\capture_live_resources.py
```

The July 29 baseline measurement was derived from these published raw files:

| File | SHA-256 |
|---|---|
| `live-resource-capture-20260730T004648Z.json` | `41816d7467880d07a484de22092d719fd0fb015f47026117d941d48e9e5c9b9b` |
| `live-resource-capture-20260730T004648Z.presentmon.csv` | `c9c309c3a42c08bc959ac70e71f17b27c2eb763edce49200e441db3843479df1` |

The initial JSON was sanitized before publication by removing its deprecated live-Sim identifier.
Its embedded summary was normalized to its 32 request-window resource samples and 218
request-window frame samples, its telemetry tool versions were added, and the pre-submission armed
interval was excluded. It still includes machine-specific process IDs for diagnostic correlation.

The thinking-disabled three-request matrix uses the corrected request-window and identifier-free
JSON format:

| File | SHA-256 |
|---|---|
| `live-resource-capture-20260730T010628Z.json` | `d542b3c598bcdbe317cd1a7e2a7c7f496e8cbbc5c72d06a1c1b67b98af0d564a` |
| `live-resource-capture-20260730T010628Z.presentmon.csv` | `ebdebe142a2d4b70056edbf849f7a7d788d573b519cad88391116fea15915369` |
| `live-resource-capture-20260730T010847Z.json` | `44e69435ff73df41dfb8f2a5b77cdb3d5a8e866c717a932cc4c5713a6b7b5584` |
| `live-resource-capture-20260730T010847Z.presentmon.csv` | `a2e5c1231d16a27cb3710cf8bfcdade9845db61f6f9e586e3f3856a2cd019eb3` |
| `live-resource-capture-20260730T020334Z.json` | `130983f849c11affeffca4288a0573acbd7713ad3b92279dbd0a8570e2c7375c` |
| `live-resource-capture-20260730T020334Z.presentmon.csv` | `c056357367b02fe64766c9efee14575646ba80a43ce991a5be06bd9019756cab` |

The failed attempts are also retained because they verify evidence preservation on process
ambiguity and operator-timeout paths:

| UTC stem | Result |
|---|---|
| `20260730T002419Z` | Multiple backend processes found before capture |
| `20260730T002440Z` | No Empneon Social observed before timeout |
| `20260730T003238Z` | No Empneon Social observed before timeout; partial PresentMon CSV retained |
| `20260730T003721Z` | No Empneon Social observed before timeout; partial PresentMon CSV retained |
| `20260730T004924Z` | No Empneon Social observed before timeout; partial PresentMon CSV retained |

Repository copies use normalized LF line endings. Neither failed evidence nor passing reports
contain prompts, replies, Sim names, or API credentials. The successful reports retain request
UUIDs and machine-specific process IDs.

The accepted conservative resource decision uses this matrix to retain the existing single-request
and incremental route estimates without changing runtime settings. It does not treat the
measurements as safe limits or attribute total
device GPU memory to the provider.
