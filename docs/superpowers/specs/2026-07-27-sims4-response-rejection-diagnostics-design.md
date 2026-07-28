# Sims 4 Response Rejection Diagnostics Design

**Status:** Implemented, automated-verified, and live funny/mischief responses captured

## Goal

Persist the reason for each rejected LM Studio dialogue attempt when both attempts fail and the
Sims 4 adapter returns deterministic fallback dialogue. Expose those reasons with the completed
decision in the existing timeline diagnostic.

## Root Cause

`HermesRuntime.dialogue()` computes a grounding, category, or role-confusion reason for every
rejected response and writes it to the backend log. After the second rejection it returns
`reasoning_fallback_response()` without carrying those reasons forward. The resulting Core
decision and action record therefore have no link to the rejected attempts, and
`/diagnostics/timeline` can show only the accepted fallback decision.

## Design

Collect one request-local diagnostic for each rejected attempt:

```json
{"attempt": 1, "reason": "dialogue copies the current input"}
```

Attempt numbers are one-based. Reasons use the same normalized text already selected for the
warning log:

- the grounding issue;
- otherwise the response-category issue;
- otherwise `speaker/listener confusion`.

After both attempts are rejected, attach the two diagnostics to the private response dictionary
returned by `HermesRuntime.dialogue()`. The Sims adapter's decision conversion ignores this
private field. The `chat()` orchestration captures it and, after the decision ID exists, stores:

```json
{
  "response_rejections": [
    {"attempt": 1, "reason": "first reason"},
    {"attempt": 2, "reason": "second reason"}
  ]
}
```

in `DocumentMemoryStore` under namespace `thesims4.response-rejections`, keyed by decision ID.
This reuses the existing Core-owned document store for adapter extensions and requires no schema
migration or new dependency.

The Sims timeline diagnostic starts with `agent_timeline()` and decorates matching decision
entries with:

```json
{
  "diagnostics": {
    "response_rejections": [
      {"attempt": 1, "reason": "first reason"},
      {"attempt": 2, "reason": "second reason"}
    ]
  }
}
```

Core's generic timeline API remains unchanged. Only the Sims
`/diagnostics/timeline?sim_id=...` response includes the adapter-owned diagnostic.

## Data Flow

```text
model attempt
    |
    +-- accepted ----------------------> normal response
    |
    +-- rejected --> reason collected --> retry
                                         |
                                         +-- accepted --> normal response
                                         |
                                         +-- rejected --> deterministic fallback
                                                           |
                                                           v
                                                decision ID assigned
                                                           |
                                                           v
                                              adapter document persisted
                                                           |
                                                           v
                                              Sims timeline decoration
```

## Privacy and Failure Behavior

- Persist only the attempt number and normalized rejection reason.
- Do not persist prompts, raw model replies, schemas, conversation text, or provider credentials.
- Do not expose the private diagnostic field in the player-facing `/chat` response.
- Persist nothing when the first or second model response is accepted.
- Provider transport and parsing failures retain their current behavior.
- A missing or malformed diagnostic document is ignored so timeline inspection remains available.
- Diagnostics follow the decision's existing database and save-slot lifecycle.

## Compatibility

- No Core contract, database schema, provider API, configuration, or Sims script-mod change.
- No change to response validation, retry prompting, fallback selection, relationship outcomes,
  native actions, or usage accounting.
- Existing Core timeline and replay output remains unchanged.

## Verification

Automated tests must prove:

- two rejected attempts produce the deterministic fallback and two ordered reason records;
- an accepted retry persists no rejection diagnostic;
- the private diagnostic field is absent from the player-facing response;
- after dialogue delivery completes the decision, the Sims timeline exposes both reasons;
- reopening the database preserves the diagnostic;
- diagnostic data contains no raw provider dialogue or prompt text;
- missing or malformed stored diagnostics do not break the timeline;
- the complete Sims adapter and Core suites still pass.

## Non-Goals

- Persisting raw provider responses or prompts.
- Changing rejection rules or making funny and mischief responses pass validation.
- Adding a new general-purpose Core diagnostics schema.
- Displaying rejection details in the game UI.
