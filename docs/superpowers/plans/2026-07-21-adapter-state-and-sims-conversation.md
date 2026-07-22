# Adapter State and Sims Conversation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a common cross-adapter agent-state snapshot, preserve grounded model dialogue while independently validating native action proposals, and keep The Sims 4 Empneon Social interaction active for the complete multi-turn session.

**Architecture:** Core gains one JSON-compatible `AgentStateSnapshot` embedded in `WorldEvent` and persisted through the existing document store. The Sims adapter translates live game state into normalized and native sections, while dialogue output separates descriptive intent from an explicit request-scoped action. A game-side conversation session owns input, backend waiting, response delivery, optional native action confirmation, continuation, and cancellation without releasing the actor's queue interaction.

**Tech Stack:** Python 3.11+ backend/Core, Python 3.7 Sims script bytecode, SQLite, standard-library JSON/threading, existing Sims interaction/dialog APIs, pytest, Ruff, mypy.

## Global Constraints

- Add no dependency or provider-specific behavior.
- Core must not import Sims or Godot types.
- Preserve unknown native game labels and primitive values; never serialize runtime game objects.
- Persist durable normalized concepts in existing typed stores and the latest complete snapshot in `DocumentMemoryStore`.
- Do not apply model-proposed Sims friendship or romance directly.
- Apply bounded Empneon trust only after the response is delivered to the player.
- Return valid grounded model dialogue even when its action proposal must be sanitized.
- Keep privacy, factual grounding, role, repetition, and native-confirmation safeguards.
- Keep one active Empneon Social session per actor.
- Manual queue cancellation suppresses late UI and resolves late action proposals without consequences.
- Preserve the untracked live SQLite `-wal` and `-shm` files.

---

### Task 1: Core agent-state contract and latest-snapshot persistence

**Files:**
- Modify: `core/src/empneon/core/contracts.py`
- Create: `core/src/empneon/core/state.py`
- Modify: `core/src/empneon/__init__.py`
- Modify: `core/tests/unit/test_contracts.py`
- Create: `core/tests/unit/test_state.py`
- Modify: `core/tests/unit/test_public_api.py`

**Interfaces:**
- Produces: `AgentStateSnapshot.from_mapping(value: Mapping[str, object]) -> AgentStateSnapshot`.
- Produces: `save_agent_state(conn: sqlite3.Connection, snapshot: AgentStateSnapshot) -> AgentStateSnapshot`.
- Produces: `load_agent_state(conn: sqlite3.Connection, agent_id: str) -> AgentStateSnapshot | None`.
- Changes: `WorldEvent.agent_state: AgentStateSnapshot | None`.

- [ ] **Step 1: Add failing contract and persistence tests**

Add to `core/tests/unit/test_contracts.py`:

```python
import dataclasses
import json

from empneon.core.contracts import AgentStateSnapshot


def test_agent_state_snapshot_is_json_compatible_and_embedded_in_event() -> None:
    snapshot = AgentStateSnapshot.from_mapping(
        {
            "schema_version": 1,
            "adapter": "test",
            "agent_id": "alice",
            "affect": {"tags": ["calm"], "valence": 0.2, "intensity": 0.5},
            "needs": {"energy": {"level": 0.8, "urgency": 0.2}},
            "native": {"unknown_mod_state": "preserved"},
        }
    )
    event = WorldEvent("observation", ("alice",), agent_state=snapshot)

    encoded = json.loads(json.dumps(dataclasses.asdict(event)))

    assert encoded["agent_state"]["native"] == {
        "unknown_mod_state": "preserved"
    }
    assert encoded["agent_state"]["effects"] == []


@pytest.mark.parametrize(
    "section,key,value",
    [
        ("affect", "valence", 1.1),
        ("affect", "intensity", -0.1),
        ("relationships", "affinity", -1.1),
        ("relationships", "romance", 1.1),
    ],
)
def test_agent_state_snapshot_rejects_out_of_range_values(
    section: str, key: str, value: float
) -> None:
    data: dict[str, object] = {
        "schema_version": 1,
        "adapter": "test",
        "agent_id": "alice",
    }
    data[section] = (
        {"bob": {key: value}} if section == "relationships" else {key: value}
    )

    with pytest.raises(ValueError, match=key):
        AgentStateSnapshot.from_mapping(data)
```

Create `core/tests/unit/test_state.py`:

```python
from empneon.core.contracts import AgentStateSnapshot
from empneon.core.state import load_agent_state, save_agent_state
from empneon.db.connection import open_db


def test_latest_agent_state_replaces_temporary_native_state(tmp_path) -> None:
    path = tmp_path / "state.sqlite3"
    first = AgentStateSnapshot.from_mapping(
        {
            "schema_version": 1,
            "adapter": "test",
            "agent_id": "alice",
            "effects": [{"kind": "buff", "label": "wet"}],
            "native": {"buffs": ["wet"]},
        }
    )
    second = AgentStateSnapshot.from_mapping(
        {
            "schema_version": 1,
            "adapter": "test",
            "agent_id": "alice",
            "effects": [],
            "native": {"buffs": []},
        }
    )

    with open_db(path) as conn:
        save_agent_state(conn, first)
        save_agent_state(conn, second)
        loaded = load_agent_state(conn, "alice")

    assert loaded == second
```

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='core\src'
py -3.12 -m pytest -q -p no:cacheprovider core/tests/unit/test_contracts.py core/tests/unit/test_state.py core/tests/unit/test_public_api.py
```

Expected: collection fails because `AgentStateSnapshot` and `empneon.core.state` do not exist.

- [ ] **Step 3: Implement the contract and reuse the document store**

Add before `WorldEvent` in `core/src/empneon/core/contracts.py`:

```python
import json
from collections.abc import Mapping


def _mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def _bounded(mapping: Mapping[str, object], key: str, low: float, high: float) -> None:
    value = mapping.get(key)
    if value is not None and (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not low <= float(value) <= high
    ):
        raise ValueError(f"agent state {key} must be between {low} and {high}")


@dataclass(frozen=True)
class AgentStateSnapshot:
    schema_version: int
    adapter: str
    agent_id: str
    affect: dict[str, object] = field(default_factory=dict)
    needs: dict[str, object] = field(default_factory=dict)
    effects: list[object] = field(default_factory=list)
    relationships: dict[str, object] = field(default_factory=dict)
    goals: list[object] = field(default_factory=list)
    intentions: list[object] = field(default_factory=list)
    capabilities: dict[str, object] = field(default_factory=dict)
    native: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported agent state schema_version")
        if not self.adapter.strip() or not self.agent_id.strip():
            raise ValueError("agent state adapter and agent_id are required")
        _bounded(self.affect, "valence", -1.0, 1.0)
        _bounded(self.affect, "arousal", 0.0, 1.0)
        _bounded(self.affect, "intensity", 0.0, 1.0)
        for need in self.needs.values():
            if isinstance(need, Mapping):
                _bounded(need, "level", 0.0, 1.0)
                _bounded(need, "urgency", 0.0, 1.0)
        for relationship in self.relationships.values():
            if isinstance(relationship, Mapping):
                _bounded(relationship, "affinity", -1.0, 1.0)
                _bounded(relationship, "romance", 0.0, 1.0)
                _bounded(relationship, "trust", 0.0, 1.0)
        try:
            json.dumps(dataclasses.asdict(self))
        except (TypeError, ValueError) as exc:
            raise ValueError("agent state must be JSON-compatible") from exc

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "AgentStateSnapshot":
        return cls(
            schema_version=int(value.get("schema_version", 0)),
            adapter=str(value.get("adapter") or ""),
            agent_id=str(value.get("agent_id") or ""),
            affect=_mapping(value.get("affect")),
            needs=_mapping(value.get("needs")),
            effects=list(value.get("effects") or []),
            relationships=_mapping(value.get("relationships")),
            goals=list(value.get("goals") or []),
            intentions=list(value.get("intentions") or []),
            capabilities=_mapping(value.get("capabilities")),
            native=_mapping(value.get("native")),
        )
```

Import `dataclasses` rather than only `dataclass`/`field`, and add to `WorldEvent`:

```python
agent_state: AgentStateSnapshot | None = None
```

Create `core/src/empneon/core/state.py`:

```python
"""Persist the latest generic agent-state snapshot."""

import dataclasses
import sqlite3
from collections.abc import Mapping

from empneon.core.contracts import AgentStateSnapshot
from empneon.core.memory.documents import DocumentMemoryStore

NAMESPACE = "core.agent-state.v1"


def save_agent_state(
    conn: sqlite3.Connection, snapshot: AgentStateSnapshot
) -> AgentStateSnapshot:
    DocumentMemoryStore(conn).set(NAMESPACE, snapshot.agent_id, dataclasses.asdict(snapshot))
    return snapshot


def load_agent_state(
    conn: sqlite3.Connection, agent_id: str
) -> AgentStateSnapshot | None:
    value = DocumentMemoryStore(conn).get(NAMESPACE, str(agent_id))
    return (
        AgentStateSnapshot.from_mapping(value)
        if isinstance(value, Mapping)
        else None
    )
```

Export `AgentStateSnapshot`, `save_agent_state`, and `load_agent_state` from `empneon.__init__` and add their names to the public API test.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the Step 2 command. Expected: all selected tests pass.

- [ ] **Step 5: Commit the Core snapshot foundation**

```powershell
git add core/src/empneon/core/contracts.py core/src/empneon/core/state.py core/src/empneon/__init__.py core/tests/unit/test_contracts.py core/tests/unit/test_state.py core/tests/unit/test_public_api.py
git commit -m "feat(core): add agent state snapshots"
```

### Task 2: Produce snapshots from both reference adapters

**Files:**
- Modify: `adapters/thesims4/src/empneon_thesims4/adapter.py`
- Modify: `adapters/thesims4/tests/test_adapter.py`
- Modify: `adapters/godot/src/empneon_godot/bridge.py`
- Modify: `adapters/godot/tests/test_godot_bridge.py`
- Modify: `tests/cross_adapter/test_game_adapters.py`
- Modify: `tests/cross_adapter/test_portability_benchmark.py`

**Interfaces:**
- Consumes: `AgentStateSnapshot` and `WorldEvent.agent_state` from Task 1.
- Produces: `Sims4Adapter.agent_state() -> AgentStateSnapshot`.
- Produces: `GodotBridge` reconstruction of optional serialized `event.agent_state`.

- [ ] **Step 1: Add failing Sims and shared adapter tests**

Add to `adapters/thesims4/tests/test_adapter.py`:

```python
def test_sims_payload_becomes_normalized_agent_state_without_losing_native_values() -> None:
    event = Sims4Adapter(
        {
            "speaker": {
                "id": "karmine",
                "current_mood": "uncomfortable",
                "needs": {"hunger": 63},
                "native": {
                    "mood": "Mood_Uncomfortable",
                    "moodlets": [{"label": "Custom DLC Moodlet"}],
                },
            },
            "listener": {"id": "bernard"},
            "relationship": {"friendship": 7, "romance": 12, "trust": 50},
            "available_actions": ["friendly_chat", "flirt"],
        }
    ).observe()[0]

    assert event.agent_state is not None
    assert event.agent_state.affect == {"tags": ["uncomfortable"]}
    assert event.agent_state.needs == {
        "hunger": {"level": 0.63, "urgency": 0.37}
    }
    assert event.agent_state.relationships["bernard"] == {
        "affinity": 0.07,
        "romance": 0.12,
        "trust": 0.5,
    }
    assert event.agent_state.capabilities == {
        "actions": ["friendly_chat", "flirt"]
    }
    assert event.agent_state.native["moodlets"] == [
        {"label": "Custom DLC Moodlet"}
    ]
```

Extend `RoundTrip` in `tests/cross_adapter/test_game_adapters.py` with
`agent_state: AgentStateSnapshot`. Return `event.agent_state` from both helpers after asserting it
is not `None`, then add:

```python
assert completed.agent_state.schema_version == 1
assert completed.agent_state.adapter in {"sims4", "godot"}
assert completed.agent_state.agent_id == completed.actor_id
```

In `_godot_round_trip`, add a serialized state to `event_data` with
`native={"unknown_engine_value": "preserved"}` and assert that exact native mapping after the
round trip.

Also modify `tests/cross_adapter/test_portability_benchmark.py`: include an `agent_state` mapping
in the portable scenario fixture and assert that both adapters preserve the normalized sections
and their own `adapter` value. Keep the existing decision comparison unchanged; state context is
input evidence, not part of the decision payload.

- [ ] **Step 2: Run adapter tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='core\src;adapters\thesims4\src;adapters\godot\src'
py -3.12 -m pytest -q -p no:cacheprovider adapters/thesims4/tests/test_adapter.py adapters/godot/tests/test_godot_bridge.py tests/cross_adapter/test_game_adapters.py tests/cross_adapter/test_portability_benchmark.py
```

Expected: Sims assertions fail because `WorldEvent.agent_state` is `None`; Godot does not reconstruct serialized state.

- [ ] **Step 3: Build the Sims snapshot from the existing payload**

Add to `Sims4Adapter`:

```python
def agent_state(self) -> AgentStateSnapshot:
    speaker = _mapping(self._payload.get("speaker"))
    listener = _mapping(self._payload.get("listener"))
    relationship = _mapping(self._payload.get("relationship"))
    listener_id = str(listener.get("id") or "")
    needs = {
        str(name): {
            "level": max(0.0, min(1.0, float(value) / 100)),
            "urgency": max(0.0, min(1.0, 1 - float(value) / 100)),
        }
        for name, value in _mapping(speaker.get("needs")).items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }
    relationships = {}
    if listener_id:
        relationships[listener_id] = {
            "affinity": max(-1.0, min(1.0, float(relationship.get("friendship", 0)) / 100)),
            "romance": max(0.0, min(1.0, float(relationship.get("romance", 0)) / 100)),
            "trust": max(0.0, min(1.0, float(relationship.get("trust", 50)) / 100)),
        }
    mood = str(speaker.get("current_mood") or "unknown")
    native = _mapping(speaker.get("native"))
    native.setdefault("mood", mood)
    native.setdefault("moodlets", _items(speaker.get("moodlets")))
    return AgentStateSnapshot(
        1,
        "sims4",
        str(speaker.get("id") or speaker.get("name") or "unknown-sim"),
        affect={"tags": [] if mood == "unknown" else [mood]},
        needs=needs,
        effects=_items(speaker.get("effects")),
        relationships=relationships,
        goals=_items(speaker.get("goals")),
        intentions=_items(speaker.get("intentions")),
        capabilities={"actions": _items(self._payload.get("available_actions"))},
        native=native,
    )
```

Pass `agent_state=self.agent_state()` when constructing the Sims `WorldEvent`.

- [ ] **Step 4: Reconstruct or default Godot state**

In `GodotBridge.decide`, parse `event_data.get("agent_state")` with `AgentStateSnapshot.from_mapping` when it is a mapping. Otherwise create:

```python
state = AgentStateSnapshot(
    1,
    "godot",
    agent_id,
    capabilities={"actions": ["acknowledge"]},
    native={"facts": dict(facts)},
)
```

Pass `agent_state=state` into `WorldEvent`. Keep the Godot engine mutation and transport unchanged.

- [ ] **Step 5: Run adapter tests and verify GREEN**

Run the Step 2 command. Expected: all selected tests pass.

- [ ] **Step 6: Commit adapter snapshot production**

```powershell
git add adapters/thesims4/src/empneon_thesims4/adapter.py adapters/thesims4/tests/test_adapter.py adapters/godot/src/empneon_godot/bridge.py adapters/godot/tests/test_godot_bridge.py tests/cross_adapter/test_game_adapters.py tests/cross_adapter/test_portability_benchmark.py
git commit -m "feat(adapters): publish normalized agent state"
```

### Task 3: Capture Sims moodlets, buffs, sentiments, and native relationship tracks

**Files:**
- Modify: `adapters/thesims4/ts4script/ai_sims_agent.py:250-506`
- Modify: `adapters/thesims4/tests/test_sims4_mod_autonomy.py:260-380`

**Interfaces:**
- Produces: `native_game_item(value: object, kind: str) -> dict[str, object]`.
- Produces: `sim_effects(sim_info: object) -> list[dict[str, object]]`.
- Produces: `sim_sentiments(sim_info: object) -> list[dict[str, object]]`.
- Changes: `sim_info_payload()` adds `effects`, `intentions`, and `native`.

- [ ] **Step 1: Add failing extraction tests using the existing fake game modules**

Extend the rich SimInfo fixture in `test_sims4_mod_autonomy.py` with two buffs, including one unknown mod label, and a sentiment tracker exposing a directed sentiment. Assert:

```python
payload = agent.sim_info_payload(rich_info)

assert payload["effects"] == [
    {
        "kind": "moodlet",
        "label": "Inspired",
        "id": "buff-inspired",
        "polarity": "unknown",
    },
    {
        "kind": "moodlet",
        "label": "ModdedAuroraState",
        "id": "buff-modded",
        "polarity": "unknown",
    },
    {
        "kind": "sentiment",
        "label": "Adoring",
        "id": "sentiment-adoring",
        "polarity": "positive",
        "target_id": "bernard",
    },
]
assert payload["native"]["mood"] == payload["current_mood"]
assert payload["native"]["buffs"][1]["label"] == "ModdedAuroraState"
assert payload["native"]["sentiments"][0]["target_id"] == "bernard"
```

- [ ] **Step 2: Run the script-mod test and verify RED**

Run:

```powershell
$env:PYTHONPATH='core\src;adapters\thesims4\src'
py -3.12 -m pytest -q -p no:cacheprovider adapters/thesims4/tests/test_sims4_mod_autonomy.py
```

Expected: `effects` and `native` are absent.

- [ ] **Step 3: Add tolerant native extraction without a game-specific allowlist**

Implement:

```python
def native_game_item(value, kind):
    source = getattr(value, "buff_type", None) or getattr(value, "sentiment", None) or value
    identifier = (
        getattr(source, "guid64", None)
        or getattr(source, "id", None)
        or short_trait_name(source)
    )
    polarity = text_value(getattr(source, "polarity", None), "unknown").casefold()
    if polarity not in ("positive", "negative", "neutral"):
        polarity = "unknown"
    return {
        "kind": kind,
        "label": short_trait_name(source),
        "id": str(identifier or ""),
        "polarity": polarity,
    }


def sim_effects(sim_info):
    component = getattr(sim_info, "buff_component", None)
    if component is None:
        try:
            component = getattr(sim_info.get_sim_instance(), "buff_component", None)
        except Exception:
            pass
    try:
        source = getattr(component, "get_all_buffs", None)
        buffs = source() if callable(source) else source or []
        return [native_game_item(buff, "moodlet") for buff in buffs]
    except Exception:
        return []
```

Implement `sim_sentiments` with per-record isolation:

```python
def sim_sentiments(sim_info):
    tracker = getattr(sim_info, "sentiment_tracker", None)
    items = None
    for attr in ("get_all_sentiments", "sentiments", "values"):
        try:
            source = getattr(tracker, attr, None)
            if source is None:
                continue
            items = source() if callable(source) else source
            break
        except Exception:
            pass
    if items is None:
        return []
    pairs = items.items() if isinstance(items, dict) else ((None, item) for item in items)
    records = []
    for target, sentiment in pairs:
        try:
            record = native_game_item(sentiment, "sentiment")
            target_id = getattr(target, "sim_id", target)
            if target_id not in (None, ""):
                record["target_id"] = str(target_id)
            records.append(record)
        except Exception:
            pass
    return records
```

`sim_info_payload` sets:

```python
effects = sim_effects(sim_info) + sim_sentiments(sim_info)
native = {
    "mood": sim_mood(sim_info),
    "buffs": [item for item in effects if item["kind"] == "moodlet"],
    "moodlets": [item for item in effects if item["kind"] == "moodlet"],
    "sentiments": [item for item in effects if item["kind"] == "sentiment"],
}
```

Keep the existing simple `moodlets` label list for backward compatibility, but derive it from all extracted moodlet records rather than truncating to twenty.

- [ ] **Step 4: Run the script-mod test and verify GREEN**

Run the Step 2 command. Expected: all script-mod tests pass.

- [ ] **Step 5: Commit native Sims state extraction**

```powershell
git add adapters/thesims4/ts4script/ai_sims_agent.py adapters/thesims4/tests/test_sims4_mod_autonomy.py
git commit -m "feat(sims4): capture native character state"
```

### Task 4: Separate natural dialogue from executable action proposals

**Files:**
- Modify: `adapters/thesims4/backend/ai_sims_server.py:190-310,925-990,1259-1715,1739-1865`
- Modify: `adapters/thesims4/backend/empneon_state.py:516-570`
- Modify: `adapters/thesims4/src/empneon_thesims4/adapter.py:10-38,159-228`
- Modify: `adapters/thesims4/tests/test_sims4_backend.py:538-850`
- Modify: `adapters/thesims4/tests/test_adapter.py:70-165`

**Interfaces:**
- Produces: `dialogue_schema(available_actions: object) -> dict[str, object]`.
- Produces: `normalize_response(raw: object, available_actions: object = ()) -> dict[str, object]`.
- Produces: `sanitize_action_proposal(response: dict[str, object], available_actions: object) -> dict[str, object]`.
- Changes: model response field `emotion` becomes `expressed_emotion`; `animation` becomes `suggested_action`, with both old names accepted on input during this release.
- Changes: `Sims4Adapter.action_for()` reads the proposed `animation` state delta before legacy intent mapping.

- [ ] **Step 1: Add the observed Karmine response as a failing regression**

Add to `test_sims4_backend.py`:

```python
def test_natural_date_reply_survives_non_romantic_action_metadata() -> None:
    context = ai_sims_server.build_context(
        {"speaker": {}, "listener": {}},
        {"name": "Karmine"},
        {"name": "Bernard"},
        {},
        {},
        [],
        {"summary": ""},
    )
    payload = {
        "message": "I would love to take you on a date sometime.",
        "available_actions": ["friendly_chat", "apologize", "flirt"],
    }
    response = ai_sims_server.normalize_response(
        {
            "dialogue": "That's sweet! A date sounds like fun. You have a certain charm.",
            "expressed_emotion": "confidence",
            "intent": "friendly",
            "player_interaction_kind": "romantic_compliment",
            "suggested_action": "friendly_chat",
            "relationship": {"friendship_delta": 1, "romance_delta": 0, "trust_delta": 50},
            "memory": {
                "importance": 0.75,
                "summary": "Bernard invited Karmine on a date.",
            },
        },
        payload["available_actions"],
    )

    assert ai_sims_server.response_grounding_issue(payload, response, context) == ""
    assert response["dialogue"].startswith("That's sweet!")
    assert response["suggested_action"] == "friendly_chat"
    assert response["relationship"]["trust_delta"] == 10
```

Add tests that an unavailable action becomes `none`, an explicit `No, I would rather stay friends` plus `flirt` becomes `none`, arbitrary descriptive intent does not change the selected action, and a copied/private/unsupported factual response still fails dialogue grounding.

- [ ] **Step 2: Run focused dialogue tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='core\src;adapters\thesims4\src'
py -3.12 -m pytest -q -p no:cacheprovider adapters/thesims4/tests/test_sims4_backend.py adapters/thesims4/tests/test_adapter.py -k "natural_date or action_metadata or grounding or conversation_response"
```

Expected: the observed response is rejected and `suggested_action` is ignored.

- [ ] **Step 3: Make the structured schema request-scoped**

Replace static action validation with:

```python
def available_actions(value):
    return tuple(
        dict.fromkeys(
            str(action)
            for action in (value if isinstance(value, (list, tuple)) else ())
            if str(action) in ("friendly_chat", "apologize", "flirt")
        )
    )


def dialogue_schema(value):
    schema = json.loads(json.dumps(DIALOGUE_SCHEMA))
    schema["properties"]["suggested_action"] = {
        "type": "string",
        "enum": list(available_actions(value)) + ["none"],
    }
    schema["required"] = [
        name for name in schema["required"] if name != "animation"
    ] + ["suggested_action"]
    schema["properties"].pop("animation", None)
    return schema
```

The system prompt explains each available action and states that `intent` is descriptive. `build_chat_prompt` renders the current normalized snapshot, native state, and action list.

- [ ] **Step 4: Normalize and sanitize metadata separately from dialogue**

Implement:

```python
def sanitize_action_proposal(response, actions):
    allowed = set(available_actions(actions))
    action = str(response.get("suggested_action") or "none")
    if action not in allowed:
        action = "none"
    dialogue = str(response.get("dialogue") or "").casefold()
    if action == "flirt" and re.search(
        r"\bno\b|not interested|rather stay friends|do not want|don't want",
        dialogue,
    ):
        action = "none"
    response["suggested_action"] = action
    return response
```

`normalize_response` reads new names first and accepts old aliases for compatibility:

```python
"expressed_emotion": str(
    raw.get("expressed_emotion") or raw.get("emotion") or "neutral"
).strip().lower(),
"suggested_action": str(
    raw.get("suggested_action") or raw.get("animation") or "none"
).strip(),
```

Delete only the romantic accept/decline keyword and required flirt/positive-romance rejection block from `response_grounding_issue`. Retain all factual, privacy, role, need, and repetition checks.

- [ ] **Step 5: Carry action independently through the Sims adapter**

`decision_from_response` adds:

```python
StateDelta(
    "animation",
    "set",
    str(response.get("suggested_action") or response.get("animation") or "none"),
)
```

`action_for` first returns a valid `animation` delta (`none` is valid for dialogue-only turns), then uses the existing intent mapping only for older/CLOD1 decisions without that delta. `response_for` returns `suggested_action` and keeps `animation` as the same compatibility alias for one release.

- [ ] **Step 6: Use the dynamic schema and persist the latest state**

`HermesRuntime.dialogue` passes `dialogue_schema(payload.get("available_actions"))`, normalizes with the same action list, and sanitizes before returning. In `chat`, call `save_agent_state(conn, event.agent_state)` after persisting the Core event when state is present. Import `dataclasses` in both backend modules that serialize the snapshot.

Add `agent_state` to the persisted event description so timeline history retains the snapshot that
was current for that request:

```python
"agent_state": (
    dataclasses.asdict(event.agent_state) if event.agent_state is not None else None
),
```

Add the latest state to `empneon_state.sim_diagnostics`:

```python
snapshot = load_agent_state(conn, agent_id)
return {
    **identity,
    "agent_state": dataclasses.asdict(snapshot) if snapshot is not None else None,
    # existing observations, beliefs, and accessible memories
}
```

- [ ] **Step 7: Run focused tests and verify GREEN**

Run the Step 2 command without `-k`, then run:

```powershell
$env:PYTHONPATH='core\src;adapters\thesims4\src'
py -3.12 -m pytest -q -p no:cacheprovider adapters/thesims4/tests/test_sims4_backend.py adapters/thesims4/tests/test_adapter.py
```

Expected: all Sims backend and adapter tests pass.

- [ ] **Step 8: Commit dialogue/action separation**

```powershell
git add adapters/thesims4/backend/ai_sims_server.py adapters/thesims4/backend/empneon_state.py adapters/thesims4/src/empneon_thesims4/adapter.py adapters/thesims4/tests/test_sims4_backend.py adapters/thesims4/tests/test_adapter.py
git commit -m "fix(sims4): preserve grounded model dialogue"
```

### Task 5: Confirm every delivered turn and report relationship sources accurately

**Files:**
- Modify: `adapters/thesims4/backend/empneon_state.py:135-190,275-315,516-570`
- Modify: `adapters/thesims4/backend/ai_sims_server.py:743-780,1980-2046,2185-2189,2235-2280`
- Modify: `adapters/thesims4/ts4script/ai_sims_agent.py:740-780,1000-1035,1335-1375`
- Modify: `adapters/thesims4/tests/test_sims4_backend.py`
- Modify: `adapters/thesims4/tests/test_sims4_mod_autonomy.py`

**Interfaces:**
- Produces: `confirm_dialogue_delivery(payload: Mapping[str, object]) -> dict[str, object]` at `POST /dialogue-result`.
- Produces: idempotent `record_delivered_experience(conn, proposal) -> Event | None`.
- Produces: `relationship_diagnostic(conn, source_id, target_id)` returning `{direction, native, empneon}`.
- Preserves: the internal flat `relationship_view()` consumed by `save_relationship()` and
  `apply_relationship_deltas()`; do not change that persistence boundary in this task.

- [ ] **Step 1: Add failing delivery and relationship-source tests**

Add backend tests proving:

```python
delivered = ai_sims_server.confirm_dialogue_delivery(
    {"decision_id": decision_id, "status": "displayed"}
)
assert delivered == {"decision_id": decision_id, "status": "displayed"}

with open_db(core_db) as conn:
    proposal = ActionRecordStore(conn).get_proposal(decision_id)
    assert proposal is not None  # native action still pending
    relationship = RelationshipStore(conn).get("karmine", "bernard")
    assert relationship is not None and relationship.trust == pytest.approx(0.51)
    assert conn.execute(
        "SELECT COUNT(*) FROM observations WHERE agent_id=?", ("karmine",)
    ).fetchone()[0] == 1

assert ai_sims_server.confirm_dialogue_delivery(
    {"decision_id": decision_id, "status": "displayed"}
) == {"decision_id": decision_id, "status": "already_displayed"}
```

For a `none` action, assert delivery closes the proposal with a succeeded result and zero native changes. Assert `relationship_diagnostic` returns:

```python
{
    "direction": {"source_id": "karmine", "target_id": "bernard"},
    "native": {"friendship": 7, "romance": 12},
    "empneon": {"trust": 51},
}
```

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='core\src;adapters\thesims4\src'
py -3.12 -m pytest -q -p no:cacheprovider adapters/thesims4/tests/test_sims4_backend.py adapters/thesims4/tests/test_sims4_mod_autonomy.py -k "dialogue_delivery or relationship_source"
```

Expected: `/dialogue-result` behavior and sourced relationship output do not exist.

- [ ] **Step 3: Split cognitive delivery from native confirmation**

Use `DocumentMemoryStore` namespace `thesims4.dialogue-delivery` keyed by decision ID for
idempotence. Move the existing memory-promotion body to
`record_delivered_experience(conn, proposal)`; it no longer accepts an `ActionResult` and always
records the confirmed cognitive exchange. Remove the memory-promotion call from `confirm_action`.

Implement the endpoint function as:

```python
# Add these imports in ai_sims_server.py:
# from empneon.core.identity.relationships import Relationship, RelationshipStore

def confirm_dialogue_delivery(payload):
    decision_id = str(payload.get("decision_id") or "").strip()
    if not decision_id or payload.get("status") != "displayed":
        raise ValueError("displayed dialogue decision_id is required")
    with open_db(CORE_DB_PATH) as conn:
        documents = DocumentMemoryStore(conn)
        if documents.get("thesims4.dialogue-delivery", decision_id) is not None:
            return {"decision_id": decision_id, "status": "already_displayed"}
        actions = ActionRecordStore(conn)
        proposal = actions.get_proposal(decision_id)
        if proposal is None:
            raise ValueError("unknown or already confirmed action proposal")
        empneon_state.record_delivered_experience(conn, proposal)
        for change in proposal.decision.state_changes:
            if change.path == "relationship.trust" and proposal.decision.target_id:
                relationship = RelationshipStore(conn).get(
                    proposal.decision.actor_id, proposal.decision.target_id
                ) or Relationship(
                    proposal.decision.actor_id,
                    proposal.decision.target_id,
                    "acquaintance",
                )
                relationship.trust = max(
                    0.0, min(1.0, relationship.trust + float(change.value or 0) / 100)
                )
                RelationshipStore(conn).set(relationship)
        documents.set("thesims4.dialogue-delivery", decision_id, {"displayed": True})
        if proposal.adapter_action == "none":
            actions.confirm(ActionResult(decision_id, "succeeded"), "none")
    return {"decision_id": decision_id, "status": "displayed"}
```

- [ ] **Step 4: Add the endpoint and game-side delivery acknowledgement**

Add to `Handler.do_POST`:

```python
if parsed.path == "/dialogue-result":
    try:
        self.send_json(200, confirm_dialogue_delivery(payload))
    except ValueError as exc:
        self.send_json(400, {"error": str(exc)})
    return
```

When `show_empneon_chat_result` is about to display valid dialogue, submit `POST /dialogue-result` on the existing worker boundary. A delivery failure is logged and shown as an Empneon error; it must not fabricate confirmation locally.

- [ ] **Step 5: Read native tracks from the latest snapshot**

`relationship_diagnostic` loads the source agent's latest snapshot and reads its normalized relationship
entry for the target:

```python
def relationship_diagnostic(conn, agent_id, target_id):
    relationship = RelationshipStore(conn).get(str(agent_id), str(target_id))
    snapshot = load_agent_state(conn, str(agent_id))
    observed = (
        snapshot.relationships.get(str(target_id), {})
        if snapshot is not None
        else {}
    )
    return {
        "direction": {"source_id": str(agent_id), "target_id": str(target_id)},
        "native": {
            "friendship": round(float(observed.get("affinity", 0)) * 100),
            "romance": round(float(observed.get("romance", 0)) * 100),
        },
        "empneon": {
            "trust": round((relationship.trust if relationship else 0.5) * 100)
        },
    }
```

Update `ai.relationship` console output to:

```text
relationship Karmine Luna -> Bernard Jaeger: Sims friendship 7, Sims romance 12, Empneon trust 51
```

Delete respect and resentment from this command. Keep the flat internal `relationship_view()`
shape unchanged for legacy imports and state-update code; its unsupported defaults are not
presented as game facts. Route only the console/API diagnostic output through
`relationship_diagnostic()`.

- [ ] **Step 6: Run focused tests and verify GREEN**

Run the Step 2 command without `-k`. Expected: all backend and script-mod tests pass.

- [ ] **Step 7: Commit delivery confirmation and truthful diagnostics**

```powershell
git add adapters/thesims4/backend/empneon_state.py adapters/thesims4/backend/ai_sims_server.py adapters/thesims4/ts4script/ai_sims_agent.py adapters/thesims4/tests/test_sims4_backend.py adapters/thesims4/tests/test_sims4_mod_autonomy.py
git commit -m "feat(sims4): confirm delivered dialogue turns"
```

### Task 6: Keep one Empneon Social session active through every turn

**Files:**
- Modify: `adapters/thesims4/ts4script/ai_sims_agent.py:1-45,130-155,607-620,925-1035`
- Modify: `adapters/thesims4/tests/test_sims4_mod_autonomy.py:50-260,396-485`

**Interfaces:**
- Produces: `EmpneonConversationSession` with phases `input`, `waiting_for_backend`, `showing_response`, `running_native_action`, and `closed`.
- Produces: `_CONVERSATION_SESSIONS: dict[str, EmpneonConversationSession]` keyed by actor Sim ID.
- Changes: response queue items carry `(session_id, turn_id, data, error)` rather than raw actor/target tuples.
- Produces: `_SESSION_EVENTS`, drained by `process_autonomy_responses`, for worker-completion
  notifications that must transition UI/session state on the Sims thread.

- [ ] **Step 1: Extend fake Sims modules and add failing lifecycle tests**

Add an `element_utils` fake with `sleep_until_next_tick_element()` and `run_child()` to the existing script-mod import fixture. Add tests that drive the generator and callbacks one phase at a time:

```python
interaction = agent.EmpneonSocialInteraction()
interaction.sim = actor
interaction.target = target
runner = interaction._run_interaction_gen("timeline")

assert next(runner) == "next-tick"
session = agent._CONVERSATION_SESSIONS[str(actor.sim_info.sim_id)]
assert session.phase == "input"

dialogs[-1].accepted = True
dialogs[-1].text_input_responses = {"message": "Hello"}
dialogs[-1].listener(dialogs[-1])
assert session.phase == "waiting_for_backend"
assert next(runner) == "next-tick"

session.accept_backend_result(
    session.turn_id,
    {"decision_id": "decision-1", "dialogue": "Hello back", "suggested_action": "none"},
    None,
)
assert session.phase == "showing_response"
assert interaction not in executed  # session owns the actor task

dialogs[-1].accepted = False
dialogs[-1].listener(dialogs[-1])
with pytest.raises(StopIteration) as stopped:
    next(runner)
assert stopped.value.value is True
assert str(actor.sim_info.sim_id) not in agent._CONVERSATION_SESSIONS
```

Add a parameterized cancellation test for `queue_cancel`, `actor_missing`, and `target_missing`.
For each case, close the generator, deliver a late response containing `decision_id`, and assert
that no dialog was added and the captured `/action-result` payload equals:

```python
{
    "decision_id": "late-decision",
    "action": "friendly_chat",
    "status": "failed",
    "reason": "Empneon Social canceled",
    "changes": [],
}
```

Add a two-turn test whose native action worker first posts its result and queues a session event.
After `process_autonomy_responses()` handles that event, assert the callback order is
`displayed`, `native_result_posted`, `native_finished`, `second_submitted`. Assert no dialog is
opened directly by the worker fixture.

- [ ] **Step 2: Run the lifecycle tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='core\src;adapters\thesims4\src'
py -3.12 -m pytest -q -p no:cacheprovider adapters/thesims4/tests/test_sims4_mod_autonomy.py -k "conversation_session or pie_menu"
```

Expected: the current generator returns immediately and no session registry exists.

- [ ] **Step 3: Add the minimum session state object**

Implement a plain class in `ai_sims_agent.py`:

```python
class EmpneonConversationSession:
    def __init__(self, interaction, actor, target):
        self.interaction = interaction
        self.actor = actor
        self.target = target
        self.id = uuid.uuid4().hex
        self.turn_id = 0
        self.phase = "input"
        self.transcript = ""
        self.closed = False
        self.canceled = False
        self.pending_decision = None

    def begin_turn(self):
        if self.closed or self.phase != "input":
            return None
        self.turn_id += 1
        self.phase = "waiting_for_backend"
        return self.turn_id

    def close(self, canceled=False):
        self.closed = True
        self.canceled = bool(canceled)
        self.phase = "closed"

    def accept_backend_result(self, turn_id, data, error):
        if turn_id != self.turn_id:
            return False
        if self.closed:
            if data and data.get("decision_id"):
                report_action_result(
                    data["decision_id"],
                    data.get("suggested_action") or "none",
                    "failed",
                    "Empneon Social canceled",
                    [],
                )
            return False
        self.phase = "showing_response"
        show_empneon_chat_result(self, data, error)
        return True
```

Keep session methods free of backend or Sims imports beyond the existing module functions so unit tests can drive them.

- [ ] **Step 4: Keep the interaction generator alive without blocking the simulation**

Import `element_utils`. Replace `_run_interaction_gen` with:

```python
def _run_interaction_gen(self, timeline):
    actor = getattr(self, "sim", None)
    target = getattr(self, "target", None)
    actor_id = str(getattr(getattr(actor, "sim_info", None), "sim_id", ""))
    if not actor_id or actor_id in _CONVERSATION_SESSIONS:
        return False
    session = EmpneonConversationSession(self, actor, target)
    _CONVERSATION_SESSIONS[actor_id] = session
    try:
        show_empneon_message_dialog(session)
        while not session.closed:
            yield element_utils.run_child(
                timeline, element_utils.sleep_until_next_tick_element()
            )
        return True
    finally:
        session.close(canceled=not session.closed)
        _CONVERSATION_SESSIONS.pop(actor_id, None)
```

The generator's `finally` block is the cancellation hook: Sims closes the generator when the
queued interaction finishes for any reason. Use:

```python
finally:
    if not session.closed:
        session.close(canceled=True)
    _CONVERSATION_SESSIONS.pop(actor_id, None)
```

Do not sleep or block the simulation thread.

- [ ] **Step 5: Route dialog and worker callbacks through session/turn IDs**

Change `show_empneon_message_dialog`, `submit_empneon_chat`, and `show_empneon_chat_result` to accept a session. The input callback calls `turn_id = session.begin_turn()` before starting the worker. The worker appends `(session.id, turn_id, data, error)`.

`process_autonomy_responses` looks up the live session by session ID and calls `accept_backend_result`. Missing/closed sessions report any returned decision as canceled and never show a dialog.

Native action-result workers append `(session.id, turn_id, "native_finished")` to
`_SESSION_EVENTS` after the `/action-result` request completes. Extend
`process_autonomy_responses` to drain that queue and call
`session.after_native_action(turn_id)`. Discard stale turn IDs and never call a Sims dialog
function from a worker thread.

- [ ] **Step 6: Complete each turn before allowing another**

On response display, acknowledge `/dialogue-result`. The response-dialog listener stores either
the next message or a close request, then calls:

```python
def finish_displayed_turn(session, data, next_message):
    action = str(data.get("suggested_action") or "none")
    session.next_message = next_message
    if action == "none":
        session.after_native_action(session.turn_id)
        return
    session.phase = "running_native_action"
    execute_sims_action(
        data.pop("_empneon_payload"),
        data,
        None,
        session_id=session.id,
        turn_id=session.turn_id,
    )
```

`after_native_action` opens the next input when `next_message` is non-empty; otherwise it closes
the session. Extend `execute_sims_action` and `report_action_result` with optional `session_id`
and `turn_id` arguments; after posting the native result, the worker queues the session event
described in Step 5. For action `none`, call `after_native_action(session.turn_id)` directly on
the Sims thread because `/dialogue-result` already closed that proposal. Reject a new
`begin_turn` unless the phase is `input`; this keeps at most one backend request and one native
action active.

- [ ] **Step 7: Run all script-mod tests and verify GREEN**

Run:

```powershell
$env:PYTHONPATH='core\src;adapters\thesims4\src'
py -3.12 -m pytest -q -p no:cacheprovider adapters/thesims4/tests/test_sims4_mod_autonomy.py
```

Expected: all script-mod tests pass, including session cancellation and late-result cleanup.

- [ ] **Step 8: Compile and build the development mod**

Run:

```powershell
py -3.12 -m py_compile adapters/thesims4/ts4script/ai_sims_agent.py
py -3.12 adapters/thesims4/build_mod.py
```

Expected: Python syntax compilation passes and `dist/Empneon_TheSims4.ts4script` plus `dist/Empneon_TheSims4.package` are rebuilt using Python 3.7 bytecode.

- [ ] **Step 9: Commit the held interaction lifecycle**

```powershell
git add adapters/thesims4/ts4script/ai_sims_agent.py adapters/thesims4/tests/test_sims4_mod_autonomy.py
git commit -m "feat(sims4): hold social conversation session"
```

### Task 7: Documentation, full verification, and in-game handoff

**Files:**
- Modify: `core/docs/adapter-development.md`
- Modify: `adapters/thesims4/docs/in-game-core-feature-test-plan.md`
- Modify: `adapters/thesims4/docs/in-game-core-feature-test-results.md`
- Modify: `adapters/thesims4/docs/setup.md`
- Modify: `docs/superpowers/specs/2026-07-21-adapter-state-and-sims-conversation-design.md` only if verified behavior differs from the approved design

**Interfaces:**
- Consumes: all prior tasks.
- Produces: updated adapter guidance and a precise Test 5 source-build retest procedure.

- [ ] **Step 1: Document the state snapshot and authority boundary**

In `core/docs/adapter-development.md`, add the required snapshot sections, normalized ranges, native preservation rule, latest-snapshot persistence, and the distinction between model proposals and game-confirmed changes. State explicitly that adapters may leave unsupported sections empty.

- [ ] **Step 2: Update Sims Test 5 without marking it passed**

Record the observed accepted-sounding Karmine response, its previous rejection by metadata validation, and the new automated regression. Keep Test 5 partial until an in-game source build verifies:

- original grounded dialogue is displayed;
- Empneon Social remains in the queue while waiting;
- autonomy does not interrupt the session;
- each displayed turn updates memory/Empneon trust;
- each selected native action completes before another input;
- only game-observed friendship/romance changes persist;
- manual queue cancellation suppresses a late result.

- [ ] **Step 3: Run complete automated verification**

From the repository root:

```powershell
$env:PYTHONPATH='core\src;adapters\thesims4\src;adapters\godot\src'
py -3.12 -m pytest -q -p no:cacheprovider core adapters/thesims4 adapters/godot tests scripts/test_release.py
py -3.12 -m ruff check --select E9,F63,F7,F82 core/src core/tests adapters/thesims4/src adapters/thesims4/tests adapters/thesims4/backend adapters/thesims4/ts4script adapters/godot/src adapters/godot/tests tests scripts
py -3.12 -m mypy core/src adapters/thesims4/src adapters/godot/src
py -3.12 -m py_compile adapters/thesims4/backend/ai_sims_server.py adapters/thesims4/backend/empneon_state.py adapters/thesims4/ts4script/ai_sims_agent.py
$env:PYTHONPATH='core\src'
py -3.12 -m empneon.benchmarks.regression core/scenarios/clod1-regressions.json
git diff --check
```

The owner approved this full-scope critical Ruff gate instead of requiring cleanup of unrelated
legacy style findings. Changed production files remain subject to the narrower all-rule Ruff gates
defined by their implementation tasks. `git diff --check` remains mandatory.

Expected: every command exits `0`; no SQLite sidecars or generated benchmark/dialogue reports are staged.

- [ ] **Step 4: Commit documentation and final automated evidence**

```powershell
git add core/docs/adapter-development.md adapters/thesims4/docs/in-game-core-feature-test-plan.md adapters/thesims4/docs/in-game-core-feature-test-results.md adapters/thesims4/docs/setup.md
git commit -m "docs(sims4): prepare state-aware Test 5 retest"
```

- [ ] **Step 5: Install the source-built mod and run the source backend**

From `adapters/thesims4`:

```powershell
py -3.12 .\build_mod.py
.\install_mod.ps1
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 .\backend\ai_sims_server.py
```

Expected: the current `.ts4script` and `.package` are installed, and the backend imports Core and the adapter from the feature worktree.

- [ ] **Step 6: Perform the focused in-game Test 5 retest**

Use a disposable save. Start Empneon Social with Karmine, submit a romantic invitation, and verify the full queue/session checklist from Step 2. Capture the exact player message, displayed response, `ai.relationship` output before/after, decision ID, native finishing result, and whether the session was continued or closed. Repeat once with manual queue cancellation during backend waiting.

- [ ] **Step 7: Record in-game evidence and push only after it passes**

Update `in-game-core-feature-test-results.md` with sanitized evidence. Run `git diff --check`, commit the evidence, and push:

```powershell
git push origin feature/sims4-core-integration
```

Do not mark Test 5 passed unless natural dialogue, held queue lifecycle, cognitive turn confirmation, and at least one game-confirmed native relationship result all pass.
