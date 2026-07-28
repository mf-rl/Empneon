# Sims 4 Mischief Tuning Mapping Implementation Plan

> **For Codex:** Use the executing-plans skill to implement this plan task by task.

**Status:** Completed, rebuilt, and installed; corrected live retest pending

**Goal:** Restore provider-backed mischief responses by matching the tuning name
reported by the live game.

**Architecture:** Keep the existing exact-name discovery path. Correct its one
stale data value and make the existing behavior test use the independently
observed live value.

**Tech Stack:** Python, pytest

---

### Task 1: Correct and verify the mischief tuning mapping

**Files:**
- Modify: `adapters/thesims4/tests/test_sims4_mod_autonomy.py`
- Modify: `adapters/thesims4/ts4script/ai_sims_agent.py`

1. Change the existing test fixture to
   `mixer_social_LieAboutCareer_group_mischief_skills`.
2. Run the focused test and confirm it fails at the mischief affordance
   assertion.
3. Change only `NATIVE_SOCIAL_TUNINGS["social.mischief"]` to the live tuning
   name.
4. Rerun the focused test and confirm it passes.
5. Run all Sims 4, Core, Godot, and shared tests, scoped lint, Python
   compilation, and `git diff --check`.
6. Update the handoff documentation with automated results and the remaining
   live retest.

Do not commit or push; the user will request that separately.

**Result:** The regression failed with only `mischief` absent, passed after the
one-value correction, and all `520` repository tests plus scoped static checks
pass. The next request used a stale archive and therefore did not validate the
mapping. A fresh corrected archive is installed for the next game restart.
