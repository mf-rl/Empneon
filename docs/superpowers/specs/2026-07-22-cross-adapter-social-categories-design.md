# Cross-Adapter Social Categories Design

## Goal

Make an Empneon conversation behave like a real game social interaction: classify the initiating
actor's message, generate a state-grounded response from the roleplayed actor, choose one semantic
response category, map it to a native adapter action, and let the game determine the actual
relationship outcome.

The first Sims implementation supports the five social categories exposed to players:

- `friendly`
- `funny`
- `romance`
- `mean`
- `mischief`

The Sims `Actions` menu is excluded because it is not a social category.

## Authority boundary

The model chooses meaning and wording. The adapter and game own state changes.

- Empneon classifies the incoming message.
- The model chooses the responding actor's primary category, tone tags, dialogue, emotion, memory,
  and Empneon-owned trust proposal.
- Empneon derives a common action from the response category. The action is not an independent
  model choice.
- The game adapter maps the common action to a native mechanic.
- The game validates and executes that mechanic.
- The adapter observes and reports the resulting relationship values.

Models do not propose friendship or romance deltas. Those values remain observations from the
authoritative game or adapter rules. Existing provider responses containing such deltas are
accepted during compatibility handling but the values are ignored.

## Common social contract

The common category vocabulary is:

```text
friendly | funny | romance | mean | mischief
```

The conversation request supplies:

```json
{
  "incoming_category": "romance",
  "available_response_categories": [
    "friendly",
    "funny",
    "romance",
    "mean",
    "mischief"
  ],
  "speaker_state": {},
  "listener_state": {}
}
```

The Speaker is the actor roleplayed by the model and responding to the message. In the player-started
Sims flow, active Sim A is the Listener who supplied the message, and Sim B is the Speaker who
answers.

Each actor state uses the existing game-neutral `AgentStateSnapshot` shape. Both snapshots include
available identity, age, traits, affect, needs, buffs/effects, goals, and a directed relationship
entry for the other actor. A-to-B and B-to-A friendship, romance, trust, and attraction may differ.
Unavailable fields remain absent rather than being converted to neutral.

The model response supplies:

```json
{
  "response_category": "romance",
  "tone_tags": ["playful", "hesitant"],
  "dialogue": "A date? Maybe—but only if you can keep me laughing.",
  "expressed_emotion": "playful",
  "intent": "accept_playfully",
  "trust_delta": 1,
  "memory": {
    "importance": 0.6,
    "summary": "Sim A invited Sim B on a date and Sim B accepted playfully."
  }
}
```

`response_category` is exactly one common category. `tone_tags` contains zero to three lowercase
descriptive identifiers; extra or malformed tags are rejected. Tone tags never cause multiple
native actions. Empneon derives one action token:

```text
social.friendly
social.funny
social.romance
social.mean
social.mischief
```

## Classification and response choice

Empneon uses a hybrid flow:

1. A deterministic, game-neutral classifier identifies the incoming category from Sim A's message.
   Explicit romance, humor, insults, and mischief take precedence; ordinary, informational, or
   ambiguous social messages default to `friendly`.
2. The model receives the incoming category and the complete normalized state for both actors.
3. The model chooses Sim B's response category independently. A romantic invitation does not force
   romantic acceptance.
4. Empneon validates the response and derives the common action from the response category.

The responding actor's decision is grounded in this priority order:

1. Age, identity, consent, and game-valid relationship constraints.
2. The Speaker's directed relationship and attraction toward the Listener.
3. Current mood, buffs/effects, needs, and goals.
4. Traits, personality, and values.
5. Memories, conversation history, and the current message.

Examples for the same romantic invitation include:

- `romance` with `playful` tone for a playful acceptance.
- `romance` with `reserved` tone for a restrained acceptance.
- `friendly` for a gentle boundary.
- `funny` for a joke that does not reciprocate romance.
- `mean` for a hostile rejection.
- `mischief` for a teasing or deceptive deflection.

Attraction influences openness but never implies consent, requires romance, or overrides age,
traits, mood, memories, relationship history, or the current message.

## Response validation

Empneon keeps one source of truth: `response_category` determines the common action.

- A category outside the advertised set is invalid.
- A model-provided legacy `suggested_action` cannot override the derived action.
- A high-signal semantic contradiction between dialogue and category triggers one retry. Examples
  include explicit romantic reciprocation marked `friendly`, or explicit refusal marked `romance`.
- If the retry still conflicts, Empneon preserves a safe grounded dialogue response but emits no
  native action.
- Subtle dialogue without a high-signal contradiction keeps the model's category so deterministic
  keywords do not erase personality nuance.

The existing dialogue grounding rules remain active: identity correctness, no unsupported facts,
no role reversal, no substantial copying, preserved concrete player facts, and natural use of
needs and traits.

## Adapter portability

Each adapter advertises the subset of common categories it can execute. The common contract does
not require a particular relationship system.

- A game with native socials maps common action tokens to its own interactions.
- A game with reputation or affinity maps them to its authoritative dialogue mechanics and reports
  observed results.
- A game with adapter-owned relationship rules executes those rules in the adapter, then reports
  the result.
- A game without relationship mechanics can use category and tone for dialogue while reporting no
  relationship change.

Unsupported categories remain valid dialogue semantics but produce no native action. Game-specific
categories may be retained in adapter `native` metadata without expanding the initial common
five-category vocabulary.

## The Sims 4 mapping and execution

The Sims adapter advertises all five common categories when their native affordances are loaded.
It uses one explicit five-entry mapping from common action token to a stable base-game targeted
social affordance:

```text
social.friendly  -> friendly_chat
social.funny     -> funny_chat
social.romance   -> flirt
social.mean      -> mean_chat
social.mischief  -> mischief_chat
```

Each adapter action key maps to one exact tuning name in `NATIVE_SOCIAL_TUNINGS`. The adapter does
not infer mappings from arbitrary tuning-name fragments or mod statistics. A missing exact tuning
causes that category to be omitted from the advertised executable set.

For a player-started interaction:

1. Active Sim A selects **Empneon Social** with Sim B.
2. The adapter captures both actors' current state and both relationship directions.
3. The backend classifies A's message and the model generates B's response.
4. The response is displayed and delivery is acknowledged.
5. Empneon derives one common action and the adapter resolves its exact native affordance.
6. The adapter asks the game to test, create, queue, and execute that native interaction.
7. The game determines acceptance, rejection, failure, and relationship effects.
8. On natural completion, the adapter compares native friendship and romance before and after and
   reports only observed differences.
9. The session continues or closes after action-result confirmation.

Selecting Empneon Social authorizes this one response cycle, so the valid mapped action executes
automatically after dialogue delivery. The game still owns affordance tests and outcomes. A
romantic response therefore initiates a real romantic Sims interaction; it does not directly add
romance points.

## Compatibility

- Existing agent snapshots, native relationship observations, memories, and databases require no
  migration.
- Provider response parsing accepts `friendship_delta`, `romance_delta`, legacy
  `player_interaction_kind`, and legacy `suggested_action` throughout the `0.3.x` line, but ignores
  them for classification, action, and native relationship authority. They are removed at the next
  breaking response-contract version.
- `trust_delta` remains model-proposed, bounded, and committed only after dialogue is displayed.
- Existing concrete Sims action records remain readable. New dialogue decisions derive their
  adapter action from `response_category`.
- Existing attraction remains observation-only.

## Failure handling

- Invalid or unavailable response category: retry once, then dialogue-only fallback.
- Missing exact Sims affordance: display dialogue, report the unavailable mapping, and apply no
  friendship or romance change.
- Native affordance test, factory, queue, or execution failure: report a failed action result and
  invent no consequence.
- Native interaction rejection or completion with no score change: preserve the actual zero delta.
- Cancellation before delivery: suppress dialogue, action, trust, and memory.
- Cancellation after delivery but before native completion: cancel the owned interaction and
  report failure without relationship consequences.
- Duplicate delivery or action results remain idempotent.

No failure path silently substitutes a different social category, because that could make the game
perform an action that contradicts the generated response.

## Verification

Automated tests cover:

- Deterministic classification of all five incoming categories and friendly default behavior.
- The same incoming category producing different response categories based on actor state.
- Both directed actor snapshots reaching the model with identity, age, traits, moodlets/effects,
  relationship, and attraction.
- Exactly one primary category plus multiple tone tags.
- Derivation of the common action from the response category.
- Romantic acceptance deriving `social.romance` and explicit rejection never doing so.
- Ignoring conflicting legacy action and friendship/romance delta fields.
- One retry for category/dialogue contradiction and actionless fallback after a second conflict.
- The explicit five-entry Sims mapping and advertised-category filtering.
- Native execution only after dialogue acknowledgement.
- Successful, rejected, failed, canceled, and zero-delta native outcomes.
- Friendship and romance changing only from observed adapter results.
- Trust changing only after displayed dialogue.
- A synthetic non-Sims adapter using the same common action contract.

The live Sims Test 5 captures one message and response for each category, the chosen tone tags,
derived common action, exact native affordance, finishing result, and before/after directed
relationship values. Romantic acceptance must launch a native romantic affordance, but the test
does not require the game to award romance when its own tests or outcome reject it.

## Deferred work

Multiple native actions per response, selection among many affordances within one category,
game-specific additions to the common vocabulary, autonomous mixed-category chains, and model-owned
friendship or romance simulation remain outside this change.
