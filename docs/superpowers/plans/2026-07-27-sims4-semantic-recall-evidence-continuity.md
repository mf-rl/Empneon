# Sims 4 Semantic Recall Evidence Continuity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Execution status:** Complete; informed recall, uninformed-pair privacy, and restart continuity
passed live.

**Goal:** Carry the semantic selector's primary attributed fact through dialogue grounding and fallback for paraphrased preference, promise, identity, and conflict questions.

**Architecture:** Mark the first grounded selector result as request-local primary semantic evidence. Reuse that fact only when existing Core slot and lexical checks find no support, then let the existing grounding, retry, neutral-outcome, and attributed-fallback paths enforce it.

**Tech Stack:** Python 3.12, standard-library dictionaries and token comparison, pytest, existing Empneon recall helpers.

## Global Constraints

- Do not add dependencies, provider calls, configuration, schemas, or Sims script-mod changes.
- Preserve pair-scoped candidate collection and locally validated request IDs.
- Preserve existing time, location, identifier, code-word ownership, and neutral factual-recall behavior.
- Keep up to three selected memories in prompt context; only the first attributed result is primary.
- Do not commit or push until the user explicitly requests it.

## July 27 Execution Record

- The primary semantic fact now survives non-lexical paraphrases through grounding and attributed
  fallback.
- Factual selection excludes accumulated factless recall answers while questions about what was
  said or how an interaction occurred retain full exchanges.
- Preference replies must preserve the preferred option; promise replies must state every
  meaningful commitment detail; sibling replies preserve the fact owner's perspective.
- Recall decisions no longer promote generated dialogue to responder facts. Existing attributed
  fallback wrappers recover the quoted fact and owner at read time without a migration.
- The post-restart informed-pair matrix passed preference, promise, identity, conflict, and
  neutral executable outcomes. The uninformed Sim disclosed neither the preference nor conflict
  fact; all six authoritative decisions applied zero changes.
- Final automated verification covers `272` Sims tests, `225` Core tests, `4` Godot tests, and
  `5` shared tests, plus compilation, scoped lint, and whitespace checks.

---

### Task 1: Preserve Primary Semantic Evidence Through Grounding

**Files:**
- Modify: `adapters/thesims4/backend/ai_sims_server.py:1451`
- Modify: `adapters/thesims4/backend/ai_sims_server.py:2141`
- Test: `adapters/thesims4/tests/test_sims4_backend.py:312`
- Test: `adapters/thesims4/tests/test_sims4_backend.py:2542`

**Interfaces:**
- Consumes: ordered, locally validated memory dictionaries returned by `select_recalled_memories(query, candidates)`.
- Produces: request-local `semantic_primary=True` metadata on the first selected memory containing attributed facts.
- Produces: `_supported_recall_facts(message, context)` returning the primary semantic facts only when existing slot and lexical checks return no support.

- [x] **Step 1: Add the failing selector-order regression**

Extend the semantic selector test with both candidates selected:

```python
monkeypatch.setattr(
    ai_sims_server,
    "llm_chat",
    lambda *_args, **_kwargs: json.dumps({"event_ids": ["m2", "m1"]}),
)

selected = ai_sims_server.select_recalled_memories(
    "What bouquet would suit me best?",
    _semantic_memory_candidates(),
)

assert [item["event_id"] for item in selected] == ["roses", "date-plan"]
assert selected[0]["semantic_primary"] is True
assert "semantic_primary" not in selected[1]
```

- [x] **Step 2: Add the failing live-shaped evidence regressions**

Add one parametrized test covering the accepted matrix:

```python
@pytest.mark.parametrize(
    ("question", "statement", "answer_term"),
    [
        (
            "What bouquet would suit me best?",
            "I prefer moon orchids to roses.",
            "orchids",
        ),
        (
            "What commitment did I make about the observatory equipment?",
            "I promise I will repair the telescope tomorrow.",
            "telescope",
        ),
        (
            "Who is my sibling?",
            "My sister is named Elara.",
            "elara",
        ),
        (
            "Why are things tense between us?",
            "I hate that you lied about the promotion.",
            "promotion",
        ),
    ],
)
def test_primary_semantic_fact_survives_paraphrase(
    question,
    statement,
    answer_term,
) -> None:
    context = ai_sims_server.build_context(
        {"speaker": {}, "listener": {}, "message": question},
        {"name": "Karmine"},
        {"name": "Bernard"},
        {},
        {},
        [
            {
                "event_id": "primary",
                "semantic_primary": True,
                "facts": [{"actor_id": "bernard", "statement": statement}],
            },
            {
                "event_id": "secondary",
                "facts": [
                    {
                        "actor_id": "bernard",
                        "statement": "My favorite season is winter.",
                    }
                ],
            },
        ],
    )
    context.update(
        conversation=[],
        speaker_id="karmine",
        listener_id="bernard",
    )

    facts = ai_sims_server._supported_recall_facts(question, context)
    assert [fact["statement"] for fact in facts] == [statement]

    accepted = ai_sims_server.normalize_response(
        {"dialogue": "I remember the {} detail.".format(answer_term)}
    )
    ignored = ai_sims_server.normalize_response(
        {"dialogue": "Tell me more about what you mean."}
    )
    assert ai_sims_server._supported_recall_issue(
        {"message": question}, accepted, context
    ) == ""
    assert ai_sims_server._supported_recall_issue(
        {"message": question}, ignored, context
    ) == "answer the recall question with the selected attributed fact"
```

- [x] **Step 3: Add the failing fallback and privacy regressions**

```python
def test_primary_semantic_fact_fallback_quotes_fact() -> None:
    question = "Why are things tense between us?"
    context = ai_sims_server.build_context(
        {"speaker": {}, "listener": {}, "message": question},
        {"name": "Karmine"},
        {"name": "Bernard"},
        {},
        {},
        [
            {
                "semantic_primary": True,
                "facts": [
                    {
                        "actor_id": "bernard",
                        "statement": "I hate that you lied about the promotion.",
                    }
                ],
            }
        ],
    )
    context.update(
        conversation=[],
        speaker_id="karmine",
        listener_id="bernard",
    )

    fallback = ai_sims_server.reasoning_fallback_response(
        {"message": question}, context
    )

    assert "promotion" in fallback["dialogue"].casefold()
    assert fallback["relationship_outcome"] == "none"
    assert fallback["suggested_action"] == "none"


def test_uninformed_semantic_paraphrase_has_no_supported_fact() -> None:
    question = "What bouquet would suit me best?"
    context = ai_sims_server.build_context(
        {"speaker": {}, "listener": {}, "message": question},
        {"name": "Karmine"},
        {"name": "Billie"},
        {},
        {},
        [],
    )
    context.update(
        conversation=[],
        speaker_id="karmine",
        listener_id="billie",
    )

    assert ai_sims_server._supported_recall_facts(question, context) == []
    fallback = ai_sims_server.reasoning_fallback_response(
        {"message": question}, context
    )
    assert "don't know" in fallback["dialogue"].casefold()
```

- [x] **Step 4: Run the focused tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider `
  tests/test_sims4_backend.py::test_semantic_selector_returns_only_selected_candidate_memories `
  tests/test_sims4_backend.py::test_primary_semantic_fact_survives_paraphrase `
  tests/test_sims4_backend.py::test_primary_semantic_fact_fallback_quotes_fact `
  tests/test_sims4_backend.py::test_uninformed_semantic_paraphrase_has_no_supported_fact
```

Working directory: `adapters/thesims4`.

Expected failures:

- selected memories contain no `semantic_primary` marker;
- `_supported_recall_facts()` returns no fact for the non-lexical paraphrases;
- conflict fallback does not quote the promotion fact.

- [x] **Step 5: Mark the first selected attributed memory**

In `select_recalled_memories()`, replace the final list comprehension with:

```python
result = [dict(item, explicit=True) for item in selected]
if result and result[0].get("facts"):
    result[0]["semantic_primary"] = True
return result
```

- [x] **Step 6: Use primary semantic evidence only after existing checks**

In `_supported_recall_facts()`:

1. Normalize facts from all recalled memories as today.
2. Record the normalized facts belonging to the memory with
   `semantic_primary=True`.
3. Apply the existing owner and identifier filters before choosing support.
4. Return slot-supported facts first.
5. Return lexically supported facts second.
6. Return the filtered primary semantic facts last.
7. If the query is not explicit, skip slot and lexical matching but still return filtered primary
   semantic facts.

Keep the existing `_supported_recall_issue()`, `reasoning_fallback_response()`, and
`CognitionRuntime.dialogue()` behavior unchanged; they already consume `_supported_recall_facts()`.

- [x] **Step 7: Run the focused tests and verify GREEN**

Repeat Step 4. Expected: all focused tests pass.

- [x] **Step 8: Run existing recall and neutral-outcome regressions**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py `
  -k "semantic_recall or semantic_selector or supported_recall or codeword or neutral"
```

Expected: all selected tests pass.

---

### Task 2: Verify and Record the Remediation

**Files:**
- Modify: `adapters/thesims4/docs/in-game-core-feature-test-results.md`
- Modify: `docs/roadmap.md`
- Verify: `adapters/thesims4/backend/ai_sims_server.py`
- Verify: `adapters/thesims4/tests/test_sims4_backend.py`

**Interfaces:**
- Consumes: the passing Task 1 behavior.
- Produces: an accurate automated-verification record and an explicit live-retest handoff.

- [x] **Step 1: Run the complete automated verification**

From the repository root:

```powershell
$env:PYTHONPATH='core\src;adapters\thesims4\src'
py -3.12 -m pytest -q -p no:cacheprovider adapters/thesims4/tests
py -3.12 -m pytest -q -p no:cacheprovider core/tests
py -3.12 -m pytest -q -p no:cacheprovider adapters/godot/tests
py -3.12 -m pytest -q -p no:cacheprovider tests
py -3.12 -m py_compile adapters/thesims4/backend/ai_sims_server.py
git diff --check
```

Expected: every suite, compilation, and whitespace check passes.

- [x] **Step 2: Record the live failure and automated remediation**

Append a dated subsection to Test 7 in
`adapters/thesims4/docs/in-game-core-feature-test-results.md` recording:

- preference and conflict failed the expanded live paraphrase matrix;
- promise and identity passed;
- all original facts were stored with correct pair attribution;
- the preference raw model answer was not the confirmed Core result;
- root cause was semantic evidence being discarded by later lexical support reconstruction;
- automated regression counts and checks pass;
- preference, conflict, and uninformed-pair live retests were pending at this checkpoint; the
  later informed-pair retests passed, leaving privacy and restart checks.

At this checkpoint, update `docs/roadmap.md` to narrow the next gate. The July 27 execution record
above is authoritative for the later live result.

- [x] **Step 3: Inspect the uncommitted result**

Run:

```powershell
git diff --check
git diff --stat
git status --short
```

Expected changed files:

- `adapters/thesims4/backend/ai_sims_server.py`
- `adapters/thesims4/tests/test_sims4_backend.py`
- `adapters/thesims4/docs/in-game-core-feature-test-results.md`
- `docs/roadmap.md`
- the approved design and this implementation plan

- [x] **Step 4: Hand off the live retest**

Rebuild and install the current mod, restart the backend, and repeat:

- informed preference: `What bouquet would suit me best?`;
- informed conflict: `Why are things tense between us?`;
- both questions against an uninformed Sim;
- the same four questions after saving and restarting the backend/game.

Pass only when the informed Sim uses the primary attributed fact, the uninformed Sim discloses
neither fact, and all factual responses retain `relationship_outcome=none`,
`suggested_action=none`, and zero applied changes.
