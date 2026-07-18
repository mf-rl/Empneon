# Empneon Working Context

Empneon is an open-source, game-agnostic and AI-agent-agnostic cognitive runtime for
persistent simulated societies. The public source of truth is `mf-rl/Empneon`.

## Architecture

```text
Game <-> Adapter <-> Empneon Core <-> AI provider or agent
                         |
                         +-> Core memory database
```

- Adapters own game APIs, observations, native actions, and confirmation of outcomes.
- Core owns identity, memory, beliefs, provider routing, scheduling, validation, telemetry,
  and replay.
- Providers own transport and model-specific behavior behind `LLMProvider`.
- The game remains authoritative for world state.

Never add game-specific types or provider transport to Core contracts. Never add provider
selection or persistent memory implementations to a game adapter.

## Implemented boundaries

- `GameAdapter` is a structural protocol using `WorldEvent`, `Decision`, and `ActionResult`.
- `LLMProvider` is a structural protocol. `ConfiguredProviderRouter` selects native LM Studio
  or OpenAI-compatible implementations from runtime configuration.
- `DocumentMemoryStore` provides Core-owned namespaced JSON persistence for adapter extensions.
- Typed Core identity, episodic memory, beliefs, action records, timeline, and replay use the
  same versioned SQLite database.
- The Sims 4 adapter imports its former SQLite memory tables once, then uses Core as the
  authority. Save-aware checkpoints back up the Core database.

SQLite is the only implemented persistence backend. Do not claim database-backend portability.
The Sims 4 backend remains a reference integration, not a production network service.

## Hardware baseline

Validation targets a Ryzen 7 4800H, RTX 2060 Laptop with 6 GB VRAM, and 16 GB RAM while
The Sims 4 is running. Default adapter concurrency is one. Do not publish new performance
claims without an in-game measurement on a stated configuration.

## Evidence rules

Distinguish implemented behavior, synthetic benchmark results, in-game measurements, and
independent validation. Existing Stage 3 and Stage 5 artifacts remain under
`adapters/thesims4/output/`; their documented limitations remain part of the result.

## Development

Empneon supports Python 3.11 or newer. Before a pull request, run the root CI equivalents:

```powershell
ruff check core/src core/tests adapters/thesims4/src adapters/thesims4/tests adapters/godot/src adapters/godot/tests tests
mypy core/src adapters/thesims4/src adapters/godot/src
pytest core
pytest adapters/thesims4
pytest adapters/godot
pytest tests
empneon-regress core/scenarios/clod1-regressions.json
```

The project is Apache 2.0. This repository contains only the open-source runtime, adapters,
tests, benchmarks, and documentation. A separate repository may be considered in the future
for unrelated deployment infrastructure only if it becomes viable; none exists here today.
