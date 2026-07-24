# Attributed Recall and Provider Usage Design

**Status:** Implemented; live attributed recall and persisted CLOD 2/CLOD 3 usage verified

## Goal

Keep recalled facts attached to their original actor through prompting,
validation, correction, fallback dialogue, and persistence. Also account for
completed semantic-selection provider calls in the same provider-neutral usage
telemetry as dialogue generation.

The fix must remain independent of any game, provider, model, or natural
language.

## Confirmed Failure

Bernard told Karmine:

`Tonight, 7pm, at my place. Does it sound good? I promise I'll make you feel in heaven.`

The confirmed memory correctly stored Bernard as the fact's actor. The initial
dialogue prompt also rendered the evidence as a statement made by Bernard.
After two generated answers failed the time-evidence check, however, Empneon
returned the fact statement verbatim as Karmine's fallback response. That made
Karmine claim Bernard's `my place` as her own.

The delivered fallback was then confirmed as a new time-bearing fact attributed
to Karmine. The database consequently contains both the original
Bernard-attributed statement and a derivative Karmine-attributed duplicate.

The same turn completed three LM Studio calls: one semantic-memory selection and
two dialogue attempts. Only the two dialogue attempts were recorded in
`cognition_usage` because semantic selection runs before the existing
generation-attempt collector is installed. Raw provider responses are not
persisted, and the provider log records validation warnings rather than every
successful request.

## Design Principles

1. Actor attribution is part of evidence, not display metadata.
2. Recall answers are derivative conversation, not new authoritative facts.
3. Fallback dialogue must remain truthful without language-specific pronoun
   rewriting.
4. Provider accounting uses Core provider result metadata and does not depend on
   a particular transport.
5. Raw prompts and responses remain unpersisted by default.

## Structured Recall Evidence

Supported recall evidence remains structured as:

```json
{
  "actor_id": "original-actor-id",
  "statement": "original statement"
}
```

Filtering and validation may inspect the statement, but they must not replace
the evidence object with a bare string.

The existing initial recalled-history rendering remains unchanged: it labels
each statement with the resolved actor name. Correction prompts use the same
attributed form instead of appending an unlabeled statement.

The time-answer validator continues comparing time values from the evidence
statements with the generated dialogue. It does not change selection, privacy,
pair scoping, or what counts as a supported answer.

## Perspective-Safe Fallback

If both generated attempts fail or the provider becomes unavailable, the
fallback renders the source relationship explicitly:

- Evidence from the Listener: `You told me: "<statement>"`
- Evidence from the Speaker: `I remember saying: "<statement>"`
- Evidence from another known actor: `<Actor name> said: "<statement>"`
- Evidence from an unresolved actor: `I remember this: "<statement>"`

Quoting preserves the original statement without pretending its first-person
words belong to the responder. Empneon will not attempt `my`/`your`
replacement, because that would be language-specific and unreliable for
names, quotations, plural speakers, possessives, and provider-generated text.

The fallback remains a normal schema-valid response with the existing neutral
relationship behavior. It does not alter response categories, actions,
animation, trust, or native relationship effects.

## Recall-Derived Fact Protection

When the incoming message is a recall question, the responder's answer remains
available as conversational history but is not promoted to a new authoritative
durable fact. Facts explicitly asserted in the incoming player message retain
their existing eligibility.

This rule applies in two places:

1. New confirmed recall interactions do not create a responder-attributed fact
   from the generated or fallback dialogue.
2. Retrieval omits responder-attributed facts already stored on legacy
   confirmed recall interactions.

The second rule neutralizes the existing Karmine-attributed duplicate without
editing or deleting live database rows. The interaction and dialogue remain
available for history, diagnostics, and audit.

This is a general provenance rule: an answer that merely recalls existing
evidence cannot become stronger evidence than its source. It contains no Sims,
date, romance, location, or provider-specific condition.

## Complete Provider Usage Accounting

Semantic memory selection continues to use the configured `small` task and the
same provider router. Its completed `GenerationResult` is collected before
dialogue generation and recorded after the interaction's cognitive request and
event exist.

The selector record uses its own task configuration and CLOD 2 estimate. Main
dialogue attempts retain the selected dialogue CLOD and their current records.
All records share the interaction request and event identifiers, allowing one
turn to show selector plus dialogue calls without a schema migration.

Provider failures continue through existing error logging and deterministic
fallback behavior. Only completed calls with a `GenerationResult` have actual
token and latency measurements.

Usage telemetry stores provider, model, CLOD, estimates, actual token counts,
and latency. It does not store prompt or response bodies. Raw content remains
visible only through provider tooling unless a separate, explicit,
privacy-reviewed diagnostic feature is designed later.

## Compatibility Boundaries

- Preserve the grounded-over-factless semantic precedence guard.
- Preserve grounded semantic selection and legacy factless semantic selection
  when deterministic recall is also factless.
- Preserve candidate limits, confirmation gating, pair privacy, save/reload
  behavior, and game-agnostic actor identifiers.
- Preserve fresh model-generated answers when validation succeeds.
- Preserve uncertainty for unsupported recall questions.
- Preserve structured-output schemas, category normalization, relationship
  outcomes, animations, portraits, and floating icons.
- Add no provider-specific request format or Sims-specific memory rule.
- Do not mutate the running database or delete historical events.
- Do not persist raw prompts or model responses.

## Tests

Regression coverage will prove:

- Supported evidence retains its actor while time validation still uses its
  statement.
- A correction prompt identifies the actor who supplied the fact.
- Repeated generation failure returns an explicitly attributed quote rather
  than presenting another actor's first-person statement as the responder's.
- Provider failure uses the same perspective-safe fallback.
- A confirmed recall response does not create a responder durable fact.
- A fact asserted in an incoming recall-shaped message can still be retained.
- Retrieval ignores legacy responder facts derived from recall answers while
  retaining their conversation history.
- Existing grounded, factless, unsupported, privacy, and confirmation behavior
  remains covered.
- A provider-backed turn with semantic selection records both the selector and
  dialogue generation results with provider-neutral metadata.
- Raw prompt and response bodies are absent from usage telemetry.

Run focused recall and usage tests, the complete Sims adapter suite, Python
compilation, the complete Core suite, and the Sims source build.

## Live Verification

Restart only the source backend and repeat the existing date-recall question.
No new invitation, save reload, or mod installation is required.

The passing response must retain tonight at 7 pm and make clear that the
location belongs to Bernard, either naturally as `your place` from Karmine's
perspective or through an explicitly attributed quotation. A subsequent recall
must not treat Karmine's earlier faulty fallback as authoritative evidence.

`empneon.usage` must show the semantic-selection call as well as all completed
dialogue attempts for the turn.
