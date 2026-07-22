# Cross-Adapter Attraction Design

## Goal

Let game adapters report one actor's current attraction toward another actor in a common form so
Empneon dialogue can account for chemistry without making Core depend on The Sims 4, Lovestruck,
or a specific mod.

## Common contract

`AgentStateSnapshot.relationships[target_id]` gains an optional `attraction` number in
`-1.0..1.0`:

```json
{
  "relationships": {
    "target-id": {
      "affinity": 0.14,
      "romance": 0.0,
      "trust": 0.5,
      "attraction": 0.75
    }
  }
}
```

- Attraction is directed: A's attraction toward B may differ from B's attraction toward A.
- `-1.0` is strong aversion, `0.0` is neutral, and `1.0` is strong attraction.
- An unavailable or unreadable value is omitted; absence is not converted to neutral.
- Attraction is observed game context. Models may not propose or directly mutate it.
- The adapter preserves the selected source, native value, and native label under its existing
  `native` snapshot data.

Core validates the optional range and otherwise treats attraction like the existing normalized
relationship context. The latest snapshot and event history provide persistence; the typed Core
relationship table remains unchanged, so no database migration is required.

## Sims source selection

The Sims adapter uses a small ordered resolver chain:

1. Explicitly supported and detected mod attraction readers.
2. The official Lovestruck attraction reader.
3. No attraction field when neither source is available.

A supported mod reader returns `None` when its module/API is unavailable or it has no value for the
pair. The first valid result wins. This makes a supported mod override the official system without
guessing from statistic names. If multiple supported mods are installed, their documented resolver
order is deterministic and the selected source is logged and retained in native diagnostics.

Arbitrary mods are not interpreted automatically. Supporting another mod requires one explicit
reader that maps its documented native value to the common range. A reader failure is isolated;
the adapter continues to the next reader and ultimately the official source.

## Model behavior

The dialogue context labels the value as the Speaker's attraction toward the Listener and explains
the common scale. Attraction may influence warmth, hesitation, boundaries, or romantic openness.
It does not require flirtation, imply consent, prove an established romance, or override identity,
current mood, memories, relationship history, or the player's message.

Provider-free fallback remains conservative. It may use attraction only to choose compatible tone;
it does not invent romantic consequences.

## Authority and data flow

1. The Sims adapter reads the current Speaker-to-Listener attraction from the highest-priority
   available supported source.
2. It normalizes the value to `-1.0..1.0` and preserves native evidence separately.
3. `Sims4Adapter.agent_state()` places the value in the directed common relationship entry.
4. Core validates and persists the snapshot without knowing which game or source produced it.
5. The backend supplies the normalized directed relationship to the model.
6. Only a later game observation may change attraction.

## Failure handling

- Missing Lovestruck content produces no official value rather than an error.
- Missing or incompatible mod APIs fall through to the next source.
- Invalid, non-finite, or out-of-range source values are rejected by that reader; they are never
  silently presented as neutral.
- One actor direction may be present while the reverse direction is absent.
- Logs identify the selected source or that no supported source was available, without logging
  private conversation text.

## Verification

Tests cover:

- Core accepts in-range attraction and rejects invalid or out-of-range values.
- Snapshot JSON round-trip preserves attraction and native source metadata.
- Official Sims attraction is normalized correctly.
- A supported mod source overrides the official source.
- A failed or absent mod source falls back to official data.
- No source omits attraction instead of emitting zero.
- Actor A to B and B to A may differ.
- Sims dialogue context identifies Speaker-to-Listener attraction and its scale.
- Existing consent, grounding, and game-confirmation behavior remains unchanged.
- A synthetic non-Sims adapter can supply the same common field.

## Deferred work

Additional mod readers, attraction-reason taxonomies, Core-owned attraction history, and
model-proposed attraction changes remain deferred until a concrete integration requires them.
