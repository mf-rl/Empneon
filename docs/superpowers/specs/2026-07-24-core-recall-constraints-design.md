# Core Recall Constraints Design

**Status:** Implemented; automated and live save/reload recall verification passed

## Problem

Empneon's recall path currently analyzes the same question independently in
several places. Retrieval recognizes `when`, dialogue grounding recognizes a
different subset, and supported-fact selection uses lexical overlap for other
forms. This caused two related failures:

- `When is it happening?` retrieved the correct fact but accepted the partial
  answer `tonight` without the supported specific time `7pm`.
- `What time are we having our date?` was classified as generic `what`.
  Recent factless recall answers outranked the authoritative date fact, so the
  invented answer `first Saturday at 10 AM` received no grounding check.

Adding another phrase-specific condition would leave the duplicated analysis
intact.

## Architecture

Add a small provider-independent module at
`core/src/empneon/core/memory/recall.py`. It owns recall-question analysis,
evidence-slot matching, temporal normalization, and response constraint
validation. It consumes ordinary text and actor-attributed facts; it has no
game, provider, model, database, or prompt dependencies.

The Sims adapter remains responsible for obtaining episodic events and
building dialogue. It calls the same Core analysis result during deterministic
retrieval, semantic-selection fallback protection, supported-fact selection,
and final response validation.

## Core Contracts

### RecallQuery

An immutable `RecallQuery` contains:

- `explicit`: whether the message asks to recall prior information;
- `requested_slots`: a frozen set initially containing `time` and/or
  `location`.

`analyze_recall_query(text)` recognizes equivalent forms, including:

- time: `when`, `what time`, `which time`, `what day`, and `what date`;
- location: `where`, `what place`, and `which place`;
- explicit recall cues such as `remember`, `recall`, and `did I say`.

The slot classification is shared. Retrieval and validation must not perform
their own competing question classification.

### Attributed facts

Core accepts facts shaped as:

```python
{"actor_id": "<stable actor ID>", "statement": "<verbatim fact>"}
```

`fact_supports_query(fact, query)` returns true when the fact supplies at
least one requested slot. A temporal fact supports a time query even when the
question and fact share no ordinary words.

The existing adapter authority filter remains responsible for excluding
generated recall answers from evidence. Core does not rewrite or migrate
stored facts.

### Temporal normalization

`temporal_values(text)` extracts normalized values without external
dependencies:

- clock time as minutes after midnight, so `7pm`, `7:00 PM`, and
  `seven o'clock PM` can compare as `1140`;
- relative labels such as `today`, `tonight`, `tomorrow`, and `yesterday`;
- weekdays.

The initial word-number vocabulary covers one through twelve for clock
expressions. Unknown temporal prose is left unclassified rather than guessed.

### Response validation

`validate_recall_response(query, facts, response, speaker_id, listener_id)`
returns an empty string when grounded or a stable issue message when not.

For a requested time slot:

- authoritative facts with a clock time require the response to contain an
  equivalent clock time;
- a different clock time is a conflict;
- an unsupported relative day or weekday is a conflict;
- when no clock time exists, the response must contain a supported relative
  day or weekday;
- a response may omit less-specific values when it includes the supported
  clock time. Thus `7pm` is sufficient for `tonight at 7pm`.

For attributed possessive locations:

- a listener-owned `my place`, `my home`, or `my house` may become
  `your ...`, a named-owner phrase, or an explicitly attributed quotation;
- the same rule applies symmetrically for speaker-owned locations;
- an answer that does not mention location is unaffected.

An answer must never introduce conflicting structured values merely because
it also contains one supported value.

## Retrieval Flow

The adapter performs these steps for an explicit recall:

1. Analyze the message once with `analyze_recall_query`.
2. Apply the existing authority filter to every candidate event.
3. Mark facts with `fact_supports_query`.
4. If any authoritative fact satisfies a requested slot, rank and select
   supporting fact-bearing events ahead of factless generated recall replies.
5. Preserve factless exchanges only as conversational context; they do not
   become supporting evidence.
6. If semantic selection returns only factless events while deterministic
   retrieval found supporting facts, retain the deterministic evidence.

This makes repeated recall questions converge on the original evidence rather
than on previous generated answers.

## Dialogue Flow

The adapter passes the same analyzed query and supporting facts to Core
validation. A model response that omits or contradicts required values enters
the existing correction-and-retry path. The correction includes attributed
evidence.

After failed retries, the existing attributed quotation fallback is returned.
This path is deterministic and works for providers with or without structured
output.

## Compatibility

The change must preserve:

- ordinary non-recall dialogue;
- valid natural paraphrases of supported times;
- correct location perspective and attributed quotations;
- time-only answers that omit an unasked location;
- supported answers generated by any model or provider;
- response categories, endearments, relationship behavior, usage telemetry,
  memory persistence, and action confirmation;
- stored event and fact schemas.

Core exposes pure functions only. No provider configuration, game terminology,
or Sims-specific conditions enter the new module.

## Testing

Core unit tests cover:

- equivalent time and location question forms;
- `7pm`, `7:00 PM`, and worded clock normalization;
- authoritative fact-slot matching;
- exact supported time acceptance;
- partial `tonight` rejection when `7pm` is known;
- invented `10 AM` and unsupported `Saturday` rejection;
- relative-only facts;
- symmetric location ownership, named ownership, quotations, and omission.

Sims adapter tests cover:

- `what time` retrieval selecting the original `7pm` fact over recent
  factless recall answers;
- the live two-turn sequence;
- invalid provider responses entering retry and attributed fallback;
- existing `when`, location, quotation, and non-recall behavior.

Verification includes the focused tests, complete Sims and Core suites, CI
Ruff scope, backend compilation, mod build, and `git diff --check`.

## Non-Goals

- General-purpose natural-language understanding.
- Calendar arithmetic or resolving a relative date against the game clock.
- Inferring facts absent from authoritative memory.
- Replacing semantic memory selection.
- Migrating or deleting prior generated recall events.
