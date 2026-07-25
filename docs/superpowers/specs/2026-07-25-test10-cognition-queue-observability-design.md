# Test 10 Cognition Queue Observability Design

**Status:** Implemented, regression-tested, and live-validated

## Goal

Make the Sims 4 Test 10 priority gate observable and reproducible without changing cognition
ordering, gameplay behavior, provider routing, persistence, or existing feature outcomes.

## Existing behavior

`CognitionQueue` already uses `PriorityScheduler` with `active_agent_limit` workers. Automated
coverage proves that, with one worker occupied, a player request at urgency `1.0` runs before an
already-waiting ambient request at urgency `0.35`.

The live test cannot currently prove its precondition. Queue depth and request lifecycle are
internal, `/health` exposes active agents rather than queued cognition, and normal Sims autonomy
skips overlapping work. Timeline and usage records appear only after execution.

## Design

### Read-only queue state

Extend `CognitionQueue` with a thread-safe snapshot of active and waiting requests. Each entry
contains only:

- request ID;
- actor ID;
- event type;
- urgency;
- lifecycle state (`waiting` or `running`);
- submission and start timestamps where applicable.

Keep the latest 64 submitted, started, completed, failed, or timed-out lifecycle records in a
bounded in-memory deque. The diagnostic snapshot includes these records under `recent`, allowing a
polling harness to prove ordering even when a request starts and completes between polls. Restarting
the backend clears this diagnostic history.

The snapshot must not expose prompts, responses, memories, names, or provider credentials. Reading
it must not pop, reorder, cancel, or otherwise mutate queued work.

### Lifecycle logging

Write one backend log entry when a request is submitted, started, and completed. Each entry includes
the same non-sensitive identifiers plus queue depth. Logging failures must never affect execution.

### Diagnostic route

Add loopback read-only `GET /diagnostics/cognition-queue`. It returns:

```json
{
  "worker_limit": 1,
  "running": [],
  "waiting": [],
  "recent": []
}
```

The route uses the existing loopback server and requires no database access.

### Controlled Test 10 gate

Add loopback-only `POST /diagnostics/cognition-queue/test10-gate` with `arm` and `release` actions.
Arming occupies one worker and queues one lower-priority ambient request. Only one run ID may be
active, and the blocker automatically releases after 60 seconds. The gate uses no provider,
database, configuration flag, or gameplay action.

### Concurrency harness

Add one standard-library script under `adapters/thesims4/scripts`. It uses loopback diagnostics to:

1. arm a controlled blocker that automatically releases after 60 seconds;
2. queue a lower-priority ambient request behind it;
3. prompt the operator to submit a real in-game Empneon Social request;
4. wait until that real player request is reported as submitted;
5. release the blocker;
6. write a local JSON report proving whether execution order was blocker, player, ambient.

The gate accepts only loopback requests, allows one active run ID, touches no database or provider,
and releases automatically if the harness exits unexpectedly. It is dormant unless explicitly
armed. Reports contain runtime queue identifiers and timestamps only; reviewed reports may be
retained as acceptance evidence.

The operator prepares the in-game message before the harness starts the blocker, then submits it at
a second prompt. Human menu navigation and typing happen before the controlled gate is armed.

If the player request is not observed before the automatic release, the harness stops with a clear
inconclusive result rather than claiming failure.

## Compatibility boundaries

- Do not modify `PriorityScheduler` ordering or `CognitiveRequest` urgency.
- Do not modify CLOD selection, provider calls, prompts, memory, relationship outcomes, animation,
  action confirmation, or Sims queues.
- Do not add dependencies, database tables, migrations, or configuration flags.
- The controlled gate must be loopback-only, explicitly armed, single-run, and auto-releasing.
- Preserve all existing diagnostic routes and response shapes.
- Keep all changes uncommitted until the user explicitly requests a commit.

## Verification

Use test-driven development:

1. Prove snapshots distinguish waiting and running work without changing the existing
   blocker/player/ambient execution order.
2. Prove snapshots become empty after completion and after worker errors.
3. Prove the diagnostic route returns only the approved fields.
4. Prove the harness recognizes a valid order and rejects missing or reversed evidence.
5. Run the complete Sims adapter suite and Core suite.
6. Run repository Ruff, mypy, backend compilation, and `git diff --check`.

Test 10 may pass only when the captured live report shows an ambient request waiting before the
player request is submitted and the player request starts before that waiting ambient request.
