# Cross-Adapter Social Categories Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Classify each incoming social message into one of five common categories, generate a state-grounded response category and tone, derive one native action, and let the adapter/game own friendship and romance outcomes.

**Architecture:** Extend existing event facts and decisions instead of creating a parallel social subsystem. Empneon deterministically classifies the incoming message, the model returns one response category plus tone/dialogue/trust, Empneon derives `social.<category>`, and the adapter maps that token to one exact native affordance and reports only observed relationship changes.

**Tech Stack:** Python 3.12 Core/backend/tests, Python 3.7-compatible Sims script source, existing Sims 4 runtime APIs, standard library only, pytest, Ruff, mypy.

## Global Constraints

- Common categories are exactly `friendly`, `funny`, `romance`, `mean`, and `mischief`.
- `Actions` is not a social category.
- The incoming category and responding actor's category are independent.
- A response has one primary category and zero to three lowercase tone tags.
- The model cannot independently choose a concrete action; `response_category` derives `social.<category>`.
- The model cannot propose friendship, romance, or attraction mutations. Only bounded Empneon `trust_delta` remains model-owned.
- Both directed actor snapshots must reach the model, including identity, age, traits, moodlets/effects, needs, relationship, and attraction when available.
- A mapped native social executes automatically only after dialogue acknowledgement.
- The adapter/game remains authoritative for action validity and relationship results.
- Preserve compatibility with legacy response fields throughout `0.3.x`, but ignore legacy category/action/friendship/romance authority.
- Keep the Sims script Python 3.7-compatible and add no dependency.
- Work locally on `main`; do not push. Preserve the SQLite `-wal` and `-shm` sidecars.

---

## File Map

- `core/src/empneon/core/contracts.py`: common category constants/type and optional event-social validation.
- `core/tests/unit/test_contracts.py`: accepted/rejected common social context.
- `tests/cross_adapter/test_game_adapters.py`: synthetic non-Sims common-action round trip.
- `adapters/thesims4/ts4script/ai_sims_agent.py`: advertise categories, capture both relationship directions, and map common actions to exact native tunings.
- `adapters/thesims4/tests/test_sims4_mod_autonomy.py`: payload, five-entry mapping, native execution, and result-observation coverage.
- `adapters/thesims4/src/empneon_thesims4/adapter.py`: translate response category/trust into Core decision state without model friendship/romance changes.
- `adapters/thesims4/tests/test_adapter.py`: derived common action and ignored legacy deltas.
- `adapters/thesims4/backend/ai_sims_server.py`: classification, provider schema, response normalization, prompt, contradiction retry, and dialogue-only fallback.
- `adapters/thesims4/tests/test_sims4_backend.py`: all category/model/compatibility/confirmation behavior.
- `adapters/thesims4/tests/test_http_simulation.py`: current HTTP request/response contract.
- `adapters/thesims4/docs/in-game-core-feature-test-plan.md`: five-category live Test 5 matrix.
- `adapters/thesims4/docs/in-game-core-feature-test-results.md`: automated evidence and honest live status.

### Task 1: Define and validate the common social contract

**Files:**
- Modify: `core/tests/unit/test_contracts.py`
- Modify: `core/src/empneon/core/contracts.py:1-125`
- Modify: `tests/cross_adapter/test_game_adapters.py`

**Interfaces:**
- Produces: `SocialCategory`, `SOCIAL_CATEGORIES`, and optional `WorldEvent.facts["social"]` with `incoming_category` and `available_response_categories`.
- Consumes: existing extensible `WorldEvent.facts`, `Decision`, and `StateDelta` contracts.

- [ ] **Step 1: Write failing common-contract tests**

Add to `core/tests/unit/test_contracts.py`:

```python
def test_world_event_accepts_common_social_context() -> None:
    event = WorldEvent(
        "conversation",
        ("alice", "bob"),
        facts={
            "social": {
                "incoming_category": "romance",
                "available_response_categories": [
                    "friendly",
                    "funny",
                    "romance",
                    "mean",
                    "mischief",
                ],
            }
        },
    )

    assert event.facts["social"] == {
        "incoming_category": "romance",
        "available_response_categories": list(SOCIAL_CATEGORIES),
    }


@pytest.mark.parametrize("category", ["actions", "neutral", "hostile", "romantic"])
def test_world_event_rejects_unknown_social_category(category: str) -> None:
    with pytest.raises(ValueError, match="social category"):
        WorldEvent(
            "conversation",
            facts={
                "social": {
                    "incoming_category": category,
                    "available_response_categories": ["friendly"],
                }
            },
        )
```

Import `SOCIAL_CATEGORIES` beside the existing contract imports.

- [ ] **Step 2: Run the Core test and verify RED**

```powershell
Set-Location core
$env:PYTHONPATH='src'; py -3.12 -m pytest -q -p no:cacheprovider tests/unit/test_contracts.py -k "social_context or social_category"
```

Expected: collection fails because `SOCIAL_CATEGORIES` does not exist, or the invalid categories are accepted.

- [ ] **Step 3: Add the minimal common validation**

In `core/src/empneon/core/contracts.py`, add:

```python
SocialCategory = Literal["friendly", "funny", "romance", "mean", "mischief"]
SOCIAL_CATEGORIES: tuple[SocialCategory, ...] = (
    "friendly",
    "funny",
    "romance",
    "mean",
    "mischief",
)


def _validate_social_context(facts: Mapping[str, object]) -> None:
    social = facts.get("social")
    if social is None:
        return
    if not isinstance(social, Mapping):
        raise ValueError("event social context must be a mapping")
    incoming = social.get("incoming_category")
    available = social.get("available_response_categories")
    if incoming not in SOCIAL_CATEGORIES:
        raise ValueError("event social category is invalid")
    if not isinstance(available, (list, tuple)) or any(
        category not in SOCIAL_CATEGORIES for category in available
    ):
        raise ValueError("event available social category is invalid")
```

Call `_validate_social_context(self.facts)` at the end of `WorldEvent.__post_init__`.

- [ ] **Step 4: Add a synthetic non-Sims common-action test**

Add to `tests/cross_adapter/test_game_adapters.py`:

```python
def test_non_sims_adapter_can_carry_common_social_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, WorldEvent] = {}
    def capture(request: CognitiveRequest) -> Decision:
        captured["event"] = request.event
        return Decision(
            request.actor_id,
            "respond_playfully",
            target_id="agent-b",
            evidence_ids=(request.event.id,),
            state_changes=(
                StateDelta("social.response_category", "set", "funny"),
                StateDelta("animation", "set", "social.funny"),
            ),
        )

    monkeypatch.setattr(bridge_module, "resolve_clod1", capture)
    bridge = GodotBridge()
    decision = bridge.decide(
        {
            "agent_id": "agent-a",
            "event": asdict(
                WorldEvent(
                    "conversation",
                    ("agent-a", "agent-b"),
                    facts={
                        "social": {
                            "incoming_category": "friendly",
                            "available_response_categories": ["friendly", "funny"],
                        }
                    },
                )
            ),
        }
    )

    assert captured["event"].facts["social"]["incoming_category"] == "friendly"
    assert {change["path"]: change["value"] for change in decision["state_changes"]} == {
        "social.response_category": "funny",
        "animation": "social.funny",
    }
```

Add `StateDelta` to this test module's Core imports.

- [ ] **Step 5: Run Core and cross-adapter GREEN checks**

```powershell
Set-Location ../
$env:PYTHONPATH='core\src'; py -3.12 -m pytest -q -p no:cacheprovider core/tests/unit/test_contracts.py
$env:PYTHONPATH='core\src;adapters\thesims4\src;adapters\godot\src'; py -3.12 -m pytest -q -p no:cacheprovider tests/cross_adapter/test_game_adapters.py
```

Expected: both commands pass.

- [ ] **Step 6: Commit locally**

```powershell
git add core/src/empneon/core/contracts.py core/tests/unit/test_contracts.py tests/cross_adapter/test_game_adapters.py
git commit -m "feat(core): define common social categories"
```

### Task 2: Advertise loaded Sims categories and both directed actor states

**Files:**
- Modify: `adapters/thesims4/tests/test_sims4_mod_autonomy.py`
- Modify: `adapters/thesims4/ts4script/ai_sims_agent.py:20-45,1995-2035`
- Modify: `adapters/thesims4/tests/test_adapter.py`
- Modify: `adapters/thesims4/src/empneon_thesims4/adapter.py:183-225`
- Modify: `adapters/thesims4/tests/test_sims4_backend.py`
- Modify: `adapters/thesims4/backend/ai_sims_server.py:1265-1315`

**Interfaces:**
- Produces: the exact Sims tuning map, request fields `available_response_categories`, `relationship` (Speaker-to-Listener), and `listener_relationship` (Listener-to-Speaker), plus common `facts["social"]`.
- Consumes: Task 1 category names and the existing `relationship_payload(source_info, target_info)`.

- [ ] **Step 1: Write failing Sims payload tests**

Replace the existing held-payload assertion in `test_sims4_mod_autonomy.py`:

```python
    assert held_payload["available_response_categories"] == [
        "friendly",
        "funny",
        "romance",
        "mean",
        "mischief",
    ]
    assert held_payload["relationship"] == {
        "direction": "bella-to-mortimer"
    }
    assert held_payload["listener_relationship"] == {
        "direction": "mortimer-to-bella"
    }
```

Add a second case whose fake interaction manager omits the Mean tuning and assert the advertised
categories omit only `mean`. Assert the exact map once here:

```python
assert agent.NATIVE_SOCIAL_TUNINGS == {
    "social.friendly": "mixer_social_AskAboutDay_targeted_Friendly_alwaysOn",
    "social.funny": "mixer_social_TellJoke_targeted_Funny_alwaysOn",
    "social.romance": "mixer_social_ComplimentAppearance_targeted_romance_alwaysOn",
    "social.mean": "mixer_social_Insult_targeted_mean_alwaysOn",
    "social.mischief": "mixer_social_LieAboutCareer_targeted_mischief_alwaysOn",
    "friendly_chat": "mixer_social_AskAboutDay_targeted_Friendly_alwaysOn",
    "apologize": "mixer_social_Apologize_targeted_friendly_lowScore",
    "flirt": "mixer_social_ComplimentAppearance_targeted_romance_alwaysOn",
}
```

The three legacy keys remain for autonomous/`0.3.x` compatibility.

For this test, replace the relationship stub with a directional one:

```python
    monkeypatch.setattr(
        agent,
        "relationship_payload",
        lambda source, target: {
            "direction": "{}-to-{}".format(source.sim_id, target.sim_id)
        },
    )
```

Add a backend state-direction test to `test_sims4_backend.py`:

```python
def test_both_actor_snapshots_keep_their_directed_relationships() -> None:
    payload = {
        "speaker": {"id": "karmine", "current_mood": "playful"},
        "listener": {"id": "bernard", "current_mood": "confident"},
        "relationship": {
            "friendship": 16,
            "romance": 0,
            "trust": 50,
            "attraction": 2 / 3,
        },
        "listener_relationship": {
            "friendship": 8,
            "romance": 4,
            "trust": 50,
            "attraction": -0.5,
        },
    }

    speaker = ai_sims_server._actor_snapshot(payload, "speaker")
    listener = ai_sims_server._actor_snapshot(payload, "listener")

    assert speaker["relationships"]["bernard"]["attraction"] == pytest.approx(2 / 3)
    assert listener["relationships"]["karmine"] == {
        "affinity": 0.08,
        "romance": 0.04,
        "trust": 0.5,
        "attraction": -0.5,
    }
```

Add an adapter observation test in `test_adapter.py` with `incoming_category="romance"` and a
three-item advertised subset. Assert `event.facts["social"]` preserves exactly those values.

- [ ] **Step 2: Run focused tests and verify RED**

```powershell
Set-Location adapters/thesims4
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_mod_autonomy.py tests/test_sims4_backend.py -k "held_payload or directed_relationships"
```

Expected: the exact social map, loaded subset, common event facts, reverse relationship, and listener snapshot assertions fail.

- [ ] **Step 3: Add the Sims category advertisement and reverse observation**

Replace `NATIVE_SOCIAL_TUNINGS` with the exact dictionary asserted in Step 1. Keep the legacy
autonomy list separate and add the local Python 3.7-compatible category tuple:

```python
SOCIAL_CATEGORIES = ("friendly", "funny", "romance", "mean", "mischief")
AVAILABLE_ACTIONS = ["friendly_chat", "apologize", "flirt"]


def available_social_categories():
    return [
        category
        for category in SOCIAL_CATEGORIES
        if find_action_affordance("social." + category) is not None
    ]
```

The script cannot import Core in the packaged game runtime, so this is the one intentional duplicate
of the common tuple. Exact lookup avoids accidentally treating a similarly named mod affordance as
official support.

Replace `chat_payload_for_target` with:

```python
def chat_payload_for_target(active, target_info, message, source):
    player = sim_payload(active)
    npc = sim_info_payload(target_info)
    return {
        "speaker": npc,
        "listener": player,
        "relationship": relationship_payload(target_info, active.sim_info),
        "listener_relationship": relationship_payload(active.sim_info, target_info),
        "location": current_location(),
        "nearby_sims": nearby_sim_payloads(npc["id"], player["id"]),
        "event": {"type": "player_conversation", "source": source},
        "available_response_categories": available_social_categories(),
        "message": message,
    }
```

Apply the same fields to the named console fallback, using an empty `listener_relationship` when no
real target `SimInfo` exists. Leave autonomous payloads on their existing concrete-action contract.

- [ ] **Step 4: Preserve the reverse relationship in the listener snapshot**

Change `_actor_snapshot` in `ai_sims_server.py`:

```python
def _actor_snapshot(payload, role):
    other = "listener" if role == "speaker" else "speaker"
    actor_payload = dict(payload)
    actor_payload.pop("sim", None)
    actor_payload["speaker"] = payload.get(role) or {}
    actor_payload["listener"] = payload.get(other) or {}
    actor_payload["relationship"] = (
        payload.get("relationship")
        if role == "speaker"
        else payload.get("listener_relationship")
    ) or {}
    return dataclasses.asdict(Sims4Adapter(actor_payload).agent_state())
```

Import `SOCIAL_CATEGORIES` from `empneon.core.contracts` in the backend and Sims adapter; do not
declare another copy. In `Sims4Adapter.observe()`, add:

```python
"social": {
    "incoming_category": self._payload.get("incoming_category"),
    "available_response_categories": _items(
        self._payload.get("available_response_categories")
    ),
},
```

Only include this `social` fact when `incoming_category` is present, so existing autonomous events
remain valid under the optional common contract.

- [ ] **Step 5: Run the complete payload/state tests**

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_mod_autonomy.py tests/test_sims4_backend.py tests/test_adapter.py -k "payload or social_tunings or social_context or actor_snapshot or actor_states or directed_relationships"
```

Expected: PASS.

- [ ] **Step 6: Commit locally**

```powershell
Set-Location ../..
git add adapters/thesims4/ts4script/ai_sims_agent.py adapters/thesims4/backend/ai_sims_server.py adapters/thesims4/src/empneon_thesims4/adapter.py adapters/thesims4/tests/test_sims4_mod_autonomy.py adapters/thesims4/tests/test_sims4_backend.py adapters/thesims4/tests/test_adapter.py
git commit -m "feat(sims4): advertise loaded social categories"
```

### Task 3: Classify incoming messages and derive response actions

**Files:**
- Modify: `adapters/thesims4/tests/test_sims4_backend.py`
- Modify: `adapters/thesims4/backend/ai_sims_server.py:200-325,950-1030,1650-1705`
- Modify: `adapters/thesims4/tests/test_adapter.py`
- Modify: `adapters/thesims4/src/empneon_thesims4/adapter.py:1-45,270-350`

**Interfaces:**
- Produces: `classify_social_category(message) -> str`, `explicit_social_category(text) -> str | None`, and normalized provider fields `response_category`, `tone_tags`, `trust_delta`, and derived `suggested_action`.
- Consumes: Task 1 categories and Task 2 `available_response_categories`.

- [ ] **Step 1: Write failing five-category classifier tests**

Replace the old multi-kind classifier assertion in `test_sims4_backend.py` with:

```python
@pytest.mark.parametrize(
    "message,expected",
    [
        ("Hello. How was your day?", "friendly"),
        ("That joke was hilarious—tell me another one!", "funny"),
        ("I love you. Would you go on a date with me?", "romance"),
        ("I hate you. Leave me alone, idiot.", "mean"),
        ("Let's prank Bob and lie about what happened.", "mischief"),
        ("Where is the garden code item?", "friendly"),
        ("The weather changed today.", "friendly"),
    ],
)
def test_common_social_classifier(message: str, expected: str) -> None:
    assert ai_sims_server.classify_social_category(message) == expected
```

Add high-signal response coverage:

```python
@pytest.mark.parametrize(
    "dialogue,expected",
    [
        ("Yes, I would love to go on a date with you.", "romance"),
        ("That was hilarious!", "funny"),
        ("Go away, you insufferable idiot.", "mean"),
        ("Let's prank them and pretend we know nothing.", "mischief"),
        ("I appreciate you asking.", None),
    ],
)
def test_explicit_social_category(dialogue: str, expected: str | None) -> None:
    assert ai_sims_server.explicit_social_category(dialogue) == expected
```

- [ ] **Step 2: Write failing response-schema and compatibility tests**

Add:

```python
def test_response_category_derives_action_and_ignores_legacy_authority() -> None:
    response = ai_sims_server.normalize_response(
        {
            "dialogue": "A date sounds wonderful. I'd love to go.",
            "response_category": "romance",
            "tone_tags": ["playful", "hesitant"],
            "trust_delta": 2,
            "friendship_delta": 9,
            "romance_delta": 9,
            "suggested_action": "social.mean",
            "relationship": {
                "friendship_delta": 9,
                "romance_delta": 9,
                "trust_delta": 7,
            },
            "memory": {"importance": 0.5, "summary": "A date was accepted."},
        },
        ["friendly", "funny", "romance", "mean", "mischief"],
    )

    assert response["response_category"] == "romance"
    assert response["tone_tags"] == ["playful", "hesitant"]
    assert response["suggested_action"] == "social.romance"
    assert response["trust_delta"] == 2
    assert "friendship_delta" not in response
    assert "romance_delta" not in response
    assert "relationship" not in response
```

Add parameterized invalid tag/category cases: four tags, uppercase tag, whitespace tag, and
`response_category="actions"`; each must raise `ValueError` with `tone_tags` or `response_category`.

- [ ] **Step 3: Run classifier/schema tests and verify RED**

```powershell
Set-Location adapters/thesims4
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "common_social_classifier or explicit_social_category or derives_action or invalid_social"
```

Expected: FAIL because the five-category functions/response fields do not exist.

- [ ] **Step 4: Implement the classifiers and single action derivation**

Replace `PLAYER_INTERACTION_KINDS` and `classify_player_interaction` with:

```python
SOCIAL_ACTIONS = {category: "social." + category for category in SOCIAL_CATEGORIES}


def explicit_social_category(message):
    value = str(message or "").casefold()
    patterns = (
        (
            "romance",
            r"\b(date|kiss|marry|girlfriend|boyfriend|attracted|attractive|beautiful|"
            r"gorgeous|handsome|hot|sexy|love you|feelings for|like you romantically)\b",
        ),
        ("mean", r"\b(hate|despise|idiot|stupid|insufferable|leave me alone|go away)\b"),
        ("mischief", r"\b(prank|trick|scare|deceive|pretend|lie about|mess with)\b"),
        ("funny", r"\b(joke|funny|hilarious|laugh|pun|comedy)\b"),
    )
    return next((category for category, pattern in patterns if re.search(pattern, value)), None)


def classify_social_category(message):
    return explicit_social_category(message) or "friendly"
```

Import `SOCIAL_CATEGORIES` from `empneon.core.contracts`; do not duplicate the common tuple in the
backend.

Change `DIALOGUE_SCHEMA` so the model must return `response_category`, `tone_tags`, `dialogue`,
`expressed_emotion`, `intent`, `trust_delta`, and `memory`. Use:

```python
"response_category": {"type": "string", "enum": list(SOCIAL_CATEGORIES)},
"tone_tags": {
    "type": "array",
    "items": {"type": "string", "pattern": "^[a-z][a-z0-9_-]{0,31}$"},
    "maxItems": 3,
    "uniqueItems": True,
},
"trust_delta": {"type": "integer", "minimum": -10, "maximum": 10},
```

Remove `relationship`, `player_interaction_kind`, and `suggested_action` from required model output.
Change `dialogue_schema` to accept categories and limit the response-category enum to the advertised
subset.

Replace `normalize_response` with a version that:

```python
def normalize_response(raw, available_categories=()):
    if not isinstance(raw, dict):
        raw = {}
    categories = tuple(
        category
        for category in available_categories
        if category in SOCIAL_CATEGORIES
    )
    legacy_kind = str(raw.get("player_interaction_kind") or "")
    legacy_categories = {
        "romantic_compliment": "romance",
        "romantic_invitation": "romance",
        "hostile": "mean",
        "informational": "friendly",
        "neutral": "friendly",
    }
    category = str(
        raw.get("response_category")
        or legacy_categories.get(legacy_kind)
        or legacy_kind
        or "friendly"
    )
    if category not in categories:
        raise ValueError("response_category is invalid or unavailable")
    tone_tags = raw.get("tone_tags") or []
    if (
        not isinstance(tone_tags, list)
        or len(tone_tags) > 3
        or len(set(tone_tags)) != len(tone_tags)
        or any(not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", str(tag)) for tag in tone_tags)
    ):
        raise ValueError("tone_tags are invalid")
    memory = raw.get("memory") if isinstance(raw.get("memory"), dict) else {}
    trust = raw.get("trust_delta")
    if trust is None and isinstance(raw.get("relationship"), dict):
        trust = raw["relationship"].get("trust_delta")
    return {
        "dialogue": str(raw.get("dialogue") or "...").strip(),
        "expressed_emotion": str(
            raw.get("expressed_emotion") or raw.get("emotion") or "neutral"
        ).strip().lower(),
        "intent": str(raw.get("intent") or "respond").strip(),
        "response_category": category,
        "tone_tags": [str(tag) for tag in tone_tags],
        "trust_delta": clamp_int(trust),
        "memory": {
            "importance": clamp_float(memory.get("importance")),
            "summary": str(memory.get("summary") or "").strip(),
        },
        "suggested_action": SOCIAL_ACTIONS[category],
        "animation": SOCIAL_ACTIONS[category],
    }
```

Legacy friendship/romance/action fields are deliberately not copied.

- [ ] **Step 5: Make the adapter emit only trust and the derived social action**

In `empneon_thesims4/adapter.py`, add:

```python
SOCIAL_ACTIONS = frozenset("social." + category for category in SOCIAL_CATEGORIES)
SIMS_ACTIONS = SIMS_ACTIONS | SOCIAL_ACTIONS
```

Use the `SOCIAL_CATEGORIES` import added in Task 2.

Replace the relationship-delta portion of `decision_from_response` with:

```python
        trust_delta = response.get("trust_delta")
        if isinstance(trust_delta, (int, float)) and not isinstance(trust_delta, bool):
            changes.append(
                StateDelta("relationship.trust", "increment", trust_delta)
            )
        category = str(response.get("response_category") or "friendly")
        changes.extend(
            (
                StateDelta("social.response_category", "set", category),
                StateDelta("social.tone_tags", "set", list(response.get("tone_tags") or [])),
                StateDelta("animation", "set", "social." + category),
            )
        )
```

Update `response_for` to expose `response_category`, `tone_tags`, and top-level `trust_delta`; do not
create response friendship/romance deltas. Update `action_for` so a `social.*` action is accepted only
when its suffix is present in `available_response_categories`.

- [ ] **Step 6: Run backend and adapter GREEN checks**

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py tests/test_adapter.py -k "social or response_category or legacy_authority or trust"
```

Expected: PASS.

- [ ] **Step 7: Commit locally**

```powershell
Set-Location ../..
git add adapters/thesims4/backend/ai_sims_server.py adapters/thesims4/src/empneon_thesims4/adapter.py adapters/thesims4/tests/test_sims4_backend.py adapters/thesims4/tests/test_adapter.py
git commit -m "feat: derive actions from common social categories"
```

### Task 4: Ground model response category and retry contradictions

**Files:**
- Modify: `adapters/thesims4/tests/test_sims4_backend.py`
- Modify: `adapters/thesims4/backend/ai_sims_server.py:200-245,1275-1470,1695-1950`

**Interfaces:**
- Produces: `response_category_issue(response) -> str`, category-aware prompt, one retry, and safe dialogue-only fallback.
- Consumes: Task 2 actor snapshots and Task 3 classifiers/normalized response.

- [ ] **Step 1: Write failing prompt and contradiction tests**

Add:

```python
def test_prompt_separates_incoming_category_from_state_grounded_response() -> None:
    payload = {
        "speaker": {"id": "karmine"},
        "listener": {"id": "bernard"},
        "message": "Would you go on a date with me?",
        "incoming_category": "romance",
        "available_response_categories": list(ai_sims_server.SOCIAL_CATEGORIES),
    }
    context = ai_sims_server.build_context(
        payload,
        {"name": "Karmine"},
        {"name": "Bernard"},
        {"friendship": 16, "romance": 0, "trust": 60, "attraction": 0},
        {},
        [],
        {},
    )
    context.update(conversation=[], speaker_id="karmine", listener_id="bernard")

    prompt = ai_sims_server.build_chat_prompt(payload, context)

    assert "Incoming social category: romance" in prompt
    assert "Choose the Speaker's response category independently" in prompt
    assert "one primary response category" in prompt
    assert "friendship_delta" not in prompt
    assert "romance_delta" not in prompt
    assert "suggested_action" not in prompt
```

Add:

```python
@pytest.mark.parametrize(
    "dialogue,category,issue",
    [
        ("Yes, I would love to date you.", "friendly", "explicit romance"),
        ("No, I would rather stay friends.", "romance", "romantic refusal"),
        ("No, I don't want to date you.", "friendly", ""),
        ("Go away, idiot.", "friendly", "explicit mean"),
        ("That was hilarious!", "funny", ""),
        ("I need time to think.", "friendly", ""),
    ],
)
def test_response_category_issue(dialogue: str, category: str, issue: str) -> None:
    assert ai_sims_server.response_category_issue(
        {"dialogue": dialogue, "response_category": category}
    ) == issue
```

Add a mocked `HERMES.dialogue` test where the first provider response is romantic acceptance marked
friendly and the second is marked romance. Assert two provider calls and final
`suggested_action == "social.romance"`. Add a second test with two contradictions and assert the
returned fallback has `suggested_action == "none"`.

Add a no-native-support case with `available_response_categories=[]`. Assert the provider is not
called and the deterministic response has `suggested_action == "none"`; an empty advertised subset
must never create an invalid empty JSON-schema enum or an unsupported action.

- [ ] **Step 2: Run tests and verify RED**

```powershell
Set-Location adapters/thesims4
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "incoming_category or response_category_issue or category_retry"
```

Expected: FAIL because the prompt and contradiction function do not exist.

- [ ] **Step 3: Replace the provider-facing prompt shape**

Update `SYSTEM_PROMPT` to require this exact response shape:

```text
{
  "dialogue": "expressive in-character reply",
  "expressed_emotion": "playful",
  "intent": "accept_playfully",
  "response_category": "romance",
  "tone_tags": ["playful", "hesitant"],
  "trust_delta": 1,
  "memory": {
    "importance": 0.4,
    "summary": "One concrete event memory."
  }
}
```

Remove provider instructions for `player_interaction_kind`, relationship friendship/romance
deltas, and `suggested_action`.

In `chat`, set the authoritative input before context construction:

```python
        payload = dict(payload)
        payload["incoming_category"] = classify_social_category(
            payload.get("message")
        )
```

Immediately after classification, if no valid advertised category remains, return
`reasoning_fallback_response` with `suggested_action="none"` and skip the provider call.

Add these prompt lines:

```text
Incoming social category: {incoming_category}
Available response categories: {available_response_categories}
Choose the Speaker's response category independently from the incoming category.
Use exactly one primary response category. Tone tags may blend style, mood, and personality but do
not select additional actions.
The Speaker may accept, reject, joke, retaliate, or deflect according to both actor states.
Do not return friendship, romance, attraction, or action fields; the adapter and game own them.
```

Format them from the authoritative payload values.

- [ ] **Step 4: Add contradiction validation and retry integration**

Add:

```python
def response_category_issue(response):
    dialogue = str(response.get("dialogue") or "")
    category = str(response.get("response_category") or "")
    normalized = dialogue.casefold()
    romantic_refusal = re.search(
        r"\b(no|not interested|rather stay friends|do not want|don't want)\b",
        normalized,
    )
    if romantic_refusal:
        return "romantic refusal" if category == "romance" else ""
    explicit = explicit_social_category(dialogue)
    if explicit is not None and explicit != category:
        return "explicit {}".format(explicit)
    return ""
```

In `HermesRuntime.dialogue`, pass `available_response_categories` to `dialogue_schema` and
`normalize_response`, include `response_category_issue(response)` beside existing grounding and role
checks, and append this correction on the first mismatch:

```python
prompt += (
    "\nCorrection: The response_category must describe the Speaker's own dialogue. "
    "Do not copy the incoming category when the Speaker rejects or changes direction."
)
```

After two failed attempts, use `reasoning_fallback_response`, force its derived action to `none`,
and keep its valid common response category for diagnostics.

- [ ] **Step 5: Make deterministic fallback use the five categories**

Replace old informational/neutral/romantic-subkind outputs with the common categories. Use these
fixed fallbacks:

```python
fallback_categories = {
    "romance": ("friendly", "reserved"),
    "mean": ("mean", "firm"),
    "mischief": ("friendly", "wary"),
    "funny": ("funny", "light"),
    "friendly": ("friendly", "neutral"),
}
```

The fallback returns `response_category`, one tone tag, bounded `trust_delta`, and
`suggested_action="none"`. Preserve the existing evidence/identity/repetition safeguards and
message-specific dialogue branches.

- [ ] **Step 6: Run the complete backend suite**

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py
```

Expected: PASS after updating old provider fixtures to the new response shape or explicit `0.3.x`
legacy inputs.

- [ ] **Step 7: Commit locally**

```powershell
Set-Location ../..
git add adapters/thesims4/backend/ai_sims_server.py adapters/thesims4/tests/test_sims4_backend.py
git commit -m "feat(sims4): ground and validate social response categories"
```

### Task 5: Execute and verify all five native Sims socials

**Files:**
- Modify: `adapters/thesims4/tests/test_sims4_mod_autonomy.py`
- Modify: `adapters/thesims4/ts4script/ai_sims_agent.py:1160-1310,1800-1885`
- Modify: `adapters/thesims4/tests/test_http_simulation.py`
- Modify: `adapters/thesims4/docs/in-game-core-feature-test-plan.md:118-175`
- Modify: `adapters/thesims4/docs/in-game-core-feature-test-results.md:321-355`

**Interfaces:**
- Produces: post-dialogue native execution and observed relationship result flow.
- Consumes: Tasks 2-4 response category, derived action, payload baseline, and dialogue acknowledgement.

- [ ] **Step 1: Write failing execution tests**

Add a held-session test that provides `suggested_action="social.romance"`, acknowledges dialogue,
then asserts `execute_sims_action` queues the romance tuning. Simulate natural completion with
before romance `0` and after romance `7`; assert `/action-result` contains only:

```python
{
    "path": "relationship.romance",
    "operation": "increment",
    "value": 7,
}
```

Add the equivalent zero-delta case and assert `changes == []`. Reuse the existing cancellation and
failed-factory tests for `social.mean` and assert no relationship consequence is reported.

- [ ] **Step 2: Run the script-mod tests and verify RED**

```powershell
Set-Location adapters/thesims4
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_mod_autonomy.py -k "social_tunings or social_romance or social_mean"
```

Expected: mapping tests from Task 2 pass, while execution/result tests fail until the held-session
path accepts the new common actions.

- [ ] **Step 3: Route common actions through the existing exact native executor**

Keep the Task 2 map and `find_action_affordance` exact-name based. Update only guards that still
assume the three legacy `AVAILABLE_ACTIONS` values so an acknowledged `social.*` action reaches the
existing executor. Do not add tuning substring scans, a second executor, or fallback to a different
category.

- [ ] **Step 4: Preserve the existing native execution authority**

Keep `continue_displayed_turn` behavior:

```python
    if action == "none":
        session.after_native_action(session.turn_id)
        return True
    session.phase = "running_native_action"
    execute_sims_action(...)
```

Keep `execute_sims_action` measuring only actual friendship/romance track differences after natural
completion. Remove UI rendering of model friendship/romance proposals. Display:

```python
details = "Emotion: {} | Category: {} | Tone: {} | Native action: {}".format(
    data.get("emotion", "neutral"),
    data.get("response_category", "friendly"),
    ", ".join(data.get("tone_tags") or []) or "neutral",
    data.get("suggested_action", "none"),
)
```

Show only `Empneon trust {:+d}` when nonzero. Native friendship/romance remain visible through
`ai.relationship` and confirmed action diagnostics.

- [ ] **Step 5: Update HTTP simulation expectations**

Change the player chat request fixture to advertise the five response categories and both directed
relationships. Change provider response fixtures to `response_category`, `tone_tags`, and
`trust_delta`; assert returned `suggested_action` is the derived `social.*` token and no model
friendship/romance delta exists.

- [ ] **Step 6: Run the complete Sims suite**

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests
```

Expected: PASS.

- [ ] **Step 7: Update Test 5 documentation**

Add this exact live matrix to `in-game-core-feature-test-plan.md`:

```markdown
| Incoming message | Expected incoming category | Acceptable response categories |
|---|---|---|
| “How was your day?” | `friendly` | any state-grounded category |
| “Tell me a joke.” | `funny` | any state-grounded category |
| “Would you go on a date with me?” | `romance` | any state-grounded category |
| “I hate you. Go away.” | `mean` | any state-grounded category |
| “Let's prank another Sim.” | `mischief` | any state-grounded category |
```

For each row capture both actor snapshots, incoming/response category, tone tags, common action,
exact native tuning, action finish result, and before/after relationship values. State explicitly
that the response category may differ from the input and a native zero delta is valid.

In `in-game-core-feature-test-results.md`, record automated completion but keep Test 5 `PARTIAL`
until all five native mappings are observed in the game. Do not claim live relationship changes from
unit tests.

- [ ] **Step 8: Run the complete repository verification gate**

Run each suite from its supported working directory:

```powershell
Set-Location core
$env:PYTHONPATH='src'; py -3.12 -m pytest -q -p no:cacheprovider tests

Set-Location ../adapters/thesims4
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests

Set-Location ../godot
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests

Set-Location ../..
$env:PYTHONPATH='core\src;adapters\thesims4\src;adapters\godot\src'; py -3.12 -m pytest -q -p no:cacheprovider tests
$env:PYTHONPATH='.'; py -3.12 -m pytest -q -p no:cacheprovider scripts/test_release.py
py -3.12 -m ruff check --select E9,F63,F7,F82 core/src core/tests adapters/thesims4/src adapters/thesims4/tests adapters/thesims4/backend adapters/thesims4/ts4script adapters/godot/src adapters/godot/tests tests scripts
py -3.12 -m mypy core/src adapters/thesims4/src adapters/godot/src
py -3.12 -m py_compile adapters/thesims4/backend/ai_sims_server.py adapters/thesims4/backend/empneon_state.py adapters/thesims4/src/empneon_thesims4/adapter.py
git diff --check
```

Expected: every command exits `0`.

- [ ] **Step 9: Build and hash the Sims artifacts**

```powershell
Set-Location adapters/thesims4
py -3.12 .\build_mod.py
Get-FileHash .\dist\Empneon_TheSims4.ts4script -Algorithm SHA256
Get-FileHash .\dist\Empneon_TheSims4.package -Algorithm SHA256
```

Expected: both artifacts build with non-empty SHA-256 hashes; the script builder uses Python 3.7
bytecode.

- [ ] **Step 10: Verify exact tunings and run the live matrix**

After installing the source build, run:

```text
ai.tunings AskAboutDay
ai.tunings TellJoke
ai.tunings ComplimentAppearance
ai.tunings Insult
ai.tunings LieAboutCareer
```

Expected output includes each exact constant from Step 1. If the current game build does not expose
one exact name, stop the live test and report that category as unavailable; do not substitute a
different category or claim the five-category requirement is complete.

Run the five Test 5 messages. For a reciprocated romance response, verify category `romance`, common
action `social.romance`, native `ComplimentAppearance`, and an observed game result. The result may
be a positive, negative, or zero romance change. Repeat one case with cancellation and verify no late
action or state effect.

- [ ] **Step 11: Commit locally without pushing**

```powershell
Set-Location ../..
git add adapters/thesims4/ts4script/ai_sims_agent.py adapters/thesims4/tests/test_sims4_mod_autonomy.py adapters/thesims4/tests/test_http_simulation.py adapters/thesims4/docs/in-game-core-feature-test-plan.md adapters/thesims4/docs/in-game-core-feature-test-results.md
git commit -m "feat(sims4): execute five native social categories"
git status --short
```

Expected: only the known SQLite `-wal` and `-shm` sidecars remain untracked. Do not run `git push`.

---

## Final Self-Review Checklist

- [ ] Every approved requirement maps to a task: five common categories, separate incoming/response category, mixed tone tags, both actor states, derived action, exact Sims mapping, automatic post-delivery execution, game-owned outcomes, compatibility, failures, and non-Sims portability.
- [ ] Friendship, romance, and attraction are never model-authored state changes.
- [ ] `response_category`, `tone_tags`, `trust_delta`, `social.<category>`, `available_response_categories`, and `listener_relationship` use the same names in every task.
- [ ] No new database table, migration, provider registry, multi-action chain, or tuning-name heuristic is introduced.
- [ ] The plan contains no placeholder instructions.
- [ ] No command pushes changes.
