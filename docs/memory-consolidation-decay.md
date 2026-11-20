# Memory consolidation and decay: design decision

Status: proposed, awaiting maintainer review (issue #35). Implementation is issue #41. This is a design
note, not shipped behavior. Nothing here is implemented, and no numbers below were measured.

## Problem

`events`, `event_observations`, and `beliefs` only grow. Recall scans every event row for a pair and
cost grows linearly (see [recall benchmark](recall-benchmark.md)). Older and rarely used memories also
compete equally with recent ones when ranking. We want bounded growth and recency-weighted recall
without losing the grounding guarantee.

## What the code does today (verified by reading it)

- Core stores never write events from model output. `EpisodicMemoryStore.create` is called by adapters
  after they confirm what happened; the Sims 4 backend stores `confirmed_interaction` events, and Core
  itself does not know that kind (it is a Sims JSON field, so Core must not either).
- Deleting an event cascades to `event_participants` and `event_observations`, but
  `belief_provenance.source_observation_id` is `ON DELETE NO ACTION`. With foreign keys on, deleting an
  event whose observation backs a belief fails. Hard deletion is therefore unsafe as a decay primitive.
- `vec_memories` / `vec_memory_index` are not tied to `events` by a foreign key; vectors outlive a
  deleted event (issue #39).
- The Sims 4 backend recalls with its own raw SQL (`json_extract` over `events`), so any new Core
  filter is invisible to it until the adapter is changed.

## Decision

### 1. Grounding rule

Consolidation and decay may only reorder, hide, or summarize rows that already exist in `events`. They
never create a fact, observation, or belief. A summary is a derived artifact that cites its source
events; it is never fed back as an observation or belief and never counts as adapter-confirmed.

Consequences:

- Version 1 consolidation is deterministic and model-free: counts, time span, participants, and
  source event ids. No LLM summary. A model-written digest is a proposal and needs its own design
  (it could not be grounded by this rule), so it is out of scope.
- Eligibility is chosen by the caller, not by Core: the policy takes agent id, age, and
  per-agent count limits, plus an optional caller-supplied predicate over `Event`. Sims-specific
  filtering (for example "only `confirmed_interaction`") lives in the adapter.
- Events that back a belief, or are referenced by an action record, are never archived by the default
  policy. The database does not enforce the action-record side: `action_results.event_id` and
  `action_proposals.event_id` are plain TEXT with no foreign key, so the policy must query them
  explicitly.

### 2. Decay is computed, not stored

Salience is a pure function of `now`, `last_recalled_at` (falling back to `happened_at`), and a
half-life: `salience = max(floor, 0.5 ** ((now - anchor) / half_life))`. A recall refreshes
`last_recalled_at`. `recall_count` is kept for inspection only and does not enter the formula. Reads compute it; no sweep rewrites values. This is deterministic, testable with a
fixed clock, and trivially reversible (change the half-life and the ranking changes).

Only recall bookkeeping (`recall_count`, `last_recalled_at`) is written, and only when the caller
opts in. Half-life defaults are not chosen here; they need the adapter's time scale.

### 3. Archive is reversible; deletion is separate

- `archive` sets a flag and a timestamp. Archived events stay in `events`, keep their observations,
  beliefs, and vectors, and are skipped by opted-in recall. `restore` clears the flag.
- Hard prune is a separate, explicit call that requires a backup path (JSON export of the rows and the
  vector) to be written first, refuses events that back beliefs, and removes the vector with the event.
  It depends on #39. It is not part of the default policy and the first slice need not ship it.
- All mutators take keyword-only `commit=True` (with `commit=False` the caller owns the transaction); a sweep is bounded (`max_rows`) and idempotent.
- Logging records counts and policy names only, never descriptions.

### 4. Consolidation produces a digest

Archiving a batch can write one digest row that lists the archived event ids. Its `summary` is a
fixed template filled from counts, time span, and participant ids (no free text from a model).
Recall may return the digest in place of the archived events, labeled as derived, so it is evidence
of what was archived and never a new confirmed event. Restoring the source events does not delete the digest; the
digest is removed by a separate explicit call.

## Schema impact (schema 15, additive)

No change to existing tables, so existing readers and both adapters' suites stay unmodified.

```text
memory_state(event_id PK REFERENCES events ON DELETE CASCADE,
             archived_at INTEGER NULL, recall_count INTEGER NOT NULL DEFAULT 0,
             last_recalled_at INTEGER NULL, digest_id TEXT NULL REFERENCES memory_digests ON DELETE SET NULL)
memory_digests(id PK, agent_id REFERENCES agents ON DELETE CASCADE, summary TEXT NOT NULL,
               source_count INTEGER NOT NULL, span_start INTEGER, span_end INTEGER,
               created_at INTEGER NOT NULL, policy TEXT NOT NULL)
```

A missing `memory_state` row means active and never recalled, so nothing needs backfilling. Per
CLAUDE.md the migration must be tested from schema 14 and from a fresh database; it is forward-only
and an older runtime refuses the file, as for schema 14 (back up `-wal` and `-shm` too).

Existing code stays untouched unless the caller opts in: `CognitiveRuntime`, `get_for_agent`, and
`SemanticMemoryIndex` default to current behavior. `SemanticMemoryIndex` would gain an
`include_archived=True` default if it applies the filter; vector search itself has no link to `events`,
so the filter is an extra step after the KNN lookup and is in slice 1's scope.

## What is reversible

| Action | Reversible | How |
|---|---|---|
| Decay weighting | yes | pure function, no stored change |
| Recall bookkeeping | yes, lossy | counters can be reset |
| Archive and digest | yes | `restore`, source rows never altered |
| Hard prune | no | explicit call, export written first, refuses belief-backed events |

## Alternatives rejected

- Delete old rows: breaks belief provenance (FK above) and the replay/causal trace.
- Add `archived` to `events`: touches the shared table, and the Sims raw SQL ignores it either way.
- LLM summaries in version 1: ungrounded, adds cost, and needs the proposal/confirmation rule extended.

## Risks and gaps I have not verified

- No evidence yet that real saves are large enough to need this (the benchmark's own trigger is
  50,000 events). Archive only helps latency if recall filters it, which the Sims backend does not yet.
- Half-life, floor, and age thresholds are unmeasured; the doc deliberately does not pick them.
- Interaction with #40 is unsettled (see below).

## Proposed scope for #41

Slice 1 (one PR): migration 15, `MemoryState` store with archive, restore, recall bookkeeping, computed
salience, bounded sweep with a caller-supplied eligibility predicate, tests from schema 14 and fresh, plus `docs/api.md` and `test_public_api.py` if any new name is exported.
Slice 2: deterministic digests. Slice 3 (only if wanted): hard prune with export, after #39. Sims 4
backend filtering is an adapter ticket.

## Questions for the maintainer

1. The ticket lists #40 as a blocker. #40 is recommended as no-go in the recall benchmark. Should #41
   proceed independent of #40 and plug salience into existing ranking?
2. Is deterministic-only consolidation acceptable for the first release, with LLM digests deferred?
3. Is hard prune wanted at all, or is archive-only enough?
