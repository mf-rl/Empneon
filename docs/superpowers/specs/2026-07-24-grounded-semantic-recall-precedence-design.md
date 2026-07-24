# Grounded Semantic Recall Precedence Design

**Status:** Implemented; grounded deterministic precedence live-verified

## Goal

Prevent a factless semantic memory selection from replacing deterministic
recall that already contains attributed evidence answering the question.

## Root Cause

For the live question `My sweet baby, you remember our date, right? Can you
tell me when is it going to be?`, deterministic recall selected the confirmed
`Tonight, 7pm, at my place` fact. The semantic selector instead chose two
similar prior recall conversations with no attributed facts.

`semantic_recalled_memories()` accepted that non-empty semantic result and
discarded the grounded fallback. The dialogue prompt therefore contained
earlier questions rather than the known date fact, so the recall-integrity
validator had no evidence to enforce and the model fabricated `the 15th`.

## Design

Add one precedence guard in `semantic_recalled_memories()`:

1. Run semantic selection exactly as today.
2. If the semantic result contains at least one attributed fact, return it.
3. If it contains no attributed facts while deterministic fallback contains
   at least one, return the deterministic fallback.
4. If neither contains attributed facts, return the semantic result when
   non-empty and otherwise retain the existing fallback behavior.

This guard treats attributed facts as stronger evidence without disabling
semantic retrieval for legacy or unstructured memories.

## Compatibility Boundaries

- Do not change candidate construction, selector prompts, provider calls,
  persistence, pair scoping, privacy, confirmation gating, or result limits.
- Do not replace a grounded semantic selection with deterministic recall.
- Preserve factless semantic recall when no grounded deterministic result
  exists.
- Do not change dialogue validation, response categories, relationship
  effects, animation, or provider transports.

## Tests

Add regression coverage proving:

- A factless semantic selection cannot replace a grounded deterministic date
  result.
- A grounded semantic selection remains authoritative.
- A factless semantic selection remains usable when the deterministic result
  is also factless.
- Empty and failed semantic selection retain their existing fallback behavior.

Run focused semantic-recall tests, the complete Sims adapter suite, backend
compilation, the complete Core suite, and the Sims source build.

## Live Verification

Restart only the source backend and repeat the existing date question. Another
invitation, game reload, or mod installation is unnecessary.
