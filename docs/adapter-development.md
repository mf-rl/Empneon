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

## Measured Godot Proof Effort

This measurement covers the minimal two-agent portability proof, not a production integration.
Commit timestamps are elapsed repository-session windows, not person-hours.

| Deliverable | Measured effort |
|---|---|
| First working adapter | 29m42s from target selection (`2e2302c`) to implementation (`6ccd507`) |
| Runtime surface | 221 added lines across 5 files |
| Runtime split | 128 Python bridge lines, 69 GDScript lines, 24 Godot scene/config lines |
| Focused validation | 36 added test lines plus one successful Godot 4.7 headless run |
| Core impact | 0 changed files and 0 changed lines under `src/empneon/core` |
| Python dependency impact | 0 changes to `pyproject.toml` |
| Contract suite and guide | 36m26s and 167 added lines (`6ccd507` to `b629df0`) |
| Selection through published guide | 1h06m08s elapsed |

Reproduce the line counts and timestamps with:

```powershell
git show -s --format="%h|%aI|%s" 2e2302c 6ccd507 b629df0
git show --format= --numstat 6ccd507 -- godot/portability src/empneon/adapters/godot tests/unit/test_godot_bridge.py
git diff --numstat 2e2302c 6ccd507 -- src/empneon/core pyproject.toml
git show --format= --numstat b629df0 -- tests/contract/test_game_adapters.py docs/adapter-development.md
```

The empty Core/dependency diff demonstrates architectural isolation for this proof. These
numbers do not estimate production gameplay mapping, engine packaging, authentication, or
long-term maintenance.

## Portability Exit Benchmark

`godot/portability/scenario.json` is the canonical Stage 6 scenario. The integration check
loads that file once, builds one canonical event and equivalent CLOD 1 requests, and executes
the resulting deterministic decision through both adapter boundaries:

```powershell
py -3.12 -m pytest tests/integration/test_portability_benchmark.py -q
```

The Sims adapter confirms its native `animation=idle` mapping. The Godot bridge confirms its
native `awareness.godot-b=true` mapping. Both preserve decision
`abc780ba-3e2c-501a-95a5-85e289d2a7f5`, its evidence, and successful status.

The real Godot scene reads the same JSON file. With the bridge running, this command must print
`EMPNEON_GODOT_OK` and exit 0:

```powershell
godot --headless --path godot/portability
```

This passed on Godot 4.7 on 2026-07-13. The Sims half uses the in-process reference adapter;
use the separate Sims live-game protocol for game performance or release validation.
