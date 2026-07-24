# Attributed Recall and Provider Usage Implementation Plan

**Status:** Completed; checklist retained as the original execution record

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve actor attribution through recall correction and fallback, prevent recall answers from becoming authoritative facts, and record completed semantic-selection provider usage.

**Architecture:** Keep recalled evidence as existing `actor_id`/`statement` dictionaries until its final consumer. Apply one provenance rule at confirmed-memory creation and retrieval so responder answers to recall questions remain conversation history rather than facts. Reuse the existing provider `GenerationResult` collector and `UsageStore` for selector telemetry without changing provider transports or the database schema.

**Tech Stack:** Python 3.12, Python 3.7-compatible Sims source, SQLite, pytest

## Global Constraints

- Remain independent of every game, provider, model, and natural language.
- Do not perform language-specific first-/second-person pronoun rewriting.
- Preserve grounded-over-factless recall precedence, grounded semantic recall, and legacy factless semantic recall.
- Preserve candidate limits, pair privacy, confirmation gating, save/reload behavior, structured-output schemas, categories, relationships, and animation.
- Preserve fresh model dialogue whenever validation succeeds.
- Do not mutate or delete existing live database rows.
- Do not persist raw prompts or provider responses.
- Add no dependency or database migration.
- Do not commit or push until explicitly requested.

---

## File Structure

- Modify `adapters/thesims4/backend/ai_sims_server.py`: retain structured supported facts, render attributed retry/fallback evidence, and collect selector generation metadata.
- Modify `adapters/thesims4/backend/empneon_state.py`: identify recall questions once, suppress new responder-derived recall facts, and filter legacy responder-derived recall facts during retrieval.
- Modify `adapters/thesims4/tests/test_sims4_backend.py`: add live-shaped regression, persistence, compatibility, and telemetry coverage.
- Modify `adapters/thesims4/docs/in-game-core-feature-test-plan.md`: update Test 5's current live-retest instruction.
- Modify `adapters/thesims4/docs/in-game-core-feature-test-results.md`: record the role-attribution failure, missing selector telemetry, repair, and verification.

### Task 1: Preserve attribution through validation, retry, and fallback

**Files:**
- Modify: `adapters/thesims4/backend/ai_sims_server.py:2003-2138`
- Modify: `adapters/thesims4/backend/ai_sims_server.py:2275-2343`
- Test: `adapters/thesims4/tests/test_sims4_backend.py:1280-1376`

**Interfaces:**
- Consumes: recalled fact dictionaries containing `actor_id` and `statement`
- Produces: `_supported_recall_facts(message, context) -> list[dict]`, `_attributed_fact_text(fact, context) -> str`, and `_recalled_fact_dialogue(fact, context) -> str`

- [x] **Step 1: Strengthen the retry test with actor attribution**

Update `test_supported_recall_retries_ignored_fact_when_rejection_is_disabled` so its final assertions are:

```python
    correction = calls[1][1]["content"]
    assert len(calls) == 2
    assert response["dialogue"] == corrected
    assert "Bernard said: Tonight, 7pm, at my place." in correction
```

This test catches a correction prompt that retains the statement but discards its actor.

- [x] **Step 2: Strengthen repeated- and failed-provider fallback tests**

Replace the loose time-only assertions in
`test_supported_recall_uses_fact_after_failed_retry` with:

```python
    assert len(calls) == 2
    assert response["dialogue"] == (
        'You told me: "Tonight, 7pm, at my place."'
    )
    assert response["intent"] == "recall"
```

Replace the loose assertions in
`test_supported_recall_uses_fact_when_provider_fails` with:

```python
    assert response["dialogue"] == (
        'You told me: "Tonight, 7pm, at my place."'
    )
    assert response["intent"] == "recall"
```

These assertions independently derive the required perspective from the live
fact's `actor_id=bernard` and the current `listener_id=bernard`.

- [x] **Step 3: Run the live-shaped tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "supported_recall"
```

Expected: the retry test fails because the correction contains the bare
statement, and both fallback tests fail because the current fallback returns
the statement as Karmine's own dialogue.

- [x] **Step 4: Keep supported evidence structured**

Change `_supported_recall_facts()` to retain normalized fact dictionaries:

```python
def _supported_recall_facts(message, context):
    cue = _recall_question_cue(message)
    if not cue:
        return []
    facts = [
        {
            "actor_id": str(fact.get("actor_id") or ""),
            "statement": str(fact.get("statement") or "").strip(),
        }
        for memory in context.get("recalled_memories") or []
        for fact in memory.get("facts") or []
        if isinstance(fact, dict)
        and str(fact.get("statement") or "").strip()
    ]
    if cue == "when":
        return [
            fact
            for fact in facts
            if empneon_state.TIME_FACT_CUE.search(fact["statement"])
        ]
    question_terms = set(_dialogue_words(message, context))
    return [
        fact
        for fact in facts
        if question_terms
        & set(_dialogue_words(fact["statement"], context))
    ]
```

In `_supported_recall_issue()`, derive statements only where text processing
requires them:

```python
    statements = [fact["statement"] for fact in facts]
```

Use `statements` for time extraction and answer-term comparison. Keep
`_memory_supports_question()` unchanged because it only tests whether the
structured list is empty.

- [x] **Step 5: Add provider-neutral attribution renderers**

Add immediately after `_supported_recall_facts()`:

```python
def _attributed_fact_text(fact, context):
    actor_id = str(fact.get("actor_id") or "")
    names = {
        context.get("speaker_id"): context["speaker"].get("name") or "Unknown actor",
        context.get("listener_id"): context["listener"].get("name") or "Unknown actor",
    }
    actor = names.get(actor_id, actor_id or "Unknown actor")
    return "{} said: {}".format(actor, fact["statement"])


def _recalled_fact_dialogue(fact, context):
    actor_id = str(fact.get("actor_id") or "")
    statement = fact["statement"]
    if actor_id == context.get("listener_id"):
        return 'You told me: "{}"'.format(statement)
    if actor_id == context.get("speaker_id"):
        return 'I remember saying: "{}"'.format(statement)
    names = {
        context.get("speaker_id"): context["speaker"].get("name") or "",
        context.get("listener_id"): context["listener"].get("name") or "",
    }
    actor = names.get(actor_id, actor_id)
    if actor:
        return '{} said: "{}"'.format(actor, statement)
    return 'I remember this: "{}"'.format(statement)
```

These renderers quote rather than rewrite the statement, so they work with any
language and provider.

- [x] **Step 6: Use attribution in fallback and correction**

In the supported-fact branch of `reasoning_fallback_response()`, replace the
candidate-string selection with:

```python
        dialogue = _recalled_fact_dialogue(supported_facts[0], context)
```

In `HermesRuntime.dialogue()`, replace the bare correction join with:

```python
                    "\nCorrection: Answer the recall question using this "
                    "attributed evidence: "
                    + " | ".join(
                        _attributed_fact_text(fact, context)
                        for fact in supported_facts
                    )
```

- [x] **Step 7: Run the focused tests and verify GREEN**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "supported_recall"
```

Expected: every supported-recall test passes.

### Task 2: Prevent recall answers from becoming authoritative facts

**Files:**
- Modify: `adapters/thesims4/backend/empneon_state.py:560-760`
- Test: `adapters/thesims4/tests/test_sims4_backend.py:690-850`

**Interfaces:**
- Consumes: confirmed-interaction dictionaries with `message`, `speaker_id`, and `facts`
- Produces: `_is_recall_question(text) -> bool` and `_authoritative_facts(data) -> list[dict]`

- [x] **Step 1: Add a failing legacy-contamination retrieval test**

Add:

```python
def test_recall_ignores_responder_fact_derived_from_prior_recall(tmp_path) -> None:
    database = str(tmp_path / "core.sqlite3")
    original = {
        "kind": "confirmed_interaction",
        "conversation_id": "date-plan",
        "speaker_id": "karmine",
        "listener_id": "bernard",
        "message": "Tonight, 7pm, at my place.",
        "dialogue": "That sounds perfect.",
        "facts": [
            {
                "actor_id": "bernard",
                "statement": "Tonight, 7pm, at my place.",
            }
        ],
    }
    derivative = {
        "kind": "confirmed_interaction",
        "conversation_id": "date-recall",
        "speaker_id": "karmine",
        "listener_id": "bernard",
        "message": "When is our date?",
        "dialogue": "Tonight, 7pm, at my place.",
        "facts": [
            {
                "actor_id": "karmine",
                "statement": "Tonight, 7pm, at my place.",
            }
        ],
    }
    with open_db(database) as conn:
        for event_id, happened_at, payload in (
            ("original", 1, original),
            ("derivative", 2, derivative),
        ):
            ai_sims_server.empneon_state.record_observed_event(
                conn,
                Event(
                    json.dumps(payload),
                    ["karmine", "bernard"],
                    happened_at=happened_at,
                    id=event_id,
                ),
                {"karmine": payload["dialogue"], "bernard": payload["message"]},
            )
        recalled = ai_sims_server.empneon_state.recalled_memories(
            conn, "karmine", "bernard", "When is our date?"
        )
        candidates = ai_sims_server.empneon_state.recall_candidates(
            conn, "karmine", "bernard", "When is our date?"
        )

    recalled_facts = [
        fact for memory in recalled for fact in memory["facts"]
    ]
    candidate_facts = [
        fact for memory in candidates for fact in memory["facts"]
    ]
    expected = {
        "actor_id": "bernard",
        "statement": "Tonight, 7pm, at my place.",
    }
    assert expected in recalled_facts
    assert expected in candidate_facts
    assert all(fact["actor_id"] != "karmine" for fact in recalled_facts)
    assert all(fact["actor_id"] != "karmine" for fact in candidate_facts)
    assert any(memory["event_id"] == "derivative" for memory in candidates)
```

The final assertion proves the legacy exchange remains conversational history
while its derivative fact loses authority.

- [x] **Step 2: Add a failing confirmation test**

Add an integration test beside
`test_displayed_dialogue_archives_attributed_durable_facts`:

```python
def test_displayed_recall_does_not_archive_responder_fact(
    tmp_path, monkeypatch
) -> None:
    database = str(tmp_path / "core.sqlite3")
    monkeypatch.setattr(ai_sims_server, "CORE_DB_PATH", database)
    monkeypatch.setattr(ai_sims_server, "DB_PATH", database)
    monkeypatch.setattr(ai_sims_server, "RESPONSE_REJECTION_ENABLED", False)
    response = _social_provider_response(
        "Tonight, 7pm, at my place. Does it sound good? "
        "I promise I'll make you feel in heaven.",
        "friendly",
    )
    monkeypatch.setattr(
        ai_sims_server,
        "llm_chat",
        lambda *_args, **_kwargs: json.dumps(response),
    )
    proposal = ai_sims_server.chat(
        {
            "speaker": {"id": "karmine", "name": "Karmine"},
            "listener": {"id": "bernard", "name": "Bernard"},
            "conversation_id": "recall-facts",
            "message": "What was it? I promise our date is tonight.",
            "event": {"type": "player_conversation", "source": "test"},
            "available_response_categories": ["friendly"],
        }
    )

    ai_sims_server.confirm_dialogue_delivery(
        {"decision_id": proposal["decision_id"], "status": "displayed"}
    )

    with open_db(database) as conn:
        confirmed = [
            json.loads(item.description)
            for item in EpisodicMemoryStore(conn).get_for_agent("karmine")
            if json.loads(item.description).get("kind")
            == "confirmed_interaction"
        ]

    assert confirmed[0]["facts"] == [
        {
            "actor_id": "bernard",
            "statement": "What was it? I promise our date is tonight.",
        }
    ]
```

This proves a player assertion remains eligible while the responder's
time-bearing recall dialogue is not promoted.

- [x] **Step 3: Run the two tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "derived_from_prior_recall or displayed_recall"
```

Expected: the legacy test exposes the Karmine-attributed fact, and the
confirmation test archives a responder fact.

- [x] **Step 4: Centralize the provenance rule**

Add after `_durable_fact()`:

```python
def _is_recall_question(text: str) -> bool:
    value = str(text or "")
    return bool(
        _RECALL_CUE.search(value)
        or (
            "?" in value
            and re.search(r"\b(?:what|when|where|who)\b", value, re.IGNORECASE)
        )
    )


def _authoritative_facts(data: dict[str, object]) -> list[dict[str, object]]:
    speaker_id = str(data.get("speaker_id") or "")
    recall_answer = _is_recall_question(str(data.get("message") or ""))
    return [
        fact
        for fact in data.get("facts") or []
        if isinstance(fact, dict)
        and not (
            recall_answer
            and str(fact.get("actor_id") or "") == speaker_id
        )
    ]
```

Use `_is_recall_question(query_text)` for the existing `explicit` decision in
`recalled_memories()`.

Replace direct `data.get("facts")` filtering in both `recall_candidates()` and
`recalled_memories()` with `_authoritative_facts(data)`.

- [x] **Step 5: Stop creating new responder-derived recall facts**

In `record_delivered_experience()`, compute:

```python
    dialogue_fact = (
        None
        if _is_recall_question(message)
        else _durable_fact(proposal.decision.actor_id, dialogue)
    )
```

Then build `facts` from the existing player-message fact and
`dialogue_fact`. Do not change the stored dialogue, summary, participants, or
observations.

- [x] **Step 6: Run the focused tests and verify GREEN**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "derived_from_prior_recall or displayed_recall or displayed_dialogue_archives"
```

Expected: all selected tests pass.

- [x] **Step 7: Protect non-question remembrance statements**

Add and run
`test_non_question_remembrance_keeps_responder_fact`, which stores
`I remember our old date.` as the incoming statement and
`I prefer red roses.` as Karmine's attributed fact. Assert that
`recall_candidates()` retains the Karmine fact. Require an actual `?` before
the provenance filter treats an exchange as a recall question, while leaving
the broader existing explicit-recall selection rule unchanged.

### Task 3: Record semantic-selector provider usage

**Files:**
- Modify: `adapters/thesims4/backend/ai_sims_server.py:2380-2538`
- Test: `adapters/thesims4/tests/test_sims4_backend.py:3120-3250`

**Interfaces:**
- Consumes: existing `(task, config, GenerationResult)` tuples appended by `llm_chat()`
- Produces: one `cognition_usage` record for every completed selector or dialogue generation

- [x] **Step 1: Add the failing usage integration test**

Add:

```python
def test_player_dialogue_records_selector_and_generation_usage(
    tmp_path, monkeypatch
) -> None:
    dialogue = _social_provider_response(
        "Tonight at 7 pm, at your place. I'm looking forward to it.",
        "romance",
    )

    class Provider:
        capabilities = ModelCapabilities(structured_output=True, local=True)

    class Router:
        def config_for(self, task):
            return {
                "name": "test",
                "model": "stub-" + task,
                "max_tokens": 300,
                "context_tokens": 4096,
                "latency_ms": 1000,
                "ram_mb": 64,
                "vram_mb": 0,
            }

        def provider_for(self, _task):
            return Provider()

        async def generate_result(
            self, task, _messages, *, schema=None, temperature=None
        ):
            del temperature
            if schema == ai_sims_server.MEMORY_SELECTOR_SCHEMA:
                return GenerationResult(
                    json.dumps({"event_ids": ["m1"]}), 5, 2, 7
                )
            return GenerationResult(json.dumps(dialogue), 20, 8, 30)

    database = str(tmp_path / "core.sqlite3")
    monkeypatch.setattr(ai_sims_server, "provider_router", lambda: Router())
    monkeypatch.setattr(ai_sims_server, "CORE_DB_PATH", database)
    monkeypatch.setattr(ai_sims_server, "DB_PATH", database)
    with open_db(database) as conn:
        payload = {
            "kind": "confirmed_interaction",
            "conversation_id": "original",
            "speaker_id": "karmine",
            "listener_id": "bernard",
            "message": "Tonight, 7pm, at my place.",
            "dialogue": "That sounds perfect.",
            "facts": [
                {
                    "actor_id": "bernard",
                    "statement": "Tonight, 7pm, at my place.",
                }
            ],
        }
        ai_sims_server.empneon_state.record_observed_event(
            conn,
            Event(
                json.dumps(payload),
                ["karmine", "bernard"],
                happened_at=1,
                id="date-plan",
            ),
            {"karmine": payload["dialogue"], "bernard": payload["message"]},
        )

    result = ai_sims_server.chat(
        {
            "speaker": {"id": "karmine", "name": "Karmine"},
            "listener": {"id": "bernard", "name": "Bernard"},
            "conversation_id": "usage-recall",
            "message": "When is our date?",
            "event": {"type": "player_conversation", "source": "test"},
            "available_response_categories": ["friendly", "romance"],
        }
    )

    with open_db(database) as conn:
        telemetry = UsageStore(conn).telemetry("karmine")

    assert result["dialogue"] == dialogue["dialogue"]
    assert telemetry["attempts"] == 2
    assert telemetry["requests"] == 1
    assert telemetry["by_provider"] == {"test": 2}
    assert telemetry["by_clod"] == {"2": 1, "3": 1}
    assert telemetry["actual"] == {
        "prompt_tokens": 25,
        "completion_tokens": 10,
        "latency_ms": 37,
    }
    assert "Tonight at 7 pm" not in json.dumps(telemetry)
```

- [x] **Step 2: Run the usage test and verify RED**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py::test_player_dialogue_records_selector_and_generation_usage
```

Expected: telemetry contains only the large dialogue generation.

- [x] **Step 3: Collect the selector result with the existing mechanism**

In `chat()`, wrap only semantic selection:

```python
        GENERATION_CONTEXT.attempts = []
        try:
            recalled = semantic_recalled_memories(
                query,
                candidates,
                deterministic_recalled,
            )
        finally:
            generations = list(GENERATION_CONTEXT.attempts)
            GENERATION_CONTEXT.attempts = None
```

Remove the later `generations = []` initialization. The resolver continues
extending this list with dialogue attempts from its worker thread.

- [x] **Step 4: Record each result under its own task CLOD**

In the existing `for task, config, generation in generations` recording loop,
replace `int(selected["clod"])` with:

```python
                        {
                            "small": 2,
                            "large": 3,
                            "deep": 4,
                        }.get(task, int(selected["clod"])),
```

Do not change `UsageStore`, its schema, or its privacy boundary.

- [x] **Step 5: Run focused usage tests and verify GREEN**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "provider_usage or selector_and_generation_usage"
```

Expected: all selected usage tests pass; turns without recall candidates still
record only their dialogue generation.

### Task 4: Full verification and live-test handoff

**Files:**
- Modify: `adapters/thesims4/docs/in-game-core-feature-test-plan.md`
- Modify: `adapters/thesims4/docs/in-game-core-feature-test-results.md`

**Interfaces:**
- Consumes: Tasks 1-3 verified behavior
- Produces: final automated evidence and backend-only live-retest instructions

- [x] **Step 1: Run focused recall and telemetry coverage together**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "semantic_recall or supported_recall or derived_from_prior_recall or displayed_recall or provider_usage"
```

- [x] **Step 2: Run the complete Sims adapter suite and compile backend files**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests
py -3.12 -m py_compile backend/ai_sims_server.py backend/empneon_state.py
```

- [x] **Step 3: Run the complete Core suite**

Run:

```powershell
$env:PYTHONPATH='src'
py -3.12 -m pytest -q -p no:cacheprovider tests
```

- [x] **Step 4: Build the Sims source artifacts**

Run:

```powershell
py -3.12 .\build_mod.py
```

- [x] **Step 5: Update the test record**

Record:

- The exact Bernard question and Karmine's copied `my place` response.
- Original fact `f6924dff-63b3-4fbf-92b8-1305b1858168:confirmed` with
  Bernard attribution.
- Latest event `f7089e72-ea92-4d51-88a1-be19677b0ac9` and confirmed decision
  `3d817e92-fac7-477e-b23a-d337d5f002dc:confirmed`.
- Both rejected dialogue attempts and the deterministic fallback path.
- The legacy derivative Karmine fact being ignored without deleting its event.
- Selector plus dialogue usage accounting and the final automated counts.
- Backend-only retest: restart the source backend, ask the same question, then
  inspect `empneon.usage`. Do not reinstall the mod or recreate the invitation.

- [x] **Step 6: Review the uncommitted diff**

Run:

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors and only intended session changes. Do not
commit, push, install, or restart the game/backend.
