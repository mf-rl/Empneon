# Directors protocol: design decision

Status: proposed, awaiting maintainer review (issue #36). Implementation is issue #42. This is a design
note, not shipped behavior. Nothing here is implemented, and no numbers below were measured.

## Problem

[Vision](vision.md#directors) says directors are optional policy modules that propose opportunities,
and never bypass the scheduler, force character decisions, or mutate game state. The
`core/directors` package exists only as an empty `__init__.py` (verified; it has had no content since
the adapter regrouping commit). Without a protocol, each adapter would invent its own "something
should happen" logic and Core could not bound, inspect, or compare it.

[Roadmap](roadmap.md) also gates this work: "only once a validated use case exists". No such use case
is recorded yet. This note therefore proposes the smallest protocol that keeps the vision's
guarantees, and asks the maintainer to name or approve a first use case (see questions).

## What the code does today (verified by reading it)

- Cognition enters Core only as a `CognitiveRequest` (`core/contracts.py`). `PriorityScheduler.submit`
  admits it (bounded queue, urgency, deadline), and `CognitiveRuntime.process` / `decide` reserve
  resources through `ResourceGovernor` before any resolver runs.
- A model or rule output is a `Decision`. It becomes state only when the adapter executes it and
  returns an `ActionResult`; `ActionRecordStore.propose` / `confirm` hold the proposal until then.
- `validate_decision` checks a decision against the `intents` and `state_paths` an adapter publishes in
  `AgentStateSnapshot.capabilities`. An absent key allows everything.
- `EpisodicMemoryStore.create` is called by adapters for confirmed events. Core never writes events
  from model output.
- `action_results.event_id` and `action_proposals.event_id` are plain TEXT with no foreign key, so a
  request may reference an event id that was never stored.
- `GameAdapter` has two methods, `observe()` and `execute()`. There is no adapter callback for
  suggestions.

## Decision

### 1. A director is a pure proposer

```text
Director.propose(view: DirectorView) -> tuple[Opportunity, ...]
```

- `DirectorView` is a read-only, game-agnostic snapshot built by Core: the current time, recent
  `WorldEvent`s the adapter already delivered, and `AgentStateSnapshot`s. It exposes no store
  handles, no adapter, and no provider, so a director cannot write memory, call a model, or execute
  anything.
- `propose` is synchronous, deterministic for a fixed view and clock, and bounded: a director declares
  `max_opportunities` and Core truncates and logs a count when it is exceeded.
- A director that raises is logged by exception type name only and skipped; it never stops other
  directors or the runtime.

### 2. An opportunity is a request for cognition, not a decision

`Opportunity` is a frozen dataclass: `director_id`, `kind` (opaque string), `agent_id`, `urgency`
(0 to 1), `deadline_ms`, `facts` (JSON-compatible), and an `id`. It carries no `intent`, no
`target_id`, and no `StateDelta`, so it cannot express a game mutation or choose what a character does.

Core converts it with one deterministic step into a `CognitiveRequest` whose `WorldEvent.type` is
`opportunity.<kind>` and whose `facts` include the `director_id`. From there it takes the normal path:
`PriorityScheduler.submit`, resource admission, CLOD selection, resolver, `validate_decision`, adapter
`execute`, and `ActionRecordStore`. Directors therefore inherit queue limits, deadlines, aging, and
degradation to CLOD 1 without any new bypass.

The synthetic event is not persisted. It is never passed to `EpisodicMemoryStore.create` by Core. Only
the adapter, after it confirms something happened, writes memory. Because the event id is unstored,
`action_results.event_id` may reference it harmlessly (no foreign key, verified above); this note
does not propose changing that.

### 3. Boundary between Core and adapters

| Concern | Owner |
|---|---|
| `Director` protocol, `Opportunity`, `DirectorView`, conversion to `CognitiveRequest`, bounding | Core |
| Which directors run, and when `propose` is called | Adapter (or host app), opt-in |
| Meaning of `kind`, game-specific facts, mapping an accepted decision to a game action | Adapter |
| Whether an opportunity is allowed at all in the current game state | Adapter, via capabilities |

Core never imports adapter code and never names a game concept. `kind` and `facts` are opaque to Core.
Game-specific directors (for example "wedding drama" for one title) live in the adapter package and
implement the same protocol; Core ships at most generic ones.

Directors run only when the adapter calls a Core entry point (proposed name `run_directors`, not
exported until slice 1 is approved). Nothing starts a background loop, so `CognitiveRuntime` and both
adapters behave as today unless opted in.

### 4. Staying game-agnostic

- Inputs and outputs use only existing generic contracts plus the opaque `kind` string.
- The adapter can restrict kinds the same way it restricts intents: an optional `opportunities`
  list in `capabilities`. An absent key allows everything, an empty list allows nothing, matching the
  existing `intents` and `state_paths` rule so there is one mental model. This needs
  `validate_capability_lists` extended to the new key; it is the only change to an existing contract.
- A cross-adapter contract test (`tests/cross_adapter`) runs the reference director against both
  adapters' fixtures and asserts the same Core behavior, so game-agnosticism is checked, not claimed.
- The Core package must contain no Sims, Godot, or provider names, as in CLAUDE.md.

### 5. Guarantees (what a director cannot do)

| Vision rule | How the protocol enforces it |
|---|---|
| Does not bypass the scheduler | Output is only `Opportunity`; Core is the sole caller of `submit` |
| Does not force character decisions | No intent or target field; the resolver still decides |
| Does not mutate game state | No `StateDelta`, no adapter or store handle in `DirectorView` |
| Model output is a proposal | A director never calls a model; resolver output keeps today's propose/confirm path |
| Inspectable | Counts per director are logged (names and counts only); see risks for persistence |

## Schema impact

None for slice 1. Opportunities are in memory and converted to requests. Persisting them (for replay or
attribution) would need a table and a migration tested from the previous schema and a fresh database;
that is deferred until a use case needs it.

## Alternatives rejected

- Directors return `Decision`s: skips resolution and `validate_decision`, and lets a policy force a
  character action. Violates the vision.
- Directors write synthetic events into memory: breaks the rule that only adapter-confirmed results
  become memory or state.
- Directors call the provider directly: bypasses `ResourceGovernor` and usage accounting.
- A background director loop inside Core: hidden concurrency and clock use; the adapter owns time.

## Risks and gaps I have not verified

- There is no validated use case; the protocol may be premature (roadmap says so). Slice 1 should stay
  small enough to discard.
- I have not checked how each adapter's `observe` cadence would feed `DirectorView`; the Sims 4
  backend builds its own request flow and may not map cleanly onto `run_directors`.
- Opportunity attribution after the fact is not persisted, so replay cannot show which director
  caused a request. Usage rows may be enough; unconfirmed.
- `urgency` set by a director competes with adapter-set urgency in one queue. Without a cap a director
  could starve real events. Aging helps starved low-urgency work, not the reverse; a per-director
  urgency ceiling may be needed.

## Proposed scope for #42

Slice 1 (one PR): `Director` protocol, `Opportunity`, `DirectorView`, deterministic conversion to
`CognitiveRequest`, `run_directors` with truncation and failure isolation, and one reference director
that uses only generic state (proposed: an idle-agent check-in that fires when an agent has had no
event for a configured number of seconds, with an urgency ceiling). Optional `opportunities`
capability key. Tests including a cross-adapter contract test, plus `docs/api.md` and
`test_public_api.py` for every new exported name. Core coverage stays at or above 90%.
Slice 2 (only if wanted): persistence and replay attribution. Adapter-side directors and wiring into
the Sims 4 and Godot adapters are separate adapter tickets.

## Questions for the maintainer

1. Is there a validated use case to anchor slice 1, or is the idle-agent check-in acceptable as a
   throwaway reference director?
2. Should directors be allowed any influence on `max_tokens` or preferred CLOD, or only urgency and
   deadline (proposed: only urgency and deadline)?
3. Is the opt-in `opportunities` capability key wanted, or is adapter-side filtering enough?
4. Is in-memory only acceptable for the first release, with persistence deferred?
