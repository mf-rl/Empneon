# Sims 4 Code-Word Owner-Aware Recall Implementation Plan

**Execution status:** Completed; automated checks and the Save A/Save B live matrix passed.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve `your` and `our` code-word questions to facts owned by the intended Sim while preserving unqualified recall behavior.

**Architecture:** Parse the requested code-word owner once in the Sims memory boundary. Filter nonmatching facts before deterministic ranking and semantic candidate construction, then reuse the same owner ID when constructing supported grounding evidence.

**Tech Stack:** Python 3.12 backend and tests, pytest, SQLite; Sims script-mod code unchanged

## Global Constraints

- `your code word` maps to the responding Sim.
- `our code word` maps to the player-message author/shared side.
- Unqualified `code word` queries retain current relevance and recency behavior.
- Do not change Core public contracts, schemas, databases, checkpoints, prompts, provider contracts, or Sims script-mod code.
- Preserve pair privacy, attribution, time/location recall, save-slot restoration, usage, cancellation, action results, and dialogue delivery.
- Leave all changes uncommitted and unpushed.

---

### Task 1: Filter Recall Inputs by Code-Word Owner

**Files:**
- Modify: `adapters/thesims4/backend/empneon_state.py:643-802`
- Test: `adapters/thesims4/tests/test_sims4_backend.py:124`

**Interfaces:**
- Produces: `codeword_recall_owner_id(query: str, responding_id: str, message_author_id: str) -> str | None`.
- Consumes: confirmed facts whose `actor_id` already represents possessive ownership.

- [x] **Step 1: Add the failing retrieval matrix**

Use `_record_confirmed_interaction()` to store an older shared A fact and newer personal B fact for the same pair. For `your`, assert both `recall_candidates()` and `recalled_memories()` expose only B facts. For `our`, assert both expose only A facts. For unqualified `What is the code word?`, assert both facts remain available and B remains first by recency.

```python
def test_codeword_recall_filters_facts_by_possessive_owner(tmp_path) -> None:
    database = str(tmp_path / "core.sqlite3")
    with open_db(database) as conn:
        _record_confirmed_interaction(
            conn,
            "shared-a",
            "sim-b",
            "sim-a",
            "Our secret code word is TEST14-A-731.",
            "Acknowledged.",
            [],
            happened_at=1,
        )
        _record_confirmed_interaction(
            conn,
            "personal-b",
            "sim-b",
            "sim-a",
            "Your secret code word is TEST14-B-731.",
            "Acknowledged.",
            [],
            happened_at=2,
        )

        results = {
            query: (
                ai_sims_server.empneon_state.recall_candidates(
                    conn, "sim-b", "sim-a", query
                ),
                ai_sims_server.empneon_state.recalled_memories(
                    conn, "sim-b", "sim-a", query
                ),
            )
            for query in (
                "What is your code word?",
                "What is our code word?",
                "What is the code word?",
            )
        }

    def facts(memories):
        return [
            (fact["actor_id"], fact["statement"])
            for memory in memories
            for fact in memory["facts"]
        ]

    expected_a = [("sim-a", "Our secret code word is TEST14-A-731.")]
    expected_b = [("sim-b", "Your secret code word is TEST14-B-731.")]
    assert facts(results["What is your code word?"][0]) == expected_b
    assert facts(results["What is your code word?"][1]) == expected_b
    assert facts(results["What is our code word?"][0]) == expected_a
    assert facts(results["What is our code word?"][1]) == expected_a
    assert facts(results["What is the code word?"][0]) == expected_b + expected_a
    assert facts(results["What is the code word?"][1]) == expected_b + expected_a
```

- [x] **Step 2: Run the test and verify RED**

From `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py::test_codeword_recall_filters_facts_by_possessive_owner
```

Expected: `our` receives B before A because current ranking treats both queries identically.

- [x] **Step 3: Implement the narrow owner parser and retrieval filters**

Add:

```python
_CODEWORD_OWNER_QUERY = re.compile(
    r"\b(?P<owner>your|our)\s+(?:secret\s+)?code\s*word\b",
    re.IGNORECASE,
)


def codeword_recall_owner_id(
    query: str,
    responding_id: str,
    message_author_id: str,
) -> str | None:
    match = _CODEWORD_OWNER_QUERY.search(str(query or ""))
    if match is None:
        return None
    return (
        str(responding_id)
        if match.group("owner").casefold() == "your"
        else str(message_author_id)
    )
```

In both `recall_candidates()` and `recalled_memories()`, compute the owner once from `query`, `actor_id`, and `other_id`. Filter `_authoritative_facts(data)` by that actor when an owner is requested, and skip a code-word event when no fact remains. Leave the unqualified path unchanged.

- [x] **Step 4: Run the matrix and existing retrieval tests and verify GREEN**

```powershell
py -3.12 -m pytest -q -p no:cacheprovider `
  tests/test_sims4_backend.py::test_codeword_recall_filters_facts_by_possessive_owner `
  tests/test_sims4_backend.py::test_recall_candidates_are_pair_scoped_and_prioritized `
  tests/test_sims4_backend.py::test_non_question_remembrance_keeps_responder_fact `
  tests/test_sims4_backend.py::test_recalled_memories_deduplicate_facts_and_cap_results
```

Expected: all pass.

---

### Task 2: Enforce Ownership During Grounding

**Files:**
- Modify: `adapters/thesims4/backend/ai_sims_server.py:2141-2187`
- Test: `adapters/thesims4/tests/test_sims4_backend.py:3620`

**Interfaces:**
- Consumes: `empneon_state.codeword_recall_owner_id(...)`.
- Produces: `_supported_recall_facts(message, context)` containing only facts owned by the requested code-word subject.

- [x] **Step 1: Add the failing selected-memory defense regression**

Construct one context containing both exact Test 14 facts in a single selected memory. Assert `your` returns only B, `our` returns only A, unqualified recall keeps both, and a context containing only the wrong owner returns grounded uncertainty.

```python
def test_supported_codeword_facts_enforce_possessive_owner() -> None:
    facts = [
        {"actor_id": "sim-b", "statement": "Your secret code word is TEST14-B-731."},
        {"actor_id": "sim-a", "statement": "Our secret code word is TEST14-A-731."},
    ]
    context = {
        "speaker_id": "sim-b",
        "listener_id": "sim-a",
        "speaker": {"name": "Sim B"},
        "listener": {"name": "Sim A"},
        "conversation": [],
        "recalled_memories": [{"facts": facts}],
    }

    assert ai_sims_server._supported_recall_facts(
        "What is your code word?", context
    ) == [facts[0]]
    assert ai_sims_server._supported_recall_facts(
        "What is our code word?", context
    ) == [facts[1]]
    assert ai_sims_server._supported_recall_facts(
        "What is the code word?", context
    ) == facts

    wrong_owner = dict(
        context,
        recalled_memories=[{"facts": [facts[0]]}],
    )
    response = ai_sims_server.reasoning_fallback_response(
        {"message": "What is our code word?"},
        wrong_owner,
    )
    assert response["intent"] == "admit_uncertainty"
```

- [x] **Step 2: Run the test and verify RED**

```powershell
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py::test_supported_codeword_facts_enforce_possessive_owner
```

Expected: both possessive queries return both facts and `our` can select B.

- [x] **Step 3: Filter supported facts with the shared owner ID**

After collecting structured facts in `_supported_recall_facts()`, call:

```python
owner_id = empneon_state.codeword_recall_owner_id(
    message,
    str(context.get("speaker_id") or ""),
    str(context.get("listener_id") or ""),
)
if owner_id is not None:
    facts = [
        fact for fact in facts
        if str(fact.get("actor_id") or "") == owner_id
    ]
```

Keep identifier and query-slot filtering after ownership filtering.

- [x] **Step 4: Run focused recall tests and verify GREEN**

```powershell
py -3.12 -m pytest -q -p no:cacheprovider `
  tests/test_sims4_backend.py::test_supported_codeword_facts_enforce_possessive_owner `
  tests/test_sims4_backend.py::test_reasoning_fallback_recalls_possessive_codeword `
  tests/test_sims4_backend.py::test_reasoning_fallback_returns_uncertainty_for_unsupported_what_question `
  tests/test_sims4_backend.py::test_confirmed_identifier_fact_is_required_for_explicit_recall
```

Expected: all pass.

---

### Task 3: Compatibility Verification and Live Handoff

**Files:**
- Modify: `docs/superpowers/specs/2026-07-26-sims4-codeword-owner-aware-recall-design.md`
- Modify: `adapters/thesims4/docs/in-game-core-feature-test-plan.md`
- Modify: `adapters/thesims4/docs/in-game-core-feature-test-results.md`
- Modify: `docs/roadmap.md`

- [x] **Step 1: Run complete automated suites**

Run:

```powershell
Set-Location adapters/thesims4
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider

Set-Location ..\..\core
$env:PYTHONPATH='src'
py -3.12 -m pytest -q -p no:cacheprovider

Set-Location ..\adapters\godot
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider

Set-Location ..\..
$env:PYTHONPATH='core\src;adapters\thesims4\src;adapters\godot\src'
py -3.12 -m pytest -q -p no:cacheprovider tests
```

Expected: zero failures in all four suites.

- [x] **Step 2: Compile production modules**

```powershell
py -3.12 -m py_compile `
  adapters/thesims4/backend/empneon_state.py `
  adapters/thesims4/backend/ai_sims_server.py
```

Expected: exit code `0`.

- [x] **Step 3: Validate existing checkpoints read-only**

From the repository root, run:

```powershell
$env:PYTHONPATH='core\src;adapters\thesims4\src;adapters\thesims4'
@'
import sqlite3
from backend import empneon_state

connection = sqlite3.connect(
    "empneon_core_memory.sqlite3.empneon-saved.slot-15"
)
connection.row_factory = sqlite3.Row
expected = {
    "What is your code word?": ["TEST14-B-731"],
    "What is our code word?": ["TEST14-A-731"],
    "What is the code word?": ["TEST14-B-731", "TEST14-A-731"],
}

def identifiers(memories):
    return [
        identifier
        for memory in memories
        for fact in memory["facts"]
        for identifier in ("TEST14-A-731", "TEST14-B-731")
        if identifier in fact["statement"]
    ]

for query, wanted in expected.items():
    candidates = empneon_state.recall_candidates(
        connection,
        "1048519419917370656",
        "1048519419914027021",
        query,
    )
    recalled = empneon_state.recalled_memories(
        connection,
        "1048519419917370656",
        "1048519419914027021",
        query,
    )
    assert identifiers(candidates) == wanted
    assert identifiers(recalled) == wanted
'@ | py -3.12 -
```

Expected: exit code `0`. The connection remains read-only in behavior: no
write statement or transaction is issued, and neither checkpoint is modified.

- [x] **Step 4: Update Test 14 records**

Record the live storage/delivery pass, the owner-selection failure, the automated fix, verification counts, and the remaining backend-restart live retest. Keep Test 14 `PARTIAL`.

- [x] **Step 5: Inspect the uncommitted result**

```powershell
git diff --check
git status --short
git diff --stat
```

Expected: only approved backend, tests, specs/plans, and Test 14 documentation are changed. Do not stage, commit, or push.
