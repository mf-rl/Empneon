# Documentation Status Corrections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct stale status statements while preserving historical execution records.

**Architecture:** Update the current Sims setup guide in place and add short supersession notices
to historical plans. Verification uses repository-wide Markdown searches and `git diff --check`;
no runtime code or configuration changes.

**Tech Stack:** Markdown, ripgrep, Git.

## Global Constraints

- Preserve original historical checklists and failure narratives.
- Do not consolidate, delete, or reorganize documentation.
- Do not change code, runtime configuration, or product claims beyond existing evidence.
- Distinguish automated verification from author-operated live validation.
- Leave implementation changes uncommitted unless the user explicitly requests a commit.

---

### Task 1: Correct current status and label historical records

**Files:**

- Modify: `adapters/thesims4/docs/setup.md`
- Modify: `docs/plans/2026-07-20-sims4-in-game-test-remediation-implementation.md`
- Modify: `docs/plans/2026-07-20-sims4-dialogue-repetition-implementation.md`
- Modify: `docs/plans/2026-07-19-sims4-http-simulation-implementation.md`
- Modify: `docs/superpowers/plans/2026-07-23-sims4-semantic-memory-selector.md`
- Modify: `docs/technical-audit-2026-07-29.md`
- Modify: `docs/session-progress-2026-07-30.md`

**Interfaces:**

- Consumes: current acceptance evidence in
  `adapters/thesims4/docs/in-game-core-feature-test-results.md` and optional authentication
  implementation documented by the technical audit.
- Produces: current user-facing status without stale pending or unauthenticated claims.

- [x] **Step 1: Correct optional-authentication wording**

Replace the two unconditional unauthenticated-server statements in `setup.md` with wording that
states `AI_SIM_API_TOKEN` provides optional shared-token authentication, while the reference server
must remain loopback-only and is not production network hardening.

- [x] **Step 2: Correct completed live-validation wording**

Replace the stale funny/mischief provider-acceptance and waiting-cancellation pending statements
with the final July 27 results already recorded in the adapter README and acceptance log:
provider-backed mischief passed after a fresh install; funny and funny/friendly normalization
remained relationship-neutral; non-user waiting finishes passed live without duplicate requests.

- [x] **Step 3: Reconcile the Stage 2 exit-gate introduction**

Change the conditional introduction from “This code path is not validated until” to a historical
description explaining that the following procedure produced the recorded passing validation
listed at the end of the section.

- [x] **Step 4: Label superseded incomplete plans**

Add a notice immediately below each affected plan title:

```markdown
> **Historical execution record:** The unchecked checklist is preserved from the original plan.
> Later implementation and live-acceptance records supersede its pending status; see
> [the current roadmap](../roadmap.md) and the Sims acceptance results.
```

Use the correct relative links for each plan directory. In the semantic-memory-selector plan,
replace the obsolete “in-game validation pending” status with an explicit historical/completed
status pointing to the July 24 and July 27 live results.

- [x] **Step 5: Update current verification totals**

Change the current Sims total from `333` to `334` in the July 29 audit and July 30 session record.
Do not alter older historical test counts. Keep the repository-wide Ruff baseline at `50`.

- [x] **Step 6: Search for stale current-status wording**

Run:

```powershell
rg -n "has no authentication|no authenticated HTTP API|provider-acceptance gap|do not yet demonstrate accepted provider dialogue|requires a live in-game retest|in-game validation pending|This code path is not validated until" --glob "*.md" .
```

Expected: no unresolved current-status occurrence; historical references must be explicitly marked
historical or replaced.

- [x] **Step 7: Verify formatting and inspect the diff**

Run:

```powershell
git diff --check
git diff -- adapters/thesims4/docs/setup.md docs/plans docs/superpowers/plans/2026-07-23-sims4-semantic-memory-selector.md docs/technical-audit-2026-07-29.md docs/session-progress-2026-07-30.md
```

Expected: `git diff --check` exits successfully and the diff contains documentation changes only.
