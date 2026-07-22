# Cross-Adapter Attraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Carry directed, game-observed attraction from any adapter into Empneon's normalized relationship context, with The Sims 4 preferring supported mod data over the official Lovestruck track.

**Architecture:** Extend the existing `AgentStateSnapshot.relationships[target_id]` mapping with one optional scalar instead of adding a database model. The Sims script mod resolves WickedWhims first, then the exact official Lovestruck tuning ID, and passes normalized data plus native evidence through the existing payload; the existing adapter, snapshot store, diagnostic, and prompt paths do the rest.

**Tech Stack:** Python 3.12 Core/backend/tests, Python 3.7-compatible Sims script source, existing Sims 4 runtime APIs, standard library only, pytest, Ruff, mypy.

## Global Constraints

- `attraction` is optional, directed, and normalized to `-1.0..1.0`; absence is not neutral.
- Only game observations may set attraction. Do not add `attraction_delta`, Core persistence columns, or model-owned mutation.
- Sims source order is WickedWhims, official Lovestruck, then omission; the first valid reader wins.
- Use the exact official attraction resource ID `358555`; do not scan tuning names or infer arbitrary mod tracks.
- Reader import/API/value failures fall through without breaking conversation capture.
- Preserve source, native value, and native label in snapshot-native diagnostics, but expose only normalized attraction as model relationship context.
- Keep the Sims script compatible with Python 3.7 and add no dependency.
- Preserve the unrelated uncommitted name-response changes and SQLite `-wal`/`-shm` files; stage only files named by each task.

---

## File Map

- `core/src/empneon/core/contracts.py`: validate the optional common attraction scalar.
- `core/tests/unit/test_contracts.py`: common range and JSON round-trip coverage.
- `tests/cross_adapter/test_game_adapters.py`: prove a non-Sims adapter can carry the field unchanged.
- `adapters/thesims4/ts4script/ai_sims_agent.py`: read WickedWhims or official Lovestruck and report the selected source.
- `adapters/thesims4/tests/test_sims4_mod_autonomy.py`: source priority, normalization, fallback, omission, direction, and console coverage.
- `adapters/thesims4/src/empneon_thesims4/adapter.py`: move the normalized value and native evidence into `AgentStateSnapshot`.
- `adapters/thesims4/tests/test_adapter.py`: adapter translation coverage.
- `adapters/thesims4/backend/ai_sims_server.py`: keep attraction in the model-facing relationship for the current request.
- `adapters/thesims4/backend/empneon_state.py`: include observed attraction and its source in diagnostics.
- `adapters/thesims4/tests/test_sims4_backend.py`: prompt, persistence, diagnostic, and non-mutation coverage.
- `adapters/thesims4/docs/in-game-core-feature-test-plan.md`: add attraction evidence to the existing partial Test 5.
- `adapters/thesims4/docs/in-game-core-feature-test-results.md`: record that automated support is ready while live Test 5 remains partial.

### Task 1: Add the common attraction contract

**Files:**
- Modify: `core/tests/unit/test_contracts.py`
- Modify: `core/src/empneon/core/contracts.py:74-78`
- Modify: `tests/cross_adapter/test_game_adapters.py`

**Interfaces:**
- Consumes: existing `AgentStateSnapshot.from_mapping(value)` and Godot's generic event reconstruction.
- Produces: optional `relationships[target_id]["attraction"]: float` constrained to `-1.0..1.0`.

- [ ] **Step 1: Write failing contract and round-trip tests**

Add these tests to `core/tests/unit/test_contracts.py`:

```python
def test_agent_state_snapshot_preserves_directed_attraction_and_native_source() -> None:
    snapshot = AgentStateSnapshot.from_mapping(
        {
            "schema_version": 1,
            "adapter": "example-game",
            "agent_id": "alice",
            "relationships": {"bob": {"attraction": -0.75}},
            "native": {
                "relationships": {
                    "bob": {
                        "attraction": {
                            "source": "example_game",
                            "value": "repelled",
                            "label": "Repelled",
                        }
                    }
                }
            },
        }
    )

    encoded = json.loads(json.dumps(dataclasses.asdict(snapshot)))

    assert encoded["relationships"]["bob"]["attraction"] == -0.75
    assert encoded["native"]["relationships"]["bob"]["attraction"] == {
        "source": "example_game",
        "value": "repelled",
        "label": "Repelled",
    }
```

Add `("relationships", "attraction", -1.1)` and `("relationships", "attraction", 1.1)` to the existing `test_agent_state_snapshot_rejects_out_of_range_values` parameter list. Add a separate non-finite case because JSON validation, not numeric comparison, owns that boundary:

```python
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_agent_state_snapshot_rejects_non_finite_attraction(value: float) -> None:
    with pytest.raises(ValueError, match="attraction|JSON-compatible"):
        AgentStateSnapshot(
            1,
            "test",
            "alice",
            relationships={"bob": {"attraction": value}},
        )
```

- [ ] **Step 2: Run the Core test and verify the range case fails**

Run from the repository root:

```powershell
$env:PYTHONPATH='core\src'; py -3.12 -m pytest -q -p no:cacheprovider core/tests/unit/test_contracts.py
```

Expected: the new out-of-range attraction cases fail because the contract does not validate that key yet; the preservation case already demonstrates that the extensible mapping survives JSON conversion.

- [ ] **Step 3: Add the single common validation line**

In `AgentStateSnapshot.__post_init__`, keep the existing loop and add one call:

```python
        for relationship in self.relationships.values():
            if isinstance(relationship, Mapping):
                _bounded(relationship, "affinity", -1.0, 1.0)
                _bounded(relationship, "romance", 0.0, 1.0)
                _bounded(relationship, "trust", 0.0, 1.0)
                _bounded(relationship, "attraction", -1.0, 1.0)
```

- [ ] **Step 4: Prove a non-Sims adapter uses the same field**

Add this focused test to `tests/cross_adapter/test_game_adapters.py`:

```python
def test_godot_round_trip_preserves_common_attraction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, WorldEvent] = {}
    resolve = bridge_module.resolve_clod1

    def capture(request: CognitiveRequest) -> Decision:
        captured["event"] = request.event
        return resolve(request)

    monkeypatch.setattr(bridge_module, "resolve_clod1", capture)
    bridge = GodotBridge()
    bridge.decide(
        {
            "agent_id": "agent-a",
            "event": asdict(
                WorldEvent(
                    "encounter",
                    ("agent-a", "agent-b"),
                    agent_state=AgentStateSnapshot(
                        1,
                        "godot",
                        "agent-a",
                        relationships={"agent-b": {"attraction": 0.4}},
                    ),
                )
            ),
        }
    )

    assert captured["event"].agent_state is not None
    assert captured["event"].agent_state.relationships == {
        "agent-b": {"attraction": 0.4}
    }
```

- [ ] **Step 5: Run Core and cross-adapter checks**

```powershell
$env:PYTHONPATH='core\src'; py -3.12 -m pytest -q -p no:cacheprovider core/tests/unit/test_contracts.py
$env:PYTHONPATH='core\src;adapters\thesims4\src;adapters\godot\src'; py -3.12 -m pytest -q -p no:cacheprovider tests/cross_adapter/test_game_adapters.py
```

Expected: both commands pass.

- [ ] **Step 6: Commit only the common contract files**

```powershell
git add core/src/empneon/core/contracts.py core/tests/unit/test_contracts.py tests/cross_adapter/test_game_adapters.py
git commit -m "feat(core): accept directed attraction context"
```

### Task 2: Read Sims attraction from WickedWhims or Lovestruck

**Files:**
- Modify: `adapters/thesims4/tests/test_sims4_mod_autonomy.py`
- Modify: `adapters/thesims4/ts4script/ai_sims_agent.py:1-45,725-780`

**Interfaces:**
- Consumes: `source_info.relationship_tracker`, `target_info.sim_id`, WickedWhims' public `get_sim_attractiveness_level_towards(TurboSim, TurboSim)`, and Lovestruck relationship track resource ID `358555`.
- Produces: `attraction_payload(source_info, target_info) -> dict | None`, shaped as `{"value": normalized, "native": {"source": str, "value": number, "label": str}}`; `relationship_payload` copies this to `relationship["attraction"]` and `relationship["native"]["attraction"]`.

- [ ] **Step 1: Write failing resolver tests**

In the existing loaded-module test in `test_sims4_mod_autonomy.py`, after the friendship/romance assertions, add:

```python
    monkeypatch.setattr(
        agent,
        "_wickedwhims_attraction",
        lambda _source, _target: {
            "value": 2 / 3,
            "native": {"source": "wickedwhims", "value": 2, "label": "HIGH"},
        },
    )
    monkeypatch.setattr(
        agent,
        "_official_attraction",
        lambda _source, _target: {
            "value": -0.5,
            "native": {
                "source": "sims4_lovestruck",
                "value": -50,
                "label": "ATTRACTION_MAIN",
            },
        },
    )
    modded = agent.attraction_payload(source_info, target_info)
    assert modded == {
        "value": 2 / 3,
        "native": {"source": "wickedwhims", "value": 2, "label": "HIGH"},
    }

    monkeypatch.setattr(agent, "_wickedwhims_attraction", lambda *_args: None)
    official = agent.attraction_payload(source_info, target_info)
    assert official == {
        "value": -0.5,
        "native": {
            "source": "sims4_lovestruck",
            "value": -50,
            "label": "ATTRACTION_MAIN",
        },
    }

    monkeypatch.setattr(agent, "_official_attraction", lambda *_args: None)
    assert agent.attraction_payload(source_info, target_info) is None
```

Before monkeypatching the reader functions in that same loaded-module test, keep the real official
reader and add focused normalization and direction assertions:

```python
    official_reader = agent._official_attraction
    track = type("ATTRACTION_MAIN", (), {})
    manager = SimpleNamespace(types={358555: track})
    monkeypatch.setattr(agent.services, "get_instance_manager", lambda _kind: manager)
    scores = {("alice", "bob"): 75.0, ("bob", "alice"): -25.0}

    def sim(sim_id):
        return SimpleNamespace(
            sim_id=sim_id,
            relationship_tracker=SimpleNamespace(
                get_relationship_score=lambda target, _track: scores[
                    (sim_id, str(getattr(target, "sim_id", target)))
                ]
            ),
        )

    assert official_reader(sim("alice"), sim("bob"))["value"] == 0.75
    assert official_reader(sim("bob"), sim("alice"))["value"] == -0.25
```

After the mod-priority assertions, add failure isolation and invalid-value checks using the same
already loaded `agent`:

```python
    monkeypatch.setattr(
        agent,
        "_wickedwhims_attraction",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("incompatible mod")),
    )
    monkeypatch.setattr(
        agent,
        "_official_attraction",
        lambda *_args: {
            "value": 0.25,
            "native": {
                "source": "sims4_lovestruck",
                "value": 25,
                "label": "ATTRACTION_MAIN",
            },
        },
    )

    result = agent.attraction_payload(SimpleNamespace(sim_id="a"), SimpleNamespace(sim_id="b"))

    assert result["value"] == 0.25
    assert agent._attraction_record("bad", float("nan"), 1, "bad") is None
    assert agent._attraction_record("bad", 1.1, 1, "bad") is None
```

- [ ] **Step 2: Run the focused tests and verify missing-reader failures**

```powershell
Set-Location adapters/thesims4
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_mod_autonomy.py -k "attraction or conversation_session"
```

Expected: FAIL because `attraction_payload`, `_official_attraction`, and `_attraction_record` do not exist.

- [ ] **Step 3: Implement the minimal ordered readers in the existing script**

Add `import math` with the standard-library imports and add these functions immediately before `relationship_payload`:

```python
OFFICIAL_ATTRACTION_TRACK_ID = 358555
WICKEDWHIMS_ATTRACTION = {
    -2: -1.0,
    -1: -0.5,
    0: 0.0,
    1: 1.0 / 3.0,
    2: 2.0 / 3.0,
    3: 1.0,
}


def _attraction_record(source, value, native_value, label):
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(normalized) or normalized < -1.0 or normalized > 1.0:
        return None
    return {
        "value": normalized,
        "native": {
            "source": source,
            "value": native_value,
            "label": str(label or "unknown"),
        },
    }


def _wickedwhims_attraction(source_info, target_info):
    try:
        from turbolib2.wrappers.sim.sim import TurboSim
        from wickedwhims.relationships.features.attractiveness.traits.preference import (
            get_sim_attractiveness_level_towards,
        )

        level = get_sim_attractiveness_level_towards(
            TurboSim(getattr(source_info, "sim_id", None)),
            TurboSim(getattr(target_info, "sim_id", None)),
        )
        native_value = int(level)
        normalized = WICKEDWHIMS_ATTRACTION.get(native_value)
        if normalized is None:
            return None
        label = getattr(level, "name", None) or str(level)
        return _attraction_record(
            "wickedwhims", normalized, native_value, label
        )
    except Exception:
        return None


def _official_attraction(source_info, target_info):
    track = None
    for resource_name in ("RELATIONSHIP_TRACK", "STATISTIC"):
        try:
            resource_type = getattr(sims4.resources.Types, resource_name, None)
            if resource_type is None:
                continue
            manager = services.get_instance_manager(resource_type)
            getter = getattr(manager, "get", None)
            if callable(getter):
                track = getter(OFFICIAL_ATTRACTION_TRACK_ID)
            if track is None:
                track = getattr(manager, "types", {}).get(OFFICIAL_ATTRACTION_TRACK_ID)
            if track is not None:
                break
        except Exception:
            pass
    if track is None:
        return None
    tracker = getattr(source_info, "relationship_tracker", None)
    target_id = getattr(target_info, "sim_id", None)
    for method_name in ("get_relationship_score", "get_relationship_score_by_sim_id"):
        method = getattr(tracker, method_name, None)
        if not callable(method):
            continue
        for target in (target_info, target_id):
            try:
                native_value = float(method(target, track))
            except Exception:
                continue
            if not math.isfinite(native_value) or not -100.0 <= native_value <= 100.0:
                return None
            return _attraction_record(
                "sims4_lovestruck",
                native_value / 100.0,
                native_value,
                getattr(track, "__name__", "ATTRACTION_MAIN"),
            )
    return None


def attraction_payload(source_info, target_info):
    for reader in (_wickedwhims_attraction, _official_attraction):
        try:
            attraction = reader(source_info, target_info)
        except Exception:
            attraction = None
        if attraction is not None:
            write_marker(
                "Attraction {} -> {}: {}".format(
                    getattr(source_info, "sim_id", "unknown"),
                    getattr(target_info, "sim_id", "unknown"),
                    attraction["native"]["source"],
                )
            )
            return attraction
    write_marker(
        "Attraction {} -> {}: unavailable".format(
            getattr(source_info, "sim_id", "unknown"),
            getattr(target_info, "sim_id", "unknown"),
        )
    )
    return None
```

Immediately after `if target_info is None: return result` in `relationship_payload`, attach the
observation once, before any friendship/romance branch can return:

```python
    attraction = attraction_payload(source_info, target_info)
    if attraction is not None:
        result["attraction"] = attraction["value"]
        result["native"] = {"attraction": attraction["native"]}
```

Leave the existing friendship/romance returns unchanged; they now all return the same result mapping
that already contains attraction when available.

- [ ] **Step 4: Run the complete script-mod test file**

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_mod_autonomy.py
```

Expected: PASS, including mod override, official fallback, no-source omission, invalid-value rejection, and directionality.

- [ ] **Step 5: Commit the Sims readers**

```powershell
Set-Location ../..
git add adapters/thesims4/ts4script/ai_sims_agent.py adapters/thesims4/tests/test_sims4_mod_autonomy.py
git commit -m "feat(sims4): observe supported attraction sources"
```

### Task 3: Carry attraction through state, prompt, and diagnostics

**Files:**
- Modify: `adapters/thesims4/tests/test_adapter.py`
- Modify: `adapters/thesims4/src/empneon_thesims4/adapter.py:126-165`
- Modify: `adapters/thesims4/tests/test_sims4_backend.py`
- Modify: `adapters/thesims4/backend/ai_sims_server.py:793-797,1317-1465`
- Modify: `adapters/thesims4/backend/empneon_state.py:148-165`
- Modify: `adapters/thesims4/tests/test_sims4_mod_autonomy.py:530-570`
- Modify: `adapters/thesims4/ts4script/ai_sims_agent.py:2077-2115`

**Interfaces:**
- Consumes: Task 2 relationship payload keys `attraction` and `native.attraction`.
- Produces: snapshot `relationships[listener_id].attraction`, snapshot-native evidence at `native.relationships[listener_id].attraction`, model relationship context containing the normalized scalar, and a diagnostic attraction object.

- [ ] **Step 1: Write failing adapter translation tests**

Extend `test_sims_payload_becomes_normalized_agent_state_without_losing_native_values` in `test_adapter.py` so its relationship payload is:

```python
            "relationship": {
                "friendship": 7,
                "romance": 12,
                "trust": 50,
                "attraction": 2 / 3,
                "native": {
                    "attraction": {
                        "source": "wickedwhims",
                        "value": 2,
                        "label": "HIGH",
                    }
                },
            },
```

Change the relationship assertion and add native evidence assertions:

```python
    assert event.agent_state.relationships["bernard"] == {
        "affinity": 0.07,
        "romance": 0.12,
        "trust": 0.5,
        "attraction": pytest.approx(2 / 3),
    }
    assert event.agent_state.native["relationships"]["bernard"]["attraction"] == {
        "source": "wickedwhims",
        "value": 2,
        "label": "HIGH",
    }
```

Add an omission test:

```python
def test_sims_adapter_omits_unavailable_attraction() -> None:
    state = Sims4Adapter(
        {
            "speaker": {"id": "alice"},
            "listener": {"id": "bob"},
            "relationship": {"friendship": 0, "romance": 0},
        }
    ).agent_state()

    assert "attraction" not in state.relationships["bob"]
```

- [ ] **Step 2: Run the adapter tests and verify missing-field failures**

```powershell
Set-Location adapters/thesims4
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_adapter.py -k "normalized_agent_state or unavailable_attraction"
```

Expected: the native and normalized attraction assertions fail.

- [ ] **Step 3: Add attraction to the existing adapter mapping**

In `Sims4Adapter.agent_state`, build the relationship entry first and append the optional scalar only when it is numeric and non-boolean:

```python
        relationships: dict[str, object] = {}
        if listener_id:
            relationship_state: dict[str, object] = {
                "affinity": max(
                    -1.0,
                    min(1.0, _number(relationship, "friendship") / 100),
                ),
                "romance": max(
                    0.0, min(1.0, _number(relationship, "romance") / 100)
                ),
                "trust": max(
                    0.0, min(1.0, _number(relationship, "trust", 50) / 100)
                ),
            }
            attraction = relationship.get("attraction")
            if isinstance(attraction, (int, float)) and not isinstance(attraction, bool):
                relationship_state["attraction"] = float(attraction)
            relationships[listener_id] = relationship_state
```

After `native = _mapping(speaker.get("native"))`, preserve evidence using the existing native mapping:

```python
        native_attraction = _mapping(
            _mapping(relationship.get("native")).get("attraction")
        )
        if listener_id and native_attraction:
            native_relationships = _mapping(native.get("relationships"))
            native_relationships[listener_id] = {"attraction": native_attraction}
            native["relationships"] = native_relationships
```

- [ ] **Step 4: Write failing backend context and diagnostic tests**

Add to `test_sims4_backend.py`:

```python
def test_attraction_is_directed_model_context_not_a_mutable_relationship(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        ai_sims_server, "CORE_DB_PATH", str(tmp_path / "core.sqlite3")
    )
    relationship = ai_sims_server.relationship_with_payload(
        "karmine",
        "bernard",
        {
            "friendship": 14,
            "romance": 0,
            "trust": 50,
            "attraction": 2 / 3,
            "native": {
                "attraction": {
                    "source": "wickedwhims",
                    "value": 2,
                    "label": "HIGH",
                }
            },
        },
    )

    assert relationship["attraction"] == pytest.approx(2 / 3)
    assert "native" not in relationship
    assert "attraction" not in ai_sims_server.apply_relationship_delta(
        "karmine", "bernard", {"attraction_delta": -1}
    )


def test_prompt_explains_directed_attraction_without_implying_consent() -> None:
    payload = {
        "speaker": {"id": "karmine"},
        "listener": {"id": "bernard"},
        "message": "How do you feel about me?",
    }
    context = ai_sims_server.build_context(
        payload,
        {"name": "Karmine"},
        {"name": "Bernard"},
        {"friendship": 14, "romance": 0, "trust": 50, "attraction": 2 / 3},
        {},
        [],
        {},
    )
    context.update(conversation=[], speaker_id="karmine", listener_id="bernard")

    prompt = ai_sims_server.build_chat_prompt(payload, context)

    assert '"attraction": 0.666' in prompt
    assert "Speaker's attraction toward the Listener" in prompt
    assert "-1 is strong aversion, 0 is neutral, and 1 is strong attraction" in prompt
    assert "does not imply consent or require flirtation" in prompt
```

Update the existing relationship diagnostic test snapshot and expected value:

```python
                relationships={
                    "bernard": {
                        "affinity": 0.07,
                        "romance": 0.12,
                        "attraction": 2 / 3,
                    }
                },
                native={
                    "relationships": {
                        "bernard": {
                            "attraction": {
                                "source": "wickedwhims",
                                "value": 2,
                                "label": "HIGH",
                            }
                        }
                    }
                },
```

Expected diagnostic native section:

```python
        "native": {
            "friendship": 7,
            "romance": 12,
            "attraction": {
                "normalized": pytest.approx(2 / 3),
                "source": "wickedwhims",
                "value": 2,
                "label": "HIGH",
            },
        },
```

- [ ] **Step 5: Run the backend tests and verify the new assertions fail**

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_adapter.py tests/test_sims4_backend.py -k "attraction or relationship_source_diagnostic"
```

Expected: FAIL because request context and diagnostics currently discard attraction.

- [ ] **Step 6: Preserve normalized attraction for the current model request**

Replace `relationship_with_payload` in `ai_sims_server.py` with:

```python
def relationship_with_payload(sim_id_value, target_id_value, payload_relationship):
    with open_db(CORE_DB_PATH) as conn:
        relationship = empneon_state.save_relationship(
            conn, sim_id_value, target_id_value, payload_relationship or {}
        )
    attraction = (payload_relationship or {}).get("attraction")
    if (
        isinstance(attraction, (int, float))
        and not isinstance(attraction, bool)
        and -1.0 <= float(attraction) <= 1.0
    ):
        relationship["attraction"] = float(attraction)
    return relationship
```

This intentionally does not pass `native` into the model relationship and does not store attraction in the typed `relationships` table.

Add these exact grounding lines beneath the existing relationship/trait grounding rules in `build_chat_prompt`:

```text
- Relationship attraction, when present, is the Speaker's attraction toward the Listener:
  -1 is strong aversion, 0 is neutral, and 1 is strong attraction.
- Attraction may shape warmth, hesitation, boundaries, or romantic openness, but it does not imply
  consent or require flirtation and never overrides identity, mood, memory, history, or the message.
```

- [ ] **Step 7: Extend snapshot diagnostics without changing the relationship table**

In `empneon_state.relationship_diagnostic`, build the native result before returning:

```python
    native: dict[str, object] = {
        "friendship": round(float(observed.get("affinity", 0)) * 100),
        "romance": round(float(observed.get("romance", 0)) * 100),
    }
    attraction = observed.get("attraction")
    native_relationships = (
        snapshot.native.get("relationships", {}) if snapshot is not None else {}
    )
    native_attraction = (
        native_relationships.get(target_id, {}).get("attraction", {})
        if isinstance(native_relationships, Mapping)
        else {}
    )
    if isinstance(attraction, (int, float)) and not isinstance(attraction, bool):
        native["attraction"] = {
            "normalized": float(attraction),
            "source": native_attraction.get("source", "unknown"),
            "value": native_attraction.get("value"),
            "label": native_attraction.get("label", "unknown"),
        }
    return {
        "direction": {"source_id": source_id, "target_id": target_id},
        "native": native,
        "empneon": {"trust": round((relationship.trust if relationship else 0.5) * 100)},
    }
```

Use the existing `from collections.abc import Mapping` import at the top of `empneon_state.py`.

- [ ] **Step 8: Show source-aware attraction in `ai.relationship`**

Update the command test response in `test_sims4_mod_autonomy.py` to include:

```python
"attraction": {
    "normalized": 2 / 3,
    "source": "wickedwhims",
    "value": 2,
    "label": "HIGH",
},
```

Change its expected line to:

```python
"relationship Cam Sadya -> Bella: Sims friendship 7, Sims romance 12, "
"Sims attraction +0.67 (wickedwhims: HIGH), Empneon trust 51"
```

In `ai_relationship`, format the optional observation without inventing neutral:

```python
    attraction = native.get("attraction") or {}
    attraction_text = "unavailable"
    if isinstance(attraction, dict) and isinstance(
        attraction.get("normalized"), (int, float)
    ):
        attraction_text = "{:+.2f} ({}: {})".format(
            float(attraction["normalized"]),
            attraction.get("source", "unknown"),
            attraction.get("label", "unknown"),
        )
```

Insert `Sims attraction {}` between romance and Empneon trust in the existing output and pass `attraction_text` to `.format(...)`.

- [ ] **Step 9: Run all touched Sims tests**

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_adapter.py tests/test_sims4_backend.py tests/test_sims4_mod_autonomy.py
```

Expected: PASS. Existing dialogue confirmation and relationship-delta tests must remain unchanged except for expected diagnostic text.

- [ ] **Step 10: Commit the adapter/backend flow**

```powershell
Set-Location ../..
git add adapters/thesims4/src/empneon_thesims4/adapter.py adapters/thesims4/backend/ai_sims_server.py adapters/thesims4/backend/empneon_state.py adapters/thesims4/ts4script/ai_sims_agent.py adapters/thesims4/tests/test_adapter.py adapters/thesims4/tests/test_sims4_backend.py adapters/thesims4/tests/test_sims4_mod_autonomy.py
git commit -m "feat(sims4): ground dialogue with attraction"
```

### Task 4: Verify, build, and hand Test 5 back to the game

**Files:**
- Modify: `adapters/thesims4/docs/in-game-core-feature-test-plan.md:118-163`
- Modify: `adapters/thesims4/docs/in-game-core-feature-test-results.md:324-333`
- Generated but not committed unless already tracked by repository policy: `adapters/thesims4/dist/Empneon_TheSims4.ts4script`, `adapters/thesims4/dist/Empneon_TheSims4.package`

**Interfaces:**
- Consumes: all prior tasks and the existing source-build install workflow in `adapters/thesims4/docs/setup.md`.
- Produces: verified artifacts and an exact live Test 5 checkpoint that checks the selected attraction source and directed value.

- [ ] **Step 1: Update the Test 5 procedure before running it**

Add this bullet to Test 5 in `in-game-core-feature-test-plan.md` after the current relationship prerequisite:

```markdown
- Attraction evidence: capture `ai.relationship Karmine` in both directions before dialogue. The
  command must show either `Sims attraction <normalized> (<source>: <label>)` or explicit
  `unavailable`. With supported WickedWhims attraction enabled, source must be `wickedwhims`; with
  it disabled and Lovestruck available, source must be `sims4_lovestruck`. Values may differ by
  direction. Confirm the prompt uses Karmine-to-Bernard attraction only, and that attraction shapes
  tone without forcing flirtation, consent, or a romance delta.
```

Update the existing sentence `only game-observed friendship/romance changes persist` to `only game-observed friendship, romance, and attraction changes persist`; keep attraction read-only from Empneon's perspective.

- [ ] **Step 2: Run the complete automated gate**

Run from the repository root:

```powershell
$env:PYTHONPATH='core\src;adapters\thesims4\src;adapters\godot\src'; py -3.12 -m pytest -q -p no:cacheprovider core adapters/thesims4 adapters/godot tests scripts/test_release.py
py -3.12 -m ruff check --select E9,F63,F7,F82 core/src core/tests adapters/thesims4/src adapters/thesims4/tests adapters/thesims4/backend adapters/thesims4/ts4script adapters/godot/src adapters/godot/tests tests scripts
py -3.12 -m mypy core/src adapters/thesims4/src adapters/godot/src
py -3.12 -m py_compile adapters/thesims4/backend/ai_sims_server.py adapters/thesims4/backend/empneon_state.py adapters/thesims4/src/empneon_thesims4/adapter.py
git diff --check
```

Expected: every command exits `0`; no SQLite sidecar is staged or deleted.

- [ ] **Step 3: Build the Python 3.7-compatible Sims artifacts**

```powershell
Set-Location adapters/thesims4
py -3.12 .\build_mod.py
Get-FileHash .\dist\Empneon_TheSims4.ts4script -Algorithm SHA256
Get-FileHash .\dist\Empneon_TheSims4.package -Algorithm SHA256
```

Expected: the builder reports both artifacts, using Python 3.7 for script bytecode, and both hashes are non-empty.

- [ ] **Step 4: Record the honest handoff state**

Append this paragraph to the current handoff section of `in-game-core-feature-test-results.md`:

```markdown
- Cross-adapter directed attraction now has automated coverage for the common `-1..1` contract,
  WickedWhims priority, official Lovestruck fallback, omission when unavailable, directionality,
  prompt grounding, diagnostics, and read-only behavior. Test 5 remains **PARTIAL** until the new
  source-built artifacts are installed and both attraction-source paths are observed in game; no
  live attraction value is claimed by automated tests.
```

Do not mark Test 5 passed during implementation. The game run must supply the actual values, source label, both directions, dialogue, and before/after evidence.

- [ ] **Step 5: Commit documentation only**

```powershell
Set-Location ../..
git add adapters/thesims4/docs/in-game-core-feature-test-plan.md adapters/thesims4/docs/in-game-core-feature-test-results.md
git commit -m "docs(sims4): add attraction to Test 5"
```

- [ ] **Step 6: Perform the manual source-build checkpoint with the user**

Follow `adapters/thesims4/docs/setup.md` exactly: install the newly built `.ts4script` and `.package`, start the source backend, then run these game commands with Karmine and Bernard active in turn:

```text
ai.relationship Bernard Jaeger
ai.relationship Karmine Luna
```

Expected with the currently installed supported mod: each line includes `Sims attraction`, source `wickedwhims`, its native label, and a normalized value in `-1.00..+1.00`; direction values are allowed to differ. Disable only WickedWhims attraction while leaving Lovestruck available and repeat; expected source is `sims4_lovestruck`. If either API is unavailable, expected output is `unavailable` and conversation still works.

Then send one neutral and one romantic message through Empneon Social. Capture the exact prompt and response. Expected: the prompt labels Speaker-to-Listener attraction and its scale; the response may reflect chemistry but is not forced to flirt, consent, or create an attraction delta. Update `in-game-core-feature-test-results.md` with the actual command lines, hashes, messages, responses, and direction values before changing Test 5's status.

---

## Final Self-Review Checklist

- [ ] Every approved requirement maps to a task: common contract, native evidence, source order, fallback, omission, direction, prompt semantics, read-only authority, synthetic non-Sims coverage, build, and live Test 5.
- [ ] No database migration, provider registry, arbitrary mod detection, attraction history, or attraction delta was added.
- [ ] All names and shapes match across tasks: `attraction_payload`, `relationship.attraction`, `relationship.native.attraction`, `snapshot.native.relationships[target].attraction`, and diagnostic `native.attraction`.
- [ ] Confirm the plan contains no placeholder instructions.
- [ ] Verify `git status --short` before every commit so the existing name-response edits and SQLite sidecars are never accidentally staged.
