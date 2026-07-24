# Sims 4 Single-Turn Empneon Social Design

**Date:** 2026-07-23
**Status:** Implemented; single-turn flow, romance effects, and waiting animation live-confirmed.
Exact dual-portrait layout and floating relationship symbols remain open visual checks.

## Goal

Replace the held multi-turn Empneon Social workflow with one cancelable, single-turn exchange.
The new flow must avoid queue deadlocks while preserving confirmed memory, Empneon trust, native
Sims relationship changes, and visible in-game feedback.

## Scope

This design changes player-triggered Empneon Social interactions. It does not change autonomous
NPC cognition, provider routing, Core persistence formats, or the existing rule that only
delivered dialogue and game-applied outcomes become confirmed consequences.

Each interaction carries exactly one player message and one Empneon answer. A later message
requires the player to select Empneon Social again.

## Interaction Lifecycle

1. Sim A selects **Empneon Social** on Sim B.
2. A queued interaction named **Start conversation** routes Sim A to Sim B.
3. Once routing completes, the input dialog opens and **Start conversation** leaves the queue.
4. When Sim A submits text, a native notification owned by Sim A shows Sim A's portrait and the
   submitted dialogue.
5. A separate cancelable interaction named **Waiting for response** enters the queue.
6. The backend request runs asynchronously. While it is pending, **Waiting for response** plays a
   cosmetic conversation animation if both Sims remain available.
7. When a valid answer arrives, **Waiting for response** ends and a native notification owned by Sim B
   shows Sim B's portrait and answer.
8. Empneon applies at most one validated native relationship loot outcome, observes the actual
   friendship or romance change, and reports only that observed delta to Core.
9. The transaction ends. No input dialog is reopened and no response-derived social interaction
   is queued.

Each transaction has a new conversation ID. Confirmed long-term pair memory remains available to
later transactions so single-turn interactions retain narrative continuity.

## Cancellation

The player may cancel **Waiting for response** from the queue. The request may continue consuming
provider work if the underlying HTTP/model operation cannot be interrupted, but its result is
discarded.

After cancellation:

- no answer notification is shown;
- no dialogue-delivery confirmation is sent;
- no confirmed memory or Empneon trust change is created;
- no relationship loot is applied;
- no native relationship consequence is reported to Core.

The same behavior applies when either Sim becomes unavailable before delivery. Cancellation must
not expose a late reply or leave a pending action proposal.

## Waiting Animation

The waiting animation is cosmetic. It must not change friendship, romance, sentiments, mood,
memory, or Empneon trust.

Run a base-game conversation animation as an animation-only child of **Waiting for response**.
The child must not enter either Sim's visible queue and must omit social loot, sentiments,
relationship changes, milestones, memory, and mood effects. It may loop while the backend request
is pending and must stop when the response arrives, the waiting interaction is canceled, or either
Sim becomes unavailable.

Use the EA-tuned visual outcome builder rather than direct raw ASM manipulation. Neutralize every
gameplay field and replace the mixer's normal outcome element. If a future game build exposes no
stable consequence-free visual sequence, keep the waiting interaction visually idle rather than
queueing a complete native Sims social.

## Notifications

Use the game's native notification UI:

- Sim A owns the submitted-dialogue notification. Its primary portrait is Sim A and its secondary
  portrait is Sim B.
- Sim B owns the answer notification. Its primary portrait is Sim B and its secondary portrait is
  Sim A.
- Provider or transport failures use an Empneon error notification and no relationship outcome.

Use the native `icon_override` and `secondary_icon_override` fields with `IconInfoData`; do not
create a custom notification UI. Portrait rendering and ordering must be verified in game.

## Relationship Outcome Contract

The existing model generation returns one additional bounded semantic value:

- `friendship_positive`
- `friendship_negative`
- `romance_positive`
- `romance_negative`
- `none`

This is part of the existing response, not a second provider request. The model cannot choose a
numeric relationship delta.

The backend validates the proposed outcome against the delivered dialogue:

- friendly or funny engagement may produce `friendship_positive`;
- mean or hostile dialogue may produce `friendship_negative`;
- a model-proposed `romance_positive` requires clear reciprocation by Sim B;
- `romance_negative` requires an explicit romantic rejection or negative romantic response;
- neutral, uncertain, informational, fallback, malformed, or unsupported responses use `none`.

An invalid or inconsistent value is replaced with `none`; it does not trigger a retry solely for
relationship classification.

For low-grade romantic reception, validation also applies a deterministic fallback when the model
returns `none`. A response becomes `romance_positive` only when all of these conditions hold:

- its response category is `romance`;
- its tone tags include at least one of `warm`, `playful`, or `romantic`;
- the dialogue contains no explicit romantic rejection;
- its tone tags do not include `hesitant`, `neutral`, `uncertain`, or `hostile`.

This fallback covers positively received remarks such as “You’re sweet” without treating every
romantic-category response as reciprocation. It uses the existing mild `5` point romance change and
native relationship headline; it does not add a stronger tier or milestone effect.

## Native Relationship Loot

Each non-`none` outcome maps to one conservative native Sims relationship loot operation with a
fixed standard magnitude. Model output never selects the tuning ID or magnitude.

The loot operation must:

- run without adding another interaction to either Sim's queue;
- affect only the intended friendship or romance track;
- use native Sims relationship feedback when supported by the installed game build;
- avoid pack-specific milestones, relationship bits, sentiments, or unrelated side effects;
- be applied only after the answer notification is delivered;
- be applied at most once for a decision ID.

The adapter captures the relevant relationship values immediately before and after loot
application. It confirms only the observed delta to Core. A zero observed delta is valid and must
not be replaced with the proposed magnitude.

If native relationship application is unavailable, the answer remains delivered, the failure is
logged, and no relationship consequence is reported. If only visual feedback is unavailable, log
the visual failure while preserving and reporting any observed relationship delta.

## Floating Relationship Feedback

The intended feedback is the game's native relationship headline effect, such as friendship
pluses/minuses or romance hearts/broken hearts. Exact symbol count, color, duration, and pack
behavior are tuning-controlled and must be recorded during the live test on the current game
build.

After a nonzero observed relationship delta, dispatch the matching base-game relationship headline
explicitly above both Sim A and Sim B. Positive and negative friendship use the corresponding
friendship headline; positive and negative romance use the corresponding romance headline. Do not
dispatch a headline for `none`, a zero observed delta, or a failed/canceled transaction.

Resolve and use base-game headline tuning rather than emulating the effect with a generic thought
balloon or custom icon. A missing compatible headline is a visual-only failure: log it, preserve the
already-applied relationship delta, and report the observed consequence normally.

This implementation supports one mild, ordinary outcome tier. Stronger `+++` feedback and major
milestone effects—including best-friend events, confessions, first kisses, proposals, and similar
relationship milestones—are deferred follow-up work. They must not be inferred or triggered by
this first implementation.

## Failure Handling

- Provider or transport failure: end **Waiting for response**, show an Empneon error, and apply no
  relationship outcome.
- Invalid response: use the existing safe response fallback; its relationship outcome is `none`.
- Sim unavailable before delivery: cancel and discard the result.
- Notification failure: do not confirm dialogue delivery or apply relationship loot.
- Loot selection, application, or observation failure: preserve the delivered answer, log the
  failure, and report no relationship consequence.
- Duplicate or late callbacks: reject them by transaction and decision ID.

No failure queues a replacement native social.

## State Boundaries

- Core continues to own identity, confirmed memory, Empneon trust, provider usage, decisions,
  action records, and replay.
- The Sims adapter owns queue interactions, routing, dialogs, notifications, cosmetic animation,
  native relationship loot, and observation of Sims relationship tracks.
- The game remains authoritative for friendship and romance values.
- Generated dialogue and proposed relationship outcomes remain unconfirmed until delivery and
  successful game application respectively.

## Automated Verification

Script-level tests must verify:

- **Start conversation** routes, opens input, and then completes.
- Submitting text shows a Sim A notification and starts **Waiting for response**.
- A valid answer ends waiting and shows a Sim B notification.
- No response-derived native social is queued.
- One validated relationship outcome applies one loot operation.
- Only the observed before/after relationship delta is reported.
- `none` applies no loot.
- Manual cancellation and Sim unavailability suppress every late effect.
- Provider, notification, loot, and observation failures are consequence-free.
- Duplicate callbacks cannot apply loot twice.

Backend tests must verify:

- the bounded relationship outcome schema;
- validation against friendly, hostile, romantic reciprocation, romantic rejection, neutral, and
  fallback dialogue;
- invalid values degrade to `none`;
- a warm, playful, or romantic positive reception in the `romance` category upgrades model `none`
  to `romance_positive`;
- explicit rejection, hostile tone, and hesitant, neutral, or uncertain tone do not receive
  the positive fallback;
- the additional field does not add a provider request.

Script-level adapter tests must verify:

- the waiting animation child starts without entering either queue and stops on response,
  cancellation, or unavailable participants;
- the animation path applies no relationship or other gameplay consequence;
- submitted-dialogue notifications use Sim A as primary and Sim B as secondary;
- response notifications use Sim B as primary and Sim A as secondary;
- a nonzero friendship or romance delta dispatches one matching headline to each Sim;
- zero, neutral, failed, canceled, and duplicate outcomes dispatch no explicit headline.

Integration tests must verify that a later single-turn transaction can retrieve confirmed pair
memory from an earlier transaction without retaining a held multi-turn session.

## Live In-Game Verification

Using a disposable save and current source build, verify:

1. The queue shows **Start conversation** while routing.
2. The input dialog opens only after Sim A reaches Sim B.
3. **Start conversation** leaves the queue when the input opens.
4. Sim A's submitted dialogue appears with Sim A's portrait.
5. **Waiting for response** appears and can be canceled.
6. Both Sims play a base-game conversation animation while waiting; it adds no queue item or
   gameplay consequence and stops with the waiting interaction.
7. Cancellation suppresses late dialogue, memory, trust, loot, and relationship changes.
8. A successful response removes **Waiting for response** and shows Sim B's portrait.
9. Positive and negative friendship outcomes display matching native feedback above both Sims and
   match observed track changes.
10. Positive and negative romance outcomes display matching native feedback above both Sims and
    match observed track changes.
11. No hidden or visible response-derived social enters either queue.
12. The submitted notification shows Sim A as primary and Sim B as secondary; the response reverses
    that order.
13. Confirmed memory, Empneon trust, relationship state, and replay survive save/reload.

Record the exact floating symbols produced by each available outcome in the tested game version.
Do not claim exact `++`, `+++`, heart, or broken-heart behavior until observed in game.

## Completion Criteria

The redesign is complete when automated coverage passes and one live source-build run proves:

- the two queue tasks transition without deadlock;
- manual cancellation suppresses all late effects;
- both speaker portraits are correct;
- at least one friendship and one romance outcome use native feedback;
- recorded Core consequences equal observed Sims relationship deltas;
- no response-derived native social is queued;
- save/reload preserves confirmed results.
