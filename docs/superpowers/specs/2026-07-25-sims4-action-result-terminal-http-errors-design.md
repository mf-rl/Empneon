# Sims 4 Action-Result Terminal HTTP Error Design

## Goal

Stop the Sims 4 action-result outbox from retrying permanent HTTP client errors forever while
preserving successful confirmations and recovery from transient backend or network failures.

## Root cause

The backend returns HTTP `400` when an action-result payload is malformed, unknown, or conflicts
with an already-finalized proposal. The Sims adapter currently reduces every failed POST to an
error string and schedules another attempt. Failed or cancelled results never reach the existing
three-attempt pause used by successful player sessions, so a rejected in-memory entry survives and
retries for as long as the game process remains open.

The Test 11 cancellation records themselves were accepted and persisted, so they were not the
rejected requests. An additional outbox entry remained in the running game across backend
restarts and was rejected repeatedly. The old client discarded the response body and decision ID,
so the available logs cannot prove whether that entry originated from a cancellation duplicate or
an unrelated autonomous result.

## Design

The adapter will distinguish permanent HTTP client errors from retryable failures at the
`/action-result` transport boundary.

- HTTP `400` through `499` is permanent.
- Network errors, timeouts, and HTTP `500` through `599` remain retryable.
- A permanent error pauses its outbox entry after the first response, preventing further requests.
- The marker log records the decision ID, HTTP status, and backend response body so the rejected
  payload can be traced.
- A successful player action uses the existing confirmation-failure session event immediately,
  preserving its retry-or-close dialog.
- A failed or cancelled result has no live session to notify; its paused entry remains inert until
  the game process ends.
- Existing successful HTTP responses still remove the outbox entry and advance the session.

The backend contract remains strict and unchanged. It continues rejecting unknown, malformed, or
conflicting results rather than returning a false success.

## Verification

One focused adapter regression will prove:

- a backend HTTP `400` is attempted once and then paused;
- its decision ID and response detail are logged;
- a transient failure still retries with the existing backoff and succeeds;
- a normal HTTP success still removes the entry.

The complete Sims 4 adapter suite, Python compilation, and mod build must pass before live retest.
The live acceptance check keeps the game open across a backend restart and confirms that a
permanent rejection produces one `400`, not an unbounded sequence.
