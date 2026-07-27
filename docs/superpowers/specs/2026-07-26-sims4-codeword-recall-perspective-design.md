# Sims 4 Code-Word Recall Perspective Design

**Status:** Implemented and live-verified

## Goal

When Sim A asks Sim B, `What is your code word?`, Sim B must answer in
first person: `My code word is TEST14-B-731.` The existing correct owner
selection, shared `our code word` response, and unrelated recall behavior must
remain unchanged.

## Root Cause

The confirmed fact is correctly attributed to Sim B, but its statement keeps
Sim A's original wording: `Your secret code word is TEST14-B-731.` The prompt
renderer treats `actor_id` as the person who uttered the stored sentence,
although for this fact it represents the code-word owner. This presents
misleading evidence such as `Sim B said: Your secret code word...`.

The grounding layer validates the identifier and existing time/location
perspective rules but has no code-word pronoun rule. It therefore accepts a
model reply that copies `your`.

## Considered Approaches

1. **Owner-aware evidence, grounding, and fallback (selected).** Render a
   code-word fact as ownership rather than quoted speech, reject a
   speaker-owned answer that lacks `my code word`, and make the deterministic
   fallback produce the same first-person wording. This fixes all response
   paths at the narrow adapter boundary.
2. **Rewrite stored facts.** Migrating `Your...` to `My...` would make the
   statement incorrect when read from Sim A's original-message perspective
   and would require checkpoint/database mutation.
3. **Post-process generated dialogue.** Replacing `your` with `my` after
   generation could corrupt quotations or unrelated uses and would bypass
   grounding rather than improve it.

## Design

Add a small adapter-local parser for identifier-bearing code-word statements.
It extracts the identifier already present in the confirmed fact.

For selected evidence:

- a fact owned by the responding Sim is rendered as
  `<Sim B name>'s code word is <identifier>`;
- an `our code word` fact is rendered as a shared code word;
- other facts keep the existing attributed-speech format.

For grounding:

- when `codeword_recall_owner_id()` resolves the responding Sim, the
  unquoted answer must contain `my code word` or `my codeword`;
- `your code word` and neutral `the code word` replies are rejected with a
  focused correction;
- `our code word` and all non-code-word questions keep current validation.

For deterministic fallback:

- responding-Sim ownership returns `My code word is <identifier>.`;
- shared/message-author ownership returns `Our code word is <identifier>.`;
- all other fact types keep `_recalled_fact_dialogue()` behavior.

## Compatibility

The change must preserve:

- Test 14 A/B fact selection and save-slot isolation;
- relationship-outcome sanitization for factual recall;
- time and location perspective validation;
- attributed quotations and third-party facts;
- normal romance and all non-recall social behavior;
- databases, checkpoints, Core contracts, provider schemas, and Sims mod code.

## Verification

Use test-first regressions for:

1. owner-aware evidence text does not claim Sim B said `Your code word`;
2. `Your code word is TEST14-B-731` is rejected for Sim B's answer;
3. `My code word is TEST14-B-731` is accepted;
4. deterministic fallback produces `My` for `your` and retains `Our` for
   `our`;
5. existing location perspective, owner selection, relationship
   sanitization, and normal romance tests remain green.

Run focused red/green tests, complete Sims adapter, Core, Godot, and shared
suites, Python compilation, and `git diff --check`. Leave all changes
uncommitted and unpushed.
