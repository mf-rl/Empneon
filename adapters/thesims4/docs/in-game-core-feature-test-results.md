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

- The newly captured pre-fix identity transcript has Bernard ask Karmine, “You make me happier than
  I ever expected ... Will you be my girlfriend?” Karmine then mirrors most of his wording and
  asks male Bernard, “Would you be my girlfriend?” This is both dialogue mirroring and a role/gender
  failure; automated coverage preserves the exact exchange as a rejected response.
- The observed accepted-sounding Karmine response was “That's sweet! A date sounds like fun. You
  have a certain charm.” It was previously rejected because non-romantic request-scoped action
  metadata was incorrectly allowed to invalidate otherwise grounded dialogue.
- Automated regression now preserves that exact dialogue while retaining its request-scoped
  `friendly_chat` proposal. Descriptive dialogue intent and native action selection remain separate.
- Automated coverage also confirms that displayed turns, not generated turns, commit cognitive
  memory and Empneon trust; native friendship/romance persists only after the selected action
  finishes and the game reports its tracks. Held Empneon Social sessions remain actionless for
  `none`, or execute the mapped native social after dialogue acknowledgement for a non-`none`
  suggestion; manual cancellation suppresses a late backend response.
- The owner accepted the full-scope critical Ruff gate (`E9,F63,F7,F82`); 119 unrelated legacy
  all-rule findings are deferred. This resolves verification scope only and is not in-game evidence.
- The focused source-build retest must record Karmine's reported life stage, gender, and traits and
  Bernard's gender, then verify all of the following without marking this test passed early:
  Karmine's response is distinct from Bernard's current and earlier messages and Karmine's earlier
  replies; male Bernard is called `boyfriend` or described neutrally, never `girlfriend`; dialogue
  reflects Karmine's life stage and traits without reciting trait labels; an exact date such as
  `Saturday` remains usable inside an otherwise distinct reply; a held Empneon Social completes
  without deadlock, stays actionless for `none`, and executes a mapped native social for a non-`none`
  suggestion; Sims friendship/romance comes only from game-observed behavior; and Empneon trust
  changes on delivered dialogue.
- **Status remains PARTIAL.** This handoff was subsequently exercised by the live Karmine runs
  recorded below. The latest remediation still requires a fresh source build and retest before
  Test 5 can pass.

**Automated/source-install handoff (2026-07-21):**

- Fresh suites passed: Core `179`, Sims 4 `82`, and Godot `2` tests. The first sandboxed run was
  invalidated by Windows ACL denial on pytest's temporary directory; the suites were rerun outside
  the sandbox. Core was run from `core` because `test_public_api.py` reads `pyproject.toml` from its
  working directory.
- The standard CI integration mypy scope passed all `51` typed source files. The brief's root-level
  command additionally includes the legacy untyped Sims backend and exits `1` with `11` existing
  errors; it also cannot resolve the top-level `backend` import from repository root. Scoped Ruff
  (`E9,F63,F7,F82`), Python compilation, and `git diff --check` all exit `0`.
- `build_mod.py` rebuilt both artifacts. `Empneon_TheSims4.ts4script` has SHA-256
  `4E5F4DD417895029B9100B00B69C1B3C156FE435DAFA9E7F4A257504DCAD1524`; the package has
  `B9F7F0758F07EFA1582E69E676E9755D44D4E049013918469D8AAEC43EF74622`.
- The Sims 4 was not running, so installation proceeded. Both files under the game's `Mods`
  directory have the same hashes as `dist`. The loopback health endpoint returns `status: ok`.
  Port `8765` already has Python listeners, so no additional backend was started or process
  terminated. The user must now fully restart the game and perform the focused live retest.

**July 21 live Test 5 progress and final remediation state:**

- The Empneon Social queue now remains held through the asynchronous backend wait and multi-turn
  input loop. A Sims scheduler desync (`Yielding non-Element handle`) and a later continuation
  deadlock were reproduced and fixed. The working live flow allows consecutive messages in one
  session while preventing autonomy from taking over the active Sim during the wait.
- Stale or duplicate local backend instances were isolated. The local server now binds
  exclusively, request bodies accept bounded rich actor state up to 1 MiB, input/retry dialogs are
  titled `Empneon Social with <target>`, and only an actual delivered response is titled
  `<target> says:`. This prevents an input echo or retry from masquerading as model dialogue.
- The accepted-sounding model reply is no longer rejected because it uses friendly intent or
  action metadata. Dialogue, descriptive intent, suggested native action, and relationship deltas
  remain separate. A friendly answer to a romantic invitation can therefore advance friendship
  without forcing romance.
- Live Karmine evidence confirmed this storytelling path. Karmine initially accepted a date in
  natural language while remaining friendly. Across further Empneon interactions, Karmine →
  Bernard moved from Sims friendship `0` to `14`; Sims romance stayed `0`, and Empneon trust stayed
  `50`. This is valid partial evidence, not a positive romance consequence.
- The same run exposed two remaining defects. Replies became repetitive, and Empneon eventually
  replaced model dialogue with an explicit statement that Karmine was uncomfortable because her
  social need was low even though the visible need remained green. Both defects break immersion.
- Root cause of the need override was a scale mismatch: the script clamped Sims motives to
  `0..100`, while the backend treated every value at or below `25` as critical and required the
  reply to name it. Root cause of the retry repetition was removal of recent conversation history
  after the first copying rejection.
- Core now accepts a game-neutral need record with normalized `level` and `urgency` in `0.0..1.0`,
  semantic `status` (`satisfied`, `low`, or `critical`), and optional native scale metadata. Each
  adapter owns its conversion and thresholds. The Sims adapter preserves native `-100..100`
  values and maps green `-25..100`, orange `-50..-26`, and red `-100..-51` bands.
- The game request already carried full state for both actors, but the prompt foregrounded only the
  roleplayed Speaker's state. The backend now supplies separately labelled normalized snapshots for
  both Speaker and Listener, including identity, traits, affect, needs, and effects.
- Needs are now model context rather than mandatory dialogue. Green needs are normally silent,
  orange needs may motivate a gentle in-world suggestion, and red needs may strongly influence or
  redirect the response. Empneon no longer rejects a structurally valid, role-correct,
  non-copying response merely because it omits a need, and deterministic fallback no longer
  replaces the topic with a forced need report.
- Repetition retries retain recent player inputs and model replies and explicitly require a new
  reaction, detail, question, or decision without reusing earlier openings or sentence frames.
  Existing deterministic guards still reject substantial copying of the current input, earlier
  inputs, or earlier replies.
- Identity context is normalized and reusable across adapters. Sims gender, life stage, and traits
  are supplied for both actors; unknown values remain unknown. Prompt and validation rules prevent
  unsupported gender/age guesses, speaker/listener reversal, and substantial dialogue mirroring.
- The final implementation commits for the need/continuity correction are `8319e11`, `1746421`,
  `f5a4957`, `51cc55a`, and `1f1e1d4`. Post-commit verification passed Core `181` tests and Sims 4
  `110` tests; `git diff --check` passed. No model provider or game backend is required for these
  automated suites.

**Current handoff state:**

- **July 22 common social-category remediation (automated only):** Empneon now uses the common
  `friendly`, `funny`, `romance`, `mean`, and `mischief` vocabulary for incoming and response
  dialogue. The model returns one response category plus up to three tone tags and Empneon trust;
  Empneon derives `social.<category>` and ignores model friendship, romance, attraction, and
  concrete-action proposals. Both directed actor relationships reach the prompt.
- The Sims script advertises only categories whose exact mapped tuning is loaded. Automated held
  session coverage confirms that acknowledged `social.romance` selects the exact targeted romance
  compliment, reports an observed native romance `+7`, accepts a naturally completed zero-delta
  result, and suppresses consequences for canceled `social.mean`. These are simulated game API
  results, not live Sims evidence.
- Fresh verification passed Core `192`, Sims 4 `145`, Godot `4`, cross-adapter `5`, and release
  `18` tests, plus Ruff, mypy (`51` source files), compilation, and `git diff --check`. Fresh source
  artifacts built with SHA-256 `3727762BB86B49CAAD83EFA5DE8B6E31665C74E946B62B7F55250CBC0CC243C3`
  for `Empneon_TheSims4.ts4script` and
  `B9F7F0758F07EFA1582E69E676E9755D44D4E049013918469D8AAEC43EF74622` for
  `Empneon_TheSims4.package`.
- **Test 5 remains PARTIAL.** Install the new source build and run all five matrix rows before
  claiming the exact tunings are present in the current game build or that any live relationship
  value changed.
- **July 22 live romance finding:** Bernard used multiple unambiguous romantic messages, including
  `You are beautiful, Karmine. I love you`, `Would you like to go on a date with me?`, and
  `I love you very much. Do you love me too?`. Karmine's replies flowed naturally and accepted the
  date, but every recorded decision proposed `relationship.romance = 0`; the later decisions also
  stored friendly intent. The backend's deterministic classifier independently labels these inputs
  `romantic_compliment`, `romantic_invitation`, and `romantic_compliment`, so more explicit player
  wording is not required. The provider response is currently allowed to return zero romance even
  when that classification is romantic. The latest Karmine-to-Bernard snapshot records affinity
  `0.16`, romance `0.0`, trust `0.5`, and WickedWhims attraction `0.0` / `AMBIVALENT`.
- This finding is separate from native Sims romance. A model romance proposal does not directly
  mutate Sims romance. After dialogue acknowledgement, Empneon Social can execute the response's
  mapped native action; `flirt` maps to the game's targeted romance compliment affordance, while
  `none` runs no native social. All six recorded turns selected `none`, so the game never received a
  romantic interaction to score. Native romance changes only after that interaction succeeds and
  the adapter observes a before/after romance difference. The remaining defect is semantic action
  selection: these reciprocated romantic replies should not all be classified as friendly with
  zero romance and `none`.
- Test 5 remains **PARTIAL**. The latest need normalization, both-actor context, model-first
  response acceptance, and continuity retry have automated evidence but no post-fix in-game run.
- The source-built `.ts4script` and `.package` hashes recorded above predate commits `8319e11`
  through `51cc55a`. Rebuild and reinstall both artifacts before the next live test; do not reuse
  those earlier hashes as evidence for the latest code.
- The backend is intentionally stopped at handoff. Automated work starts it only when a test
  requires a live server and stops it before completion. The user starts the source backend for
  manual Sims testing.
- The next live run starts again at Test 5. Capture both actors' visible state, exact prompt and
  response, several continued turns, relationship output before/after, queue behavior, and a
  manual-cancel case. Verify green needs do not force a report, orange/red needs influence wording
  naturally, replies advance rather than recycle dialogue, and only game-observed friendship,
  romance, or attraction changes persist.
- Cross-adapter directed attraction now has automated coverage for the common `-1..1` contract,
  WickedWhims priority, official Lovestruck fallback, omission when unavailable, directionality,
  prompt grounding, diagnostics, and read-only behavior. Test 5 remains **PARTIAL** until the new
  source-built artifacts are installed and both attraction-source paths are observed in game; no
  live attraction value is claimed by automated tests.
- SQLite `-wal` and `-shm` sidecars are local runtime files and must not be committed.
- The first post-push Monorepo CI run (`29891676140`) stopped at Ruff with five test-only style
  findings: three long assertions, one `.format` call, and one long callback line. The assertions
  and test behavior are unchanged; the exact CI Ruff command now passes locally.
- Once lint was unblocked locally, the cross-adapter gate exposed an outdated equality assertion:
  it compared the complete Sims and Godot need dictionaries even though native scales are
  adapter-owned. The test now compares common normalized `level`, `urgency`, and `status` while
  separately verifying Sims `-100..100` and Godot `0..100` native metadata. Local CI-equivalent
  verification passes Core `181`, Sims 4 `110`, Godot `4`, cross-adapter `3`, and release `18`
  tests; mypy passes `51` source files, the scenario regression passes, and all three packages
  build successfully. Replacement Monorepo CI run `29892097554` passed every step on commit
  `0625e19`.

### July 22 late-session Test 5 handoff

**Status:** PARTIAL / MULTI-TURN NATIVE ACTION DEADLOCK

This retest used Bernard Jaeger as the active Sim and Karmine Luna as the roleplayed target. The
backend ran from source with LM Studio on its native `/api/v1/chat` endpoint.

**Persistent actor/session-memory implementation completed before this retest:**

- Empneon now keeps one durable actor identity per stable Sim ID. Duplicate display names do not
  merge actors, and changing a display name does not discard that Sim's stored identity or memory.
- The lightweight local `HermesRuntime` wakes the roleplayed Sim for a request and returns it to a
  dormant state afterward; `AgentManager` bounds simultaneously active actors without introducing
  the external Hermes Agent framework.
- Static profile/personality data and confirmed long-term memory live in Core SQLite rather than
  being recreated as a complete transcript on every request. Dynamic Sims state such as mood,
  needs, relationship, attraction, and current social category is refreshed per interaction.
- Working conversation context is scoped by `conversation_id`. A new Empneon Social starts with a
  clean short-term exchange window while confirmed pair memories remain available across later
  socials and backend restarts.
- Recall now selects confirmed, relevant memories for the exact speaker/listener pair. It does not
  inject another actor's private memory, an unconfirmed generated reply, or a large generic memory
  summary into every prompt.
- Automated coverage verifies dormant wake/reload behavior, stable-ID isolation, duplicate-name
  isolation, pair-specific memory, cross-session persistence, confirmation gating, and bounded
  prompt context. The implementation landed in commits `7d3500a`, `2fd79de`, `a3c493d`,
  `f8ba691`, and `b84155c`; completed actor-memory plans/specifications were then removed in
  `264c15d`.

**Final-message transport fix:**

- Bernard sent `You are the most beautiful flower my eyes have seen. What's your name,
  sweetheart?`.
- LM Studio generated the grounded final answer `Oh, Bernard! You're so charming. Well, here's
  Karmine Luna.` The existing validator gives that exact input/answer pair similarity `0.0`, no
  grounding issue, and no role confusion, so the answer is not dialogue mirroring.
- LM Studio's native response can contain more than one `output` item. Core's
  `LMStudioProvider` returned the first non-empty message, while LM Studio displayed the final
  message. Validation could therefore inspect an earlier draft and reject it even though the
  visible final answer was valid.
- Core now scans the response in reverse and returns the last non-empty `message`. Regression
  coverage supplies an earlier mirrored message followed by `My name is Karmine Luna.` and
  verifies that Core returns the latter.
- Red/green evidence: the new focused regression originally failed with the earlier message and
  passed after the one-line provider change. Fresh verification passed Core `193` tests, Sims 4
  `166` tests, Ruff, mypy (`51` source files), and the Core package build.

**Live evidence after restarting the backend:**

- At `21:25:01`, the first request reached the backend. Karmine's displayed response was
  `Oh, you're sweet! My name is Karmine. And thanks for noticing!`; the agent slept normally at
  `21:25:33`.
- The response was confirmed and stored with Karmine as speaker, Bernard as listener, and the
  original message intact. This confirms that self-identification and final-message selection
  worked for the first live turn.
- Bernard submitted a second message in the same input window. The game trace records
  `Empneon Social input keys=('message',) length=86`, but the backend agent log, cognition usage,
  and LM Studio log contain no second request.
- The first response selected `social.romance`; the exact loaded tuning
  `mixer_social_ComplimentAppearance_targeted_romance_alwaysOn` was found and queued. This is the
  first live evidence that the common romance category reaches its exact mapped tuning, but it is
  not evidence of successful completion or a romance delta.

**Deadlock root cause:**

- When a displayed response has a non-`none` action, `finish_displayed_turn` stores the next text
  as `session.next_message`. `continue_displayed_turn` then enters `running_native_action` and
  intentionally delays the next `/chat` call until the native action reports completion.
- For player dialogue, the payload correctly labels Karmine as response `speaker` and Bernard as
  `listener`, but `execute_sims_action` reverses those IDs when no autonomy interaction is
  supplied. The native romance is therefore actually initiated by Bernard even though the marker
  misleadingly prints `Karmine Luna -> Bernard Jaeger`.
- Bernard is still running the held Empneon Social super-interaction. The newly queued Bernard
  action cannot complete while that holder waits for the action's completion callback, so the
  second message remains in `next_message` and never reaches the backend.
- The game eventually finished the native interaction with `FinishingType.LIABILITY`. Empneon
  treated every non-natural finish as `native_failed`, displayed the raw finishing value as an
  Empneon error, and closed the session instead of submitting the waiting message.

**Secondary cancellation defect:**

- Closing the failed session calls `native_interaction.cancel()` without arguments.
- The live Sims interaction requires `finishing_type` and `cancel_reason_msg`, producing
  `TypeError: cancel() missing 2 required positional arguments: 'finishing_type' and
  'cancel_reason_msg'`.
- This cleanup error is downstream of the queue deadlock. Suppressing it alone would still lose
  the second message.

**Resume point for the next session:**

1. Keep Test 5 `PARTIAL`; do not advance to Test 6.
2. Add a failing script-level regression for a held player session with a non-`none` response
   action and a waiting second message.
3. Correct the native response direction/lifecycle so the response Speaker performs the action
   without waiting on the active Sim's held interaction. Verify relationship before/after values
   use the same direction.
4. Decide explicitly whether an ordinary native-action failure resumes a queued next message;
   manual cancellation must still suppress late dialogue and consequences.
5. Call the Sims cancellation API with its required arguments and never expose a raw
   `FinishingType` as the complete user-facing error.
6. Log the actual native actor/target IDs and the transition that dispatches `next_message`; the
   current name marker reflects payload roles, not execution direction.
7. Rebuild and reinstall the `.ts4script`, restart both game and backend, then repeat the romance
   row with at least two messages in one window. Capture action completion, relationship deltas,
   and cancellation behavior before continuing the remaining category matrix.

Only the LM Studio final-message transport fix is implemented in this final checkpoint. The native
action deadlock, failure-resume policy, cancellation signature, and misleading execution-direction
log remain documented defects for the next session.

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
