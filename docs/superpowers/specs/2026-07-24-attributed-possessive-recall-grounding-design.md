# Attributed Possessive Recall Grounding Design

**Status:** Implemented; live perspective-safe recall passed

## Problem

Empneon correctly recalls that Bernard said, “Tonight, 7pm, at my place,”
and preserves Bernard as the fact's actor. When Karmine answers, however, the
current recall validator accepts any response containing the supported time.
It therefore accepts “at my place” from Karmine even though that reverses the
location's owner.

## Design

Add a deterministic, provider-independent check to the existing attributed
recall grounding path. When a supported fact contains a first-person
possessive location belonging to one actor, a response from the other actor
must not restate that location as the responder's first-person possession.

For a listener-attributed fact containing `my place`, `my home`, or `my
house`, the responder may:

- use second-person possession, such as `your place`;
- name the owner, such as `Bernard's place`;
- preserve the original wording inside an explicitly attributed quotation,
  such as `You told me: "at my place"`; or
- omit the location and answer only the requested detail.

The same rule applies symmetrically when the recalled fact belongs to the
responder: first-person possession is valid and second-person possession is
not.

An ownership conflict becomes a grounding issue. The existing model retry
receives a correction containing the attributed evidence. If retries remain
invalid, the existing attributed recall fallback supplies an unambiguous
quotation. Stored memories and their wording are never rewritten.

## Scope

The check is based on actor attribution and ordinary language, not Sims
relationships, locations, providers, models, or gameplay rules. It remains in
the current dialogue-grounding boundary and does not change Core memory
ownership or persistence.

The initial deterministic vocabulary is deliberately limited to `place`,
`home`, and `house`, where possessive inversion changes the factual owner.
Other possessions remain unchanged until a demonstrated case requires them.

## Compatibility

The fix must continue accepting:

- a correct `your place` response to a listener-owned location;
- a correct `my place` response to a responder-owned location;
- an explicitly attributed quotation containing the original `my place`;
- a time-only answer that does not mention location;
- non-recall dialogue and recall facts without supported location ownership;
- existing response-category, freshness, endearment, memory, and usage
  behavior.

## Testing

Use test-driven development:

- reproduce the live listener-owned fact with the invalid responder phrase
  `at my place` and verify it is rejected;
- verify `your place`, a named owner, an attributed quotation, and omission
  of location remain valid;
- verify the symmetric responder-owned case;
- verify failed model retries use the existing attributed fallback;
- run focused tests, the complete Sims adapter suite, the complete Core
  suite, CI Ruff scope, backend compilation, and mod build.

## Non-Goals

- Rewriting or migrating existing memories.
- Inferring physical ownership from game state.
- Adding provider-specific instructions or schema fields.
- General-purpose pronoun resolution.
