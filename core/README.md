# Empneon Core

Empneon Core is a game- and AI-provider-agnostic cognitive runtime for persistent
simulated societies. It gives game agents durable identity and memory while allocating
AI reasoning within explicit performance and cost limits.

## What it provides

- Persistent agent identity and structured state
- Epistemic social memory: agents can remember who said what and distinguish belief from fact
- Provider- and game-independent recall constraints for question slots, normalized time evidence,
  and attributed location ownership
- Cognitive level of detail (CLOD) with deterministic degradation under resource pressure
- Typed contracts for observations, decisions, state changes, and action results
- Adapter boundaries for different games and AI providers
- Regression scenarios and benchmarks for validating behavior

Empneon Core is not tied to The Sims 4, a particular game engine, or a particular model vendor.
Game-specific integrations live in adapters outside the core runtime.

```text
game <-> game adapter <-> Empneon Core <-> AI provider <-> model
```

## Status

Empneon is under active development and has not reached a stable 1.0 API. The core contracts
are exercised by separate reference integrations for The Sims 4 and Godot. Configured providers
declare structured-output capability explicitly; schema-bearing requests are rejected when a
provider cannot enforce them instead of silently dropping the schema.

## Development

Empneon requires Python 3.11 or newer.

```bash
python -m pip install -e ".[dev]"
ruff check src tests
mypy src
pytest
empneon-regress scenarios/clod1-regressions.json
```

## Documentation

- [Project vision](docs/vision.md)
- [API reference](docs/api.md)
- [Adapter development](docs/adapter-development.md)
- [Technical innovations](docs/innovations.md)

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) and the [Code of Conduct](../CODE_OF_CONDUCT.md).

## License

Licensed under the [Apache License 2.0](../LICENSE).
