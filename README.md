# Empneon

**An open-source cognitive runtime for persistent simulated societies.**

Empneon keeps character identity and memory as structured data, schedules optional AI
reasoning within explicit limits, and applies model output only through game-confirmed actions.

> The game simulates the world. Empneon simulates the mind.

## Architecture

```text
Games
├── The Sims 4 reference adapter
├── Godot 4 portability adapter
└── community adapters
            │
            ▼
Empneon Core
├── generic events, decisions, state deltas, and action results
├── identity, episodic memory, social beliefs, and adapter memory documents
├── CLOD scheduling and resource admission
├── provider configuration and capability routing
└── telemetry, timeline, and deterministic replay
            │
            ├──► SQLite memory database
            │
            ▼
AI providers or agents
├── LM Studio
├── OpenAI-compatible endpoints, including OpenRouter
└── user-defined `LLMProvider` implementations
```

The boundaries are structural Python protocols:

- A game integration implements `GameAdapter.observe()` and `GameAdapter.execute()`.
- An AI integration implements `LLMProvider.generate()` and `health_check()`.
- Core owns provider selection, persistent memory, scheduling, and replay.
- An adapter translates game data and confirms native outcomes; it does not own provider
  transport or persistent memory.

SQLite is the only implemented database backend. Godot is a minimal portability proof, and
The Sims 4 integration is a reference adapter rather than a general replacement for game
autonomy.

## Repository

The public `mf-rl/Empneon` monorepo is the source of truth:

- `core/` — runtime, contracts, providers, persistence, benchmarks, and tests
- `adapters/thesims4/` — script mod, local game bridge, configuration, and evidence
- `adapters/godot/` — localhost bridge and minimal Godot project
- `tests/` — shared adapter-contract tests
- `docs/` — current open-source roadmap

Each Python project remains independently buildable and releasable from its directory.

## Releases

GitHub Releases use one synchronized version and component-specific tags:

- `core-vX.Y.Z`
- `thesims4-vX.Y.Z`
- `godot-vX.Y.Z`

Pushing a Core tag tests and publishes Core plus both adapters. An adapter tag publishes only
that adapter. Maintainers can also run **Independent releases** manually and select `all`,
`core`, `thesims4`, or `godot`.

Core releases contain a wheel and source distribution. Download the wheel and install it with:

```bash
python -m pip install ./empneon-X.Y.Z-py3-none-any.whl
```

Adapter ZIPs contain their adapter wheel and the matching Core wheel. Every release includes
`SHA256SUMS.txt`; verify it with `sha256sum -c SHA256SUMS.txt` on Linux or compare it with
`Get-FileHash -Algorithm SHA256` on Windows.

## Install for development

Empneon requires Python 3.11 or newer. From the monorepo root:

```powershell
py -3.12 -m pip install -e "core[dev]" -e "adapters/thesims4[dev]" -e "adapters/godot[dev]"
```

Run the same checks as CI:

```powershell
ruff check core/src core/tests adapters/thesims4/src adapters/thesims4/tests adapters/godot/src adapters/godot/tests tests
mypy core/src adapters/thesims4/src adapters/godot/src
pytest core
pytest adapters/thesims4
pytest adapters/godot
pytest tests
empneon-regress core/scenarios/clod1-regressions.json
```

## Providers

Core selects providers from runtime configuration. The included implementations are:

- `LMStudioProvider`, which discovers a loaded local model, uses LM Studio's native
  `/api/v1/chat` endpoint for unconstrained generation, and sends JSON Schema requests through
  the structured-output `/v1/chat/completions` endpoint;
- `OpenAICompatibleProvider`, used by Ollama, llama.cpp-compatible servers, OpenAI,
  OpenRouter, and other compatible endpoints;
- custom implementations of the `LLMProvider` protocol.

The Sims 4 configuration contains an `openrouter` entry using
`https://openrouter.ai/api/v1`. Select it with `AI_SIM_PROVIDER=openrouter`, set the desired
model with `AI_SIM_MODEL`, and provide credentials through `AI_SIM_API_KEY`. The adapter sees
the same Core contracts regardless of provider.

## Memory

Core's versioned SQLite schema stores typed identity, relationships, emotions, goals, voice,
canonical events, observations, beliefs, provider usage, action proposals, confirmed results,
and ordered consequences. `DocumentMemoryStore` provides namespaced JSON documents for
adapter-specific state that is not yet a shared domain concept.

The Sims 4 bridge imports its former `ai_sims_memory.sqlite3` tables once, then treats the
Core database as authoritative. Optional save-aware checkpoints back up and restore that Core
database by Sims save slot.

## Cognitive Level of Detail

| Level | Mechanism |
|---|---|
| CLOD 0 | Persistent state and event history |
| CLOD 1 | Deterministic rules without a provider |
| CLOD 2 | Small model or bounded heuristic |
| CLOD 3 | Interactive conversation or planning |
| CLOD 4 | Rare consequential reasoning |

`ResourceGovernor` admits declared RAM, VRAM, concurrency, token, and latency estimates.
`select_cognition` chooses an affordable route and falls back to deterministic CLOD 1 when
no route fits or provider execution fails. The current Sims integration does not measure live
CPU, RAM, VRAM, or frame time for admission, so the governor must not be described as a full
hardware monitor.

## Hardware baseline

The validation target is:

- Ryzen 7 4800H
- RTX 2060 Laptop with 6 GB VRAM
- 16 GB RAM
- The Sims 4 running concurrently

The reference adapter defaults to one concurrent agent request. Existing measurements show
severe pressure during a 20-call local-model run; they do not establish acceptable performance
or scalability. See the [benchmark results](adapters/thesims4/docs/benchmark-results.md) and
[artifact manifest](adapters/thesims4/output/README.md).

## Current evidence

- Core contracts are exercised by two materially different adapters.
- The Sims 4 path proposes mapped actions and records only game-confirmed outcomes.
- Player-triggered Sims dialogue is a cancelable single-turn transaction with separate routing and
  waiting queue phases, portrait notifications, cosmetic waiting animation, and bounded observed
  friendship or romance consequences.
- The Sims 4 bridge selects relevant, pair-scoped confirmed memories through a bounded model
  request with deterministic fallback. Shared Core recall constraints prioritize authoritative
  attributed facts, normalize equivalent time expressions, preserve location ownership, reject
  unsupported schedules, and allow fresh response wording. Live save/reload testing recalled a
  date as `tonight at 7pm at your place` in a new grounded response.
- Epistemic memory scenarios cover observations, belief provenance, contradiction, revision,
  and deterministic trust-decayed propagation.
- The differentiated adaptive benchmark reduced provider calls on one synthetic workload while
  passing its declared preference threshold; this is not a player study.
- Timeline, replay, telemetry, regression fixtures, and package builds are implemented.

No result establishes novelty, broad player value, or production scalability.

## Documentation

- [Project vision](core/docs/vision.md)
- [API and compatibility](core/docs/api.md)
- [Adapter development](core/docs/adapter-development.md)
- [Research hypotheses and evidence](core/docs/innovations.md)
- [Open-source roadmap](docs/roadmap.md)
- [The Sims 4 setup and privacy](adapters/thesims4/docs/setup.md)

This repository contains only the open-source project. If separate deployment infrastructure
becomes viable in the future, it can be evaluated in an independent repository without changing
Core's contracts.

## License

Apache License 2.0. See [LICENSE](LICENSE).
