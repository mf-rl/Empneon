# Sims 4 Possessive Code-Word Recall Design

**Status:** Implemented, automated-verified, and live-verified in Test 14

## Goal

Allow confirmed, identifier-bearing statements such as `Our secret code word is
TEST14-A-731.` and `Your secret code word is TEST14-B-731.` to support correctly
attributed recall. An explicit recall question must never fail with HTTP `500`
when no structured supporting fact exists.

## Root Cause

Confirmed conversations retain both statements in episodic memory, and save-slot
checkpoints restore them correctly. The authoritative-fact extractor does not
recognize `our ... is <identifier>` or `your ... is <identifier>`, so the
confirmed events contain no structured facts.

Semantic retrieval can still select the raw event and the model can answer
correctly. Grounding rejects that answer because structured evidence is absent.
The fallback builder then fails because its uncertainty branch recognizes only
a subset of explicit question forms and raises `RuntimeError`.

## Design

Extend the existing authoritative-fact boundary with a narrow possessive
identifier-assignment rule:

- `my` and `our` assignments are attributed to the player-message author;
- `your` assignments are attributed to the addressed Sim;
- the rule applies only when the statement contains the existing structured
  identifier shape, such as `TEST14-A-731`;
- questions remain ineligible as durable facts.

Reuse the existing Core `analyze_recall_query()` result when choosing the
unsupported-recall fallback. Any explicit recall question without authoritative
support returns grounded uncertainty rather than exhausting generic candidates
and raising an exception.

Existing confirmed events are interpreted when recalled, so slots 14 and 15
require no migration or recreation.

## Compatibility

The change must preserve:

- existing identifier-first assignments;
- current `my ... is ...` durable facts;
- exact actor attribution and pair privacy;
- time and location recall constraints;
- semantic selection and deterministic fallback;
- save-slot checkpoint behavior;
- successful dialogue, cancellation, action-result, and provider usage flows.

No schema, configuration, HTTP contract, or Sims script-mod change is required.

## Verification

Add focused regressions proving:

1. `Our secret code word is TEST14-A-731.` produces one authoritative fact
   attributed to the message author.
2. `Your secret code word is TEST14-B-731.` produces one authoritative fact
   attributed to the addressed Sim.
3. Both exact Test 14 recall questions accept the supported identifier.
4. An unsupported explicit `What is ...?` question returns uncertainty and
   never raises `RuntimeError`.
5. Existing durable-fact, attributed-recall, privacy, fallback, and save-slot
   tests remain green.

Run the focused tests first, then the complete Sims 4 adapter and Core suites,
Python compilation, and whitespace verification. Leave all changes uncommitted
until explicitly requested.
