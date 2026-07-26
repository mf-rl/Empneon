# Sims 4 Waiting Interaction User-Cancellation Design

**Status:** Implemented and automated-verified; live Test 14 retest pending.

## Problem

During Test 14, the backend completed both `Where is TEST14-A-731?` requests and produced grounded answers, but The Sims 4 ended the visible `Waiting for response` interaction first. The adapter treated every interaction finish as cancellation, closed the conversation session, discarded the late answer, and reported `Empneon Social canceled`.

The current finishing callback ignores the interaction's finishing type. The waiting generator also marks any early exit as cancellation. A normal game-driven finish is therefore indistinguishable from an explicit player cancellation.

## Required Behavior

- `Waiting for response` remains visible until the backend response is handled.
- Only an explicit player cancellation closes the session as canceled.
- A game-driven, non-user finish while the backend request is pending immediately queues a replacement waiting interaction for the same session.
- Requeueing never submits another backend request.
- A received response marks the session as responded before the current waiting interaction ends naturally.
- Missing participants or an interaction that cannot be requeued produce a delivery failure, not a false user-cancellation report.

## Design

Keep the existing conversation session and backend request. Change only the waiting-interaction lifecycle:

1. Centralize pending-interaction finish handling in the adapter.
2. Classify `FinishingType.USER_CANCEL` as the sole user-cancellation signal.
3. For explicit user cancellation, close the session once with `canceled=True`; the existing late-result path continues to suppress delivery and report the canceled proposal.
4. For any other finish while the session is pending, queue the existing waiting affordance again with the same actor, target, and session. Do not call `submit_empneon_chat`.
5. Ignore stale callbacks: only the interaction currently stored in `session.interaction` may cancel or requeue the session. This also prevents the callback and generator cleanup from creating duplicate replacements.
6. When the backend response arrives, preserve the existing order: set `session.response_received`, display/process the result, then finish the active waiting interaction with `FinishingType.NATURAL`. The finish handler sees the response flag and does nothing.

The generator cleanup uses the same finish handler instead of unconditionally closing the session. No new scheduler, persistence layer, timeout, or configuration is needed.

## Compatibility Requirements

The change must preserve these working paths:

- Explicit player cancellation still stops delivery of a later backend answer.
- A successful backend answer ends the waiting interaction naturally and is displayed once.
- Provider and transport errors still show their existing error response and end the waiting interaction.
- Action-result confirmation and native social consequences remain unchanged.
- Test 11 cancellation persistence remains unchanged.
- Autonomy scheduling and target selection remain unchanged.
- Save-slot checkpoints and memory restoration remain unchanged.
- Existing configuration, logs, databases, and Test 14 checkpoint artifacts are not modified by implementation work.

## Regression Checks

Add focused coverage proving:

- A non-user finish requeues the waiting interaction and leaves the session open.
- The replacement uses the same session and does not submit another backend request.
- An explicit user finish closes the session as canceled.
- A backend response marks the session responded, finishes naturally, and does not requeue.
- A stale finishing callback cannot cancel or requeue the current interaction.

Then run the focused waiting-session tests, the full Sims 4 adapter test suite, Python compilation, the mod build, and diff/status checks.

## Implementation Record

The regression failed against the original unconditional cancellation path, then passed after the
shared finish gate and queue-only helper were added. Final verification passed all `246` Sims
adapter tests, Python compilation, the mod build, and `git diff --check`. The rebuilt mod has not
yet been installed for the live Test 14 retry.
