# Sims 4 Recalled Evidence and Fresh Response Design

**Status:** Implemented; automated and live fresh-response verification passed

## Goal

Let recalled interactions ground a new answer without exposing an earlier model-generated reply
for reuse.

## Design

Change the shared recalled-history renderer in
`adapters/thesims4/backend/ai_sims_server.py`. For every selected memory, render only:

- the original player statement;
- confirmed attributed facts.

Do not render the stored generated `dialogue`. Semantic selection, pair scoping, candidate limits,
deterministic fallback, and current-session conversation history remain unchanged.

This fixes the source of repetition even when response rejection is disabled: the old answer is no
longer present in the main generation prompt.

The dialogue prompt may let the model add a fresh term of endearment when both Sims' relationship
and traits support it. The term is optional, must fit the current context, and must not be copied
from recalled dialogue. Do not use one for a neutral or hostile relationship, rejected romance, or
when identity or context makes it inappropriate. Do not add a separate random-term list or
injection subsystem.

## Verification

Add focused prompt tests covering:

1. The live date case: the prompt retains `Tonight at 7 pm at your place` but excludes the earlier
   `That sounds perfect!` response.
2. An unrelated memory case proving the rule is not date-specific.
3. The prompt permits, but does not require, a fresh relationship- and trait-appropriate term of
   endearment.
4. Existing pair privacy and semantic-selection tests remain passing.

After automated verification, repeat the live date question and confirm that Sim B preserves the
date fact while answering in new wording. Then repeat with a non-date memory.

## Scope

Do not add another model request, enable response rejection, change similarity thresholds, alter
stored memories, or modify retrieval ranking.
