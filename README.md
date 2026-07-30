<p align="center">
  <img src="assets/empneon-banner.png" alt="Empneon — Persistent AI cognition for game characters" width="100%">
</p>

<p align="center">
  <a href="LICENSE"><img alt="License: Apache 2.0" src="https://img.shields.io/badge/license-Apache%202.0-blue.svg"></a>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-3776AB.svg">
  <img alt="Status: experimental alpha" src="https://img.shields.io/badge/status-experimental%20alpha-orange.svg">
</p>

<p align="center">
  <strong>The game simulates the world. Empneon simulates the mind.</strong>
</p>

Empneon Core is an open-source cognitive runtime for persistent, state-aware game characters. It
keeps identity, relationships, memories, beliefs, and confirmed outcomes as structured data, then
uses deterministic rules or optional language models to decide what a character should say or
attempt next.

> [!IMPORTANT]
> Empneon is an experimental alpha. It is suitable for development, demonstrations, and controlled
> testing, not production use or unattended deployment.

## Why Empneon?

Most language-model-driven characters generate text from a prompt and immediately treat that text
as reality. Empneon separates proposals from confirmed world state:

```text
Character context + confirmed memories
              │
              ▼
   Deterministic rule or AI model
              │
              ▼
      Dialogue / proposed action
              │
              ▼
        Game attempts action
              │
              ▼
   Adapter reports actual outcome
              │
              ▼
 Only confirmed facts become memory
```

This reduces a common failure mode in AI characters: invented dialogue becoming false history.

## What Core provides

| Capability | Current implementation |
|---|---|
| Persistent identity | Structured profiles, goals, emotions, voice, and relationships |
| Episodic memory | Confirmed events, observations, beliefs, provenance, and recall |
| Grounded actions | Models propose actions; adapters confirm what actually happened |
| Cognitive levels | Deterministic behavior through bounded interactive reasoning |
| Provider independence | LM Studio, OpenAI-compatible endpoints, and custom providers |
| Resource controls | Declared RAM, VRAM, concurrency, token, and latency admission |
| Replay and diagnostics | Timeline, telemetry, regression scenarios, and deterministic replay |

## Architecture

<p align="center">
  <img src="assets/architecture.svg" alt="Empneon architecture diagram" width="100%">
</p>

```text
Game adapters
      │
      ▼
 Empneon Core
├── contracts and state transitions
├── identity, relationships, memories, and beliefs
├── cognitive-level scheduling and deterministic fallbacks
├── provider configuration and capability routing
├── resource admission, telemetry, and replay
└── SQLite persistence
      │
      ▼
Optional AI providers
├── LM Studio
├── OpenAI-compatible endpoints
└── custom LLMProvider implementations
```

The game boundary is defined by two structural Python protocols:

```python
class GameAdapter(Protocol):
    def observe(self) -> tuple[WorldEvent, ...]: ...
    def execute(self, decision: Decision, /) -> ActionResult: ...


class LLMProvider(Protocol):
    @property
    def capabilities(self) -> ModelCapabilities: ...

    async def generate(
        self,
        request: GenerationRequest,
    ) -> GenerationResult: ...

    async def health_check(self) -> bool: ...
```

Adapters translate game-specific state and report native outcomes. Core owns provider selection,
persistent memory, scheduling, resource admission, telemetry, and replay. SQLite is currently the
only database backend.

## Cognitive Level of Detail

Empneon assigns work to a bounded cognitive level instead of sending every decision to the largest
available model.

| Level | Mechanism | Example |
|---|---|---|
| CLOD 0 | Persistent state and history | Identity, memories, observations |
| CLOD 1 | Deterministic rules | Routine autonomous behavior |
| CLOD 2 | Small model or bounded heuristic | Memory selection or classification |
| CLOD 3 | Interactive reasoning | Player conversation or planning |
| CLOD 4 | Rare consequential reasoning | High-impact, infrequent decisions |

`ResourceGovernor` admits declared RAM, VRAM, concurrency, token, and latency estimates.
`select_cognition` chooses an affordable route and falls back to deterministic CLOD 1 when no route
fits or provider execution fails. These declared estimates are admission controls, not live
hardware monitoring.

## Memory and grounding

The versioned SQLite schema stores:

- Character identity and goals
- Relationships and emotional state
- Canonical events and observations
- Beliefs with provenance and revision history
- Episodic memories and adapter-owned documents
- Provider usage and latency
- Action proposals, confirmed results, and ordered consequences

Recall is bounded:

```text
Confirmed candidates
        │
        ▼
Deterministic filtering and ranking
        │
        ▼
Optional small-model memory selection
        │
        ▼
Deterministic validation and fallback
        │
        ▼
Selected evidence enters generation
```

Model output never mutates the database or game directly. Core parses provider output into typed
decisions and state deltas, validates them against adapter capabilities, and persists only
confirmed results.

## Providers

Core includes:

- **`LMStudioProvider`** — discovers a loaded local model and supports LM Studio's native and
  OpenAI-compatible APIs.
- **`OpenAICompatibleProvider`** — supports compatible services such as OpenRouter, Ollama,
  llama.cpp servers, and other endpoints implementing the expected API shape.
- **Custom providers** — implement the `LLMProvider` protocol.

> [!CAUTION]
> Never commit API keys, `.env` files, private conversation databases, save data, or diagnostic
> bundles containing unredacted user content.

## Development

Empneon Core requires Python 3.11 or newer.

```powershell
py -3.12 -m pip install -e "core[dev]"
ruff check core/src core/tests
mypy core/src
pytest core
empneon-regress core/scenarios/clod1-regressions.json
```

Core is independently buildable and releasable from the `core/` directory.

## Current validation

Core's automated suites cover:

- identity, relationships, emotions, goals, and schema migration;
- canonical events, observations, beliefs, contradiction, revision, and trust-decayed propagation;
- grounded action proposals, confirmation, failure, and ordered consequences;
- deterministic and provider-backed cognitive selection with resource admission;
- provider usage, latency, and selected-CLOD telemetry;
- bounded recall, timeline queries, recorded replay, and regression scenarios;
- structural adapter contracts and provider-independent typed output.

These results do not establish novelty, broad player value, general hardware compatibility, or
production scalability.

## Project status and roadmap

Empneon Core is an experimental reusable cognition runtime and technical reference for persistent
memory, grounded actions, bounded reasoning, and provider-independent AI integration.

Current priorities:

- improve typed application boundaries;
- document third-party adapter development;
- expand reproducible examples and regression scenarios;
- validate resource policies across more providers and hardware;
- improve developer-facing diagnostics and replay.

See the [open-source roadmap](docs/roadmap.md).

## Releases

Core releases use the `core-vX.Y.Z` tag and contain a wheel, source distribution, and
`SHA256SUMS.txt`.

Install a downloaded wheel with:

```bash
python -m pip install ./empneon-X.Y.Z-py3-none-any.whl
```

Verify checksums:

```bash
sha256sum -c SHA256SUMS.txt
```

On Windows PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 .\empneon-X.Y.Z-py3-none-any.whl
```

## Adapters

- [The Sims 4](adapters/thesims4/README.md)
- [Godot](adapters/godot/README.md)

## Documentation

- [Project vision](docs/vision.md)
- [API and compatibility](docs/api.md)
- [Adapter development](docs/adapter-development.md)
- [Research hypotheses and evidence](docs/innovations.md)
- [Open-source roadmap](docs/roadmap.md)

## Responsible use

Users and contributors are responsible for protecting credentials and private data and for
complying with provider terms, applicable laws, and the policies of communities where Empneon is
used.

## License

Licensed under the [Apache License 2.0](LICENSE).
