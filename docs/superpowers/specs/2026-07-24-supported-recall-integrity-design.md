# Supported Recall Integrity Design

**Status:** Implemented; corrected model response and grounded fallback live-verified

## Goal

When Empneon supplies attributed memory that answers a player's recall
question, the generated dialogue must use that evidence instead of denying,
ignoring, or asking the player for the same information.

## Root Cause

The persisted date event and attributed time fact reached the dialogue prompt,
but the model ignored them. The grounding validator did not recognize the live
message as a recall question because `when` appeared after a conversational
prefix. Its evidence check also required lexical overlap between `date` and
the time fact `Tonight, 7pm`. With general response rejection disabled, the
schema-valid but unsupported reply was accepted immediately.

## Design

Keep general response rejection configurable. Add a narrow recall-integrity
rule that always applies when all of these conditions hold:

1. The current message contains a natural recall question, including a
   `what`, `when`, `where`, or `who` clause anywhere in the message or an
   explicit memory phrase such as `remember`.
2. Recall selection already supplied at least one attributed fact.
3. The selected evidence answers the detected question cue.

For a `when` question, a selected time-bearing fact is sufficient evidence;
it does not also need to repeat the topic noun from the question. Existing
selection remains responsible for pair scoping, privacy, confirmation,
deduplication, and relevance.

After generation, reject only responses that fail this supported-recall
contract: uncertainty, asking the same question back, or omitting the
available answer. Retry once with a correction containing the attributed
evidence. If the retry still fails or the provider errors, use the existing
grounded fallback path.

## Compatibility Boundaries

- Do not enable broad response rejection.
- Do not change memory selection, persistence, schemas, categories,
  relationship effects, animation, or provider transports.
- Do not require an answer when no attributed evidence was selected.
- Do not constrain ordinary invitations, friendly questions, creative
  reactions, unsupported-memory uncertainty, or non-recall dialogue.
- Keep the rule provider- and model-agnostic; it validates dialogue behavior,
  not a provider-specific payload.

## Tests

Add regression coverage proving:

- `Hey, my sweet baby. When are we going on our date? Can you tell me?` is a
  supported recall question when the selected fact says `Tonight, 7pm, at my
  place`.
- The live-shaped response that asks `when are we going on our date?` is
  rejected even when general response rejection is disabled.
- One corrected response using `tonight at 7 pm` is accepted.
- Unsupported recall questions may still admit uncertainty.
- Ordinary questions and existing response-rejection-disabled behavior remain
  unchanged.

Run the focused tests, complete Sims adapter suite, complete Core suite,
Python 3.12 backend compilation, and the Python 3.7 Sims mod build.

## Live Verification

After installing the rebuilt mod and restarting the backend and game, repeat
only the existing date recall question. A new invitation is unnecessary.
Confirm that Sim B states tonight at 7 pm in fresh wording and that no
unrelated relationship, category, or animation behavior changes.
