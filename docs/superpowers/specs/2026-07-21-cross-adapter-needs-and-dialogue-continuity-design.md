# Cross-Adapter Needs and Dialogue Continuity Design

## Goal

Let each game describe both actors' current needs in a common form, let the model use that state
naturally, and prevent Empneon from replacing valid dialogue merely because a need was not named.
Retries must also retain enough conversation context to avoid repetitive replies.

## Common need contract

The existing `AgentStateSnapshot.needs` mapping remains the cross-adapter boundary. Each need uses:

```json
{
  "hunger": {
    "level": 0.62,
    "urgency": 0.38,
    "status": "satisfied",
    "native": {"value": 24, "minimum": -100, "maximum": 100}
  }
}
```

- `level` and `urgency` remain normalized to `0.0..1.0` for every game.
- `status` is one of `satisfied`, `low`, or `critical`.
- The adapter owns the conversion and thresholds because only it understands the native game.
- `native` preserves optional diagnostic values without making Core or the model depend on them.
- Unsupported or unreadable needs are omitted rather than invented.

For The Sims 4, the adapter preserves the native `-100..100` motive value instead of clamping it.
It maps the observed game bands as follows:

- `-25..100`: `satisfied`;
- `-50..-26`: `low`;
- `-100..-51`: `critical`.

Normalization converts the full native range to `level 0.0..1.0`; `urgency` is its inverse. A game
using `0..100`, discrete states, or different thresholds supplies the same common fields using its
own rules.

## Both-actor context

The game request continues to carry state for the Speaker and Listener. The backend builds and
labels a normalized current-state snapshot for each actor, including identity, traits, affect,
needs, and effects. The prompt identifies which actor is roleplayed and which actor wrote the
message, while allowing the Speaker to respond with awareness of both actors' condition.

## Model-first need behavior

Need state guides generation; it does not prescribe dialogue:

- `satisfied` needs may color a reply only when conversationally relevant;
- `low` needs may motivate a natural suggestion, such as getting food or resting;
- `critical` needs should strongly influence urgency and may redirect the conversation;
- the prompt asks for in-world language rather than metric names, numeric values, or phrases such
  as "my hunger need is critical";
- the model may continue the current topic even when a need is critical.

Empneon accepts a structurally valid, role-correct, non-copying model response even when it omits a
need. Need omission no longer triggers retry or deterministic replacement. Existing validation for
invalid structured output, role confusion, unsupported recalled facts, and substantial copying
remains.

If provider generation fails completely, the deterministic fallback stays relevant to the current
message. It does not override the conversation with a need report. Need-aware wording is optional
and uses the common status rather than game-specific thresholds.

## Dialogue continuity and repetition

Recent player inputs and model replies remain visible during a repetition retry. The correction
asks the model to advance the exchange with a new reaction, detail, question, or decision and to
avoid previous wording and openings. The existing deterministic similarity check remains the
guard; no embeddings, extra model, random phrase engine, or dependency is added.

This supersedes the retry rule in
`2026-07-21-cross-adapter-identity-and-dialogue-variety-design.md` that removed recent conversation
text after a copying failure.

## Compatibility and persistence

The contract keeps the existing normalized `level` and `urgency` fields. Readers that ignore the
new `status` and `native` entries continue to work. No database migration is required because
snapshots are JSON-compatible records and current observations replace current transient state.

## Verification

Tests cover:

- Sims motive extraction preserves negative native values;
- Sims boundary values map to the three statuses and normalized range correctly;
- a synthetic adapter can represent a different native scale with the same common fields;
- both actors' affect, needs, effects, identity, and traits appear in dialogue context;
- a valid model reply is not rejected merely for omitting a low or critical need;
- prompts describe need severity without exposing game metrics as dialogue;
- repetition retries retain recent conversation and request a new conversational direction;
- copied current inputs, earlier inputs, and earlier replies remain rejected;
- provider failure produces a topic-relevant fallback rather than a forced need report.

## Deferred work

Per-need localization, configurable thresholds in Core, semantic repetition embeddings, and a
generated library of need-specific phrases are deferred until an adapter demonstrates a concrete
case the common status and normalized values cannot represent.
