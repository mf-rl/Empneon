# Sims 4 Neutral Factual-Recall Outcomes Design

**Status:** Implemented, automated-verified, and live-verified with zero applied consequences

## Goal

Prevent a supported factual-recall answer from creating a social action or
relationship outcome solely because the model labels its neutral dialogue as
romantic. Preserve the generated answer and all existing non-recall social
behavior.

## Evidence and Root Cause

The two successful Test 14 recall turns were stored with neutral code-word
dialogue but model metadata declaring `response_category=romance`, warm or
romantic tone tags, and `relationship_outcome=romance_positive`. The current
validator treats a romance category plus those tags as sufficient evidence.
Both turns consequently applied `relationship.romance +5`.

The owner-aware recall fix did not introduce this behavior. The permissive
warm-romance rule predates it and remains necessary for existing subtle
romance replies that do not contain a small set of explicit keywords.

## Considered Approaches

1. **Neutralize supported factual recall at the response boundary
   (selected).** After a model response is normalized, supported explicit
   recall keeps its dialogue and descriptive metadata but forces
   `relationship_outcome`, `suggested_action`, and `animation` to `none`.
   This directly prevents relationship mutations and native social execution
   without changing normal romance classification.
2. **Tighten the global warm-romance heuristic.** This would reject the
   observed result, but it would also regress already-working subtle romantic
   reciprocation that intentionally relies on category and tone.
3. **Change only the prompt.** This may reduce model mistakes but cannot
   enforce safety against future local-model misclassification.

## Design

`HermesRuntime.dialogue()` already computes the request's supported recall
facts before model generation. Immediately after normalizing a model response,
when that set is non-empty:

- preserve the generated dialogue, emotion, intent, category, tone, trust,
  and memory summary;
- set `relationship_outcome` to `none`;
- set `suggested_action` and `animation` to `none`.

`_supported_recall_facts()` returns facts only for explicit recall, so this
guard does not affect ordinary conversation, unsupported questions, or
non-recall semantic memory.

The response category remains descriptive metadata. It is not rewritten,
because changing it could make a fact containing genuinely romantic wording
fail existing category-consistency validation. Removing the outcome and
actions is the smallest complete prevention of game-state side effects.

## Compatibility

The change must preserve:

- normal romance initiation, subtle reciprocation, rejection, and outcomes;
- friendship, mean, funny, and mischief outcomes;
- Test 14 owner-aware retrieval and grounded dialogue;
- fallback recall behavior, which is already actionless;
- trust, memory, usage, cancellation, delivery, and save-slot behavior.

## Verification

Add a test-first regression reproducing the exact model metadata from the live
code-word turns. Assert that supported recall preserves dialogue but returns
no relationship outcome or action. In the same boundary test, prove an
otherwise identical normal romantic exchange still returns
`romance_positive` and its existing romance action.

Run the focused red/green test, complete Sims adapter, Core, Godot, and shared
test suites, Python compilation, and `git diff --check`. Keep all changes
uncommitted and unpushed.
