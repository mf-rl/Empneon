# Empneon — guide for AI coding agents and contributors

Empneon Core is a game-agnostic cognitive runtime (persistent identity, grounded memory, bounded
cognition). Adapters (`adapters/thesims4`, `adapters/godot`) translate a game to Core's contracts.
Read `README.md`, `docs/vision.md`, `docs/api.md`, and `docs/adapter-development.md` for intent.

## Layout

```text
core/src/empneon/
  core/contracts.py      WorldEvent, CognitiveRequest, Decision, StateDelta, ActionResult, Clod
  core/ports.py          GameAdapter protocol, Resolver alias
  core/runtime.py        ActionRecordStore, CognitiveRuntime (event -> decision -> result)
  core/clod/             deterministic CLOD 1 rules and degradation fallback
  core/scheduler/        PriorityScheduler, ResourceGovernor, select_cognition, UsageStore
  core/identity/         agents, personality, relationships, emotions, goals, voice
  core/memory/           events, observations, beliefs, recall constraints, documents, vectors
  db/                    SQLite connection, versioned schema and migrations
  providers/llm/         LLMProvider protocol, LM Studio and OpenAI-compatible providers
  benchmarks/            SocietyBench, believability, regression runner (empneon-regress)
core/tests/              unit/ and integration/
tests/cross_adapter/     contract tests shared by both adapters
```

## Commands (Python 3.11+ required)

```bash
pip install -e "core[dev]" -e "adapters/thesims4[dev]" -e "adapters/godot[dev]"
ruff check core/src core/tests adapters/thesims4/src adapters/thesims4/tests \
  adapters/godot/src adapters/godot/tests tests scripts/release.py scripts/test_release.py
mypy core/src adapters/thesims4/src adapters/godot/src
(cd core && pytest)
(cd adapters/thesims4 && pytest)
(cd adapters/godot && pytest)
pytest tests
pytest scripts/test_release.py
empneon-regress core/scenarios/clod1-regressions.json
```

These mirror `.github/workflows/ci.yml`; all must pass before a PR.

## Rules that are easy to get wrong

- **Core stays game-agnostic.** No Sims, Godot, engine, or provider-specific names in Core.
- **Model output is a proposal.** Only adapter-confirmed results become memory or state.
- **Do not break the supported API:** names in `empneon.__all__` and
  `empneon.providers.llm.__all__` are supported (see `docs/api.md`). Do not remove or rename them;
  update `core/tests/unit/test_public_api.py` and `docs/api.md` when adding one.
- **Transactions:** store mutators take keyword-only `commit=True`. `commit=False` means the caller
  owns the transaction; never commit inside such a call.
- **Logging:** use `logging.getLogger(__name__)`. Never log prompts, replies, API keys, or exception
  messages (log exception type names and status codes only).
- **Schema changes** need a migration in `db/schema.py`, tested from the previous schema and from a
  fresh database (see `docs/api.md`).
- **Resource limits are admission estimates**, not live hardware monitoring.

## Workflow

- One logical change per PR; link or describe the problem; add or update tests and docs.
- Write the failing test first for defects, then the fix.
- Conventional commit subjects (`fix(core): ...`, `refactor(core): ...`, `docs: ...`).
- Add a line to `CHANGELOG.md` under *Unreleased* for any user-visible change.
- Never commit secrets, `.env`, databases, save data, or unredacted diagnostics.
