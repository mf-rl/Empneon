# The Sims 4 Core Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make The Sims 4 adapter use Empneon Core as its authoritative identity, memory, cognition, scheduling, telemetry, and diagnostic system while preserving existing saves.

**Architecture:** Keep the game script as a tolerant observation/action bridge and keep current HTTP routes compatible. Add one focused backend state module around Core stores, then reduce `ai_sims_server.py` to orchestration. Use one active SQLite database, `empneon_core_memory.sqlite3`, with idempotent import from both prior database names.

**Tech Stack:** Python 3.11+ backend and Core, Python 3.7-compatible Sims script, SQLite/sqlite-vec, standard-library HTTP server, pytest, PowerShell release bootstrap.

## Global Constraints

- All work stays on `feature/sims4-core-integration`.
- `empneon_core_memory.sqlite3` is the only active database.
- Never delete or write to `empneon_core.sqlite3` or `ai_sims_memory.sqlite3`.
- Existing HTTP payloads, cheat commands, save-slot behavior, and release ZIP startup remain compatible.
- No new dependency, cloud service, UI, external repository token, or embedding model.
- Every game-derived field is optional except a stable observed Sim ID.
- Only game-confirmed actions may create consequences or confirmed memories.
- Diagnostics must not expose credentials or arbitrary files.

## File Structure

- Create `adapters/thesims4/backend/empneon_state.py`: unified database preparation, legacy import, canonical identity/memory synchronization, vector retrieval, serialization, and diagnostic read models.
- Modify `adapters/thesims4/backend/ai_sims_server.py`: configuration, request scheduling, dynamic cognition, telemetry, routes, and delegation to `empneon_state`.
- Modify `adapters/thesims4/src/empneon_thesims4/adapter.py`: richer optional observation facts, urgency/value helpers, and deterministic feature hashing.
- Modify `core/src/empneon/providers/llm/configured.py`: preserve `GenerationResult` without breaking the existing string-returning API.
- Modify `adapters/thesims4/ts4script/ai_sims_agent.py`: safely probe richer game state and add `empneon.*` diagnostic commands.
- Modify `adapters/thesims4/config/config.json`: unified database and cognition resource estimates.
- Extend `adapters/thesims4/tests/test_adapter.py`, `test_sims4_backend.py`, and `test_sims4_mod_autonomy.py`.
- Extend `core/tests/unit/test_openai_compatible_provider.py` or create `core/tests/unit/test_configured_provider.py` for the router result contract.
- Create `adapters/thesims4/docs/in-game-core-feature-test-plan.md`.
- Modify `adapters/thesims4/README.md`, `adapters/thesims4/docs/setup.md`, and release contract tests only where paths or commands change.

---

### Task 1: Unified Database and Safe Legacy Core Adoption

**Files:**
- Create: `adapters/thesims4/backend/empneon_state.py`
- Modify: `adapters/thesims4/backend/ai_sims_server.py`
- Modify: `adapters/thesims4/config/config.json`
- Test: `adapters/thesims4/tests/test_sims4_backend.py`

**Interfaces:**
- Produces: `prepare_database(target: str, legacy_core: str, legacy_adapter: str) -> MigrationStatus`
- Produces: `open_memory(target: str) -> contextlib.AbstractContextManager[sqlite3.Connection]`
- Produces: immutable `MigrationStatus(active_path, sources, backups, completed, error)` with `as_dict()`.

- [ ] **Step 1: Write failing tests for the new default and one-time Core adoption**

```python
def test_unified_database_is_the_only_active_default() -> None:
    assert ai_sims_server.MEMORY_DB_PATH.endswith("empneon_core_memory.sqlite3")


def test_prepare_database_adopts_legacy_core_without_modifying_it(tmp_path) -> None:
    old = tmp_path / "empneon_core.sqlite3"
    new = tmp_path / "empneon_core_memory.sqlite3"
    with open_db(old) as conn:
        AgentStore(conn).create(Agent("bella", "Bella", game_id="bella", adapter="sims4"))
    before = old.read_bytes()

    status = empneon_state.prepare_database(str(new), str(old), str(tmp_path / "missing.db"))

    with open_db(new) as conn:
        assert AgentStore(conn).get("bella").name == "Bella"
    assert old.read_bytes() == before
    assert status.active_path == str(new.resolve())
    assert status.completed is True
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest tests/test_sims4_backend.py -k "unified_database or prepare_database" -q`

Expected: FAIL because `MEMORY_DB_PATH`, `empneon_state`, and `prepare_database` do not exist.

- [ ] **Step 3: Implement the minimal safe database preparation**

```python
@dataclass(frozen=True)
class MigrationStatus:
    active_path: str
    sources: tuple[str, ...] = ()
    backups: tuple[str, ...] = ()
    completed: bool = True
    error: str | None = None

    def as_dict(self) -> dict[str, object]:
        return dataclasses.asdict(self)


def prepare_database(target: str, legacy_core: str, legacy_adapter: str) -> MigrationStatus:
    destination = Path(target).resolve()
    sources = tuple(str(path.resolve()) for path in map(Path, (legacy_core, legacy_adapter)) if path.exists())
    backups: list[str] = []
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        core_source = Path(legacy_core).resolve()
        if not destination.exists() and core_source.exists() and core_source != destination:
            with sqlite3.connect(core_source) as source, sqlite3.connect(destination) as output:
                source.backup(output)
            backup = core_source.with_suffix(core_source.suffix + ".pre-core-memory.bak")
            if not backup.exists():
                shutil.copy2(core_source, backup)
            backups.append(str(backup))
        with open_db(destination):
            pass
        return MigrationStatus(str(destination), sources, tuple(backups))
    except Exception as exc:
        return MigrationStatus(str(destination), sources, tuple(backups), False, str(exc))


def open_memory(target: str):
    return open_db(target)
```

In `ai_sims_server.py`, derive `MEMORY_DB_PATH` from `memory_database`, retain the two old config keys only as `LEGACY_CORE_DB_PATH` and `LEGACY_ADAPTER_DB_PATH`, call `prepare_database()` during startup, and point save-slot backup/restore functions exclusively at `MEMORY_DB_PATH`.

- [ ] **Step 4: Run focused and save-slot regression tests**

Run: `$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest tests/test_sims4_backend.py -k "database or memory_session or checkpoint" -q`

Expected: PASS; neither legacy input changes.

- [ ] **Step 5: Commit**

```powershell
git add adapters/thesims4/backend/empneon_state.py adapters/thesims4/backend/ai_sims_server.py adapters/thesims4/config/config.json adapters/thesims4/tests/test_sims4_backend.py
git commit -m "feat(sims4): unify cognitive database"
```

### Task 2: Canonical Identity and Idempotent Legacy Adapter Import

**Files:**
- Modify: `adapters/thesims4/backend/empneon_state.py`
- Modify: `adapters/thesims4/backend/ai_sims_server.py`
- Test: `adapters/thesims4/tests/test_sims4_backend.py`

**Interfaces:**
- Produces: `identity_stores(conn) -> IdentityStores`
- Produces: `sync_sim(conn, sim: Mapping[str, object]) -> dict[str, object]`
- Produces: `import_legacy_adapter(conn, source_path: str) -> bool`
- Produces: `relationship_view`, `emotion_view`, `voice_view`, and `save_voice` backed only by Core stores.

- [ ] **Step 1: Write failing identity and migration tests**

```python
def test_sync_sim_populates_all_canonical_identity_stores(tmp_path) -> None:
    with open_db(tmp_path / "memory.db") as conn:
        profile = empneon_state.sync_sim(conn, {
            "id": "bella", "name": "Bella", "traits": ["Outgoing", "Good"],
            "current_mood": "happy", "aspiration": "Successful Lineage",
            "needs": {"hunger": 20}, "career": "Secret Agent",
        })
        stores = empneon_state.identity_stores(conn)
        assert stores.agents.get("bella").occupation == "Secret Agent"
        assert stores.personality.get("bella").extraversion > 0.5
        assert stores.emotions.get("bella", "happiness").value > 0
        assert {goal.description for goal in stores.goals.get_all("bella", "active")} == {
            "Aspiration: Successful Lineage", "Restore hunger"
        }
        assert profile["id"] == "bella"


def test_legacy_adapter_import_is_idempotent_and_read_only(tmp_path) -> None:
    legacy = tmp_path / "ai_sims_memory.sqlite3"
    with sqlite3.connect(legacy) as source:
        source.executescript("""
            CREATE TABLE sim_profiles (
                sim_id TEXT PRIMARY KEY, name TEXT, identity_json TEXT,
                personality_json TEXT, values_json TEXT, behavioral_rules_json TEXT,
                knowledge_json TEXT, goals_json TEXT, voice_json TEXT,
                created_at REAL, updated_at REAL
            );
            CREATE TABLE goals (
                id INTEGER PRIMARY KEY, sim_id TEXT, goal TEXT,
                status TEXT, importance REAL, updated_at REAL
            );
        """)
        source.execute(
            "INSERT INTO sim_profiles VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ("bella", "Bella", "{}", "{}", "[]", "[]", "{}", "[]", "{}", 1, 1),
        )
        source.execute("INSERT INTO goals VALUES (1,'bella','Protect family','active',0.8,1)")
    before = legacy.read_bytes()
    with open_db(tmp_path / "empneon_core_memory.sqlite3") as conn:
        assert empneon_state.import_legacy_adapter(conn, str(legacy)) is True
        assert empneon_state.import_legacy_adapter(conn, str(legacy)) is False
        assert AgentStore(conn).get("bella") is not None
        assert len(GoalStore(conn).get_all("bella")) == 1
    assert legacy.read_bytes() == before
```

- [ ] **Step 2: Run and verify RED**

Run: `$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest tests/test_sims4_backend.py -k "canonical_identity or legacy_adapter_import" -q`

Expected: FAIL because the canonical synchronization/import functions are missing.

- [ ] **Step 3: Implement canonical mappings and deterministic goal IDs**

Use `uuid.uuid5(uuid.NAMESPACE_URL, f"empneon:sims4:{agent_id}:{kind}:{name}")` for aspiration/need goals. Normalize Sims percentages with `max(0.0, min(1.0, value / 100.0))`. Map known trait words directly to OCEAN adjustments and leave every unknown dimension at `0.5`. Upsert `Agent`, `Personality`, `EmotionalState`, `Goal`, `Relationship`, and `VoiceProfile` through their Core stores.

Legacy import reads the source with SQLite read-only URI mode, creates a `.pre-core-memory.bak` copy once, uses a `DocumentMemoryStore` marker named `thesims4.migration/legacy-adapter-v1`, and writes all imported Core records in a savepoint. Remove new calls to `save_profile`, `save_relationship`, `save_emotion`, and document-backed voice functions; keep route response shapes by converting Core dataclasses to the existing JSON fields.

- [ ] **Step 4: Run identity, profile, relationship, emotion, and voice tests**

Run: `$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest tests/test_sims4_backend.py -k "profile or relationship or emotion or voice or legacy" -q`

Expected: PASS with no duplicate rows after a second sync/import.

- [ ] **Step 5: Commit**

```powershell
git add adapters/thesims4/backend/empneon_state.py adapters/thesims4/backend/ai_sims_server.py adapters/thesims4/tests/test_sims4_backend.py
git commit -m "feat(sims4): canonicalize Sim identity"
```

### Task 3: Private Episodic, Belief, and Vector Memory

**Files:**
- Modify: `adapters/thesims4/src/empneon_thesims4/adapter.py`
- Modify: `adapters/thesims4/backend/empneon_state.py`
- Modify: `adapters/thesims4/backend/ai_sims_server.py`
- Test: `adapters/thesims4/tests/test_adapter.py`
- Test: `adapters/thesims4/tests/test_sims4_backend.py`

**Interfaces:**
- Produces: `feature_hash(text: str, dimensions: int = 384) -> list[float]`
- Produces: `record_observed_event(conn, event, perceptions, factual_statement=None) -> Event`
- Produces: `record_confirmed_experience(conn, proposal, result) -> Event | None`
- Produces: `relevant_memories(conn, agent_id, query, limit=6) -> list[dict[str, object]]`.

- [ ] **Step 1: Write failing deterministic-vector and privacy tests**

```python
def test_feature_hash_is_deterministic_and_normalized() -> None:
    first = feature_hash("Bella remembers a secret garden")
    second = feature_hash("Bella remembers a secret garden")
    assert first == second
    assert len(first) == 384
    assert sum(value * value for value in first) == pytest.approx(1.0)


def test_vector_retrieval_never_leaks_an_unobserved_secret(tmp_path) -> None:
    with open_db(tmp_path / "memory.db") as conn:
        empneon_state.sync_sim(conn, {"id": "bella", "name": "Bella"})
        empneon_state.sync_sim(conn, {"id": "mortimer", "name": "Mortimer"})
        event = Event("A key is hidden in the garden", ["bella"])
        empneon_state.record_observed_event(conn, event, {"bella": "I saw the garden key"}, "The key is in the garden")
        assert empneon_state.relevant_memories(conn, "bella", "garden key")
        assert empneon_state.relevant_memories(conn, "mortimer", "garden key") == []
```

- [ ] **Step 2: Run and verify RED**

Run: `$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest tests/test_adapter.py tests/test_sims4_backend.py -k "feature_hash or unobserved_secret" -q`

Expected: FAIL because vector encoding and canonical observation recording are missing.

- [ ] **Step 3: Implement minimal hashing, provenance, and filtered retrieval**

```python
def feature_hash(text: str, dimensions: int = 384) -> list[float]:
    vector = [0.0] * dimensions
    for token in re.findall(r"\w+", text.casefold()):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        raw = int.from_bytes(digest, "big")
        vector[raw % dimensions] += -1.0 if raw & 1 else 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else vector
```

`record_observed_event()` creates the event, creates exactly one observation per explicit perception, creates a belief only for the observation owner when `factual_statement` is non-empty, and indexes the event. `relevant_memories()` searches more candidates than requested, intersects event IDs with `ObservationStore.get_for_agent(agent_id)`, loads events, and truncates after privacy filtering. Catch only sqlite-vec load/search errors and fall back to recent observed events.

Change chat so the incoming player statement is observed before cognition, while generated dialogue/memory is persisted only from `confirm_action()` after success. Replace new `DocumentMemoryStore` experience writes with these functions.

- [ ] **Step 4: Run epistemic, memory, chat-confirmation, and adapter tests**

Run: `$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest tests/test_adapter.py tests/test_sims4_backend.py -k "memory or belief or observation or chat_waits" -q`

Expected: PASS; failed confirmation adds no confirmed event.

- [ ] **Step 5: Commit**

```powershell
git add adapters/thesims4/src/empneon_thesims4/adapter.py adapters/thesims4/backend/empneon_state.py adapters/thesims4/backend/ai_sims_server.py adapters/thesims4/tests/test_adapter.py adapters/thesims4/tests/test_sims4_backend.py
git commit -m "feat(sims4): add private cognitive memory"
```

### Task 4: Dynamic CLOD, Provider Results, Scheduling, and Telemetry

**Files:**
- Modify: `core/src/empneon/providers/llm/configured.py`
- Create: `core/tests/unit/test_configured_provider.py`
- Modify: `adapters/thesims4/src/empneon_thesims4/adapter.py`
- Modify: `adapters/thesims4/backend/ai_sims_server.py`
- Modify: `adapters/thesims4/config/config.json`
- Test: `adapters/thesims4/tests/test_adapter.py`
- Test: `adapters/thesims4/tests/test_sims4_backend.py`

**Interfaces:**
- Produces: `ConfiguredProviderRouter.generate_result(...) -> GenerationResult`; existing `generate(...) -> str` delegates to it.
- Produces: `cognition_priority(payload) -> tuple[float, int, float]` containing urgency, preferred CLOD, and deeper-reasoning value.
- Produces: `CognitionQueue.run(request: CognitiveRequest, work: Callable[[], object]) -> object`, backed by one bounded `PriorityScheduler` and `ACTIVE_AGENT_LIMIT` workers.

- [ ] **Step 1: Write failing provider-result, priority, dynamic-CLOD, and usage tests**

```python
async def test_router_exposes_generation_result_without_breaking_generate(monkeypatch) -> None:
    expected = GenerationResult("hello", 10, 3, 25)
    router = ConfiguredProviderRouter(
        "test", {"test": {"endpoint": "http://localhost", "model": "stub"}}, {"large": {}}
    )
    provider = SimpleNamespace(generate=AsyncMock(return_value=expected))
    monkeypatch.setattr(router, "provider_for", lambda _task: provider)
    result = await router.generate_result("large", (Message("user", "hi"),))
    assert result.prompt_tokens == 10
    assert await router.generate("large", (Message("user", "hi"),)) == "hello"


def test_player_dialogue_uses_dynamic_clod_and_records_usage(tmp_path, monkeypatch) -> None:
    content = json.dumps({
        "dialogue": "Hello.", "emotion": "happy", "intent": "greet",
        "relationship": {"friendship_delta": 0, "romance_delta": 0, "trust_delta": 0},
        "memory": {"importance": 0.2, "summary": "A greeting."},
        "animation": "friendly_chat",
    })
    generation = GenerationResult(content, 20, 8, 30)
    class Router:
        def config_for(self, _task):
            return {"name": "test", "model": "stub", "max_tokens": 300,
                    "context_tokens": 4096, "latency_ms": 1000, "ram_mb": 64, "vram_mb": 0}
        def provider_for(self, _task):
            return SimpleNamespace(capabilities=ModelCapabilities(structured_output=True, local=True))
        async def generate_result(self, *_args, **_kwargs):
            return generation
    monkeypatch.setattr(ai_sims_server, "provider_router", lambda: Router())
    monkeypatch.setattr(ai_sims_server, "MEMORY_DB_PATH", str(tmp_path / "empneon_core_memory.sqlite3"))
    result = ai_sims_server.chat({
        "speaker": {"id": "bella", "name": "Bella"},
        "listener": {"id": "mortimer", "name": "Mortimer"},
        "message": "Hello", "event": {"type": "player_conversation", "source": "test"},
        "available_actions": ["friendly_chat"],
    })
    with open_db(tmp_path / "empneon_core_memory.sqlite3") as conn:
        telemetry = UsageStore(conn).telemetry("bella")
    assert result["selected_clod"] == 3
    assert telemetry["actual"] == {"prompt_tokens": 20, "completion_tokens": 8, "latency_ms": 30}
```

- [ ] **Step 2: Run and verify RED**

Run Core: `$env:PYTHONPATH='src'; py -3.12 -m pytest tests/unit/test_configured_provider.py -q`

Run Sims: `$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest tests/test_adapter.py tests/test_sims4_backend.py -k "dynamic_clod or records_usage or priority" -q`

Expected: FAIL because result-preserving routing and dynamic selection are absent.

- [ ] **Step 3: Preserve provider metadata and route cognition dynamically**

```python
async def generate_result(self, task, messages, *, schema=None, temperature=None):
    request = self.generation_request(task, messages, schema=schema, temperature=temperature)
    return await self.provider_for(task).generate(request)

async def generate(self, task, messages, *, schema=None, temperature=None):
    return (await self.generate_result(task, messages, schema=schema, temperature=temperature)).content
```

Add cognition scoring exactly as specified: player `0.4`, novelty `0.2`, emotional intensity `0.2 * intensity`, active-goal relevance `0.2`, bounded to `1.0`. Build `CognitionRoute` values from `small`, `large`, and optional `deep` config entries and their declared RAM/VRAM/context/completion/latency estimates.

Implement `CognitionQueue` with a `PriorityScheduler`, a dictionary keyed by request ID, one `threading.Event` per submitted job, and `ACTIVE_AGENT_LIMIT` daemon workers. `run()` registers the job, submits the request, waits no longer than its deadline, and returns or re-raises the worker result. Each worker pops the globally highest-priority request, executes only that request's callable, stores its outcome, and signals its event. This makes concurrent HTTP requests honor priority without associating one payload with another request. Replace the custom semaphore path with this coordinator. Call `decide_dynamic()` inside the selected job and capture the selected request CLOD inside the resolver. Record `GenerationResult` with `UsageStore`; record CLOD 1 as `core-rules/clod1` with a zero-token result.

- [ ] **Step 4: Run Core and Sims suites focused on cognition**

Run: `$env:PYTHONPATH='src'; py -3.12 -m pytest tests/unit/test_configured_provider.py tests/unit/test_runtime.py tests/unit/test_priority_scheduler.py tests/unit/test_usage_store.py -q`

Run: `$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest tests -k "clod or usage or priority or provider" -q`

Expected: PASS, including existing `llm_chat` compatibility.

- [ ] **Step 5: Commit**

```powershell
git add core/src/empneon/providers/llm/configured.py core/tests/unit/test_configured_provider.py adapters/thesims4/src/empneon_thesims4/adapter.py adapters/thesims4/backend/ai_sims_server.py adapters/thesims4/config/config.json adapters/thesims4/tests
git commit -m "feat(sims4): select and measure cognition"
```

### Task 5: Rich, Backward-Compatible Sims Observations

**Files:**
- Modify: `adapters/thesims4/ts4script/ai_sims_agent.py`
- Modify: `adapters/thesims4/src/empneon_thesims4/adapter.py`
- Test: `adapters/thesims4/tests/test_sims4_mod_autonomy.py`
- Test: `adapters/thesims4/tests/test_adapter.py`

**Interfaces:**
- Produces optional payload keys `needs`, `moodlets`, `aspiration`, `career`, `skills`, `household`, `location`, and `nearby_sims`.
- Existing minimal `{id, name, traits, current_mood}` payload remains valid.

- [ ] **Step 1: Write failing tolerant-probe and observation-fact tests**

```python
# Add inside test_alarm_submits_one_npc_pair_without_overlap after loading `agent`.
def assert_rich_payload_aggregation(agent, monkeypatch) -> None:
    info = SimpleNamespace(sim_id="bella", full_name="Bella", trait_tracker=None)
    monkeypatch.setattr(agent, "sim_needs", lambda _info: {"hunger": 18})
    monkeypatch.setattr(agent, "sim_moodlets", lambda _info: ["Uncomfortable"])
    monkeypatch.setattr(agent, "sim_aspiration", lambda _info: "Master Chef")
    payload = agent.sim_info_payload(info)
    assert payload["needs"] == {"hunger": 18}
    assert payload["moodlets"] == ["Uncomfortable"]
    assert payload["aspiration"] == "Master Chef"


def test_old_payload_still_observes_with_neutral_optional_facts() -> None:
    event = Sims4Adapter({"speaker": {"id": "bella"}, "available_actions": ["friendly_chat"]}).observe()[0]
    assert event.facts["needs"] == {}
    assert event.facts["moodlets"] == []
```

- [ ] **Step 2: Run and verify RED**

Run: `$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest tests/test_sims4_mod_autonomy.py tests/test_adapter.py -k "optional_cognition or neutral_optional" -q`

Expected: FAIL because optional probes/facts are absent.

- [ ] **Step 3: Implement narrow safe probes**

Add small functions following the existing `getattr`/`try` pattern: `sim_needs`, `sim_moodlets`, `sim_aspiration`, `sim_career`, `sim_skills`, and `sim_household`. Each returns `{}`, `[]`, or `"unknown"` on unsupported APIs and caps collections at 20 entries. Add `current_location()` and nearby Sim payloads to chat/autonomy requests. Copy these fields into `WorldEvent.facts` without requiring them. Do not import unstable Sims modules solely for these probes.

- [ ] **Step 4: Run mod contract and adapter tests**

Run: `$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest tests/test_sims4_mod_autonomy.py tests/test_adapter.py -q`

Expected: PASS on fake old and rich Sims objects.

- [ ] **Step 5: Commit**

```powershell
git add adapters/thesims4/ts4script/ai_sims_agent.py adapters/thesims4/src/empneon_thesims4/adapter.py adapters/thesims4/tests/test_sims4_mod_autonomy.py adapters/thesims4/tests/test_adapter.py
git commit -m "feat(sims4): observe richer game state"
```

### Task 6: Confirmation Consequences, Timeline, Replay, and Identity Portability

**Files:**
- Modify: `adapters/thesims4/backend/empneon_state.py`
- Modify: `adapters/thesims4/backend/ai_sims_server.py`
- Modify: `adapters/thesims4/src/empneon_thesims4/adapter.py`
- Test: `adapters/thesims4/tests/test_sims4_backend.py`

**Interfaces:**
- Produces: `apply_confirmed_consequences(conn, proposal, result) -> None`.
- Produces: `export_identity(conn, agent_id) -> dict[str, object]` and `import_identity(conn, data) -> Agent`.
- Confirmation accepts validated relationship, emotion, need, and goal status paths.

- [ ] **Step 1: Write failing consequence and portability tests**

```python
def test_failed_action_records_replay_but_applies_no_consequences(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ai_sims_server, "MEMORY_DB_PATH", str(tmp_path / "empneon_core_memory.sqlite3"))
    proposal = ai_sims_server.autonomous_action({
        "speaker": {"id": "bella", "name": "Bella"},
        "listener": {"id": "mortimer", "name": "Mortimer"},
        "event": {"type": "autonomous_social", "source": "test"},
        "available_actions": ["friendly_chat"],
    })
    decision_id = proposal["decision_id"]
    ai_sims_server.confirm_action({"decision_id": decision_id, "action": "friendly_chat", "status": "failed", "reason": "cancelled"})
    with open_db(tmp_path / "empneon_core_memory.sqlite3") as conn:
        assert replay_action_record(conn, decision_id)["result"]["status"] == "failed"
        assert RelationshipStore(conn).get("bella", "mortimer") is None


def test_identity_export_import_round_trip_uses_unified_database(tmp_path) -> None:
    with open_db(tmp_path / "source.db") as source:
        empneon_state.sync_sim(source, {"id": "bella", "name": "Bella", "traits": ["Good"]})
        exported = empneon_state.export_identity(source, "bella")
    with open_db(tmp_path / "target.db") as target:
        empneon_state.import_identity(target, exported)
        assert export_agent("bella", empneon_state.identity_stores(target)) == exported
```

- [ ] **Step 2: Run and verify RED**

Run: `$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest tests/test_sims4_backend.py -k "replay_but_applies_no or identity_export_import" -q`

Expected: FAIL because expanded consequences and portability wrappers are absent.

- [ ] **Step 3: Implement validated transaction boundaries**

Allow only these confirmed paths: `relationship.friendship`, `relationship.romance`, `relationship.trust`, `emotion.<name>`, `need.<name>`, and `goal.<uuid>.status`. Validate numeric ranges and goal status values before opening the write transaction. Call `actions.confirm()` for all statuses; apply Core store mutations and confirmed episodic memory only for `succeeded`. Wrap `export_agent()` and `import_agent()` using one `IdentityStores` set from the unified connection.

- [ ] **Step 4: Run confirmation, replay, timeline, serialization, and save-slot tests**

Run Sims: `$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest tests/test_sims4_backend.py -k "confirm or replay or timeline or identity or memory_session" -q`

Run Core: `$env:PYTHONPATH='src'; py -3.12 -m pytest tests/unit/test_replay.py tests/unit/test_timeline.py tests/unit/test_serialization.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add adapters/thesims4/backend/empneon_state.py adapters/thesims4/backend/ai_sims_server.py adapters/thesims4/src/empneon_thesims4/adapter.py adapters/thesims4/tests/test_sims4_backend.py
git commit -m "feat(sims4): persist confirmed cognition"
```

### Task 7: Local Diagnostics and In-Game Commands

**Files:**
- Modify: `adapters/thesims4/backend/empneon_state.py`
- Modify: `adapters/thesims4/backend/ai_sims_server.py`
- Modify: `adapters/thesims4/ts4script/ai_sims_agent.py`
- Test: `adapters/thesims4/tests/test_sims4_backend.py`
- Test: `adapters/thesims4/tests/test_sims4_mod_autonomy.py`

**Interfaces:**
- Adds GET routes `/diagnostics/sim`, `/diagnostics/timeline`, `/diagnostics/replay`, `/diagnostics/usage`, `/diagnostics/migration`, and `/identity/export`.
- Adds POST `/identity/import`.
- Adds cheat aliases `empneon.status`, `empneon.timeline`, `empneon.beliefs`, `empneon.goals`, and `empneon.usage`.

- [ ] **Step 1: Write failing route validation and command-registration tests**

```python
def test_diagnostics_sim_returns_canonical_state_without_secrets(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ai_sims_server, "MEMORY_DB_PATH", str(tmp_path / "memory.db"))
    with open_db(tmp_path / "memory.db") as conn:
        empneon_state.sync_sim(conn, {"id": "bella", "name": "Bella"})
    handler = ai_sims_server.Handler.__new__(ai_sims_server.Handler)
    handler.path = "/diagnostics/sim?sim_id=bella"
    responses = []
    monkeypatch.setattr(handler, "send_json", lambda status, body: responses.append((status, body)))
    handler.do_GET()
    status, body = responses[0]
    assert status == 200
    assert body["agent"]["name"] == "Bella"
    assert "api_key" not in json.dumps(body).casefold()


@pytest.mark.parametrize("path, expected", [
    ("/diagnostics/sim", 400),
    ("/diagnostics/replay?decision_id=missing", 404),
])
def test_diagnostics_require_identifiers(monkeypatch, path, expected) -> None:
    handler = ai_sims_server.Handler.__new__(ai_sims_server.Handler)
    handler.path = path
    responses = []
    monkeypatch.setattr(handler, "send_json", lambda status, body: responses.append((status, body)))
    handler.do_GET()
    assert responses[0][0] == expected


def test_empneon_diagnostic_commands_are_registered() -> None:
    source = Path(mod.__file__).read_text(encoding="utf-8")
    for command in ("empneon.status", "empneon.timeline", "empneon.beliefs", "empneon.goals", "empneon.usage"):
        assert f'@command("{command}")' in source
```

- [ ] **Step 2: Run and verify RED**

Run: `$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest tests/test_sims4_backend.py tests/test_sims4_mod_autonomy.py -k "diagnostic or empneon" -q`

Expected: FAIL because routes and commands are missing.

- [ ] **Step 3: Implement read models, route status mapping, and concise commands**

Build diagnostics only from Core store dataclasses, `agent_timeline`, `replay_action_record`, and `UsageStore.telemetry`. Parse query values with existing `urllib.parse`; reject blank or over-128-character identifiers. Map `ValueError` for unknown records to `404`, malformed input to `400`, and storage failures to a generic `500` body while logging details server-side. `/identity/import` accepts only a JSON object and calls Core validation. Commands call these local routes and print counts plus the latest entries; keep all `ai.*` aliases.

- [ ] **Step 4: Run diagnostics, handler, and mod tests**

Run: `$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest tests/test_sims4_backend.py tests/test_sims4_mod_autonomy.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add adapters/thesims4/backend/empneon_state.py adapters/thesims4/backend/ai_sims_server.py adapters/thesims4/ts4script/ai_sims_agent.py adapters/thesims4/tests
git commit -m "feat(sims4): expose cognitive diagnostics"
```

### Task 8: In-Game Test Plan, Packaging, and Full Verification

**Files:**
- Create: `adapters/thesims4/docs/in-game-core-feature-test-plan.md`
- Modify: `adapters/thesims4/README.md`
- Modify: `adapters/thesims4/docs/setup.md`
- Modify: `scripts/release.py` only if its runtime allowlist does not already include the new backend module/document.
- Test: `scripts/test_release.py`

**Interfaces:**
- Produces player-facing setup and an exact manual scenario for every implemented Core capability.
- Preserves the self-contained release ZIP and prebuilt `.package`/`.ts4script` contract.

- [ ] **Step 1: Write a failing release-content assertion**

```python
def test_sims_release_contains_core_integration_runtime_and_test_plan(tmp_path) -> None:
    root = _fake_repo(tmp_path)
    _write(root / "adapters/thesims4/backend/empneon_state.py")
    _write(root / "adapters/thesims4/docs/in-game-core-feature-test-plan.md")
    assets = release.package_component(root, "thesims4", "0.3.0", root / "release")
    archive = next(path for path in assets if path.suffix == ".zip")
    with zipfile.ZipFile(archive) as release:
        names = set(release.namelist())
    assert "backend/empneon_state.py" in names
    assert "docs/in-game-core-feature-test-plan.md" in names
```

- [ ] **Step 2: Run and verify RED**

Run: `py -3.12 -m pytest scripts/test_release.py -k "core_integration_runtime" -q`

Expected: FAIL because the runtime module and test plan are not packaged yet.

- [ ] **Step 3: Write the in-game plan and update packaging/docs**

The manual plan must include, for each capability, prerequisites, exact console command/gameplay action, expected visible result, expected `empneon.*` diagnostic result, restart/save-slot persistence check, and cleanup. Cover: unified migration, canonical profile, OCEAN traits, emotions, goals/needs, directed relationships, private beliefs, vector retrieval, CLOD 1/provider CLOD, usage, priority under concurrent Sims, successful/failed confirmation, timeline, replay, export/import, save-slot isolation, and LLM-unavailable fallback.

Update setup paths to `empneon_core_memory.sqlite3`. Ensure the release allowlist includes `backend/empneon_state.py` and the new test plan while still excluding databases, backups, logs, caches, secrets, tests, and unrelated adapters.

- [ ] **Step 4: Run all automated verification**

Run Core:

```powershell
cd core
$env:PYTHONPATH='src'
py -3.12 -m pytest tests -q -p no:cacheprovider
```

Expected: 167 or more passed, 0 failed.

Run Sims:

```powershell
cd adapters/thesims4
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest tests -q -p no:cacheprovider
py -3.12 build_mod.py
```

Expected: 18 or more passed, 0 failed; `.package` and `.ts4script` artifacts created.

Run release contracts and package smoke test:

```powershell
cd ../..
$env:PYTHONPATH='core\src;adapters\thesims4\src'
py -3.12 -m pytest scripts/test_release.py -q -p no:cacheprovider
py -3.12 scripts/release.py package thesims4 0.3.0 --output .release-smoke
$archive = (Get-ChildItem .release-smoke/Empneon-TheSims4-*.zip).FullName
Expand-Archive $archive .release-smoke/extracted
& .\.release-smoke\extracted\run_backend.ps1 -InstallOnly
```

Expected: release contracts pass and backend dependencies install from the ZIP without repository source.

- [ ] **Step 5: Review for secrets and legacy writes**

Run:

```powershell
rg -n "ai_sims_memory|empneon_core\.sqlite3" adapters/thesims4
rg -n "api[_-]?key|secret|token" adapters/thesims4/config adapters/thesims4/backend
git diff --check
```

Expected: old database names appear only in migration compatibility/tests/docs; no credential values; no whitespace errors.

- [ ] **Step 6: Commit**

```powershell
git add adapters/thesims4/docs adapters/thesims4/README.md scripts/release.py scripts/test_release.py
git commit -m "docs(sims4): add in-game Core test plan"
```

- [ ] **Step 7: Final branch verification**

Run: `git status --short --branch`

Expected: `feature/sims4-core-integration` with a clean worktree.
