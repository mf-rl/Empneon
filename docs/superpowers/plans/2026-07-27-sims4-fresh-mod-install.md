# Sims 4 Fresh Mod Install Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent source checkouts from installing stale Sims 4 mod artifacts.

**Status:** Completed; automated verification, rebuild, and installation passed.

**Architecture:** Prefer the local builder whenever it exists. Preserve
prebuilt-only release installation as the fallback path.

**Tech Stack:** PowerShell, Python, pytest

## Global Constraints

- Do not change backend or Sims social behavior.
- Release ZIPs without `build_mod.py` must still install prebuilt artifacts.
- Do not commit or push; the user will request that separately.

---

### Task 1: Make source-checkout installs rebuild first

**Files:**
- Modify: `adapters/thesims4/tests/test_sims4_mod_autonomy.py:26-44`
- Modify: `adapters/thesims4/install_mod.ps1:3-12`
- Modify: `adapters/thesims4/README.md`
- Modify: `adapters/thesims4/docs/in-game-core-feature-test-results.md`
- Modify: `docs/roadmap.md`

**Interfaces:**
- Consumes: `build_mod.py`, the two existing `dist` artifact paths.
- Produces: fresh artifacts in source checkouts; unchanged prebuilt release
  installation when the builder is absent.

- [x] **Step 1: Change the installer regression**

Replace the old missing-artifacts condition assertion with literal assertions
for this branch:

```powershell
$builder = Join-Path $PSScriptRoot "build_mod.py"
if (Test-Path $builder) {
    python $builder
} elseif (-not ((Test-Path $scriptSource) -and (Test-Path $tuningSource))) {
    throw "Prebuilt Empneon mod files are missing. Download the complete release ZIP."
}
```

- [x] **Step 2: Run the focused test and verify RED**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_mod_autonomy.py::test_build_and_installer_use_empneon_artifact_names
```

Expected: FAIL because the installer still rebuilds only when artifacts are
missing.

- [x] **Step 3: Implement the minimal installer branch**

Set `$builder` before the condition. Run it whenever it exists; otherwise,
validate that both prebuilt artifacts exist.

- [x] **Step 4: Run the focused test and verify GREEN**

Rerun the command from Step 2. Expected: PASS.

- [x] **Step 5: Run repository verification**

Run all Sims 4, Core, Godot, and shared pytest suites, scoped Ruff, Python
compilation, and `git diff --check`.

- [x] **Step 6: Build and install**

Run:

```powershell
.\install_mod.ps1
```

Verify the rebuilt and installed `.ts4script` hashes match and that its bytecode
contains `mixer_social_LieAboutCareer_group_mischief_skills` but not the stale
targeted tuning.

- [x] **Step 7: Update handoff documentation**

Record that the prior live test used a stale archive, the installer now rebuilds
source checkouts, and a new game restart plus provider-backed mischief row is
required.

**Result:** The installer regression failed on the old branch, then passed.
All `520` repository tests and scoped static checks pass. After closing the
game, the corrected installer rebuilt and installed hash-matching artifacts
that contain the live mischief tuning and exclude the stale one.
