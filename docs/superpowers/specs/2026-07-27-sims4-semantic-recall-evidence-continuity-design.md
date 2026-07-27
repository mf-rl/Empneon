# Sims 4 Semantic Recall Evidence Continuity Design

**Status:** Informed-pair live matrix passed; privacy and restart checks pending

## Goal

Preserve the semantic memory selector's relevant attributed fact through dialogue validation and
deterministic fallback when the player's question paraphrases that fact without shared keywords.

The accepted live cases are:

- `What bouquet would suit me best?` recalls `I prefer moon orchids to roses.`;
- `What commitment did I make about the observatory equipment?` recalls the telescope promise;
- `Who is my sibling?` recalls the named sister;
- `Why are things tense between us?` recalls the lie about the promotion.

## Observed Failure

The live test stored all four original statements as attributed facts for the correct Sim pair.
The semantic selector could retrieve the conflict fact, but the later grounding boundary rebuilt
support using recall classification and lexical overlap:

- `bouquet` has no lexical overlap with `moon orchids`;
- `tense` has no lexical overlap with `lied about the promotion`;
- a general `why` question is not classified as explicit recall.

The preference model initially produced a relevant answer, but broad response validation rejected
it for copying part of the question. The deterministic fallback then saw no lexically supported
fact and returned uncertainty. The conflict response ignored selected evidence and was accepted
because that evidence was not considered supported at the grounding boundary.

## Design

`select_recalled_memories()` already returns selected candidates in provider order and removes
factless candidates when any selected candidate contains attributed facts. Preserve that contract.
Mark the first returned attributed memory as the primary semantic selection.

At the response boundary:

1. For factual queries, exclude factless prior recall answers before semantic selection; retain
   full exchanges when the question asks what was said/discussed or how an interaction occurred.
2. Keep existing deterministic time, location, identifier, and code-word constraints unchanged.
3. Continue using exact Core recall analysis and lexical support when either identifies a fact.
4. When those checks find no fact, use the primary semantic selection's attributed facts.
5. Require generated dialogue to use the primary fact and preserve category-specific preference,
   complete-promise, and relation-owner constraints.
6. If both model attempts fail, reuse the existing attributed-fact fallback with the primary fact.

This makes the selector's relevance decision survive the full request without treating every
candidate as authoritative. Secondary selected memories remain prompt context, but they cannot
override the primary fact during grounding or fallback.

## Data Flow

```text
pair-scoped confirmed candidates
        |
        v
semantic selector (ordered IDs)
        |
        v
first attributed result marked primary
        |
        +--> prompt context
        |
        +--> response grounding
                 |
                 +--> accepted grounded dialogue
                 |
                 +--> retry, then attributed fallback
```

The marker is request-local dictionary metadata. It is not written to SQLite and does not change
Core contracts or database schemas.

## Privacy and Safety

- Candidate collection remains restricted to the exact Sim pair.
- The selector may only return locally validated request-scoped IDs.
- An uninformed pair has no attributed candidate to mark primary and retains the existing
  uncertainty behavior.
- A selected fact cannot create a relationship outcome or native action; the existing neutral
  factual-recall boundary remains authoritative.
- Stored generated replies remain non-authoritative. A confirmed recall decision archives the
  exchange but never promotes its generated dialogue to a new responder fact. Historical
  attributed fallback wrappers recover their quoted fact owner at read time without migration.

## Compatibility

- No dependency, provider API, configuration, schema, or Sims script-mod change.
- Existing time/location grounding and code-word ownership behavior remain unchanged.
- Deterministic recall remains the fallback when selection fails or returns no valid memory.
- Up to three selected memories remain available to the dialogue prompt.

## Verification

Automated tests must reproduce the four live-shaped paraphrases with unrelated pair-scoped
memories present.

They must prove:

- the primary semantic fact survives when query and fact share no useful terms;
- a relevant generated answer is accepted;
- an answer that ignores the primary fact is rejected;
- failed retries return the attributed primary fact rather than uncertainty;
- secondary selected facts do not replace the primary fact;
- an uninformed pair still receives uncertainty;
- preference answers preserve the preferred option rather than promoting the alternative;
- promise answers state the complete commitment rather than repeating its subject;
- sibling answers preserve the fact owner's `my`/`your` perspective;
- attributed fallback text is not learned as a new responder fact;
- repeated factless recall answers cannot displace an older attributed fact;
- time, location, identifier, code-word ownership, and neutral factual outcomes do not regress.

Run the focused Sims backend tests, the complete Sims adapter suite, the complete Core suite,
Python compilation, and whitespace checks. The remaining live matrix asks an uninformed Sim the
preference and conflict questions, then repeats all four informed-pair questions after a
backend/game restart.

## Non-Goals

- Adding embeddings or another model call.
- Creating category-specific synonym tables.
- Guaranteeing perfect semantic retrieval from every provider.
- Rewriting or migrating stored historical records.
- Expanding relationship effects, social categories, or visual behavior.
