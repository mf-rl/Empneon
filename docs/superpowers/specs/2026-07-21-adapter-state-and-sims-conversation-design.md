# Adapter State and Sims Conversation Design

**Date:** 2026-07-21
**Status:** Approved design
**Scope:** Empneon Core contracts, shared adapter tests, and The Sims 4 adapter

## Goal

Let game adapters provide complete, current character context in a common form; let AI models
produce natural grounded dialogue and explicitly propose only actions the current game can
execute; and keep The Sims 4's Empneon Social interaction active until the player closes the
conversation.

The design separates three authorities:

- the adapter observes and translates game state;
- the model authors dialogue and proposes cognitive and native consequences;
- the game confirms native actions and native relationship changes.

## Requirements

1. Core accepts a versioned, JSON-compatible agent-state snapshot from every adapter.
2. The snapshot includes normalized cross-game semantics and namespaced, JSON-serializable native
   details without discarding unknown labels or values.
3. Temporary game state is available to the model and timeline without becoming permanent
   identity.
4. Grounded model dialogue is not discarded because its action metadata is imperfect.
5. The model sees and selects only actions available for the current request.
6. Model intent remains descriptive and does not secretly select a native action.
7. Every delivered dialogue turn can update confirmed Empneon cognitive state.
8. Sims friendship and romance change only from game-confirmed native results.
9. Empneon Social remains in the actor's queue through input, backend waiting, responses, child
   native actions, and repeated turns.
10. Manual queue cancellation closes the session, suppresses late UI, and resolves any late
    action proposal without consequences.

## Cross-Adapter Agent State

Core adds one `AgentStateSnapshot` contract with this JSON shape:

```json
{
  "schema_version": 1,
  "adapter": "sims4",
  "agent_id": "1048519419914027021",
  "affect": {
    "tags": ["uncomfortable", "embarrassed"],
    "valence": -0.6,
    "arousal": 0.4,
    "intensity": 0.75
  },
  "needs": {
    "hunger": {"level": 0.63, "urgency": 0.37}
  },
  "effects": [
    {
      "kind": "moodlet",
      "label": "Uncomfortably Wet",
      "polarity": "negative",
      "intensity": 0.6,
      "target_id": null
    }
  ],
  "relationships": {
    "other-sim-id": {
      "affinity": 0.07,
      "romance": 0.0,
      "trust": 0.5
    }
  },
  "goals": [],
  "intentions": [],
  "capabilities": {
    "actions": ["friendly_chat", "apologize", "flirt"]
  },
  "native": {
    "mood": "Mood_Uncomfortable",
    "buffs": [],
    "moodlets": [],
    "sentiments": []
  }
}
```

Every top-level key is present, but its section may be empty when the adapter cannot observe that
category. Common numeric values use stable ranges:

- `valence`: `-1.0..1.0`;
- `arousal`, `intensity`, need `level`, need `urgency`, romance, and trust: `0.0..1.0`;
- affinity: `-1.0..1.0`.

Labels, tags, effect kinds, need names, goal contents, and intention contents are open-ended.
Adapters normalize values they understand and preserve JSON-serializable identifiers, labels, and
primitive values for unknown DLC, mod, or engine state under `native`. Runtime game objects are
never serialized. Core does not contain Sims classes or require every adapter to populate every
category.

The Sims adapter dynamically extracts available mood, moodlet/buff, sentiment, need, aspiration,
goal, trait, skill, household, and directed relationship information. Unknown native values are
preserved rather than filtered out merely because Empneon lacks a mapping.

## State Persistence

Each observation carries the current snapshot into the event and model request. Core stores the
latest snapshot for diagnostics, replacing the previous current snapshot instead of accumulating
stale moodlets.

Durable normalized concepts continue to use their typed Core stores:

- identity and personality;
- directed relationships;
- lasting emotional state;
- goals;
- confirmed memories and beliefs.

Temporary effects remain in the event/timeline and latest snapshot. They do not become permanent
identity. Native details remain adapter-owned context even when Core stores their JSON snapshot.

## Model Context and Response

The dialogue prompt contains clearly labeled sections for:

1. normalized current state;
2. native adapter context;
3. relevant confirmed memories;
4. directed relationship state;
5. actions available for this request and a short meaning for each.

The response contract is:

```json
{
  "dialogue": "That's sweet! A date sounds like fun.",
  "expressed_emotion": "confident",
  "intent": "friendly but interested",
  "player_interaction_kind": "romantic_invitation",
  "suggested_action": "friendly_chat",
  "relationship": {
    "trust_delta": 1
  },
  "memory": {
    "importance": 0.75,
    "summary": "Bernard invited Karmine on a date."
  }
}
```

`intent` and `expressed_emotion` are descriptive model output. `suggested_action` is independent
and constrained dynamically to the request's available actions plus `none`. The adapter uses
`suggested_action`, not `intent`, for native execution.

The model's expressed emotion is recorded with the exchange. It does not overwrite the affect
observed from the game.

## Dialogue Validation and Proposal Sanitization

Dialogue and proposals are evaluated separately.

Dialogue may be retried or replaced only when it has an integrity failure:

- invalid structured output;
- speaker/listener role confusion;
- unsupported factual claims or denial of available supporting memory;
- observation-privacy violation;
- substantial copying of the player's message or reuse of a prior reply;
- failure to answer a direct state question from current critical state.

Romantic dialogue is not required to match a fixed accept/decline phrase list. A natural response
is returned even when its intent, relationship proposal, or action choice is non-romantic.

Proposal problems do not replace valid dialogue. Empneon sanitizes them:

- unavailable action becomes `none`;
- an unmistakable rejection paired with `flirt` becomes `none`;
- native relationship proposals are recorded as proposals but never applied directly;
- out-of-range cognitive deltas are clamped;
- unsupported relationship dimensions are discarded.

The current Core relationship model retains directed affinity/strength and trust. Respect and
resentment are removed from the model contract and `ai.relationship` output until Core implements
real semantics for them.

## Relationship Authority

Relationship output identifies its source:

- `friendship` and `romance` are last-observed Sims-native tracks;
- `trust` is an Empneon cognitive relationship value;
- model-native friendship or romance values are proposals only;
- confirmed Sims action results update native friendship and romance;
- a response displayed to the player confirms the cognitive dialogue turn and may apply a bounded
  Empneon trust delta, regardless of whether a later native action succeeds.

`ai.relationship` reports the direction of the edge and labels native versus Empneon values. It
does not synthesize unsupported metrics with neutral-looking defaults.

## Empneon Social Session Lifecycle

One game-side conversation session belongs to one `EmpneonSocialInteraction`. The interaction's
generator remains alive until the session closes, so the task stays visible and active in the
actor's queue.

The session state contains only what the asynchronous boundary needs:

- unique session and turn identifiers;
- actor and target references;
- transcript;
- current phase;
- pending backend result;
- cancellation/closed state.

The phases are:

```text
input
-> waiting_for_backend
-> showing_response
-> running_native_action (optional)
-> input (continue)
-> closed
```

For each turn:

1. The player submits text from the dialog.
2. The dialog closes, but Empneon Social remains active in the queue.
3. A worker performs the backend request while the game thread continues normally.
4. The response pump delivers the result to the matching live session on the simulation thread.
5. Valid dialogue is displayed. Displaying it confirms the cognitive turn and records its
   memory/trust consequence; cancellation before display records neither.
6. When the response dialog is dismissed, the selected native action runs as a child step of the
   session when it is not `none`.
7. The game-confirmed result updates native friendship/romance and closes the action proposal.
8. Continuing opens the next input within the same session. Cancel closes the session after any
   final selected native action completes.

The session does not queue several deferred socials. Each turn's optional native action completes
before the next turn starts. A `none` action is closed as a successful dialogue-only turn with no
native changes when its response is displayed.

## Cancellation and Failure Handling

Manual removal of Empneon Social from the queue:

- marks the session canceled;
- prevents further dialogs and native actions;
- ignores late response text in the UI;
- reports a late-created decision as failed/canceled with no applied changes;
- releases actor and target references.

If the actor or target leaves the active zone, the same cancellation path runs. Backend timeout or
provider failure is displayed inside the still-active session; the player may retry or close it.
No failure fabricates a confirmed memory or relationship change.

Only one Empneon Social session may be active per actor. Existing autonomous request limits remain
unchanged.

## Verification

### Shared Core and adapter contracts

- Snapshot JSON round-trip and version validation.
- Normalized range validation.
- Unknown native fields survive round-trip.
- An adapter may omit unsupported categories.
- Both Sims and Godot produce valid snapshots without Core importing game types.

### Sims state extraction

- Known moods, needs, relationship tracks, moodlets/buffs, and sentiments map correctly.
- Unknown DLC/mod values remain under `native`.
- Temporary effects replace the latest snapshot and remain in event history.
- Model context contains normalized and native current state.

### Dialogue and actions

- Karmine's observed `A date sounds like fun` response is returned unchanged with
  `friendly_chat` and zero romance.
- Descriptive intent does not control native action selection.
- Only request-available actions can be proposed.
- Invalid action metadata is sanitized without replacing dialogue.
- Explicit rejection never executes `flirt`.
- Native friendship/romance changes come only from the action-result payload.
- Confirmed turns may update bounded Empneon trust.

### In-game lifecycle

- Empneon Social remains active during backend waiting and response display.
- The actor does not begin autonomous work while the session is active.
- Each turn's child native action completes before another input begins.
- Canceling the response dialog closes the session after its final action.
- Canceling the queued interaction suppresses late UI and resolves late proposals as canceled.
- Backend errors leave no pending action proposal or confirmed consequence.

Run the complete Core, Sims adapter, Godot adapter, cross-adapter, release-contract, lint, type,
syntax, and deterministic regression checks before the next in-game Test 5 build.

## Non-Goals

- A universal enumeration of every game's emotions, buffs, or sentiments.
- Direct model mutation of game-native state.
- Automatic execution of unavailable native actions.
- Persisting temporary moodlets as permanent identity.
- Adding respect, resentment, or other cognitive relationship dimensions without defined Core
  behavior and a demonstrated use.
- Increasing adapter concurrency or changing provider routing.
