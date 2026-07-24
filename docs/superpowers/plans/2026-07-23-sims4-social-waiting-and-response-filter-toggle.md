# Sims 4 Social Waiting and Response Filter Toggle Implementation Plan

**Status (2026-07-23): Implemented and live-tested.** The waiting task now hosts a visible
conversation animation, and response rejection defaults to disabled. The current EA animation may
occasionally give Sim B a bored-looking gesture; this is accepted cosmetic behavior for now.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the waiting animation inside a real Sims social group and allow model-response rejection to be disabled.

**Architecture:** Change only the waiting interaction from `SuperInteraction` to `SocialSuperInteraction`, using native chat group/listen tuning and session propagation to the linked target interaction. Add one validated backend boolean at the existing response-acceptance gate; disabled mode returns the first normalized response and enabled mode preserves current validation.

**Tech Stack:** The Sims 4 Python 3.7 scripting API and XML tuning, Python backend, pytest.

## Global Constraints

- Work on normal `main`.
- Do not create a worktree.
- Do not commit or push until the user explicitly requests it.
- Keep the queue labels `Start conversation` and `Waiting for response`.
- Do not run native social relationship loot.
- `response_rejection_enabled` defaults to `false`.

---

### Task 1: Native waiting social context

**Files:**
- Modify: `adapters/thesims4/ts4script/ai_sims_agent.py`
- Modify: `adapters/thesims4/tuning/empneon_waiting_interaction.xml`
- Test: `adapters/thesims4/tests/test_sims4_mod_autonomy.py`

**Interfaces:**
- Consumes: `EmpneonConversationSession.id`, native chat group `16390`, canonical animation `11326`, listen animation `11570`.
- Produces: `EmpneonWaitingInteraction(SocialSuperInteraction)` and `get_source_social_kwargs()` carrying `empneon_session_id`.

- [ ] **Step 1: Write failing tests**

Add a fake `interactions.social.social_super_interaction` module, assert the
waiting class subclasses it, assert its source-social kwargs carry the session
ID, assert only the initiated side builds the conversation animation, and
assert the waiting XML contains the native chat/listen tuning with no loot.

- [ ] **Step 2: Verify the tests fail**

Run:

```powershell
py -3.12 -m pytest -q -p no:cacheprovider adapters/thesims4/tests/test_sims4_mod_autonomy.py
```

Expected: failure because the waiting class still subclasses
`EmpneonSocialInteraction` and the native social tuning is absent.

- [ ] **Step 3: Implement the minimum social interaction**

Import `SocialSuperInteraction`; give the waiting class a constructor accepting
`empneon_session_id`; propagate it from `get_source_social_kwargs`; notify the
social group when the interaction starts; run paired animation only when
`initiated` is true; retain the existing session loop/cancellation behavior.

Tune `_social_group_type=16390`, native canonical/listen/idle animations,
flexible content, no loot, no relationship scoring, no greetings, and target
type `TARGET`.

- [ ] **Step 4: Verify the focused tests pass**

Run the Task 1 command again. Expected: pass.

### Task 2: Configurable response rejection

**Files:**
- Modify: `adapters/thesims4/backend/ai_sims_server.py`
- Modify: `adapters/thesims4/config/config.json`
- Modify: `adapters/thesims4/docs/setup.md`
- Test: `adapters/thesims4/tests/test_sims4_backend.py`

**Interfaces:**
- Consumes: normalized response returned by `normalize_response()` or `fallback_response()`.
- Produces: boolean `RESPONSE_REJECTION_ENABLED` and first-response return when false.

- [ ] **Step 1: Write failing tests**

Assert the checked-in configuration defaults to `false`. Feed a structurally
valid response that the grounding validator rejects, set the toggle false, and
assert it returns after one provider call. Set the toggle true and assert the
existing retry path still makes two calls.

- [ ] **Step 2: Verify the tests fail**

Run:

```powershell
py -3.12 -m pytest -q -p no:cacheprovider adapters/thesims4/tests/test_sims4_backend.py
```

Expected: failure because the config key/global bypass does not exist.

- [ ] **Step 3: Implement the minimum toggle**

Add `"response_rejection_enabled": false` to both default and checked-in config,
validate that it is boolean, and return the first normalized response in
`HermesRuntime.dialogue()` when the global is false. Document the toggle and
backend restart requirement.

- [ ] **Step 4: Verify the focused tests pass**

Run the Task 2 command again. Expected: pass.

### Task 3: Regression verification and install

**Files:**
- Build outputs: `adapters/thesims4/dist/Empneon_TheSims4.ts4script`
- Build outputs: `adapters/thesims4/dist/Empneon_TheSims4.package`

**Interfaces:**
- Consumes: completed Tasks 1 and 2.
- Produces: tested, built, installed uncommitted Sims mod.

- [ ] **Step 1: Run the full Sims suite**

```powershell
py -3.12 -m pytest -q -p no:cacheprovider adapters/thesims4/tests
```

Expected: all tests pass.

- [ ] **Step 2: Check the diff**

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors; only intended work plus pre-existing live
SQLite WAL/SHM files are present.

- [ ] **Step 3: Build and install**

```powershell
py -3.7 adapters/thesims4/build_mod.py
.\adapters\thesims4\install_mod.ps1
```

Expected: both artifacts build and install. If the game locks either artifact,
close the game and rerun installation.
