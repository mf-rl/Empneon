# Sims 4 Code-Word Owner-Aware Recall Design

**Status:** Implemented, automated-verified, and live-verified across Save A and Save B

## Goal

Disambiguate multiple confirmed code-word facts for the same Sim pair:

- `your code word` selects the fact attributed to the responding Sim;
- `our code word` selects the shared/message-author fact;
- an unqualified `code word` query retains existing relevance and recency behavior.

For the live Test 14 branches, Save B must answer `your` with
`TEST14-B-731` and `our` with inherited `TEST14-A-731`.

## Root Cause

Save-slot restoration and possessive fact attribution are correct. In Save B,
both A and B are valid pair-scoped facts. The current recall terms discard
`your` and do not retain the short token `our`, so deterministic retrieval and
semantic candidates are identical for both questions. Recency ranks B first.

The semantic selector receives actor IDs without query-role constraints, and
the grounding boundary accepts any selected supported fact. It therefore
accepts B for both `your` and `our`.

## Design

Add one adapter-local ownership predicate for code-word queries. It consumes
the query, fact actor ID, responding-Sim ID, and player-message-author ID:

- `your ... code word` accepts only the responding-Sim ID;
- `our ... code word` accepts only the player-message-author ID;
- other queries accept every fact and preserve existing behavior.

Use the predicate at both relevant boundaries:

1. Filter authoritative facts before deterministic ranking and before building
   semantic-selector candidates.
2. Filter facts again when validating and constructing supported recall
   evidence after semantic selection.

The second check prevents a malformed or stale selected-memory payload from
bypassing owner semantics. If the requested owner has no matching fact, the
existing unsupported explicit-recall path returns uncertainty.

## Scope

The ownership parser is deliberately limited to `code word` and `codeword`.
It does not change Core's public `RecallQuery`, schemas, database contents,
checkpoint files, prompts, provider contracts, or Sims script-mod code.

## Compatibility

The change must preserve:

- unqualified code-word relevance and recency ranking;
- identifier-first and possessive durable facts;
- pair privacy and attributed recall;
- time and location constraints;
- non-code-word semantic selection;
- save-slot restoration;
- provider usage, cancellation, action results, and dialogue delivery.

## Verification

Add test-first regressions proving:

1. In a Save B-shaped fact set, `What is your code word?` exposes only B.
2. In the same fact set, `What is our code word?` exposes only A.
3. `What is the code word?` retains both facts and current ranking behavior.
4. Missing requested ownership returns grounded uncertainty, not another
   owner's fact or HTTP `500`.
5. Existing recall, privacy, attribution, fallback, and save-slot tests remain
   green.

Run focused RED/GREEN tests, the complete Sims adapter and Core suites, Godot
and shared tests, Python compilation, real slot 14/15 read-only validation,
and whitespace checks. Leave all changes uncommitted and unpushed.
