# Global In-Game Usage Diagnostic Design

**Status:** Implemented; automated command and HTTP diagnostic coverage passed

## Problem

`empneon.usage` uses the shared active-Sim diagnostic helper. Player-directed
dialogue records cognition against the responding actor, so running the command
while controlling the initiating actor can incorrectly display zero usage even
though telemetry was recorded.

## Design

The in-game `empneon.usage` command will request global usage telemetry without
a `sim_id`. The Sims backend will accept an omitted `sim_id` only for
`/diagnostics/usage` and call the existing `UsageStore.telemetry(None)` path.

Explicit `/diagnostics/usage?sim_id=<ACTOR_ID>` requests will remain filtered to
that actor and will continue validating that the actor exists. All other
diagnostic routes and in-game commands will continue requiring and using the
active Sim.

Core usage attribution remains unchanged: each cognitive attempt belongs to the
actor that performed it. No records are duplicated or reassigned.

## Error Handling

An explicitly supplied empty `sim_id` is treated the same as an omitted filter
for the usage route. Invalid non-empty actor identifiers continue returning the
existing not-found response.

## Testing

- Add a backend test proving `/diagnostics/usage` aggregates records belonging
  to different actors.
- Preserve a test proving `/diagnostics/usage?sim_id=<ACTOR_ID>` remains
  actor-filtered.
- Add a Sims mod source-contract test proving `empneon.usage` does not use the
  active-Sim helper.
- Run the focused tests, the full Sims adapter suite, and the Core suite.

## Non-Goals

- Changing usage ownership or persistence.
- Changing the output format of `empneon.usage`.
- Changing any other diagnostic command.
- Adding conversation-target state to the Sims mod.
