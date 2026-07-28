# Sims 4 Funny Word Forms Design

## Status

Implemented and automated-verified on 2026-07-27. A live retest confirmed the
word-form fix but exposed a separate marker-free funny-response defect.

## Problem

`explicit_social_category()` recognizes the whole words `joke` and `funny`,
but not the observed forms `jokes` and `funniest`. A live provider reply using
both forms was therefore accepted as `friendly` and applied an incorrect
friendship increase.

## Design

Extend only the existing funny-category regular expression:

- `joke` becomes `jokes?`.
- `funny` becomes `funn(?:y|ier|iest)`.

Keep category order, recategorization, relationship validation, and all other
social patterns unchanged. A regression test will use the exact live dialogue
and verify it is recategorized from `friendly` to `funny`, with no relationship
outcome or suggested action.

## Verification

Run the focused regression test first, then the complete Sims 4 adapter test
suite and the changed-file lint check.
