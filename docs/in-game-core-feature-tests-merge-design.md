# In-Game Core Feature Tests Merge Design

**Date:** 2026-07-30
**Status:** Approved for implementation

## Goal

Replace the separate Sims 4 in-game test plan and results documents with one canonical
`in-game-core-feature-tests.md` document.

## Structure

The merged document will contain:

1. A shared title and introduction.
2. **Part I — Test Plan and Procedures**, preserving the complete plan.
3. **Part II — Recorded Results**, preserving the complete result and remediation history.

The source documents' reciprocal links will become internal links between the two parts.

## File and Link Changes

- Create `adapters/thesims4/docs/in-game-core-feature-tests.md`.
- Delete:
  - `adapters/thesims4/docs/in-game-core-feature-test-plan.md`
  - `adapters/thesims4/docs/in-game-core-feature-test-results.md`
- Update existing references in current README and setup documentation to the new filename.
- Preserve unrelated documentation-reorganization changes already present in the worktree.

## Constraints

- Preserve all procedures, statuses, results, and historical evidence.
- Do not reinterpret or summarize recorded test outcomes.
- Do not modify code, configuration, or unrelated documentation.
- Use one canonical link wherever the old plan and results were listed separately.

## Verification

- Confirm neither old filename remains in the active Markdown corpus.
- Confirm every updated relative link resolves.
- Confirm the merged file contains all 15 numbered test sections and both completion records.
- Run `git diff --check`.
