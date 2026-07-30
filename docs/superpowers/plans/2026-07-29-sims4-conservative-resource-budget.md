# Sims 4 Conservative Resource Budget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Status:** Complete; canonical documentation updated and verified without runtime changes

**Goal:** Publish the approved conservative baseline-hardware resource budget proposal in the
canonical benchmark and roadmap documentation without changing runtime behavior.

**Architecture:** Treat the approved design specification as the detailed evidence record.
Summarize its hold decision in the benchmark results and move the roadmap from proposal formulation
to evidence-triggered follow-up. Do not edit Core, adapter configuration, capture artifacts, or
tests.

**Tech Stack:** Markdown, PowerShell, Git

## Global Constraints

- Make no runtime, route-estimate, token-limit, configuration, or concurrency changes.
- Retain `active_agent_limit = 1`, Core `max_ram_mb = 256`, small/large RAM estimates of
  `64/128 MiB`, and small/large latency estimates of `30,000/90,000 ms`.
- Describe `vram_mb = 0` as unknown and unenforced, never as zero consumption.
- Do not claim a safe operating limit, recommended hardware profile, acceptable performance,
  broad hardware support, or scalability.
- Do not add a dependency or generate new capture evidence.
- Do not commit or push until the user explicitly requests it.

---

### Task 1: Publish the conservative hold decision

**Files:**
- Modify: `adapters/thesims4/docs/benchmark-results.md:217`
- Modify: `docs/roadmap.md:77-89`

**Interfaces:**
- Consumes: `docs/superpowers/specs/2026-07-29-sims4-conservative-resource-budget-design.md`
- Produces: canonical benchmark and roadmap summaries of the approved proposal

- [x] **Step 1: Replace the benchmark's pending-gate sentence**

In `adapters/thesims4/docs/benchmark-results.md`, retain the existing capture results and
verification counts. Replace:

```markdown
The next engineering gate is a conservative resource
budget proposal based on this matrix; runtime budgets, routing, and the single-request concurrency
limit remain unchanged.
```

with:

```markdown
The conservative baseline proposal retains the current single-request limit, Core `256 MiB`
incremental RAM ceiling, `64/128 MiB` small/large route estimates, and `30/90` second latency
estimates. It leaves VRAM admission unknown and unenforced because the captures report total device
use rather than provider-attributable memory. These are advisory hold values, not measured safe
limits, and no runtime setting changed. See the
[resource budget proposal](../../../docs/superpowers/specs/2026-07-29-sims4-conservative-resource-budget-design.md).
```

- [x] **Step 2: Move the roadmap gate to evidence-triggered follow-up**

In `docs/roadmap.md`, add this bullet at the end of `## Implemented`:

```markdown
- The conservative baseline resource proposal retains one concurrent request and the existing
  incremental RAM and latency estimates without changing runtime settings; route-attributable
  VRAM remains unknown under Windows WDDM
```

Replace the `### Resource evidence` list with:

```markdown
### Resource evidence

- Keep the conservative baseline proposal unchanged until a specific routing or capacity change
  requires new evidence.
- Before changing RAM estimates, repeat the neutral and recall cases enough to characterize
  request-window variance.
- Establish provider-attributable VRAM before enforcing VRAM admission; Windows WDDM reports
  per-process GPU memory as unavailable.
- Require a controlled concurrent in-game capture before increasing the single-request limit or
  claiming scalability.
```

- [x] **Step 3: Verify the documented measurements against the successful captures**

Run from the repository root:

```powershell
$files = Get-ChildItem 'adapters\thesims4\output\live-resource-capture-*.json' |
    Where-Object { $_.Name -notlike '*.failed.json' } |
    Sort-Object Name

foreach ($file in $files) {
    $capture = Get-Content -Raw $file.FullName | ConvertFrom-Json
    [PSCustomObject]@{
        File = $file.Name
        DurationMs = $capture.request.duration_ms
        SystemRamMiB = $capture.summary.system.peak_ram_mb
        ProviderRamMiB = $capture.summary.processes.provider.peak_ram_mb
        GpuMiB = $capture.summary.gpu.peak_memory_used_mb
        FrameP95Ms = $capture.summary.frames.p95_ms
    }
}
```

Expected: four passing captures; the three thinking-disabled runs retain durations
`19015`, `25328`, and `18422` ms, total GPU peaks `4681`, `4693`, and `4678` MiB, and frame-time
p95 values `55.7145`, `61.686255`, and `65.34703` ms.

- [x] **Step 4: Check documentation consistency**

Run:

```powershell
rg -n "active_agent_limit|max_ram_mb|64/128|30/90|VRAM|concurr|safe|scalab" `
  docs/superpowers/specs/2026-07-29-sims4-conservative-resource-budget-design.md `
  adapters/thesims4/docs/benchmark-results.md `
  docs/roadmap.md
git diff --check
```

Expected: the proposal consistently retains concurrency `1`, the `256 MiB` Core ceiling,
`64/128 MiB` route estimates, and `30/90` second latency estimates; every VRAM reference says it
is unknown or unattributed; `git diff --check` exits successfully.

- [x] **Step 5: Inspect the uncommitted documentation change**

Run:

```powershell
git status --short
git diff -- adapters/thesims4/docs/benchmark-results.md docs/roadmap.md
```

Expected: the approved specification and this plan remain untracked, the two canonical documents
are modified, and no source, configuration, test, or capture-artifact file changed. Do not commit
or push.
