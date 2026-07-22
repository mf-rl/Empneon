# Actor-Isolated Conversation Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Isolate each actor's persona, keep working dialogue scoped to one Empneon Social, and selectively recall confirmed interactions across later conversations and saved-game reloads without injecting generic memory summaries.

**Architecture:** Reuse Core's persistent `AgentStore`, directed `RelationshipStore`, `EpisodicMemoryStore`, and `ObservationStore`. The Sims adapter carries a conversation ID through the existing generic event `facts`; confirmed events store exact dialogue plus attributed durable facts. Each prompt receives the responder profile, current state, the current conversation's six newest confirmed turns, and at most three high-precision recalled facts or episodes.

**Tech Stack:** Python 3.12, SQLite, Empneon Core memory/identity stores, The Sims 4 Python adapter, pytest

## Global Constraints

- Work directly on `main`; do not create a branch or worktree.
- Do not push any commit.
- Do not import Hermes Agent or add a dependency.
- Do not add provider-native thread/session state or one model process per actor.
- Keep Core's existing stores as the source of truth.
- Record dialogue as memory only after `/dialogue-result` confirms it was displayed.
- Keep working history to the newest six complete exchanges or the provider context budget, whichever is smaller.
- Never use a display name as an actor key.
- Preserve save-slot isolation through the existing Sims 4 memory checkpoint flow.

---

## File Map

- Modify `adapters/thesims4/src/empneon_thesims4/adapter.py`: carry the adapter-neutral `conversation_id` in `WorldEvent.facts`.
- Modify `adapters/thesims4/ts4script/ai_sims_agent.py`: attach the active `EmpneonConversationSession.id` to every interactive `/chat` request.
- Modify `adapters/thesims4/backend/empneon_state.py`: archive confirmed exchanges once, extract attributed durable facts, query current-session turns, and perform bounded high-precision recall.
- Modify `adapters/thesims4/backend/ai_sims_server.py`: assemble actor-isolated prompt context and remove unconditional summary/vector-memory injection.
- Modify `adapters/thesims4/tests/test_sims4_backend.py`: cover archive, recall, prompt isolation, persistence, and failure behavior.
- Modify `adapters/thesims4/tests/test_sims4_mod_autonomy.py`: cover propagation of the in-game conversation ID.

No new production file or database table is needed.

---

### Task 1: Carry and archive the conversation identity

**Files:**
- Modify: `adapters/thesims4/src/empneon_thesims4/adapter.py:186-235`
- Modify: `adapters/thesims4/ts4script/ai_sims_agent.py:1739-1763`
- Modify: `adapters/thesims4/backend/ai_sims_server.py:2280-2305`
- Modify: `adapters/thesims4/backend/empneon_state.py:472-525,564-605`
- Test: `adapters/thesims4/tests/test_sims4_backend.py`
- Test: `adapters/thesims4/tests/test_sims4_mod_autonomy.py`

**Interfaces:**
- Consumes: `payload["conversation_id"]: str`, `EmpneonConversationSession.id: str`, and existing confirmed `ActionProposal` records.
- Produces: `WorldEvent.facts["conversation_id"]: str`, confirmed event JSON containing `conversation_id`, and `recent_conversations(conn, actor_id, other_id, conversation_id, limit=6) -> list[dict[str, object]]`.

- [ ] **Step 1: Write failing adapter and mod tests**

Add tests proving that the generic event carries the ID and the mod sends its active session ID:

```python
def test_conversation_id_is_preserved_in_world_event() -> None:
    event = Sims4Adapter(
        {
            "speaker": {"id": "karmine"},
            "listener": {"id": "bernard"},
            "message": "Hello.",
            "conversation_id": "social-17",
        }
    ).observe()[0]

    assert event.facts["conversation_id"] == "social-17"
```

In `test_sims4_mod_autonomy.py`, run the worker synchronously so the posted payload is deterministic:

```python
class ImmediateThread:
    def __init__(self, target):
        self.target = target
        self.daemon = False

    def start(self):
        self.target()


posted = []
monkeypatch.setattr(agent.threading, "Thread", ImmediateThread)
monkeypatch.setattr(agent, "show_empneon_notification", lambda *_args: None)
monkeypatch.setattr(agent, "chat_payload_for_target", lambda *_args: {})
monkeypatch.setattr(
    agent,
    "post_json",
    lambda path, payload: posted.append((path, payload)) or {},
)
agent.submit_empneon_chat(session, "Hello.")

assert posted[0][0] == "/chat"
assert posted[0][1]["conversation_id"] == session.id
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run from `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py::test_conversation_id_is_preserved_in_world_event tests/test_sims4_mod_autonomy.py -k conversation_id
```

Expected: FAIL because neither payload path currently preserves `conversation_id`.

- [ ] **Step 3: Propagate the conversation ID**

Add the value to adapter facts without making it Sims-specific in Core:

```python
facts={
    "source": str(social_event_data.get("source") or "sims4"),
    "message": message,
    "conversation_id": str(self._payload.get("conversation_id") or ""),
}
```

This snippet shows the exact new key; retain every other existing entry in the `facts` mapping.

Add the active UI session ID before posting `/chat`:

```python
payload = chat_payload_for_target(
    actor,
    getattr(target, "sim_info", None),
    message,
    "pie_menu",
)
payload["conversation_id"] = session.id
```

Preserve it when `persist_core_event` serializes the pending source event:

```python
description = dumps(
    {
        "kind": "observed_interaction",
        "type": event.type,
        "source": event.facts.get("source") or "sims4",
        "conversation_id": str(event.facts.get("conversation_id") or ""),
        "message": message,
        "summary": message or event.type,
        "agent_state": dataclasses.asdict(event.agent_state) if event.agent_state else None,
    }
)
```

For non-interactive `/chat` callers, replace the participant-pair fallback in `chat` with a unique
one-turn ID so unrelated calls never share working memory:

```python
conversation_id = str(payload.get("conversation_id") or uuid.uuid4())
payload["conversation_id"] = conversation_id
```

- [ ] **Step 4: Write failing confirmed-session query tests**

Create three confirmed interaction events for the same pair: two identical exchanges in
`social-17` and one in `social-18`. Also create an `observed_interaction` source event. Assert that
only the two confirmed `social-17` turns are returned and both identical turns remain:

```python
turns = empneon_state.recent_conversations(
    conn, "karmine", "bernard", "social-17", limit=6
)

assert [turn["message"] for turn in turns] == ["Hello.", "Hello."]
assert all(turn["conversation_id"] == "social-17" for turn in turns)
```

- [ ] **Step 5: Run the session query test and verify failure**

Run from `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "recent_conversations and conversation_id"
```

Expected: FAIL because the current query selects both observed and confirmed events by pair only.

- [ ] **Step 6: Scope working memory to confirmed events and one conversation**

Replace `recent_conversations` with:

```python
def recent_conversations(
    conn: sqlite3.Connection,
    actor_id: str,
    other_id: str,
    conversation_id: str,
    limit: int = 6,
) -> list[dict[str, object]]:
    pair = {str(actor_id), str(other_id)}
    limit = max(0, int(limit))
    if limit == 0:
        return []
    rows = []
    for event in EpisodicMemoryStore(conn).get_for_agent(str(actor_id)):
        data = _event_data(event.description)
        if data.get("kind") != "confirmed_interaction":
            continue
        if str(data.get("conversation_id") or "") != str(conversation_id):
            continue
        if {str(data.get("speaker_id") or ""), str(data.get("listener_id") or "")} != pair:
            continue
        rows.append(
            {
                "conversation_id": str(conversation_id),
                "speaker_id": str(data.get("speaker_id") or ""),
                "listener_id": str(data.get("listener_id") or ""),
                "message": str(data.get("message") or ""),
                "dialogue": str(data.get("dialogue") or ""),
            }
        )
        if len(rows) >= limit:
            break
    rows.reverse()
    return rows
```

Copy `conversation_id` from the pending source event into the confirmed event payload in
`record_delivered_experience`:

```python
payload = {
    "kind": "confirmed_interaction",
    "conversation_id": str(source.get("conversation_id") or ""),
    "speaker_id": proposal.decision.actor_id,
    "listener_id": proposal.decision.target_id or "",
    "message": message,
    "dialogue": dialogue,
    "summary": " ".join(value for value in (message, dialogue) if value),
}
```

Delete the unused pre-confirmation `record_conversation` function and its unused
`save_conversation` wrapper. Do not write a second conversation event.

- [ ] **Step 7: Run focused tests and commit**

Run from `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "conversation_id or recent_conversations or dialogue_delivery" tests/test_sims4_mod_autonomy.py -k "conversation_id or submit_empneon_chat"
```

Expected: PASS.

```powershell
git add adapters/thesims4/src/empneon_thesims4/adapter.py adapters/thesims4/ts4script/ai_sims_agent.py adapters/thesims4/backend/ai_sims_server.py adapters/thesims4/backend/empneon_state.py adapters/thesims4/tests/test_sims4_backend.py adapters/thesims4/tests/test_sims4_mod_autonomy.py
git commit -m "feat(sims4): scope working memory to social session"
```

---

### Task 2: Store durable facts and perform selective recall

**Files:**
- Modify: `adapters/thesims4/backend/empneon_state.py:380-425,527-605,1032-1048`
- Test: `adapters/thesims4/tests/test_sims4_backend.py`

**Interfaces:**
- Consumes: confirmed interaction event JSON from Task 1.
- Produces: `_durable_fact(actor_id: str, text: str) -> dict[str, str] | None` and `recalled_memories(conn, actor_id, other_id, query, limit=3) -> list[dict[str, object]]`.

- [ ] **Step 1: Write failing durable-fact tests**

Add direct tests for high-precision extraction:

```python
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("I prefer red roses.", "I prefer red roses."),
        ("I promise I will call tomorrow.", "I promise I will call tomorrow."),
        ("My sister is named Nina.", "My sister is named Nina."),
        ("What a lovely name you have.", None),
        ("Can you tell me your name?", None),
    ],
)
def test_durable_fact_requires_a_personal_fact_cue(text, expected) -> None:
    fact = empneon_state._durable_fact("bernard", text)
    assert (fact or {}).get("statement") == expected
    if fact:
        assert fact["actor_id"] == "bernard"
```

- [ ] **Step 2: Run the extractor test and verify failure**

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k durable_fact
```

Expected: FAIL because `_durable_fact` does not exist.

- [ ] **Step 3: Implement the deterministic extractor**

Add a deliberately narrow cue matcher; the full exchange remains in episodic storage even when a
sentence is not promoted to a durable fact:

```python
_DURABLE_FACT_CUE = re.compile(
    r"\b(?:i am|i'm|i like|i love|i hate|i prefer|i want|i need|i promise|"
    r"my\s+[a-z][a-z -]{0,30}\s+is|we met|we are|we're)\b",
    re.IGNORECASE,
)


def _durable_fact(actor_id: str, text: str) -> dict[str, str] | None:
    statement = " ".join(str(text or "").split())
    if not statement or statement.endswith("?") or not _DURABLE_FACT_CUE.search(statement):
        return None
    return {"actor_id": str(actor_id), "statement": statement}
```

In `record_delivered_experience`, add attributed facts for both sides and deduplicate equal
`(actor_id, casefolded statement)` pairs before serializing:

```python
facts = [
    fact
    for fact in (
        _durable_fact(proposal.decision.target_id or "", message),
        _durable_fact(proposal.decision.actor_id, dialogue),
    )
    if fact is not None
]
payload["facts"] = list(
    {
        (fact["actor_id"], fact["statement"].casefold()): fact
        for fact in facts
    }.values()
)
```

Stop passing the old unattributed `_declarative_fact(message)` into `record_observed_event`; the
structured `facts` field is the semantic source for this feature. Keep old beliefs readable for
diagnostics, but do not inject them into prompts.

- [ ] **Step 4: Write failing recall tests**

Record confirmed events containing a rose preference, a promise, a prior name compliment, and an
unrelated pizza exchange. Assert:

```python
assert empneon_state.recalled_memories(
    conn, "karmine", "bernard", "I brought you red roses."
)[0]["facts"] == [
    {"actor_id": "bernard", "statement": "I prefer red roses."}
]

assert empneon_state.recalled_memories(
    conn, "karmine", "bernard", "Do you remember what I promised?"
)[0]["message"] == "I promise I will call tomorrow."

assert empneon_state.recalled_memories(
    conn, "karmine", "bernard", "What a lovely name you have."
) == []

assert empneon_state.recalled_memories(
    conn, "karmine", "agnes", "Do you remember my promise?"
) == []
```

Also create four matching episodes and assert `len(results) == 3`.

- [ ] **Step 5: Run recall tests and verify failure**

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k recalled_memories
```

Expected: FAIL because recall still uses broad vector results and has no fact gate.

- [ ] **Step 6: Implement bounded pair-scoped recall**

Use lexical evidence as the high-precision gate; do not use vector similarity alone:

```python
_RECALL_CUE = re.compile(
    r"\b(?:remember|recall|what did|when did|where did|who did|first time|last time)\b",
    re.IGNORECASE,
)
_RECALL_STOPWORDS = frozenset(
    "about again been conversation did does first from have interaction just know last like remember said tell that the them then they this time was were what when where which who will with would your".split()
)


def _recall_terms(text: str) -> set[str]:
    terms = set()
    for token in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", str(text).casefold()):
        if (len(token) < 4 and token != "met") or token in _RECALL_STOPWORDS:
            continue
        terms.add(token)
        if token == "meet":
            terms.add("met")
        if token.endswith("ed") and len(token) > 5:
            terms.update((token[:-1], token[:-2]))
    return terms


def recalled_memories(
    conn: sqlite3.Connection,
    actor_id: str,
    other_id: str,
    query: str,
    limit: int = 3,
) -> list[dict[str, object]]:
    pair = {str(actor_id), str(other_id)}
    terms = _recall_terms(query)
    explicit = bool(_RECALL_CUE.search(str(query)))
    matches = []
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
            [str(data.get("message") or ""), str(data.get("dialogue") or "")]
            if explicit
            else [str(fact.get("statement") or "") for fact in facts]
        )
        overlap = terms & _recall_terms(searchable)
        if explicit and not terms:
            overlap = {"history"}
        if not overlap:
            continue
        selected = dict(data)
        selected["event_id"] = event.id
        selected["created_at"] = event.happened_at
        selected["facts"] = [
            fact
            for fact in facts
            if terms & _recall_terms(str(fact.get("statement") or ""))
        ]
        matches.append((len(overlap), event.happened_at, selected))
    if re.search(r"\bfirst time\b", str(query), re.IGNORECASE):
        matches.sort(key=lambda item: item[1])
    elif re.search(r"\blast time\b", str(query), re.IGNORECASE):
        matches.sort(key=lambda item: item[1], reverse=True)
    else:
        matches.sort(key=lambda item: (item[0], item[1]), reverse=True)
    recalled = []
    seen_facts = set()
    for _score, _created_at, memory in matches:
        unique_facts = []
        for fact in memory["facts"]:
            key = (
                str(fact.get("actor_id") or ""),
                str(fact.get("statement") or "").casefold(),
            )
            if key in seen_facts:
                continue
            seen_facts.add(key)
            unique_facts.append(fact)
        memory["facts"] = unique_facts
        if explicit or unique_facts:
            recalled.append(memory)
        if len(recalled) >= max(0, min(3, int(limit))):
            break
    return recalled
```

- [ ] **Step 7: Run focused tests and commit**

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "durable_fact or recalled_memories or dialogue_delivery"
```

Expected: PASS.

```powershell
git add adapters/thesims4/backend/empneon_state.py adapters/thesims4/tests/test_sims4_backend.py
git commit -m "feat(sims4): add selective confirmed memory recall"
```

---

### Task 3: Build actor-isolated bounded prompts

**Files:**
- Modify: `adapters/thesims4/backend/ai_sims_server.py:847-960,1298-1470,1746-1810,1828-1842,2061-2090,2165-2185`
- Test: `adapters/thesims4/tests/test_sims4_backend.py`

**Interfaces:**
- Consumes: `recent_conversations(..., conversation_id, limit=6)` from Task 1 and `recalled_memories(..., limit=3)` from Task 2.
- Produces: context fields `conversation`, `recalled_memories`, `speaker_id`, and `listener_id`; no model-visible generic memory summary.

- [ ] **Step 1: Write failing prompt-boundary tests**

Add a prompt test with an actor profile, six current-session turns, one recalled fact, and an
unrelated archived phrase. Assert the exact boundaries:

```python
prompt = ai_sims_server.build_chat_prompt(payload, context)

assert "Speaker:\nKarmine Luna" in prompt
assert "Traits: romantic, self-assured" in prompt
assert "Bernard Jaeger said: I prefer red roses." in prompt
assert "Current Empneon Social:" in prompt
assert "Memory summary:" not in prompt
assert "Relevant memories:" not in prompt
assert "UNRELATED-PIZZA-ARCHIVE" not in prompt
```

Add a repeated-input test where two previous confirmed turns have the same message and assert both
different responses appear in the prompt. Add a second actor context and assert Karmine's traits,
facts, moodlets, and transcript do not appear in Luna's prompt. Update Karmine's traits on a second
request and assert the new profile replaces rather than appends to the old traits.

- [ ] **Step 2: Run prompt tests and verify failure**

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "prompt and (isolated or recalled or repeated)"
```

Expected: FAIL because the prompt currently contains summary plus broad memories and removes all
past turns matching the current normalized input.

- [ ] **Step 3: Replace unconditional memory context**

Change the last `build_context` parameter from `summary` to `recalled_memories`. In the existing
return literal, make this exact replacement and leave every other key and expression unchanged:

```diff
-        "memories": memories,
-        "summary": summary.get("summary", "") if isinstance(summary, dict) else "",
+        "recalled_memories": recalled_memories,
```

Format recalled facts with current participant names, falling back to stable IDs:

```python
def _recalled_memory_lines(context):
    names = {
        context["speaker_id"]: context["speaker"]["name"],
        context["listener_id"]: context["listener"]["name"],
    }
    lines = []
    for memory in context.get("recalled_memories") or []:
        facts = memory.get("facts") or []
        if facts:
            lines.extend(
                "- {} said: {}".format(
                    names.get(str(fact.get("actor_id") or ""), str(fact.get("actor_id") or "Actor")),
                    str(fact.get("statement") or ""),
                )
                for fact in facts
            )
        else:
            lines.append(
                "- {} said: {} / {} replied: {}".format(
                    names.get(str(memory.get("listener_id") or ""), "Listener"),
                    str(memory.get("message") or ""),
                    names.get(str(memory.get("speaker_id") or ""), "Speaker"),
                    str(memory.get("dialogue") or ""),
                )
            )
    return "\n".join(dict.fromkeys(lines)) or "- None recalled"
```

Bound the recent transcript against the selected model context. Preserve whole exchange pairs and
drop the oldest first:

```python
def _bounded_conversation(lines, max_chars):
    exchanges = [lines[index : index + 2] for index in range(0, len(lines), 2)]
    selected = []
    used = 0
    for exchange in reversed(exchanges):
        size = sum(len(line) + 1 for line in exchange)
        if selected and used + size > max(0, int(max_chars)):
            break
        if size > max(0, int(max_chars)):
            continue
        selected.append(exchange)
        used += size
    return "\n".join(line for exchange in reversed(selected) for line in exchange)
```

Build the template once with `Recent conversation: None yet`, reserve four characters per output
token, then rebuild it with `_bounded_conversation` using:

```python
prompt_limit = int(context.get("max_context_tokens", 4096)) * 4
completion_reserve = int(context.get("max_completion_tokens", 300)) * 4
conversation_chars = max(0, prompt_limit - completion_reserve - len(base_prompt))
```

Add both limits to `context` from `task_model_config("large")`. Test with a deliberately tiny
limit and assert the newest complete exchange is present while the oldest is absent.

Replace the two old prompt sections with one:

```text
Recalled long-term history:
{recalled_memories}

Current Empneon Social:
{recent_conversation}
```

Pass `recalled_memories=_recalled_memory_lines(context)` to the existing final `.format(...)`
call. Do not retain `summary=` or `memories=` format arguments.

Keep the existing grounding rule that historical claims require supplied evidence, but point it
to `Recalled long-term history` or the current social. Remove references to `Memory summary` and
`Relevant memories`.

Use one evidence renderer for fallback and grounding so both paths see exactly the same recalled
content:

```python
def _recalled_memory_text(context):
    parts = []
    for memory in context.get("recalled_memories") or []:
        parts.extend(
            (
                str(memory.get("message") or ""),
                str(memory.get("dialogue") or ""),
            )
        )
        parts.extend(
            str(fact.get("statement") or "")
            for fact in memory.get("facts") or []
            if isinstance(fact, dict)
        )
    return " ".join(part for part in parts if part)
```

Replace all reads of `context["summary"]` and `context["memories"]` in `_memory_supports_question` and
`reasoning_fallback_response` with `_recalled_memory_text(context)`. The unsupported-history
fallback remains uncertain when this text is empty.

Delete the current-message equality filter from the transcript loop. The current input has not
yet been confirmed, so filtering it is incorrect:

```python
for turn in context.get("conversation") or []:
    # existing speaker/listener display mapping and append logic
```

- [ ] **Step 4: Wire chat to session history and selective recall**

Replace `recent_memories(...)` and the concatenated summary in `chat` with:

```python
with open_db(CORE_DB_PATH) as conn:
    recalled = empneon_state.recalled_memories(
        conn, speaker_id, listener_id, payload.get("message") or "", limit=3
    )
    conversation = empneon_state.recent_conversations(
        conn, speaker_id, listener_id, conversation_id, limit=6
    )

context = build_context(
    payload,
    speaker_profile,
    listener_profile,
    relationship,
    emotions,
    recalled,
)
model_config = task_model_config("large")
context.update(
    conversation=conversation,
    speaker_id=speaker_id,
    listener_id=listener_id,
    max_context_tokens=int(model_config.get("context_tokens") or 4096),
    max_completion_tokens=int(model_config.get("max_tokens") or 300),
)
```

Use `novel=not conversation` for cognition priority. Remove the response-only
`memory_summary` calculation and field; it is not consumed by the mod and would preserve the old
misleading model-visible concept.

Delete `recent_memories`, `save_memory_summary`, and `maybe_summarize_memories`, which exist only
for the old chat prompt. Keep `memories_for_pair`, `_rank_memories`, and `memory_summary` for the
existing diagnostic `/memories` endpoint, and keep `memories_for_sim` for the separate Director
endpoint. Neither diagnostic path may feed ordinary `/chat` prompts.

- [ ] **Step 5: Update grounding and fallback tests**

Update all `build_context` calls to pass recalled-memory lists instead of `(memories, summary)`.
Keep the unsupported-history test, but provide no recalled items:

```python
context = ai_sims_server.build_context(
    payload,
    {"name": "Bella"},
    {"name": "Mortimer"},
    {},
    {},
    [],
)
```

Add one supported-history fallback test with a recalled exact episode and assert the fallback can
cite it. Keep the existing identity, role-confusion, social-category, attraction, and repetition
tests unchanged except for the new context signature.

- [ ] **Step 6: Run backend tests and commit**

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py
```

Expected: all backend tests PASS.

```powershell
git add adapters/thesims4/backend/ai_sims_server.py adapters/thesims4/tests/test_sims4_backend.py
git commit -m "fix(sims4): isolate actor prompt memory"
```

---

### Task 4: Verify persistence, failure safety, and full regression behavior

**Files:**
- Modify: `adapters/thesims4/tests/test_sims4_backend.py`
- Modify only if a failing integration test exposes a defect: `adapters/thesims4/backend/ai_sims_server.py`
- Modify only if a failing integration test exposes a defect: `adapters/thesims4/backend/empneon_state.py`

**Interfaces:**
- Consumes: completed Task 1-3 behavior and existing `start_memory_session` / `save_memory_session` checkpoint functions.
- Produces: end-to-end proof that confirmed actor memory survives reload while save slots, failed proposals, and personalities remain isolated.

- [ ] **Step 1: Write the save/reload integration test**

Use a temporary active database and the existing session checkpoint API:

```python
def test_confirmed_actor_memory_survives_save_slot_reload(tmp_path, monkeypatch) -> None:
    database = str(tmp_path / "memory.sqlite3")
    monkeypatch.setattr(ai_sims_server, "CORE_DB_PATH", database)
    monkeypatch.setattr(ai_sims_server, "DB_PATH", database)
    monkeypatch.setattr(ai_sims_server, "ACTIVE_DB_PATH", database)
    monkeypatch.setattr(ai_sims_server, "PRESERVE_MEMORY_ONLY_ON_GAME_SAVE", True)

    ai_sims_server.start_memory_session("game-a", "slot-7")
    proposal = ai_sims_server.chat(
        {
            "speaker": {"id": "karmine", "name": "Karmine Luna"},
            "listener": {"id": "bernard", "name": "Bernard Jaeger"},
            "conversation_id": "social-a",
            "message": "I prefer red roses.",
            "event": {"type": "player_conversation", "source": "test"},
            "available_response_categories": [],
        }
    )
    ai_sims_server.confirm_dialogue_delivery(
        {"decision_id": proposal["decision_id"], "status": "displayed"}
    )
    ai_sims_server.save_memory_session("game-a", "slot-7")

    ai_sims_server.start_memory_session("game-b", "slot-8")
    with open_db(database) as conn:
        assert empneon_state.recalled_memories(
            conn, "karmine", "bernard", "Do you remember red roses?"
        ) == []

    ai_sims_server.start_memory_session("game-c", "slot-7")
    with open_db(database) as conn:
        recalled = empneon_state.recalled_memories(
            conn, "karmine", "bernard", "Do you remember red roses?"
        )
    assert recalled[0]["message"] == "I prefer red roses."
```

Use the existing deterministic response-category-empty path so this test makes no provider call.

- [ ] **Step 2: Write failure and actor-isolation integration tests**

Add tests proving:

```python
# An unconfirmed proposal is absent from both current-session history and recall.
assert empneon_state.recent_conversations(
    conn, "karmine", "bernard", "social-unconfirmed"
) == []
assert empneon_state.recalled_memories(
    conn, "karmine", "bernard", "Do you remember red roses?"
) == []

# A duplicate displayed acknowledgement still produces one confirmed event.
assert first["status"] == "displayed"
assert second["status"] == "already_displayed"
assert len(confirmed_events) == 1

# A different responder profile never appears in Karmine's prompt.
assert "Karmine Luna" in karmine_prompt
assert "romantic" in karmine_prompt
assert "Agnes Crumplebottom" not in karmine_prompt
assert "hot-headed" not in karmine_prompt
```

Also assert that a delivered deterministic fallback is archived exactly once and failed/cancelled
native-action confirmation does not create another dialogue event.

- [ ] **Step 3: Run integration tests and make only root-cause corrections**

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "survives_save_slot_reload or actor_isolation or unconfirmed or dialogue_delivery"
```

Expected: PASS. If a failure occurs, correct the shared archive/query/prompt function responsible;
do not add a test-only bypass or a second memory path.

- [ ] **Step 4: Run static checks and all suites**

From `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m ruff check src backend tests scripts
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m mypy src
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m compileall -q src backend
```

Expected: every command exits `0`.

From `core`:

```powershell
$env:PYTHONPATH='src'; py -3.12 -m pytest -q -p no:cacheprovider tests
```

Expected: all Core tests PASS.

From the repository root:

```powershell
$env:PYTHONPATH='.'; py -3.12 -m pytest -q -p no:cacheprovider scripts/test_release.py
```

Expected: all release tests PASS.

- [ ] **Step 5: Build the Sims artifacts and commit**

From `adapters/thesims4`, build and verify both artifacts. Do not install into the game unless the
user explicitly requests installation.

```powershell
py -3.12 .\build_mod.py
Test-Path .\dist\Empneon_TheSims4.ts4script
Test-Path .\dist\Empneon_TheSims4.package
```

Expected: build exits `0` and both `Test-Path` calls print `True`.

```powershell
git status --short
git diff --check
git add adapters/thesims4/backend/ai_sims_server.py adapters/thesims4/backend/empneon_state.py adapters/thesims4/tests/test_sims4_backend.py
git commit -m "test(sims4): verify persistent actor memory"
```

Expected: the commit contains only corrections exposed by integration testing and the new tests.
If no production correction was needed, omit unchanged production paths from `git add`.

- [ ] **Step 6: Remove completed planning artifacts after implementation**

After every test and build above passes, delete this implementation plan and its implemented
design spec, as previously requested by the user:

```powershell
git rm docs/superpowers/plans/2026-07-22-actor-session-memory.md docs/superpowers/specs/2026-07-22-actor-session-memory-design.md
git commit -m "docs: remove completed actor memory plans"
```

Do not push any commit.
