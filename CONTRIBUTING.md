# Contributing to Empneon

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
ruff check core/src core/tests adapters tests
mypy core/src adapters/thesims4/src adapters/godot/src
pytest core adapters tests
```

All three must pass. CI enforces this.

## PR scope

- One logical change per PR
- No unrequested refactors bundled into feature PRs
- Link the issue your PR addresses

## License

By contributing, you agree your contributions are licensed under Apache 2.0.
