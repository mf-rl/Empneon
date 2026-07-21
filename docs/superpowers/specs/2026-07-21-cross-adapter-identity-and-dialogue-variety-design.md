# Cross-Adapter Identity and Dialogue Variety Design

## Goal

Give dialogue models enough normalized identity context to roleplay both actors correctly, and prevent replies that mirror the current input, earlier inputs, or earlier model replies.

## Normalized identity contract

`AgentStateSnapshot` gains an `identity` mapping. Adapters translate game-specific identity data into this common shape:

```json
{
  "gender": {"key": "male", "label": "Male"},
  "age": {"kind": "life_stage", "value": "young_adult", "label": "Young Adult"},
  "traits": [
    {
      "id": "trait_outgoing",
      "label": "Outgoing",
      "description": "Enjoys socializing and approaches conversations confidently."
    }
  ]
}
```

The identity record is intentionally game-neutral:

- `gender.key` is a stable normalized value; `gender.label` is display text.
- `age.kind` explains how to interpret `age.value`. The Sims 4 uses `life_stage`; games with chronological ages can use `years`.
- `traits` contain stable IDs, labels, and optional behavioral descriptions. An adapter may omit a description when its game API does not provide one.
- Missing or unreadable values become `unknown`; Empneon must not invent them.
- Original game identifiers and labels remain available under `native.identity` for diagnostics and adapter-specific behavior.

The Sims 4 adapter maps the game's gender and age enums to stable labels such as `male`, `female`, `teen`, `young_adult`, `adult`, and `elder`. It must not treat an enum ordinal as chronological years.

## Prompt behavior

The dialogue prompt shows normalized identity for both the Speaker and Listener. It explicitly assigns their roles and instructs the model to:

- use the Speaker's traits to influence tone, preferences, confidence, boundaries, and choices;
- combine traits with current mood, needs, relationship, memories, and the current message;
- avoid merely naming or caricaturing traits;
- use gendered relationship terms only when supported by the supplied identity;
- avoid guessing gender or age when either is unknown;
- answer the current message without restating or closely paraphrasing it;
- produce a reply distinct from all recent player inputs and model replies.

Trait interpretation remains adapter-owned. Empneon Core stores and transports normalized trait records without hard-coding The Sims 4 trait catalog.

## Anti-mirroring validation

After generation, the backend compares normalized dialogue words against:

1. the current player input;
2. every recent player input in the conversation window;
3. every recent model reply in the conversation window.

Names are excluded from similarity scoring. Small necessary facts such as dates, places, and relationship terms may recur, but substantially copied or lightly paraphrased sentences are rejected. Romantic requests receive no exemption.

The existing deterministic word-sequence comparison remains the first implementation. Its threshold is tightened from `0.8` to `0.72` for inputs with enough words to establish meaningful similarity. This avoids adding embeddings, another model call, or a new dependency.

On rejection, the model receives one explicit correction and retries without recent conversation text that could encourage copying. If the second response still mirrors or confuses roles, the existing grounded fallback produces a distinct reply.

## Data flow

1. A game adapter reads each actor's native gender, age representation, and traits.
2. The adapter emits normalized `identity` plus the original values in `native.identity`.
3. `AgentStateSnapshot` validates that identity is JSON-compatible and carries it through events and persistence.
4. The Sims backend includes Speaker and Listener identity in dialogue context and prompts.
5. The model generates a structured response.
6. Role-confusion, grounding, and anti-mirroring checks accept the response or request one correction.

Existing stored agents require no migration. Fresh game observations supply the normalized identity snapshot; legacy numeric Sims age ordinals are no longer presented as years.

## Failure handling

- Missing Sims API properties produce `unknown` identity fields without blocking dialogue.
- A malformed trait entry is skipped independently so one modded trait cannot erase the remaining identity data.
- Unknown identity prevents unsupported gender or age assumptions in the prompt.
- Persistent mirroring after one retry uses a grounded fallback rather than returning copied dialogue.

## Verification

Tests cover:

- `AgentStateSnapshot` identity serialization and JSON validation;
- The Sims 4 gender, life-stage, trait, unknown-value, and modded-trait extraction;
- preservation of native identity values;
- Speaker and Listener identity in prompts;
- trait-guided prompt instructions;
- rejection of the recorded Bernard/Karmine romantic-message mirror;
- rejection of reused earlier inputs and replies;
- acceptance of distinct replies that repeat only necessary facts such as `Saturday`;
- unchanged autonomous action availability and held Empneon Social behavior.

## Deferred work

Semantic embeddings, a universal trait ontology, generated pronoun sets, and exact chronological Sims ages are deferred until a game supplies a concrete need that the normalized records cannot represent.
