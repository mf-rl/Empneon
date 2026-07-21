# Empneon Core In-Game Test Results

Test evidence for `in-game-core-feature-test-plan.md`. Raw diagnostic responses remain local;
this record contains only the evidence needed to determine pass/fail status.

## Remediation awaiting in-game verification (2026-07-20)

The feature branch now includes automated regressions and fixes for every actionable defect below.
Test 4 has passed its release-build retest; the remaining statuses stay unchanged until their
corresponding in-game retests pass:

- Test 3 generic fallback summaries now contain the concrete message and reply.
- Test 4 now passes: the live aspiration tracker is ingested, and need-goal lifecycle state
  persists correctly.
- Test 5 resolves relationship display names to numeric Sim IDs, recognizes common romantic
  phrases, rejects copied or recycled dialogue, supports explicit acceptance or rejection, maps
  accepted invitations to `flirt`, and reads native friendship and romance tracks separately.
- Test 6 rejects denial or contradiction when a supporting private memory is available.
- Test 7 ranks the complete observable memory set, filters it by the exact Sim pair, and excludes
  irrelevant historical summaries from the dialogue prompt.
- `FinishingType.OBJECT_CHANGED` remains a reported game cancellation and is not retried
  automatically, avoiding duplicate native socials.

## Test 2: Canonical Sim profile and OCEAN personality

**Status:** PASS

**Procedure:** Saved the game, restarted the game, and queried the same Sim profile.

**Evidence:**

- Stable Sim: Bernard Jaeger (`1048519419914027021`).
- Adapter: `sims4`; age: `16`.
- Profile persisted after save and game restart.
- OCEAN: openness `0.75`, conscientiousness `0.5`, extraversion `0.8`,
  agreeableness `0.75`, neuroticism `0.5`.
- Openness and agreeableness are above the neutral `0.5` baseline; extraversion is also
  distinctly non-neutral.
- Emotion was normalized as `fine` with value `0.75`.

**Notes:** `occupation` was unavailable (`null`), which is permitted by the plan and does not
affect the profile/personality result.

## Test 3: Rich game state and emotional state

**Status:** PASS

**Procedure:** Made Bernard hungry, captured diagnostics, saved the game, then restarted both the
game and backend and queried the same Sim again.

**Evidence passed:**

- Canonical `uncomfortable` emotion was recorded at `0.75`.
- Need-derived state included active `Restore hunger` (priority `1.0`) and `Restore hygiene`
  (priority `0.6`) goals.
- After reloading the game and backend, Empneon Social answered: “I'm uncomfortable because my
  hygiene and hunger need is critical.” This is grounded in the captured mood and critical needs.
- Agent, personality, relationship, emotions, goal IDs, statuses, and timestamps were identical
  after game/backend restart.
- After native completion, diagnostics contained confirmed event
  `8a6a9e77-9007-4373-88c1-d3308b826959:confirmed` with the submitted question and exact grounded
  reply. The event appears in both observations and accessible memories.
- Relationship strength moved from `0.50` to `0.52`, providing additional evidence that the
  confirmed native interaction applied its consequence.

**Quality note:** The stored summary was the generic “The conversation needed a careful
response.” The full confirmed memory still contains the concrete question and dialogue, so this
does not fail Test 3, but summary quality should be improved separately.

## Test 4: Aspirations and need-derived goals

**Status:** PASS

**Retest procedure (2026-07-20):** Started with a clean database, initialized the active Sim with
`ai.profile`, changed individual needs, synchronized the profile, queried `empneon.goals`, and
restarted both the game and backend before the final verification.

**Evidence:**

- The active `Aspiration: ...` goal appeared in every `empneon.goals` query.
- Lowering hunger produced an active `Restore hunger` goal.
- Restoring hunger changed that same goal to `completed`.
- Lowering fun produced an active `Restore fun` goal while `Restore hunger` remained completed.
- After restarting the game and backend and running `ai.profile` again, the aspiration remained
  active, `Restore hunger` remained completed, and `Restore fun` remained active.
- This verifies aspiration ingestion, need-goal activation/completion, coexistence of aspiration
  and need goals, and persistence across restart.

## Test 5: Directed relationships and confirmed consequences

**Status:** PARTIAL / AUTOMATED REMEDIATION AWAITING IN-GAME RETEST

**Retest evidence (2026-07-20):**

- With Billie Jang active, `ai.relationship Cam Sadya` returned friendship `0`, romance `0`,
  trust `50`, respect `50`, and resentment `0` before and after “Let's be girlfriends.”
- The same values appear for every newly queried relationship.
- Root cause of the repeated display is confirmed: `ai.relationship <name>` passes the name as
  `sim_id`, but Core stores relationship edges under numeric Sim IDs. A missing edge then returns
  the documented default values. The native/Core consequence cannot be judged from these two
  name-based queries and must be rechecked by numeric ID.
- Cam's decision `59cd1c4b-b94f-48c1-987a-ba77903d036f` directly addressed the proposal with
  `set_boundary` and “No, I would rather stay friends.” All proposed relationship deltas were
  zero, which correctly preserves consent and avoids an invented romance consequence.
- The native result was `failed` with `FinishingType.OBJECT_CHANGED` and no applied changes. This
  verifies the explicit-rejection branch but does not verify a completed native flirt or confirmed
  romance consequence; an accepted invitation is still required for that branch.
- A later Billie/Bernard retest exposed dialogue repetition: Billie copied Bernard's compliment
  almost verbatim and then reused that old compliment to answer “Would you go out with me
  sometime?”. Timeline decisions confirm the stale dialogue rather than a display-only problem.
- Root cause: romantic-request validation recognizes `date`, `love`, `romance`, and `kiss`, but not
  `go out`, `girlfriend`, or `boyfriend`; it also has no guard against echoing the current message
  or reusing a previous reply.
- Those recent native results also failed with `no compatible social super-interaction offers
  friendly_chat`, so no confirmed relationship consequence could be applied.

**Automated remediation (2026-07-20):**

- `ai.relationship <name>` now resolves the existing SimInfo and queries Core with its numeric Sim
  ID; direct numeric-ID input remains supported.
- Romantic validation now recognizes `go out`, `girlfriend(s)`, and `boyfriend(s)` in addition to
  its original phrases.
- The shared validator rejects a near-verbatim copy of the current player message and reuse of a
  prior reply for a different message. It then uses the existing grounded retry/fallback path,
  leaving the model free to write any distinct, relevant, grounded response.
- Regression tests reproduce the Billie/Bernard transcript and the name-resolution defect. The
  complete verification passed: Core 168, Sims 4 54, Godot 1, integration 3, and release 18 tests
  (`244 passed` total), plus Ruff, mypy, and Python compilation.

**Release retest after remediation (2026-07-20):**

- With Bernard active, `ai.relationship Cam Sandya` resolved successfully and reported Cam →
  Bernard friendship `0`, romance `0`, trust `50`, respect `50`, and resentment `0`.
- After an Empneon Social friendship request, the same name-based command reported friendship `7`
  with all other displayed values unchanged. This verifies name resolution and a confirmed native
  friendship consequence.
- Bernard's diagnostic correctly showed no reverse relationship because the measured edge is Cam
  → Bernard. Cam's diagnostic/timeline is still required to record that directed edge directly.
- This exchange does not test romance; Test 5 remains partial until an accepted invitation produces
  a completed native flirt and a confirmed romance consequence.

**Second automated remediation after the Karmine retest (2026-07-20):**

- The Karmine transcript reproduced a near-copy (`It's just looking at you...`) that escaped the
  previous exact-match guard. A later response degraded to the generic “Give me a moment...” text
  after both grounded model attempts reused stale conversation history.
- The existing model response now classifies the current player interaction as friendly, romantic
  compliment, romantic invitation, hostile, informational, or neutral. This uses the same model
  generation rather than adding a classifier request. Direct romantic invitations retain the
  deterministic accept-or-decline consent boundary; compliments do not.
- Near-copy detection now uses token-sequence similarity. When a response copies the current
  message or an earlier reply, the second model attempt keeps identity, state, relationship,
  memories, and the current message but removes recent dialogue history.
- If model routing falls back to Core CLOD 1, the Sims adapter now returns a conservative,
  interaction-relevant response instead of the generic model-unavailable message. Usage remains
  attributed to `core-rules`, and native confirmation is still required for consequences.
- Automated coverage now reproduces the Karmine near-copy, verifies clean retry history, separates
  romantic compliments from invitations, covers all six fallback categories, and verifies the
  provider-unavailable CLOD 1 path. A new packaged release must still retest accepted romance and
  native confirmation in game.
- Final verification passed: Core 168, Sims 4 60, Godot 1, cross-adapter 3, and release 18 tests
  (`250 passed` total), plus Ruff, mypy (50 source files), and the deterministic CLOD1 scenario.

**Follow-up Karmine release evidence (2026-07-20):**

- For “I would love to take you on a date sometime,” decision
  `e9475b34-8b67-4a7c-acb8-9dff5fa0bdd9` proposed `intent=friendly`, friendship `+1`, and romance
  `0`. Native confirmation used `friendly_chat` and observed friendship `-2`; no romance was
  applied.
- For “Would you like to be my girlfriend?”, decision
  `8e11d0e7-6913-4f7f-93c2-213dc1ca8d0e` returned `intent=recall` and copied the preceding player
  date message. The native action then failed because no compatible `friendly_chat` was available.
- Usage confirms both requests stayed on LM Studio/CLOD 3. The first sentence was not covered by
  the conservative invitation phrase matcher. On the second, deterministic fallback evaluated
  memory-question recall before romantic invitations, so a related earlier player message became
  the reply.
- Regression coverage now includes both exact observed sentences. Date-taking language is treated
  as an invitation, and romantic invitation fallback runs before memory recall. The complete Sims 4
  adapter suite passes with 61 tests; another packaged release is required for the in-game romance
  confirmation retest.

**Procedure:** Recorded `ai.relationship Billie Jang`, asked Billie on a date through Empneon
Social, then queried the relationship again.

**Evidence:**

- Before: Billie Jang → Bernard Jaeger had friendship `0`, romance `0`, trust `50`, respect `50`,
  resentment `0`.
- Billie's reply discussed critical hygiene and hunger instead of addressing the date request.
- After: every displayed relationship value was unchanged.

**Failures:**

- Dialogue was not relevant to the player's date request.
- `ai.relationship` displayed no before/after change, and no romance consequence was proposed or
  confirmed despite the explicit date request.

**Timeline evidence:**

- Decision `c2fcd1c8-8962-45ee-abb0-edfd8f68e522` completed with status `succeeded`.
- The model proposed intent `agree`, `friendship +10`, `trust +10`, romance `0`, and
  `friendly_chat`.
- Native confirmation applied `friendly_chat` and observed `friendship +2`; no trust or romance
  consequence was confirmed. This correctly preserves game-observed effects instead of applying
  the model's unverified proposed values.
- The confirmed memory repeated irrelevant hygiene/hunger context from earlier conversations.
  This confirms a retrieval/grounding defect rather than a native-action failure.

**Directed-edge result:**

- Billie → Bernard: strength `0.56`, trust `0.50`, updated by the successful date interaction at
  `1784525512`.
- Bernard → Billie: strength `0.53`, trust `0.50`, last updated earlier at `1784525002`.
- The distinct values, IDs, and timestamps verify independent directed Core edges. The confirmed
  interaction updated Billie's edge without overwriting Bernard's reverse edge.

**Persistence result:** PASS. After saving and restarting both game and backend, both directed
relationship IDs, strengths, trust values, and timestamps were unchanged (`0.56` Billie → Bernard
and `0.53` Bernard → Billie).

**Final Test 5 result:** Native confirmation, directed storage, and persistence pass. Dialogue and
name-resolution defects are remediated in automated tests; a new release must still verify the
dialogue behavior and a positive native romance consequence in game.

**Source-build handoff (2026-07-21):**

- The observed accepted-sounding Karmine response was “That's sweet! A date sounds like fun. You
  have a certain charm.” It was previously rejected because non-romantic request-scoped action
  metadata was incorrectly allowed to invalidate otherwise grounded dialogue.
- Automated regression now preserves that exact dialogue while retaining its request-scoped
  `friendly_chat` proposal. Descriptive dialogue intent and native action selection remain separate.
- Automated coverage also confirms that displayed turns, not generated turns, commit cognitive
  memory and Empneon trust; native friendship/romance persists only after the selected action
  finishes and the game reports its tracks; queued multi-turn sessions wait for that result; and
  manual cancellation suppresses a late backend response.
- **Status remains PARTIAL.** No 2026-07-21 in-game source-build result is recorded. Run the focused
  Test 5 procedure, including the manual-cancel repetition, and append the exact player message,
  displayed response, relationship output before/after, decision ID, native finishing result, and
  session continued/closed state before marking this test passed.

## Test 6: Private observations and beliefs

**Status:** PARTIAL / RECALL CONSISTENCY FAILED

**Procedure:** Bernard taught Karmine `PRIVATE-GARDEN-731 is under the blue bench`, asked Karmine
to recall it, taught it again, and asked uninvolved Billie for the same fact.

**Confirmation analysis:**

- The first teaching event (`104c15f9-1c7a-4957-855f-9f2d622ce3ec`) was observed but never
  confirmed by a completed native action. Core therefore created no belief or accessible memory;
  Karmine's subsequent “I don't know or remember that” was correct for confirmation-gated memory.
- The second teaching completed successfully as decision
  `eaea5766-c0ea-4c11-9950-5494cf488799`, applying `friendly_chat` and observed `friendship +1`.
- Successful confirmation created Karmine's private belief with confidence `0.9` and a confirmed
  accessible memory containing the exact fact.

**Evidence passed:**

- Confirmed facts become observation-backed beliefs and accessible memories.
- Unconfirmed facts do not become durable memory.
- Billie has no matching belief or accessible memory and answered “I don't know or remember
  that.” Privacy isolation therefore passed.
- Karmine's later reply retrieved the correct location, “under the blue bench.”

**Failure:** Karmine contradicted the retrieved belief by adding “you didn't mention it before.”
The fact was present in the prompt-accessible belief and memory, so this is a dialogue-grounding
failure. The recall action itself later failed natively with `FinishingType.OBJECT_CHANGED`, but
that does not explain the already-generated contradiction.

**Persistence result:** PASS. After several unrelated interactions and a game save/reload, Karmine
still answered that the item was under the blue bench while Billie did not reveal the location.

**Remaining defect:** A clean, non-contradictory recall remains to be retested after the grounding
defect is fixed.

## Test 7: Local vector retrieval

**Status:** FAIL

**Procedure:** After several additional Empneon interactions, Bernard asked both Karmine and
Billie `Where is the PRIVATE-GARDEN-731?`, then saved/reloaded and repeated both questions.

**Evidence passed:**

- Karmine retrieved “under the blue bench” before and after save/reload.
- Billie did not disclose the private location before or after save/reload.
- Several intervening interactions did not displace Karmine's confirmed memory.
- Retrieval/privacy state persisted across game and backend restart.

**Additional failure:** After reload, Billie's response repeated irrelevant hygiene/hunger content
from an earlier conversation. It did not leak the private location, but confirms the existing
retrieval/grounding relevance defect.

**Paraphrased-query result:**

- Karmine answered: “The garden code item? What are you talking about now? Where exactly is it
  located?” Although the confirmed fact remained stored and exact-code recall worked, semantic
  retrieval from the paraphrase failed.
- Billie answered: “The garden code item? Where is the PRIVATE-GARDEN-731?” Billie did not reveal
  `under the blue bench`. Mentioning the identifier is not location leakage because Bernard had
  previously asked Billie about that exact identifier; Billie may remember the question while
  remaining uninformed about its answer.

**Final result:** Persistence and answer privacy pass. Paraphrased local vector retrieval fails and
requires a fix.
