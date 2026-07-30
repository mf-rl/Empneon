# Documentation Status Corrections Design

**Date:** 2026-07-30
**Status:** Approved for implementation

## Goal

Make current user-facing documentation agree with the implemented and verified Sims 4 behavior
without rewriting or deleting historical execution records.

## Scope

- Correct `adapters/thesims4/docs/setup.md` statements that still describe:
  - the loopback API as unauthenticated instead of optionally authenticated;
  - funny and mischief provider acceptance as pending;
  - waiting-interaction cancellation as awaiting live verification;
  - the Stage 2 exit gate as unvalidated.
- Add concise historical or superseded notices to incomplete legacy plans whose work is recorded as
  complete by later specifications and acceptance results.
- Update verification totals where the current suite has advanced from 333 to 334 Sims tests while
  retaining the documented 50-finding repository-wide Ruff baseline.

## Constraints

- Preserve original historical checklists and failure narratives.
- Do not consolidate, delete, or reorganize documentation.
- Do not change code, runtime configuration, or product claims beyond existing evidence.
- Treat automated verification and author-operated live validation as distinct evidence.

## Verification

- Search all Markdown for the stale authentication, provider-acceptance, cancellation-retest, and
  Stage 2 validation wording.
- Confirm current documentation describes optional `AI_SIM_API_TOKEN` authentication consistently.
- Confirm historical notices point readers to the current roadmap or acceptance results.
- Run `git diff --check`.
