# Sims 4 Autonomous Sim-Payload Compatibility

**Status:** Implemented, automated-verified, and live-verified in Test 15

## Problem

The in-game `aiautonomous` command sends `{"sim": sim_payload(...)}` to
`POST /autonomous`. `autonomous_action` can build its event from that legacy
shape, but then unconditionally tries to persist empty `speaker` and `listener`
objects. Persisting the first empty object raises `ValueError("observed Sim id
is required")`, returning HTTP 500 before CLOD 1 usage is recorded.

Scheduled autonomy sends `speaker` and `listener` and must remain unchanged.

## Design

Resolve the autonomous actor from `speaker` when it is a non-empty mapping;
otherwise use `sim`. Persist that actor. Persist `listener` only when it is a
non-empty mapping with an ID.

Do not weaken `sync_sim` validation: unidentified Sims remain invalid at the
state boundary. Do not change event creation, decision selection, action
mapping, scheduled execution, or usage accounting.

## Compatibility

- Sim-only requests persist the active Sim and complete as provider-free CLOD 1.
- Scheduled requests continue to persist both speaker and listener.
- Empty optional listener data is ignored.
- A request without an identified actor still fails validation.

## Verification

Add a regression reproducing the live sim-only payload and assert:

- the request succeeds;
- the active Sim is persisted;
- the result selects CLOD 1 and a supported action;
- usage records provider `core-rules`, model `clod1`, and zero tokens.

Keep the existing scheduled speaker/listener regression passing, then run the
complete Sims adapter, core, Godot, and shared test suites plus Python compile
and diff checks.
