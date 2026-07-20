# Sims 4 HTTP Simulation Design

## Goal

Automate the Empneon Core checks that do not require The Sims 4 itself by reproducing the HTTP
traffic sent by the Empneon Social interaction. Run against the installed release backend and its
current `empneon_core_memory.sqlite3` database.

## Scope

The harness will exercise the real loopback API at `http://127.0.0.1:8765`:

- `POST /chat` with the same speaker, listener, relationship, location, nearby-Sim, event,
  available-action, and message fields produced by the mod.
- `POST /action-result` to simulate successful and failed native game execution.
- Diagnostic reads through `/diagnostics/sim`, `/diagnostics/usage`,
  `/diagnostics/timeline`, and `/diagnostics/replay`.
- Identity export/import and provider-free `/autonomous` checks where useful.

The harness will not simulate Sims APIs, native affordance selection, animations, interaction
queues, or actual save/load events. Those remain in-game tests.

## Isolation and data policy

The user has backed up the current database and approved testing against it. Synthetic Sims will
use IDs and names prefixed with `empneon-test-` so generated records are distinguishable from game
data. The harness will not delete or rewrite existing records. It will record database and
diagnostic counts before and after execution. Repeated runs use a unique run identifier.

The database may be read directly for verification, but all state mutations must go through the
public HTTP API. No configuration files, secrets, save files, or legacy databases are modified.

## Harness

Add one standard-library Python script under `adapters/thesims4/scripts`. It accepts the backend
URL, sends scenarios sequentially, performs assertions, and writes a timestamped JSON report.
Each scenario records its request, response, diagnostic evidence, duration, and pass/fail result.
Sensitive configuration and API keys are never collected.

The initial scenarios cover:

1. Health and release connectivity.
2. Canonical profile, mood, needs, and need-derived goals.
3. A successful chat proposal and simulated successful confirmation.
4. A failed confirmation with no applied consequences.
5. Private fact retention for one synthetic Sim and non-disclosure to another.
6. Topical memory retrieval using a paraphrased question.
7. Usage telemetry for provider-backed dialogue and provider-free CLOD 1 autonomy.
8. Timeline ordering and replay integrity.
9. Identity export/import idempotence.

Assertions target Core invariants rather than exact LLM wording. The report preserves dialogue so
grounding quality can also be reviewed manually.

## Error handling

Connectivity failure stops the run without changing data. Scenario failures are captured in the
report and later independent scenarios continue when safe. A chat proposal is confirmed only when
the response contains a decision ID and proposed action. Every confirmation uses the exact action
returned by that proposal.

## Verification

Unit tests will mock the HTTP boundary and verify payload shape, confirmation pairing, report
generation, and failure reporting. A live smoke run against the installed backend then proves the
release path end to end. Existing Core, Sims adapter, lint, and type checks remain the regression
gate.

## Remaining in-game tests

- Accuracy of data extracted from live Sim objects.
- Native social mapping, animation, queue completion, cancellation, and consequence capture.
- Real game concurrency and priority behavior.
- Save-slot hooks and persistence across actual game save/reload cycles.
