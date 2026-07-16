# Adapter Development Guide

An Empneon adapter translates between a game's native state and the generic contracts in
`empneon.core.contracts`. The game remains authoritative for world state, and the adapter is a
separate package that depends on Empneon Core.

## Choose a boundary

- **In-process Python:** implement `GameAdapter.observe()` and `GameAdapter.execute()`.
- **External engine:** serialize the same contract fields over a local transport.

Do not add game types, action names, engine objects, or provider details to Core.

## Contract flow

1. Translate an observed game occurrence into `WorldEvent`.
2. Submit a `CognitiveRequest` for one actor.
3. Receive a validated `Decision`; treat its intent and state deltas as proposals.
4. Map supported proposals to native game actions.
5. Return an `ActionResult` containing only changes the game actually applied.

| Type | Adapter obligation |
|---|---|
| `WorldEvent` | Stable ID, non-empty type, actor IDs, generic facts, and game time |
| `Decision` | Preserve its ID, actor, evidence IDs, intent, and proposed deltas |
| `StateDelta` | Map supported generic paths and reject unsupported paths safely |
| `ActionResult` | Preserve the decision ID and report the confirmed status and changes |

Rejected or failed actions require a reason. Rejected actions cannot claim applied changes.
Never report success before the engine confirms the action.

## Minimal adapter

```python
from empneon.core.contracts import ActionResult, Decision, WorldEvent


class MyAdapter:
    def observe(self) -> tuple[WorldEvent, ...]:
        return (WorldEvent("encounter", ("agent-a", "agent-b")),)

    def execute(self, decision: Decision, /) -> ActionResult:
        if decision.intent != "acknowledge":
            return ActionResult(decision.id, "rejected", reason="unsupported intent")
        # Apply and confirm the native game action here.
        return ActionResult(decision.id, "succeeded", decision.state_changes)
```

Structural typing is sufficient; registration, inheritance, and adapter factories are not
required. `GameAdapter` is available from `empneon.core.ports` and the top-level `empneon`
package.

## Validation

Each adapter repository should verify four invariants:

- the event's primary actor becomes the decision actor;
- the decision cites the event as evidence;
- the action result preserves the decision ID;
- success is reported only after a confirmed game outcome.

Use stable synthetic identities and no personal save data. Adapter-specific tests belong in the
adapter repository; Core tests use a fake adapter and never import a concrete game integration.

## Scenario regressions

Store provider-free cognition requests and expected `Decision` fields in a JSON fixture, then run:

```powershell
empneon-regress scenarios/clod1-regressions.json
```

Each case requires a unique `name`, a generic `request` with its `event`, and a non-empty
`expected` object. The command returns `0` for a pass, `1` for a decision mismatch, and `2` for an
invalid fixture or I/O error.
