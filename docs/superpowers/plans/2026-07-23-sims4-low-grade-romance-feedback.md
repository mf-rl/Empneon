# Sims 4 Low-Grade Romance Feedback Implementation Plan

**Status (2026-07-23): Implemented and live-confirmed.** Warm romantic replies now produce mild
game-side romance increases. Stronger tiers and milestone effects remain deferred.

> **For agentic workers:** Execute inline on the existing `main` worktree. Do not create a
> worktree, branch, subagent, commit, or push.

**Goal:** Convert positively received, low-grade romantic replies into the existing mild
`romance_positive` outcome so The Sims 4 can display its native romance headline.

**Architecture:** Extend the existing backend relationship-outcome validator with one deterministic
fallback. When the model returns `none`, a romantic response with positive tone and without
rejection or disqualifying tone becomes `romance_positive`; all existing explicit outcomes and
validation rules remain unchanged.

**Tech Stack:** Python 3.12 backend tests, Python standard library, pytest.

## Global Constraints

- Continue on the existing `main` worktree.
- Do not commit or push until the user explicitly requests it.
- Reuse the existing mild `5` point native romance update.
- Do not add stronger `+++`, milestone, sentiment, or relationship-bit effects.
- Explicit rejection remains negative; hesitant, neutral, uncertain, or hostile replies remain
  relationship-neutral unless the model supplied another valid grounded outcome.

---

### Task 1: Validate Low-Grade Romantic Reception

**Files:**
- Modify: `adapters/thesims4/tests/test_sims4_backend.py`
- Modify: `adapters/thesims4/backend/ai_sims_server.py`
- Modify: `adapters/thesims4/docs/in-game-core-feature-test-plan.md`

**Interfaces:**
- Consumes: `validated_relationship_outcome(response: dict) -> str`
- Produces: the existing bounded outcome string `romance_positive` for approved fallback cases

- [ ] **Step 1: Add the failing regression cases**

Extend `test_relationship_outcome_is_bounded_and_grounded` so each case supplies tone tags:

```python
        (
            {
                "dialogue": "Oh, you're sweet! Thanks for noticing!",
                "response_category": "romance",
                "tone_tags": ["playful", "romantic"],
                "relationship_outcome": "none",
            },
            "romance_positive",
        ),
        (
            {
                "dialogue": "It is nice to hear that. I need time to think.",
                "response_category": "romance",
                "tone_tags": ["warm", "hesitant"],
                "relationship_outcome": "none",
            },
            "none",
        ),
        (
            {
                "dialogue": "No, I would rather stay friends.",
                "response_category": "romance",
                "tone_tags": ["warm"],
                "relationship_outcome": "none",
            },
            "none",
        ),
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py::test_relationship_outcome_is_bounded_and_grounded
```

Expected: FAIL because the positive romantic `none` case remains `none`.

- [ ] **Step 3: Implement the minimal deterministic fallback**

In `validated_relationship_outcome`, normalize tone tags and return the existing positive romance
outcome only for the approved combination:

```python
    tone_tags = {
        str(tag).strip().casefold() for tag in response.get("tone_tags") or ()
    }
    positive_romance_tones = {"warm", "playful", "romantic"}
    blocked_romance_tones = {"hesitant", "neutral", "uncertain", "hostile"}
    if (
        value == "none"
        and category == "romance"
        and tone_tags & positive_romance_tones
        and not tone_tags & blocked_romance_tones
        and not ROMANTIC_REJECTION.search(dialogue)
    ):
        return "romance_positive"
```

Place this after bounded-value validation and before returning `value`. Do not alter numeric
magnitude, native relationship application, or explicit positive/negative validation.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run the Step 2 command again.

Expected: PASS.

- [ ] **Step 5: Update live-test status**

Record in `in-game-core-feature-test-plan.md` that warm/playful/romantic reception now produces the
existing mild romance outcome, and add a live check that the romance score changes by the observed
amount and the native floating headline appears.

- [ ] **Step 6: Run complete Sims adapter verification**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests
py -3.7 build_mod.py
```

Expected: all Sims adapter tests pass and both mod artifacts rebuild successfully.

- [ ] **Step 7: Inspect without committing**

Run:

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors; all changes remain uncommitted on `main`.
