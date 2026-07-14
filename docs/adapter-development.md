# Adapter Development Guide

An Empneon adapter has one job: translate between a game's native state and the generic
contracts in `empneon.core.contracts`. The game remains authoritative for world state.

## Choose a Boundary

Use the smallest boundary your engine supports:

- **In-process Python:** implement `GameAdapter.observe()` and `GameAdapter.execute()`.
- **External engine:** serialize the same contract fields over a local transport. The Godot
  proof uses JSON over localhost and the Python standard library.

Do not add game types, action names, engine objects, or provider details to Core.

## Contract Flow

1. Translate a completed or observed game occurrence into `WorldEvent`.
2. Submit a `CognitiveRequest` for one actor.
3. Receive a validated `Decision`; treat its intent and state deltas as proposals.
4. Map supported proposals to native game actions.
5. Return an `ActionResult` containing only changes the game actually applied.

The required generic types are:

| Type | Adapter obligation |
|---|---|
| `WorldEvent` | Stable ID, non-empty type, actor IDs, generic facts, and game time |
| `Decision` | Preserve its ID, actor, evidence IDs, intent, and proposed deltas |
| `StateDelta` | Map supported generic paths and reject unsupported paths safely |
| `ActionResult` | Preserve the decision ID and report the confirmed status and changes |

Rejected or failed actions require a reason. Rejected actions cannot claim applied changes.
Never report success before the engine confirms the action.

## Minimal In-Process Adapter

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
required.

## External-Engine Example

The Godot proof in `godot/portability/` sends a JSON `WorldEvent` to `POST /decision`, applies
the returned generic intent in GDScript, and sends the confirmed result to `POST /result`.
Run it in two terminals:

```powershell
py -3.12 -m empneon.adapters.godot.bridge
godot --headless --path godot/portability
```

The successful engine output contains `EMPNEON_GODOT_OK` and exits with code 0. Keep local
bridges bound to loopback unless authentication and transport security are added.

## Conformance Check

`tests/contract/test_game_adapters.py` runs the same four invariants against the Sims 4
in-process adapter and Godot's external-engine bridge:

- the event's primary actor becomes the decision actor;
- the decision cites the event as evidence;
- the action result preserves the decision ID;
- the game reports a successful confirmed outcome.

Run the published suite with:

```powershell
py -3.12 -m pytest tests/contract -q
```

Add a small round-trip factory for a new adapter to that parametrized test. Use stable synthetic
identities and no personal save data. Adapter-specific validation belongs in focused unit tests;
cross-engine performance and believability belong in SocietyBench.
