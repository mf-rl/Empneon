# Sims 4 Mod-Aware Social Execution and Identity Grounding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute a model-selected native social when a relationship mod makes the mapped mixer valid without enumerating it, and reject replies that ask for the known Listener's name.

**Architecture:** Keep the existing exact category mapping and response retry pipeline. Native execution first prefers an enumerated mixer, then lets The Sims 4 test the same mapped mixer against available supers; grounding adds one high-signal known-listener-name check.

**Tech Stack:** Python 3.7-compatible Sims script, Python 3.12 backend, pytest, stdlib `re`.

## Global Constraints

- Work directly on `main` and do not push.
- Do not substitute a different social category.
- Do not infer social categories from tuning names or add mod-specific dependencies.
- The game remains authoritative: an interaction executes only after native AOP test and factory creation succeed.
- Preserve valid nickname and preferred-name questions.
- After verification, remove implemented documents from `docs/superpowers/plans` and `docs/superpowers/specs`.

---

### Task 1: Mod-aware native social fallback

**Files:**
- Modify: `adapters/thesims4/tests/test_sims4_mod_autonomy.py`
- Modify: `adapters/thesims4/ts4script/ai_sims_agent.py:1218-1261`

**Interfaces:**
- Consumes: `target.potential_interactions(context)`, mapped `affordance`, and `AffordanceObjectPair`.
- Produces: the existing `mapped_aop` and `mapped_interaction` values; no new public interface.

- [ ] **Step 1: Write the failing regression**

In the existing native-social lifecycle test, temporarily make the social super enumerate every mapped mixer except `romance`, then execute `social.romance` and assert that the created AOP still uses the exact `romance` affordance and reaches `running_native_action`:

```python
interaction._aop.super_affordance.all_affordances_gen = classmethod(
    lambda _cls, **_kwargs: iter((mixer, apologize, funny, mean, mischief))
)

assert agent.continue_displayed_turn(romance_session) is True
assert romance_session.phase == "running_native_action"
assert mapped_aops[-1].affordance is romance
```

- [ ] **Step 2: Verify RED**

Run from `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_mod_autonomy.py -k "native_social"
```

Expected: failure because execution reports `no compatible social super-interaction offers social.romance`.

- [ ] **Step 3: Implement the minimal fallback**

Preserve the advertised fast path. For each candidate, skip an unadvertised affordance only while an advertised match has not failed; after the advertised pass finds nothing, run a second pass that constructs the same AOP and accepts it only when native `test(context)` and `interaction_factory(context)` succeed:

```python
def try_mapped_social(candidate, affordance, target, context, pair_type):
    proposed = pair_type(
        affordance,
        target,
        candidate.affordance,
        None,
        push_super_on_prepare=True,
    )
    test_result = proposed.test(context)
    factory_result = proposed.interaction_factory(context) if test_result else None
    return proposed, test_result, factory_result
```

Reuse this helper from two small loops: enumerated candidates first, then candidates not already tried. Record every native rejection in the existing `failures` list.

- [ ] **Step 4: Verify GREEN and existing failure behavior**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_mod_autonomy.py
```

Expected: all tests pass, including existing action-failure coverage.

- [ ] **Step 5: Commit locally**

```powershell
git add adapters/thesims4/ts4script/ai_sims_agent.py adapters/thesims4/tests/test_sims4_mod_autonomy.py
git commit -m "fix(sims4): allow mod-enabled native socials"
```

---

### Task 2: Known-listener identity grounding

**Files:**
- Modify: `adapters/thesims4/tests/test_sims4_backend.py`
- Modify: `adapters/thesims4/backend/ai_sims_server.py:1746-1792`

**Interfaces:**
- Consumes: `response_grounding_issue(payload, response, context)` and `context["listener"]["name"]`.
- Produces: the existing grounding issue string used by `HermesRuntime.dialogue` to retry.

- [ ] **Step 1: Write failing regressions**

```python
def test_grounding_rejects_asking_for_known_listener_name() -> None:
    context = {
        "speaker": {"name": "Karmine Luna"},
        "listener": {"name": "Bernard Jaeger"},
        "conversation": [],
    }
    issue = ai_sims_server.response_grounding_issue(
        {"message": "What a lovely name you have."},
        {"dialogue": "It's nice to meet you, Bernard! What is your name then?"},
        context,
    )
    assert "known Listener" in issue


def test_grounding_allows_preferred_name_question() -> None:
    context = {
        "speaker": {"name": "Karmine Luna"},
        "listener": {"name": "Bernard Jaeger"},
        "conversation": [],
    }
    assert ai_sims_server.response_grounding_issue(
        {"message": "Hello."},
        {"dialogue": "Do you prefer Bernard or another nickname?"},
        context,
    ) == ""
```

- [ ] **Step 2: Verify RED**

Run from `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py -k "known_listener or preferred_name"
```

Expected: the known-listener test fails because the current validator returns an empty string.

- [ ] **Step 3: Add the minimal grounding guard**

Add this high-signal check after repetition checks and before memory-question handling:

```python
listener_name = str(context.get("listener", {}).get("name") or "").strip()
asks_listener_name = re.search(
    r"\b(?:what(?:'s| is) your (?:full )?name|tell me your (?:full )?name)\b",
    dialogue.replace("’", "'"),
)
if listener_name and asks_listener_name:
    return "do not ask for the known Listener's name"
```

- [ ] **Step 4: Verify GREEN**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py
```

Expected: all backend tests pass.

- [ ] **Step 5: Commit locally**

```powershell
git add adapters/thesims4/backend/ai_sims_server.py adapters/thesims4/tests/test_sims4_backend.py
git commit -m "fix(sims4): reject redundant listener name questions"
```

---

### Task 3: Verify and remove completed superpower documents

**Files:**
- Delete implemented files under `docs/superpowers/plans/`
- Delete implemented files under `docs/superpowers/specs/`

**Interfaces:**
- Consumes: repository history, implementation tests, and the final verification result.
- Produces: no runtime interface; completed temporary planning artifacts are absent.

- [ ] **Step 1: Run repository verification**

Run the Core, Sims, Godot, cross-adapter, release, lint, and type-check commands already used by the social-category implementation. Expected: every suite and static check passes.

- [ ] **Step 2: Audit document completion against code and commits**

Confirm each plan/spec has corresponding implementation commits and passing coverage. Current candidates are the adapter-state, identity/dialogue-variety, needs/dialogue-continuity, attraction, social-category, and this mod-social/identity-grounding pairs.

- [ ] **Step 3: Remove only confirmed completed documents**

Use `apply_patch` deletion hunks for each confirmed file. Do not remove either directory or any document whose implementation is incomplete.

- [ ] **Step 4: Verify cleanup and unchanged runtime results**

Run:

```powershell
rg --files docs/superpowers/plans docs/superpowers/specs
git diff --check
git status --short
```

Expected: no implemented planning/specification files remain; only SQLite sidecars may remain untracked; no whitespace errors.

- [ ] **Step 5: Commit locally without pushing**

```powershell
git add docs/superpowers/plans docs/superpowers/specs
git commit -m "docs: remove completed superpower plans"
```
