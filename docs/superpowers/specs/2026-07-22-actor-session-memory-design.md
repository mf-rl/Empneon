# Actor-Isolated Conversation Memory Design

**Date:** 2026-07-22
**Status:** Approved for implementation planning

## Purpose

Empneon must keep each game actor's personality isolated while preserving believable memory
across separate conversations, backend restarts, and saved-game reloads. It must not achieve
continuity by inserting an ever-growing transcript, a generic memory summary, or a list of loosely
related dialogue into every model request. Those inputs encourage repeated names, recycled
openings, and confusion between speakers.

This design borrows the useful actor/session separation from Hermes Agent without importing
Hermes Agent or adding its tool, skill, delegation, or general-assistant features.

## Goals

- Keep identity and personality isolated per actor.
- Keep relationship state isolated per directed actor pair.
- Preserve every confirmed delivered interaction in a searchable episodic archive.
- Preserve durable learned facts across conversations and game reloads.
- Give the model only the current conversation and specifically relevant long-term memories.
- Keep the design game-agnostic; game adapters report state but do not own cognition.
- Reuse Empneon's existing agent, event, observation, relationship, and save-checkpoint stores.

## Non-goals

- Importing or running Hermes Agent.
- Running a dedicated language model process for every actor.
- Depending on provider-native threads or hidden conversational state.
- Making every historical interaction visible to the model on every turn.
- Replacing the common social-category or relationship-state contracts.
- Adding a new memory dependency when the existing Core stores are sufficient.

## Chosen Architecture

### Actor profile

An actor profile owns stable or slowly changing characteristics:

- stable game actor ID;
- display name and identity;
- traits, personality, values, goals, and durable knowledge;
- adapter-provided attributes that affect roleplay.

Profiles are addressed by `(adapter, world/save namespace, actor ID)`, never by display name.
The adapter sends the latest snapshot; Core creates the profile when first seen and refreshes
changed fields on later requests. Traits and age are refreshable rather than immutable because a
game can change them.

The actor profile is persistent. "Wake" means loading it for a cognition request, and "sleep"
means releasing active runtime references. It does not mean retaining hidden state inside a
language model.

### Directed relationship state

Relationship state belongs to `(responding actor, other actor)`, not to either actor profile.
It contains the latest normalized friendship, romance, attraction, trust, and other common
relationship fields supplied by the adapter or maintained by Core. The reverse direction is a
different record when a game supports asymmetric state.

Authoritative current relationship metrics always override textual memories. A remembered event
may explain a relationship, but it must not replace the game's latest values.

### Conversation session

A conversation session belongs to a specific Empneon Social and its participants. Its stable
conversation ID is supplied on every turn. A new Empneon Social receives a new ID, even when the
same actors spoke previously.

The session contains only confirmed turns from that active social. It does not contain unrelated
conversations involving either actor. Core bounds the active transcript to the newest six complete
exchanges or the provider's remaining context budget, whichever is smaller.

No additional long-running worker or in-memory session object is required. Each request wakes and
sleeps the responding actor using the existing `AgentManager`; the conversation ID provides
continuity. When the game stops sending that ID because the social completed, was cancelled, or
was abandoned, it is no longer active. Confirmed events remain persistent and require no
abandoned runtime state to clean up.

### Replaceable current state

Current state includes moodlets, needs, age stage, location, nearby actors, social category,
available response categories, and any other temporal adapter data. Each turn replaces the prior
snapshot. Temporal snapshots are not accumulated as prose memories.

The common state remains game-agnostic. A game-specific adapter may derive values from official
systems or mods, but Core receives normalized inputs and does not need to know their origin.

## Memory Model

### Working memory

Working memory is the bounded transcript for the current conversation ID. It gives immediate
continuity and prevents the model from repeating replies already delivered during that social.
Only the final confirmed response is appended once.

### Semantic memory

Semantic memory contains attributed durable facts learned from confirmed interactions, including
names, preferences, promises, opinions, conflicts, relationship events, and important shared
history. Facts are associated with their owning actor, participants, source event, and save/world
namespace. Equivalent facts are deduplicated.

Semantic facts never override authoritative actor or game state. For example, a past statement
about being happy cannot override a current sad moodlet, and a remembered romance cannot override
the latest relationship metrics.

### Episodic archive

Every interaction confirmed as delivered is retained as an event containing the exact incoming
message, delivered response, participants, conversation ID, time, location when available, and
source metadata. This archive is persistent and searchable but is not automatically copied into
ordinary prompts.

Rejected model candidates, transport duplicates, cancelled proposals, failed native actions, and
undelivered responses are not recorded as completed interactions. If a deterministic fallback is
actually delivered and confirmed, that final delivered text is archived; intermediate fallback
candidates are not.

### Recall policy

Ordinary dialogue does not receive a generic memory summary, raw vector-search results, or prior
transcripts from completed sessions.

Long-term recall uses two high-precision paths:

1. An explicit history request such as "Do you remember...?", "What did I promise?", or "Where
   did we meet?" searches semantic memory and the episodic archive for the relevant participants,
   entities, topic, and chronology.
2. A normal message may receive a semantic fact only when the message explicitly mentions an
   entity or topic stored in that fact. Semantic similarity by itself is insufficient.

Recall results are deduplicated and bounded. Raw archived dialogue is used for explicit episodic
questions; ordinary continuity uses attributed semantic facts. If no supported memory is found,
the actor expresses uncertainty instead of inventing shared history.

This policy means Empneon can store all delivered interactions while exposing only the few facts
needed for the current response.

## Request Flow

For each incoming Empneon Social turn:

1. Resolve the save/world namespace and stable participant IDs.
2. Wake and refresh the responding actor profile.
3. Replace the current actor snapshots and directed relationship state with the latest adapter
   values.
4. Load confirmed turns for the current conversation ID.
5. Apply the recall policy to the current message.
6. Build a bounded prompt in this order:
   - stable responding-actor identity and persona;
   - current participant state and directed relationship;
   - zero or more specifically recalled facts or events;
   - current conversation transcript;
   - incoming message and response contract.
7. Generate and validate a response.
8. Return the proposal without writing it as delivered memory.
9. After the game confirms delivery, atomically archive the final exchange once and update
   deduplicated semantic facts.
10. Release the active actor reference.

Keeping stable persona content early in the prompt also permits provider prefix caching when a
provider supports it. Caching is an optimization only; persisted Core records remain the source of
truth.

## Save and Reload Behavior

Memory is scoped to the game adapter and saved-world identity. For The Sims 4, the existing save
slot checkpoint mechanism remains responsible for saving and restoring the Core memory database.
After loading a slot or restarting the backend, Core reconstructs actor profiles, pair
relationships, semantic memories, and archived events from persistent storage.

Different save slots must not share actor profiles or memories even if actor IDs happen to match.
Adapters for games without save slots must supply another stable world/campaign namespace; a
single-world adapter may use its stable installation or campaign namespace.

## Failure Handling

- A provider or validation failure does not create delivered memory.
- A cancellation or failed game action closes the proposal without recording a completed
  interaction.
- A duplicate delivery confirmation is idempotent and cannot create a duplicate event or fact.
- A memory lookup failure degrades to no recalled memory; it does not block ordinary dialogue or
  permit fabricated history.
- A persistence failure is logged and returned through the existing confirmation error path so it
  is not silently treated as durable memory.
- Actor references and temporary runtime state are released in success and failure paths.
- Abandoned conversation IDs leave no active runtime object while confirmed history remains
  persistent.
- A missing or malformed actor, namespace, or conversation ID is rejected at the adapter/Core
  boundary rather than merged into another actor's state.

## Changes to Current Behavior

- Stop putting both `Memory summary` and `Relevant memories` into every Sims dialogue prompt.
- Stop selecting completed-session conversation turns solely by participant pair.
- Select working turns by the current conversation ID.
- Preserve repeated player inputs as distinct confirmed turns instead of removing all transcript
  entries whose normalized message matches the current input.
- Avoid the current observed-plus-confirmed duplication in model-visible memory.
- Keep full confirmed events available for explicit historical recall.
- Keep actor persona data isolated and refreshed independently of conversation history.

These changes belong in the common Core contracts and stores where practical. The Sims 4 backend
adapts its existing payload and lifecycle to those contracts; game-specific state extraction stays
inside the adapter.

## Verification

Automated tests must demonstrate:

- two actors with different traits cannot exchange identities or personalities;
- one actor's directed relationships with two other actors remain isolated;
- only turns from the current conversation ID appear in working memory;
- repeated identical incoming messages remain represented as separate confirmed turns;
- ordinary dialogue excludes generic summaries and unrelated archived events;
- explicit history questions retrieve the correct prior fact or episode;
- a later social recalls an earlier confirmed interaction between the same participants;
- recall survives a backend restart and a Sims 4 save/reload cycle;
- equal actor IDs in different save slots do not share profiles or memories;
- cancelled, failed, rejected, duplicate, and undelivered interactions do not create completed
  memories;
- a delivered deterministic fallback is archived exactly once;
- identity questions use the responding actor's own profile without causing unsolicited repeated
  name introductions;
- missing memory produces uncertainty rather than fabricated history;
- prompt size remains bounded as the episodic archive grows;
- existing social categorization, attraction, response grounding, confirmation, and native-action
  tests continue to pass.

## Acceptance Criteria

The feature is complete when a Sim can maintain a consistent isolated persona, continue a single
Empneon Social naturally, recall relevant facts and exact episodes from earlier completed socials
after saving and reopening the game, and avoid receiving unrelated or repetitive historical text
in ordinary model requests. The implementation must remain provider-independent, game-agnostic in
Core, and require no Hermes Agent dependency.
