# README Boundary and Markdown Reference Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every surviving Markdown reference valid and assign Core, Sims 4, and Godot
information to their owning README.

**Architecture:** Edit documentation in place. Keep the root README Core-only except for two
adapter navigation links, move its adapter-specific material into the existing adapter READMEs,
and repair references to files removed during the documentation cleanup.

**Tech Stack:** Markdown, Git, PowerShell filesystem checks, Ripgrep.

## Global Constraints

- Preserve all existing user deletions and unrelated worktree changes.
- Do not recreate removed plan, specification, audit, or report files.
- The root README may name The Sims 4 and Godot only in links to their adapter READMEs.
- Detailed evidence remains in adapter-local documents; each adapter README summarizes and indexes
  that evidence.
- Do not change application code or runtime behavior.

---

### Task 1: Enforce README ownership

**Files:**

- Modify: `README.md`
- Modify: `adapters/thesims4/README.md`
- Modify: `adapters/godot/README.md`

**Interfaces:**

- Consumes: the ownership rules in `docs/readme-boundary-cleanup-design.md`
- Produces: one Core README and two authoritative adapter entry points

- [ ] **Step 1: Record the current boundary violations**

Run:

```powershell
Select-String -Path README.md -Pattern 'Sims|Godot|AI_SIM|Electronic Arts|Maxis|Ryzen|RTX|frame-time'
```

Expected: matches throughout badges, setup, architecture, memory, providers, hardware, validation,
roadmap, releases, documentation, and affiliation sections.

- [ ] **Step 2: Make the root README Core-only**

Apply these exact content boundaries:

- remove both adapter badges and the sentence describing included adapters;
- remove the Sims testing path and replace `Choose your path` with an `Adapters` section containing
  only links to `adapters/thesims4/README.md` and `adapters/godot/README.md`;
- retain the generic `GameAdapter` contract and adapter-development link, correcting moved Core
  document links to their current locations under `docs/`;
- make the architecture diagram text generic (`Game adapters` above `Empneon Core`) and remove both
  adapter implementation paragraphs;
- keep Core cognitive scheduling and memory behavior, but remove Sims monitoring, pair-recall,
  dialogue-validation, and privacy examples;
- make repository layout and development commands Core-only;
- retain Core provider implementations but remove `AI_SIM_*` configuration;
- remove the adapter hardware section;
- reduce current validation and roadmap sections to Core behavior and priorities;
- document only the `core-vX.Y.Z` release and Core wheel installation;
- keep Core documentation links and move adapter links to the approved navigation section;
- replace the EA/Maxis affiliation text with provider-neutral Core responsible-use wording.

- [ ] **Step 3: Add relocated Sims information to its README**

Ensure `adapters/thesims4/README.md` contains or links to:

- supported interaction, memory, action-confirmation, autonomy, persistence, and diagnostics
  behavior;
- setup, privacy, compatibility, and provider configuration;
- the Ryzen 7 4800H, RTX 2060 6 GB, 16 GB RAM validation machine and conservative
  one-concurrent-request result;
- current live and automated validation limitations;
- the `thesims4-vX.Y.Z` release tag and archive contents;
- links to `adapters/thesims4/docs/setup.md`,
  `adapters/thesims4/docs/benchmark-results.md`,
  `adapters/thesims4/docs/in-game-core-feature-tests.md`, and
  `adapters/thesims4/output/README.md`;
- the independent-project EA/Maxis affiliation disclaimer.

Reuse the root README wording where it is still accurate; do not duplicate the detailed evidence
already present in adapter-local documents.

- [ ] **Step 4: Add relocated Godot information to its README**

Ensure `adapters/godot/README.md` contains:

- its scope as a smaller portability adapter rather than a production integration;
- the `EMPNEON_GODOT_OK` headless validation result and its limitation;
- the `godot-vX.Y.Z` release tag and matching Core-wheel requirement;
- the existing release, development, and license instructions.

- [ ] **Step 5: Verify the README boundary**

Run:

```powershell
$boundaryMatches = Select-String -Path README.md -Pattern 'Sims|Godot|AI_SIM|Electronic Arts|Maxis|Ryzen|RTX|frame-time'
$boundaryMatches
if ($boundaryMatches.Count -ne 2) { throw "Expected only two adapter navigation lines" }
if ($boundaryMatches[0].Line -notmatch 'adapters/thesims4/README.md') { throw "Missing Sims README navigation" }
if ($boundaryMatches[1].Line -notmatch 'adapters/godot/README.md') { throw "Missing Godot README navigation" }
```

Expected: exactly two matches, both in the adapter navigation section.

- [ ] **Step 6: Commit the README ownership change**

```powershell
git add -- README.md adapters/thesims4/README.md adapters/godot/README.md
git commit -m "docs: separate Core and adapter READMEs"
```

---

### Task 2: Repair references to removed Markdown files

**Files:**

- Modify: `adapters/thesims4/docs/benchmark-results.md`
- Modify: `adapters/thesims4/docs/setup.md`
- Modify: `adapters/thesims4/output/README.md`
- Modify: `.superpowers/sdd/2026-07-29-sims4-backend-decomposition/progress.md`
- Modify: `.superpowers/sdd/2026-07-29-sims4-backend-decomposition/task-1-report.md`
- Modify: `.superpowers/sdd/2026-07-29-sims4-backend-decomposition/task-8-brief.md`
- Modify: `.superpowers/sdd/2026-07-29-sims4-backend-decomposition/task-8-report.md`
- Preserve: `adapters/thesims4/docs/in-game-core-feature-tests.md`
- Preserve deletion of the two source documents merged into the surviving test document

**Interfaces:**

- Consumes: the current filesystem after the user's Markdown removals
- Produces: no surviving reference to a removed `.md` path

- [ ] **Step 1: Repair current product-document links**

Make these replacements:

- in the benchmark, setup guide, output manifest, and Sims README, remove the link to the deleted
  conservative-resource specification; retain the decision as prose and link to
  `benchmark-results.md` where evidence is needed;
- in the task-1 report, replace the former results-document path with
  `adapters/thesims4/docs/in-game-core-feature-tests.md`.

- [ ] **Step 2: Repair historical workflow references**

Make these historical records accurate without recreating deleted files:

- change the progress ledger heading from the deleted plan path to
  `SDD ledger — Sims 4 backend decomposition`;
- in the task-8 brief and report, replace deleted technical-audit, design-specification, and
  implementation-plan paths with plain descriptions such as `the July 29 technical audit`,
  `the approved backend-decomposition design`, and `the backend-decomposition plan`;
- replace commands that target the deleted audit file with historical prose stating that the
  command originally inspected that audit.

- [ ] **Step 3: Run the repository-path audit**

Run from the repository root:

```powershell
$repo = (Get-Location).Path
$docs = Get-ChildItem . -Recurse -Force -Filter *.md -File -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch '\\.git\\|pytest|\\.verify_' }
$missing = @()
foreach ($doc in $docs) {
    $text = Get-Content -Raw -LiteralPath $doc.FullName
    foreach ($match in [regex]::Matches(
        $text,
        '(?<![A-Za-z0-9_])(?<path>(?:\.\.?/|[A-Za-z0-9_.-]+/)[A-Za-z0-9_./-]+\.md)'
    )) {
        $path = $match.Groups['path'].Value.TrimEnd('.')
        $relative = [IO.Path]::GetFullPath((Join-Path $doc.DirectoryName ($path -replace '/', '\')))
        $rooted = [IO.Path]::GetFullPath((Join-Path $repo ($path -replace '/', '\')))
        if (-not (Test-Path -LiteralPath $relative) -and -not (Test-Path -LiteralPath $rooted)) {
            $missing += "$($doc.FullName.Substring($repo.Length + 1)) -> $path"
        }
    }
}
$missing
if ($missing.Count) { throw "$($missing.Count) missing Markdown path references" }
```

Expected: no missing paths and exit code 0.

- [ ] **Step 4: Commit the reference repairs and existing test-document merge**

```powershell
git add -u -- adapters/thesims4/docs
git add -- adapters/thesims4/docs/in-game-core-feature-tests.md adapters/thesims4/output/README.md .superpowers/sdd/2026-07-29-sims4-backend-decomposition/progress.md .superpowers/sdd/2026-07-29-sims4-backend-decomposition/task-1-report.md .superpowers/sdd/2026-07-29-sims4-backend-decomposition/task-8-brief.md .superpowers/sdd/2026-07-29-sims4-backend-decomposition/task-8-report.md
git commit -m "docs: repair removed file references"
```

---

### Task 3: Verify every surviving Markdown document

**Files:**

- Inspect: every `*.md` file, including `.github` and `.superpowers`
- Modify only if a verification finding remains

**Interfaces:**

- Consumes: Tasks 1 and 2
- Produces: a clean repository-wide Markdown reference audit

- [ ] **Step 1: Verify local Markdown and image links**

Run:

```powershell
$repo = (Get-Location).Path
$docs = Get-ChildItem . -Recurse -Force -Filter *.md -File -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch '\\.git\\|pytest|\\.verify_' }
$missing = @()
foreach ($doc in $docs) {
    $text = Get-Content -Raw -LiteralPath $doc.FullName
    foreach ($match in [regex]::Matches($text, '!?\[[^\]]*\]\((?<target><[^>]+>|[^)\s]+)')) {
        $target = $match.Groups['target'].Value.Trim('<', '>')
        if ($target -match '^(https?:|mailto:|#|data:)') { continue }
        $path = [uri]::UnescapeDataString(($target -split '#', 2)[0])
        if (-not $path) { continue }
        $resolved = [IO.Path]::GetFullPath((Join-Path $doc.DirectoryName $path))
        if (-not (Test-Path -LiteralPath $resolved)) {
            $missing += "$($doc.FullName.Substring($repo.Length + 1)) -> $target"
        }
    }
}
$missing
if ($missing.Count) { throw "$($missing.Count) broken local Markdown links" }
```

Expected: no missing links and exit code 0.

- [ ] **Step 2: Repeat the repository-path and README-boundary checks**

Repeat Task 2 Step 3 and Task 1 Step 5.

Expected: both checks exit 0.

- [ ] **Step 3: Check formatting and inspect the final scope**

Run:

```powershell
git diff --check
git status --short
git diff --stat
```

Expected: no whitespace errors; only intended documentation changes and the user's existing
deletions remain.

- [ ] **Step 4: Commit any verification-only corrections**

If Step 1 or Step 2 required an additional Markdown correction, stage only the corrected files
listed by `git status --short`, using their explicit paths, then run:

```powershell
git commit -m "docs: finish Markdown verification"
```

If no correction was needed, do not create an empty commit.
