# Sims 4 In-Game Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the state-quality, grounding, memory, telemetry, fallback, and diagnostic defects found during the 15-section in-game test plan.

**Architecture:** Normalize Sims data at the game boundary, keep unconfirmed Core events inaccessible, promote only confirmed declarative facts, query memory with the player's current message, and validate provider output before it becomes dialogue. Reuse existing Core stores and provider result types; add no dependencies or new persistence formats.

**Tech Stack:** Python 3.11+, SQLite, pytest, The Sims 4 script API, Empneon Core providers and stores.

## Global Constraints

- Preserve the single active `empneon_core_memory.sqlite3` database design.
- Never modify or delete player databases during implementation or automated tests.
- Keep legacy sources read-only.
- Add no dependencies.
- Do not commit until the user requests it.

---

### Task 1: Normalize Sims identity, mood, and needs

**Files:**
- Modify: `adapters/thesims4/ts4script/ai_sims_agent.py`
- Modify: `adapters/thesims4/backend/empneon_state.py`
- Test: `adapters/thesims4/tests/test_sims4_mod_autonomy.py`
- Test: `adapters/thesims4/tests/test_sims4_backend.py`

**Interfaces:**
- Produces canonical payload fields: `age`, `current_mood`, and six human need names.
- `empneon_state.sync_sim()` persists canonical identity and completes obsolete generated goals.

- [x] Add failing tests proving raw mood classes become `uncomfortable`, only bladder/hunger/etc. become needs, age persists, old internal goals are completed, and status updates advance `updated_at`.
- [x] Run the focused tests and confirm the observed raw mood/internal-goal behavior fails.
- [x] Implement boundary normalization with a six-need allowlist and timestamp status mutations.
- [x] Run the focused tests and confirm they pass.

### Task 2: Persist only confirmed observations and factual beliefs

**Files:**
- Modify: `adapters/thesims4/backend/empneon_state.py`
- Modify: `adapters/thesims4/backend/ai_sims_server.py`
- Test: `adapters/thesims4/tests/test_sims4_backend.py`

**Interfaces:**
- Produces `record_pending_event(conn, event)` for replay evidence without observations.
- `record_confirmed_experience()` promotes successful interactions and creates beliefs only for declarative player statements.

- [x] Add failing tests proving proposed/failed actions create no accessible memory or question-belief, while a successful declarative statement becomes accessible to participants.
- [x] Run the focused tests and confirm premature persistence fails.
- [x] Split pending event storage from confirmed observation storage and reject questions/placeholders as factual beliefs.
- [x] Run the focused tests and confirm they pass.

### Task 3: Ground replies in needs and relevant private memory

**Files:**
- Modify: `adapters/thesims4/backend/ai_sims_server.py`
- Modify: `adapters/thesims4/backend/empneon_state.py`
- Test: `adapters/thesims4/tests/test_sims4_backend.py`

**Interfaces:**
- `memories_for_pair(..., query="")` preserves vector relevance when a query is supplied.
- Dialogue validation rejects unsupported factual guesses and replies that ignore critical needs.

- [x] Add failing tests for paraphrased private-memory retrieval, nonparticipant uncertainty, and critical bladder grounding.
- [x] Run the focused tests and confirm retrieval/grounding failures.
- [x] Query Core memory with the current message, strengthen the prompt, and use deterministic safe fallbacks after retry exhaustion.
- [x] Run the focused tests and confirm they pass.

### Task 4: Harden provider output, fallback, and telemetry

**Files:**
- Modify: `core/src/empneon/providers/llm/lmstudio.py`
- Modify: `adapters/thesims4/backend/ai_sims_server.py`
- Modify: `adapters/thesims4/src/empneon_thesims4/adapter.py`
- Test: `core/tests/unit/test_openai_compatible_provider.py`
- Test: `adapters/thesims4/tests/test_sims4_backend.py`
- Test: `adapters/thesims4/tests/test_adapter.py`

**Interfaces:**
- LM Studio returns `GenerationResult` with native input/output token counts and measured latency.
- JSON extraction accepts the first complete object and never exposes malformed JSON as dialogue.
- CLOD fallback explicitly reports model unavailability and proposes no memory mutation.

- [x] Add failing tests for LM Studio usage, duplicate fenced JSON, malformed output, and clear CLOD fallback.
- [x] Run the focused tests and confirm all four defects.
- [x] Implement stdlib-only parsing/measurement and safe fallback text.
- [x] Run the focused tests and confirm they pass.

### Task 5: Improve native-action failure diagnostics and verify

**Files:**
- Modify: `adapters/thesims4/ts4script/ai_sims_agent.py`
- Test: `adapters/thesims4/tests/test_sims4_mod_autonomy.py`

**Interfaces:**
- Failed social selection reports the mapped action and absence of a compatible social super-interaction.

- [x] Add a failing assertion for a non-empty selection failure reason.
- [x] Run it and confirm the empty reason.
- [x] Add the minimum diagnostic reason without changing safe execution semantics.
- [x] Run Core, adapter, release, lint, type, syntax, and build verification.
- [x] Rebuild and install `Empneon_TheSims4.ts4script` and `Empneon_TheSims4.package` for focused in-game retesting.
