# Sims 4 Semantic Memory Selector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Execution status:** Implemented; date and non-date paraphrase recall live-passed.

**Goal:** Select relevant shared Sims memories through one bounded LM Studio request so paraphrased
questions retrieve supporting history without growing the main dialogue prompt indefinitely.

**Architecture:** The existing episodic store supplies a pair-scoped, 6,000-character candidate
list. A small-model request selects up to three short request-local memory IDs, which are validated,
mapped to stored event IDs locally, and passed through the existing recalled-history prompt path.
Current deterministic retrieval remains the fallback for empty, malformed, invalid, or failed
selector results.

**Tech Stack:** Python 3.12 tests, Python 3.7-compatible Sims backend code, SQLite episodic memory,
LM Studio native chat through the existing provider router, pytest.

## Global Constraints

- Candidate JSON must never exceed 6,000 characters.
- Return at most three memories and accept only IDs from the candidate list.
- Memory candidates must be confirmed interactions observed by the requested Sim pair.
- Prefer attributed facts for factual recall; unsupported prior recall answers are not evidence.
- Do not add an embedding model, stateful LM Studio chat, attached files, or a database migration.
- Do not commit or push until the user explicitly requests it.

---

### Task 1: Build a bounded pair-scoped candidate list

**Files:**
- Modify: `adapters/thesims4/backend/empneon_state.py`
- Test: `adapters/thesims4/tests/test_sims4_backend.py`

**Interfaces:**
- Consumes: `EpisodicMemoryStore`, `_event_data()`, `_recall_terms()`
- Produces: `recall_candidates(conn, actor_id, other_id, query, max_chars=6000) -> list[dict[str, object]]`

- [ ] **Step 1: Write the failing pair-isolation and priority test**

Add a test that records:

```python
def _record_confirmed_interaction(
    conn,
    event_id,
    speaker_id,
    listener_id,
    message,
    dialogue,
    facts,
    happened_at,
):
    ai_sims_server.empneon_state.record_observed_event(
        conn,
        Event(
            json.dumps(
                {
                    "kind": "confirmed_interaction",
                    "conversation_id": event_id,
                    "speaker_id": speaker_id,
                    "listener_id": listener_id,
                    "message": message,
                    "dialogue": dialogue,
                    "facts": facts,
                }
            ),
            [speaker_id, listener_id],
            happened_at=happened_at,
            id=event_id,
        ),
        {speaker_id: message, listener_id: message},
    )


def test_recall_candidates_are_pair_scoped_and_prioritized(tmp_path) -> None:
    database = str(tmp_path / "core.sqlite3")
    with open_db(database) as conn:
        _record_confirmed_interaction(
            conn,
            "old-match",
            "karmine",
            "bernard",
            "The garden key is beneath the blue bench.",
            "I will remember that.",
            [{"actor_id": "bernard", "statement": "The garden key is beneath the blue bench."}],
            happened_at=1,
        )
        _record_confirmed_interaction(
            conn,
            "other-pair",
            "karmine",
            "agnes",
            "The garden key is in the kitchen.",
            "Understood.",
            [{"actor_id": "agnes", "statement": "The garden key is in the kitchen."}],
            happened_at=2,
        )
        _record_confirmed_interaction(
            conn,
            "recent-fact",
            "karmine",
            "bernard",
            "I prefer red roses.",
            "That is thoughtful.",
            [{"actor_id": "bernard", "statement": "I prefer red roses."}],
            happened_at=3,
        )

        candidates = ai_sims_server.empneon_state.recall_candidates(
            conn,
            "karmine",
            "bernard",
            "Where is the garden key?",
        )

    assert candidates[0]["event_id"] == "old-match"
    assert {item["event_id"] for item in candidates} == {"old-match", "recent-fact"}
```

Keep this helper local to `test_sims4_backend.py`; production code must not expose test setup.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "recall_candidates_are_pair_scoped"
```

Expected: FAIL because `recall_candidates` does not exist.

- [ ] **Step 3: Implement candidate collection**

Add `recall_candidates()` next to `recalled_memories()`:

```python
def recall_candidates(
    conn: sqlite3.Connection,
    actor_id: str,
    other_id: str,
    query: str,
    max_chars: int = 6000,
) -> list[dict[str, object]]:
    pair = {str(actor_id), str(other_id)}
    terms = _recall_terms(query)
    ranked = []
    for event in EpisodicMemoryStore(conn).get_for_agent(str(actor_id)):
        data = _event_data(event.description)
        if data.get("kind") != "confirmed_interaction":
            continue
        participants = {
            str(data.get("speaker_id") or ""),
            str(data.get("listener_id") or ""),
        }
        if participants != pair:
            continue
        facts = [fact for fact in data.get("facts") or [] if isinstance(fact, dict)]
        searchable = " ".join(
            (
                str(data.get("message") or ""),
                str(data.get("dialogue") or ""),
                *(str(fact.get("statement") or "") for fact in facts),
            )
        )
        overlap = len(terms & _recall_terms(searchable))
        candidate = {
            "event_id": event.id,
            "created_at": event.happened_at,
            "speaker_id": str(data.get("speaker_id") or ""),
            "listener_id": str(data.get("listener_id") or ""),
            "message": str(data.get("message") or ""),
            "dialogue": str(data.get("dialogue") or ""),
            "facts": facts,
        }
        ranked.append((bool(overlap), bool(facts), event.happened_at, candidate))
    ranked.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    selected = []
    for _overlap, _has_facts, _created_at, candidate in ranked:
        trial = json.dumps(selected + [candidate], ensure_ascii=True, sort_keys=True)
        if len(trial) > max(2, int(max_chars)):
            continue
        selected.append(candidate)
    return selected
```

This ranking puts lexical matches first, then fact-bearing memories, then recent exchanges, while
the serialized-size check enforces the exact budget.

- [ ] **Step 4: Add and run the fixed-budget test**

Create 100 long confirmed interactions for one pair, call `recall_candidates(..., max_chars=6000)`,
and assert:

```python
encoded = json.dumps(candidates, ensure_ascii=True, sort_keys=True)
assert len(encoded) <= 6000
assert candidates
```

Run both candidate tests. Expected: PASS.

- [ ] **Step 5: Run existing deterministic recall tests**

Run:

```powershell
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "recalled_memories or recall_candidates"
```

Expected: all selected tests PASS. Do not commit.

---

### Task 2: Select and validate semantic memory IDs

**Files:**
- Modify: `adapters/thesims4/backend/ai_sims_server.py`
- Test: `adapters/thesims4/tests/test_sims4_backend.py`

**Interfaces:**
- Consumes: candidate dictionaries from `recall_candidates()`, `llm_chat()`, `extract_json()`
- Produces: `select_recalled_memories(query, candidates) -> list[dict[str, object]]`

- [ ] **Step 1: Write the failing semantic-selection test**

```python
def test_semantic_selector_returns_only_selected_candidate_memories(monkeypatch) -> None:
    candidates = [
        {
            "event_id": "date-plan",
            "created_at": 1,
            "speaker_id": "karmine",
            "listener_id": "bernard",
            "message": "Tonight, 7pm, at my place.",
            "dialogue": "That sounds perfect.",
            "facts": [{"actor_id": "bernard", "statement": "Tonight, 7pm, at my place."}],
        },
        {
            "event_id": "roses",
            "created_at": 2,
            "speaker_id": "karmine",
            "listener_id": "bernard",
            "message": "I prefer red roses.",
            "dialogue": "I will remember.",
            "facts": [{"actor_id": "bernard", "statement": "I prefer red roses."}],
        },
    ]
    monkeypatch.setattr(
        ai_sims_server,
        "llm_chat",
        lambda *_args, **_kwargs: json.dumps({"event_ids": ["date-plan"]}),
    )

    selected = ai_sims_server.select_recalled_memories(
        "Can you tell the day and time we're going on a date?",
        candidates,
    )

    assert [item["event_id"] for item in selected] == ["date-plan"]
    assert selected[0]["explicit"] is True
```

- [ ] **Step 2: Run the focused test and verify RED**

Expected: FAIL because `select_recalled_memories` does not exist.

- [ ] **Step 3: Add the selector schema and prompt**

Define:

```python
MEMORY_SELECTOR_SCHEMA = {
    "type": "object",
    "properties": {
        "event_ids": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 3,
        }
    },
    "required": ["event_ids"],
}
```

Build a selector prompt that includes the current message and serialized candidates, and contains
these exact rules:

```text
Select zero to three event_ids that provide evidence relevant to the current message.
Match meaning, not exact wording.
Prefer attributed facts for plans, preferences, promises, identity, locations, and past events.
Use full exchanges only when the player asks what was said or how an interaction occurred.
A previous answer to a memory question without supporting facts is not authoritative evidence.
Return only candidate event_ids.
```

Call:

```python
content = llm_chat(
    [
        {"role": "system", "content": "Select relevant Sims memories. Return only valid JSON."},
        {"role": "user", "content": prompt},
    ],
    temperature=0,
    schema=MEMORY_SELECTOR_SCHEMA,
    schema_name="sims_memory_selector",
    task="small",
)
```

- [ ] **Step 4: Implement strict local result validation**

`select_recalled_memories()` must parse malformed model output as an empty selection while allowing
provider failures to propagate to the fallback wrapper:

```python
try:
    raw = extract_json(content)
except (ValueError, json.JSONDecodeError):
    return []
event_ids = raw.get("event_ids")
if not isinstance(event_ids, list) or len(event_ids) > 3:
    return []
if any(not isinstance(event_id, str) for event_id in event_ids):
    return []
if len(set(event_ids)) != len(event_ids):
    return []
by_id = {str(item["event_id"]): item for item in candidates}
if any(event_id not in by_id for event_id in event_ids):
    return []
return [dict(by_id[event_id], explicit=True) for event_id in event_ids]
```

- [ ] **Step 5: Verify GREEN**

Run the focused selector test. Expected: PASS.

- [ ] **Step 6: Add malformed-result parameter tests**

Parameterize these provider outputs and assert an empty result:

```python
[
    "not json",
    json.dumps({}),
    json.dumps({"event_ids": "date-plan"}),
    json.dumps({"event_ids": ["date-plan", "date-plan"]}),
    json.dumps({"event_ids": ["unknown"]}),
    json.dumps({"event_ids": ["a", "b", "c", "d"]}),
]
```

Expected: every case returns `[]` without exposing an untrusted ID.

- [ ] **Step 7: Run selector tests**

Expected: all semantic-selector tests PASS. Do not commit.

---

### Task 3: Integrate semantic selection with deterministic fallback

**Files:**
- Modify: `adapters/thesims4/backend/ai_sims_server.py`
- Test: `adapters/thesims4/tests/test_sims4_backend.py`

**Interfaces:**
- Consumes: `select_recalled_memories()`, deterministic `recalled_memories()`
- Produces: `semantic_recalled_memories(query, candidates, fallback) -> list[dict[str, object]]`
- Updates: `chat(payload)` recalled-history assembly

- [ ] **Step 1: Write the failing provider-failure fallback test**

```python
def test_semantic_recall_falls_back_when_selector_provider_fails(monkeypatch) -> None:
    fallback = [{"event_id": "fallback", "message": "I prefer roses.", "facts": []}]
    candidates = [{"event_id": "candidate", "message": "Tonight at seven.", "facts": []}]
    monkeypatch.setattr(
        ai_sims_server,
        "select_recalled_memories",
        lambda _query, _candidates: (_ for _ in ()).throw(
            ai_sims_server.ProviderError("selector failed")
        ),
    )

    recalled = ai_sims_server.semantic_recalled_memories(
        "What did I prefer?",
        candidates,
        fallback,
    )

    assert recalled == fallback
```

- [ ] **Step 2: Run the focused fallback test and verify RED**

Expected: FAIL because `semantic_recalled_memories` does not exist.

- [ ] **Step 3: Implement the fallback wrapper**

```python
def semantic_recalled_memories(query, candidates, fallback):
    if not candidates:
        return fallback
    try:
        selected = select_recalled_memories(query, candidates)
    except (ProviderError, ValueError, json.JSONDecodeError, OSError):
        PROVIDER_LOG.warning("semantic memory selection failed; using deterministic recall")
        return fallback
    return selected or fallback
```

- [ ] **Step 4: Verify GREEN and add empty/invalid selection coverage**

Assert both an empty valid selector result and an invalid selector result return the deterministic
fallback. Expected: PASS.

- [ ] **Step 5: Integrate into `chat()`**

Inside the existing database block, collect both paths:

```python
query = str(payload.get("message") or "")
with open_db(CORE_DB_PATH) as conn:
    deterministic_recalled = empneon_state.recalled_memories(
        conn, speaker_id, listener_id, query, limit=3
    )
    candidates = empneon_state.recall_candidates(
        conn, speaker_id, listener_id, query
    )
    conversation = empneon_state.recent_conversations(
        conn, speaker_id, listener_id, conversation_id, limit=6
    )
recalled = semantic_recalled_memories(
    query,
    candidates,
    deterministic_recalled,
)
```

The LM request occurs after leaving the database context so inference does not hold a SQLite
connection open.

- [ ] **Step 6: Add paraphrase integration tests for two scenarios**

Add a parameterized prompt-path test:

```python
@pytest.mark.parametrize(
    ("query", "selected_id", "supported_text", "unsupported_text"),
    [
        (
            "Can you tell the day and time we're going on a date?",
            "date-plan",
            "Tonight, 7pm, at my place.",
            "Next Saturday at the museum.",
        ),
        (
            "Any idea where I put the thing that opens the garden?",
            "garden-key",
            "The garden key is beneath the blue bench.",
            "The garden key is in the kitchen.",
        ),
    ],
)
def test_semantic_recall_exposes_only_selected_support(
    monkeypatch,
    query,
    selected_id,
    supported_text,
    unsupported_text,
) -> None:
    candidates = [
        {
            "event_id": "date-plan",
            "speaker_id": "karmine",
            "listener_id": "bernard",
            "message": "Tonight, 7pm, at my place.",
            "dialogue": "That sounds perfect.",
            "facts": [{"actor_id": "bernard", "statement": "Tonight, 7pm, at my place."}],
        },
        {
            "event_id": "unsupported-date",
            "speaker_id": "karmine",
            "listener_id": "bernard",
            "message": "When is our date?",
            "dialogue": "Next Saturday at the museum.",
            "facts": [],
        },
        {
            "event_id": "garden-key",
            "speaker_id": "karmine",
            "listener_id": "bernard",
            "message": "The garden key is beneath the blue bench.",
            "dialogue": "I will remember that.",
            "facts": [
                {
                    "actor_id": "bernard",
                    "statement": "The garden key is beneath the blue bench.",
                }
            ],
        },
        {
            "event_id": "unsupported-key",
            "speaker_id": "karmine",
            "listener_id": "bernard",
            "message": "Where is the garden key?",
            "dialogue": "The garden key is in the kitchen.",
            "facts": [],
        },
    ]
    monkeypatch.setattr(
        ai_sims_server,
        "select_recalled_memories",
        lambda _query, items: [
            dict(
                next(item for item in items if item["event_id"] == selected_id),
                explicit=True,
            )
        ],
    )
    selected = ai_sims_server.semantic_recalled_memories(query, candidates, [])
    context = ai_sims_server.build_context(
        {"speaker": {}, "listener": {}, "message": query},
        {"name": "Karmine"},
        {"name": "Bernard"},
        {},
        {},
        selected,
    )
    context.update(
        conversation=[],
        speaker_id="karmine",
        listener_id="bernard",
    )

    prompt = ai_sims_server.build_chat_prompt({"message": query}, context)

    assert supported_text in prompt
    assert unsupported_text not in prompt
```

The two cases demonstrate that the prompt path is scenario-independent and that unsupported later
recall replies do not enter the main generation context.

- [ ] **Step 7: Run all recall, prompt, and chat integration tests**

Run:

```powershell
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "recall or memory_selector or actor_prompt or semantic"
```

Expected: all selected tests PASS. Do not commit.

---

### Task 4: Verify compatibility and update feature status

**Files:**
- Modify: `docs/superpowers/specs/2026-07-23-sims4-semantic-memory-selector-design.md`
- Verify: `adapters/thesims4/backend/empneon_state.py`
- Verify: `adapters/thesims4/backend/ai_sims_server.py`
- Verify: `adapters/thesims4/tests/test_sims4_backend.py`

**Interfaces:**
- Consumes: completed selector implementation
- Produces: verified uncommitted working tree ready for in-game testing

- [ ] **Step 1: Run the complete Sims 4 adapter suite**

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests
```

Expected: all tests PASS with zero failures.

- [ ] **Step 2: Run source compatibility and diff checks**

```powershell
py -3.12 -m py_compile backend/ai_sims_server.py backend/empneon_state.py
git diff --check
git status --short
```

Expected: compilation succeeds, `git diff --check` prints nothing, and only intended uncommitted
files appear.

- [ ] **Step 3: Update the design status**

Change the design status to:

```markdown
**Status:** Implemented and automated tests passing; in-game validation pending
```

Add the final test count and explicitly list these manual tests:

```text
When is our date?
Hey, baby. When are we going on a date?
Can you tell the day and time we're going on a date?
Any idea where I put the thing that opens the garden?
```

- [ ] **Step 4: Restart and validate**

Restart the backend only. Keep The Sims 4 running. Verify the first three questions recall tonight
at 7pm at Bernard's place and the fourth recalls the stored garden-key location.

- [ ] **Step 5: Report without committing**

Report automated results, files changed, backend restart requirement, and any remaining in-game
observations. Do not commit or push until explicitly requested.

## Execution notes

The configured Gemma model initially copied candidate JSON and later shortened UUID event IDs. The
implemented protocol therefore uses compact labeled candidate text and request-local IDs (`m1`,
`m2`, and so on), then maps them back to stored events locally. If selected evidence contains
attributed facts, selected no-fact recall answers are discarded. This refinement passed a direct
LM Studio check against the Bernard/Karmine database and all 200 Sims 4 adapter tests.

The first in-game paraphrase retest selected the correct `Tonight at 7 pm at your place` plan for
`Hey, baby. When are we going on a date?`. The main dialogue then repeated the stored acceptance
response verbatim. The selector task is complete; the next session should change response synthesis
so selected exchanges ground a fresh answer rather than becoming copyable answer text, then retest
both date and unrelated memory scenarios.

July 24 closeout: subsequent recall-integrity work produced fresh attributed date responses across
save/reload. The informed Sim then retrieved `under the blue bench` from `Where is the garden code
item?` before and after backend restart, while the uninformed Sim disclosed no private location.
The selector's date and non-date live acceptance is complete.
