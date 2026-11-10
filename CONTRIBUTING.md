# Contributing

Contributions are welcome once the public contribution workflow is enabled. Useful areas include:

- Installation and troubleshooting documentation
- Sims patch compatibility testing
- Diagnostics and support tooling
- Additional game adapters
- Provider integrations
- Memory retrieval fixtures
- Typed DTO and service extraction
- Performance measurements on additional hardware

Before opening a large pull request, create an issue or discussion describing the proposed change and its intended boundary.

## Before you start

Empneon is in early development. Architecture decisions are made by the project author.
Open an issue before implementing significant changes — avoid wasted effort.

## Development setup

```bash
git clone https://github.com/mf-rl/Empneon.git
cd Empneon
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e "core[dev]" -e "adapters/thesims4[dev]" -e "adapters/godot[dev]"
```

## Every feature needs

1. Requirements
2. Acceptance criteria
3. Performance budget (CPU / RAM / VRAM / latency)
4. Tests
5. Documentation
6. Implementation

No exceptions. Performance budgets matter — target hardware is Ryzen 7 4800H + RTX 2060 6GB + 16GB RAM.

## Before submitting a PR

```bash
ruff check core/src core/tests adapters/thesims4/src adapters/thesims4/tests \
  adapters/godot/src adapters/godot/tests tests scripts/release.py scripts/test_release.py
mypy core/src adapters/thesims4/src adapters/godot/src
(cd core && pytest)
(cd adapters/thesims4 && pytest)
(cd adapters/godot && pytest)
pytest tests
pytest scripts/test_release.py
```

All of these must pass. CI enforces this (see `.github/workflows/ci.yml`).

## PR scope

- One logical change per PR
- No unrequested refactors bundled into feature PRs
- Link the issue your PR addresses

## License

By contributing, you agree your contributions are licensed under Apache 2.0.
