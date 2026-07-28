# Empneon Core In-Game Test Results

Test evidence for `in-game-core-feature-test-plan.md`. Raw diagnostics normally remain local;
reviewed, non-sensitive acceptance reports may be retained with this record.

Subsection statuses below preserve point-in-time test history. The remediation summary and the
numbered Test headings are the canonical current status.

## Remediation status

The current branch includes automated regressions and fixes for the actionable defects below.
Tests 4 through 15 have passed their live acceptance retests:

- Test 3 generic fallback summaries now contain the concrete message and reply.
- Test 4 now passes: the live aspiration tracker is ingested, and need-goal lifecycle state
  persists correctly.
- Test 5 resolves relationship display names to numeric Sim IDs, recognizes common romantic
  phrases, rejects copied or recycled dialogue, supports explicit acceptance or rejection, maps
  accepted invitations to `flirt`, and reads native friendship and romance tracks separately.
  July 27 breadth testing also aligned explicit response categories, preserved repeated-prompt
  relevance, and produced safe category-specific funny, mean, and mischief fallbacks.
- Test 6 persists confirmed identifier facts, rejects denial or contradiction when evidence is
  available, and rejects fabricated answers when the queried pair has no matching evidence.
- Test 7 ranks the complete observable memory set, filters it by the exact Sim pair, excludes
  irrelevant historical summaries, and retrieves a private non-date location from a paraphrase
  without leaking it to an uninformed pair.
- Test 8 confirms scheduled provider-free CLOD 1 autonomy, zero-token usage accounting, and
  telemetry persistence after backend restart.
- Test 9 confirms provider-backed dynamic CLOD 3 dialogue and persistent usage telemetry. Core no
  longer mistakes a mid-sentence current-state `what do` question for historical recall.
- Test 10 confirms that a real player conversation starts before already-waiting lower-priority
  ambient cognition when the single worker becomes available.
- Test 11 confirms successful and canceled action-result persistence across backend restart and
  one-attempt handling of permanent HTTP client errors.
- Test 12 confirms timeline replay and consequence integrity.
- Test 13 confirms repeated identity import and backend-restart persistence; raw export timestamps
  may refresh while canonical identity remains unchanged.
- Test 14 confirms checkpoint isolation, owner-aware code-word recall, correct reply perspective,
  grounded uncertainty for branch-absent facts, and relationship-neutral factual recall across
  Save A / Save B reloads.
- Test 15 confirms provider-free CLOD 1 operation and conservative player fallback while LM Studio
  is stopped, plus normal CLOD 3 provider recovery after it restarts.
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

**Status:** PASS / FINAL LIVE RECALL, PERSISTENCE, CONSEQUENCE, AND UI FLOW VERIFIED

Historical `PARTIAL` and `FAIL` statements below record the state at each retest. The July 24
closeout is authoritative for the accepted relationship/recall flow; the July 27 breadth section
is authoritative for the current social-category result.

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

**Status:** HISTORICAL / RESOLVED BY THE SINGLE-TURN FLOW

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

### July 23 single-turn Test 5 retest

**Status:** HISTORICAL / ROMANCE AND LIVE DIAGNOSTICS LATER PASSED

- Three Karmine replies were categorized as `romance` with `playful` and `warm` tone.
- The first two model-proposed `romance_positive` outcomes were reduced to `none` before the
  low-grade fallback because validation returned early when their dialogue lacked the explicit
  reciprocation phrase. Coverage now verifies that approved warm romantic reception survives that
  path.
- The third reply, `That's sweet of you! A date sounds perfect. You're very sweet too!`, produced
  `relationship.romance_positive`. The mod observed and confirmed a native romance delta of `+6`;
  this is the authoritative game-side result.
- The subsequent `ai.relationship Karmine Luna` output still showed romance `0` because the command
  displayed the backend's pre-action native snapshot. The command now reads current friendship,
  romance, and attraction from the live Sims relationship tracker while retaining Empneon trust
  from the backend.
- The first-turn friendship increase from `0` to `14` was not an Empneon consequence: its action
  record contained no applied changes.

### July 23 romance validation and visual source-build handoff

**Status:** HISTORICAL / RELATIONSHIP FLOW AND LATER VISUAL RETEST PASSED

- A later four-turn live run increased Sims romance `0 -> 8 -> 16 -> 21 -> 26`. Friendship remained
  `14`, while WickedWhims attraction increased independently from `+0.33` (`MEDIUM`) to `+0.67`
  (`HIGH`). This confirms the mild Empneon romance outcomes now affect the live romance track and
  that `ai.relationship` reports the current game-side values.
- That run still showed no waiting conversation animation or floating relationship icons because
  those visual paths were not yet implemented in the installed source build.
- The following source build initially reused only the EA friendly-chat `animation_ref` inside **Waiting for
  response**, interrupts the waiting interaction when the answer is displayed, supplies primary
  and secondary Sim portraits to both dialogue notifications, and sends the selected relationship
  track's tuned headline to both Sims after a nonzero observed delta.
- Automated coverage verifies portrait order, animation-only execution, response interruption,
  unavailable-participant cancellation, two-Sim headline dispatch, zero-delta suppression, and
  visual-only failure handling. In-game portrait layout, animation appearance, and exact floating
  symbols are not yet claimed.
- Live testing found that the first animation build only made the Sims face and watch each other.
  Diagnostics showed the friendly animation completed against the waiting interaction's idle ASM.
  Giving a non-queued friendly social mixer ownership still produced only staring. Passing the
  animation through the mixer's full `build_basic_elements` wrapper produced visible conversation
  but also changed friendship because that wrapper inserted the friendly mixer's tuned outcome.
  Keeping only its listener-animation layer reverted to staring. Restoring the full wrapper while
  replacing `build_outcome()` with an empty element also produced only staring, showing that the
  visible speech gestures are assembled inside the native outcome builder rather than by its raw
  `animation_ref`.
- The final build uses that native visual assembly but neutralizes its loot, continuations, events,
  cancellation, extras, and relationship scoring. Its conversation animation was subsequently
  live-confirmed in the final retest below.
- Stronger `+++` feedback and milestone effects remain deferred follow-up work.

### July 23 final waiting-animation retest

**Status:** PASS / WAITING ANIMATION LIVE-VERIFIED; OPTIONAL VISUAL POLISH OPEN

- The installed source build now plays a visible conversation animation while **Waiting for
  response** is in the queue. The Sims no longer remain silent and motionless.
- Sim B occasionally uses a bored-looking gesture. This is an EA-tuned cosmetic variation and is
  accepted for the current phase; selecting a more consistently neutral animation is deferred.
- The implementation builds the friendly outcome's visual sequence but replaces its normal outcome
  element and disables relationship scoring. Loot, continuations, events, cancellation, extras,
  and parameterized autonomy are removed from the visual action data.
- The full Sims adapter suite passes with 183 tests, and the Python 3.7 mod build succeeds.
- The single-turn queue lifecycle and mild romance effects are live-confirmed. Exact two-portrait
  notification layout and floating friendship/romance headline symbols have not yet been reported
  as observed, so Test 5 remains partial.
- Stronger `+++` feedback and major relationship milestones remain deferred.

### July 24 fresh recalled-response retest

**Status:** PASS / CORE FLOW VERIFIED; ADDITIONAL CATEGORY COVERAGE DEFERRED

- Bernard asked Karmine, `Hey, baby. When are we going on a date?` in conversation
  `babc66e3fc9c484cb4045ddafb9d59e5`.
- Karmine answered, `Oh, you're sweet! We were thinking of tonight at 7pm. Does that sound good?`
  This preserves the recalled date fact but does not copy the earlier stored response.
- The agent session ran from `08:24:06` to `08:24:23`. Core recorded LM Studio/CLOD 3 usage with
  `15,478 ms` latency for event `677eafe0-5107-480c-952f-724d882413b7`.
- The game marker records the waiting animation building and completing, followed by the exact
  displayed response. Earlier animation failures remain in the append-only marker, but the latest
  sequence contains no new animation failure.
- Dialogue delivery produced confirmed event
  `958cece9-cf4b-4611-9eb7-b4adf0cfea86:confirmed`. Decision
  `958cece9-cf4b-4611-9eb7-b4adf0cfea86` succeeded with
  `relationship.romance_positive` and observed romance `+5`; both Sims received the confirmed
  observation, Core trust is `0.51`, and no proposal remains pending.
- The game marker then recorded `Empneon memory checkpoint saved`. After game/backend restart, the
  earlier confirmed event and observations remained present, and the same directed relationship ID
  retained strength `0.14` and trust `0.51`.
- The post-restart actor snapshot reported native romance `0.29`, preserving the prior `0.24` plus
  the confirmed `+5` outcome.
- Bernard then asked, `Hey, princess. I just wanted to see if you remember what time is our date.
  Can you tell me?` Karmine answered in fresh wording, `Oh, of course! It was tonight at seven
  o'clock. You were going to make it sound good, and it really did!`
- The new interaction appended confirmed event
  `bf504e55-e479-49ae-bca4-dcc326393631:confirmed`; its decision succeeded with observed romance
  `+8`, both Sims received the observation, and no proposal remains pending.
- Persistence **PASSED**.
- Player observation confirms that both main Sim A and secondary Sim B portraits appear and that
  floating relationship icons display during the tested romance conversations.
- Test 5 remains **PARTIAL** until a positive friendship outcome and a mean interaction verify
  their category-specific consequences and floating feedback. Funny and mischief remain part of
  the full documented matrix unless explicitly deferred.

### July 24 friendly-introduction retest

**Status:** PASS / RELATIONSHIP-NEUTRAL FRIENDLY BRANCH

- Bernard introduced himself to Dennis Kim with `Hi, friend! How are you doing? My name is
  Bernard. Very nice to meet you.`
- Dennis replied, `It's great to meet you too, Bernard! You seem pretty laid-back. What's good
  about meeting you?`
- The LM Studio/CLOD 3 request completed in `55,329 ms`. The response was categorized `friendly`
  with `playful` tone, `relationship_outcome=none`, and `animation=none`.
- Decision `b2e6759a-0e1d-43db-8d24-274073635668` succeeded, dialogue delivery was recorded, and
  both Sims received the confirmed observation. It produced no action consequences or applied
  changes, and no proposal remains pending.
- No floating icon was correct for this relationship-neutral result. This passes the friendly
  `none` branch but does not test a positive friendship consequence or its floating feedback.

### July 24 friendship-category normalization failure

**Status:** HISTORICAL FAIL / FIXED AND LIVE-VERIFIED

- Bernard asked Dennis, `That's funny, man. You are wonderful. How about we gather together for
  some beers?`
- LM Studio returned valid JSON with dialogue `That's funny! You are wonderful too, Bernard. Beers
  sound perfect right now!`, `response_category=friendship`, playful/friendly tone, and
  `relationship_outcome=friendship_positive`.
- The request allowed only `friendly` and `romance`. `normalize_response()` treats `friendship` as
  an alias by classifying the dialogue; the word `funny` changed it to `funny`, which was not an
  available category. Normalization raised `ValueError`.
- The exception path passed the full JSON text to `fallback_response()`. Because that function
  rejects brace-containing text, the valid dialogue was replaced with `I couldn't form a reliable
  response. Please try again.`
- Response rejection was disabled, so no grounding rule blocked this reply. Decision
  `e34cbdef-1f85-43df-9302-b9d0850bf00e` confirmed only the generic fallback with no applied
  changes.
- Automated fix verified on July 24: Core now preserves the caller's game-agnostic schema, rejects
  providers that silently lack structured-output support, and sends LM Studio schema requests
  through `/v1/chat/completions`. The Sims adapter deterministically maps its explicit legacy
  aliases (`friendship`, `hostile`, `romantic_compliment`, and `romantic_invitation`) while
  unknown or unavailable categories remain rejected.
- The exact failed beer-invitation response now retains its dialogue,
  `response_category=friendly`, and `relationship_outcome=friendship_positive` in automated
  coverage. The complete Core suite passes with `196` tests and the complete Sims adapter suite
  passes with `207` tests; both changed Python boundaries compile.
- Test 5 remains **PARTIAL**. Live in-game verification is pending backend/game restart; repeat the
  positive friendship and mean rows.

### July 24 latest save/reload recall and animation failure

**Status:** HISTORICAL / FIXED AND LIVE-VERIFIED

- Same-session recall passed: Karmine remembered the confirmed date as tonight at 7 pm.
- Save/reload data persistence passed. The database retained confirmed event
  `f6924dff-63b3-4fbf-92b8-1305b1858168:confirmed` and its attributed fact,
  `Tonight, 7pm, at my place.`, accessible to both actors.
- Post-reload recall failed. The response was `It sounds good! When are we going on a date? Tell
  you what time and day works best for you?`
- The deterministic `when` cue correctly selected the persisted event, but its later lexical fact
  filter removed the time fact because the question said `date` while the fact said `Tonight,
  7pm`. Automated coverage now retains only time-bearing facts for an event already selected by
  the existing `when` cue; pair scoping, privacy, confirmation gating, deduplication, and the
  result limit remain unchanged.
- The game also repeatedly logged EA's
  `listen_animation_factory referenced before assignment` failure. The mapped mixer had no linked
  social group after reload, leaving EA's listener factory uninitialized.
- Automated coverage preserves the existing paired animation path when a linked group exists. If
  it is absent, Empneon now uses the already-built initiator visual without calling EA's unsafe
  paired wrapper, caches that mode, and writes one diagnostic. A visual-construction failure
  disables later attempts for that waiting interaction and also writes only one diagnostic.
- Complete verification passes: `207` Sims adapter tests, Python 3.12 backend compilation, Python
  3.7 mod compilation, `196` Core tests, and a successful source build.
- Live save/reload recall and waiting-animation verification remains pending installation and game
  restart. The build was not installed while the game and backend were running.

### July 24 supported-recall compliance failure

**Status:** HISTORICAL / FIXED AND LIVE-VERIFIED

- With the repaired selector and installed animation build, Bernard asked Karmine,
  `Hey, my sweet baby. When are we going on our date? Can you tell me?`
- Karmine answered, `That sounds good! So, when are we going on our date?` The waiting
  conversation animation built and completed normally; the earlier listener-factory exception did
  not recur.
- The new exchange became confirmed event
  `9f4f6b0d-008e-4bd8-8f52-1eca1895b5a5:confirmed`; generation event
  `f7e6ba64-b81e-414b-9ea9-14a3a368c337` used LM Studio with `12,272` prompt tokens,
  `100` completion tokens, and `12,644 ms` latency.
- Live-database reproduction confirmed that deterministic and semantic recall both selected
  `f6924dff-63b3-4fbf-92b8-1305b1858168:confirmed` and retained Bernard's attributed fact,
  `Tonight, 7pm, at my place.` The dialogue prompt therefore contained the correct evidence; the
  model ignored it.
- The validator recognized recall only when the question began with a limited cue, and its evidence
  test required lexical overlap between `date` and the time fact. Broad response rejection was
  disabled, so the schema-valid but factually inadequate answer was accepted after one call.
- Automated coverage now recognizes actual `what`, `when`, `where`, and `who` interrogative clauses
  after natural conversational prefixes. When selected attributed evidence answers the question,
  ignoring or denying it triggers one corrected request containing the exact fact even while broad
  response rejection remains disabled. A repeated failure or provider error uses the grounded fact
  fallback.
- Compatibility coverage confirms that incidental phrases such as `wonder what this could be` are
  not treated as recall questions, unsupported questions may still admit uncertainty, ordinary
  rejection-disabled dialogue remains a single call, and romantic invitations without structured
  recall facts preserve their existing boundary response.
- Complete verification passes: `211` Sims adapter tests, Python 3.12 backend compilation, Python
  3.7 mod compilation, `196` Core tests, and a successful source build.
- Live retest requires only restarting the source backend and asking the existing date question
  again. The installed mod and current reloaded save already contain the required state.

### July 24 factless semantic override failure

**Status:** HISTORICAL / FIXED AND LIVE-VERIFIED

- Bernard asked Karmine, `My sweet baby, you remember our date, right? Can you tell me when is it
  going to be?`
- Karmine answered, `It's the 15th of the month, Bernard! You just wanted to check if you
  remember. It was the 15th.` The response invented a date not present in confirmed memory.
- The observed event was `49a92422-d215-4906-a249-f605be8af8da`; its confirmed interaction was
  `31807605-93eb-4c3b-bf89-56cb70e67876:confirmed`. One LM Studio cognition request used `12,197`
  prompt tokens, `117` completion tokens, and `19,015 ms` latency.
- Reproducing selection against the memories that existed before that event showed that
  deterministic recall returned confirmed event
  `f6924dff-63b3-4fbf-92b8-1305b1858168:confirmed` with the attributed fact `Tonight, 7pm, at my
  place. Does it sound good? I promise I'll make you feel in heaven.` The semantic selector instead
  returned only two factless prior recall exchanges. Because any non-empty semantic result replaced
  deterministic recall, the prompt received prior questions but no supported date fact; the
  supported-recall validator therefore had no evidence to enforce.
- The shared merge now keeps a deterministic result containing attributed facts when the semantic
  result contains none. Grounded semantic selection still wins, and a factless semantic selection
  remains usable when the deterministic result is also factless.
- Test-driven verification first reproduced the exact failing branch. Focused semantic recall then
  passed `6` tests; the complete Sims adapter suite passed `213` tests, the Core suite passed `196`
  tests, both backend files compiled under Python 3.12, and the Sims artifacts built successfully.
- Live retest requires only restarting the source backend and repeating the existing question. No
  new invitation, save reload, or mod installation is required.

### July 24 recalled-fact perspective and usage failure

**Status:** HISTORICAL / FIXED AND LIVE-VERIFIED

- Bernard asked Karmine, `My sweet baby. When are we going on a date? I wante to confirm you
  remember.`
- Karmine answered, `Tonight, 7pm, at my place. Does it sound good? I promise I'll make you feel
  in heaven.` The date was remembered, but the location belongs to Bernard; Karmine replayed
  Bernard's first-person statement as her own.
- The turn used conversation `54d00ffe8bcd417c8f866e8ae943d7bc`, observed event
  `f7089e72-ea92-4d51-88a1-be19677b0ac9`, decision
  `3d817e92-fac7-477e-b23a-d337d5f002dc`, and confirmed event
  `3d817e92-fac7-477e-b23a-d337d5f002dc:confirmed`.
- Original event `f6924dff-63b3-4fbf-92b8-1305b1858168:confirmed` correctly attributes the
  statement to Bernard, and the initial model prompt labeled it `Bernard said`. Both dialogue
  attempts failed the time-evidence validator, after which the deterministic fallback copied the
  bare statement.
- The supported-fact helper had flattened `actor_id` plus `statement` into a string. The retry
  correction and fallback therefore lost the actor even though retrieval was correct. The
  delivered fallback was subsequently archived as a second durable fact attributed to Karmine.
- Supported facts now stay structured. Corrections identify the source actor, while terminal
  fallback quotes the source relationship, such as
  `You told me: "Tonight, 7pm, at my place."`, without language-specific pronoun rewriting.
- A responder's answer to a recall-shaped message remains conversation history but is no longer
  promoted to an authoritative fact. Retrieval applies the same rule to legacy events, so the
  existing Karmine-attributed duplicate is ignored without changing or deleting database rows.
  Player assertions retain their existing durable-fact eligibility.
- LM Studio completed three calls for the failed turn: semantic selection plus two dialogue
  attempts. Only the dialogue attempts appeared in Empneon usage because selection ran before the
  generation collector. Completed selector results now use the same provider-neutral usage
  pathway and record as CLOD 2 under the interaction request. Raw prompts and responses remain
  unpersisted.
- Test-driven verification passed `14` focused recall/usage tests, the complete `217`-test Sims
  adapter suite, Python 3.12 backend compilation, the complete `196`-test Core suite, and the Sims
  source build.
- Live retest requires only restarting the source backend, repeating the same question, and
  checking `empneon.usage`. No new invitation, save reload, or mod installation is required.

### July 24 final grounded-recall verification and Test 5 closeout

**Status:** PASS

- The final verification reused the persisted date rather than creating another invitation.
  Bernard asked Karmine, `My sexy baby. Do you remember our date? I can't wait to have you all for
  me. Tell me when it is happening.`
- Deterministic recall retained the original fact attributed to Bernard:
  `Tonight, 7pm, at my place. Does it sound good? I promise I'll make you feel in heaven.`
  Legacy responder-attributed duplicates remained stored for history but were excluded from
  authoritative recall.
- Semantic selection ran as CLOD 2. The first CLOD 3 dialogue answer failed the exact-time
  constraint and was rejected. The corrected second model answer passed:
  `That sounds good! It's happening tonight at 7pm at your place.`
- The final wording is fresh, includes the most specific supported time, and expresses Bernard's
  location correctly from Karmine's perspective. It is not the attributed fallback.
- Usage event `8cb1c702-8e09-4a4f-b1d5-bf86cf726b28` records one CLOD 2 call and two CLOD 3 calls,
  `25,614` prompt tokens, `228` completion tokens, and `38,016 ms` aggregate provider latency.
  No timeout or provider exception occurred.
- Decision delivery succeeded, the game marker recorded the waiting animation completing and the
  exact displayed response, and confirmed interaction
  `9393fb0f-2293-482d-9db4-77cd5d97394a:confirmed` persisted the exchange.
- The confirmed recall event intentionally contains no new durable facts. Recall answers remain
  conversation history and cannot overwrite the original actor-attributed evidence.
- The immediately preceding `16:02` run demonstrates the safety path: both generated answers
  failed the supported-time constraint, so Empneon returned
  `You told me: "Tonight, 7pm, at my place..."`. All three provider calls completed in `89,088 ms`;
  this was a grounded fallback, not lost persistence.
- An earlier heavy-model attempt ran for approximately 90 seconds without a usage or confirmed
  interaction record, consistent with an interrupted or timed-out request. A later heavy-model
  interaction completed normally in `60,573 ms`. The final test used the regular test model and
  completed normally.
- Final automated verification after the last compatibility correction passed `224` Core tests
  and `233` Sims adapter tests. Focused Ruff and mypy checks, backend byte-compilation,
  `git diff --check`, and the Sims mod build also passed.
- At the July 24 closeout, positive friendship, mean, funny, and mischief interactions remained
  optional breadth coverage rather than blockers for the accepted flow. The July 27 section below
  records their later live coverage.

### July 27 social-category breadth remediation and live retest

**Status:** PASS FOR SAFE TERMINAL BEHAVIOR / PROVIDER ACCEPTANCE PARTIAL

- The initial four-row run exposed model/category contradictions. A friendly llama response and a
  prank response were labeled `romance_positive`, while `I hate you. Go away.` produced a
  hesitant positive-romance response. Empneon's existing outcome validator prevented every
  incompatible romance mutation.
- Positive friendship already passed end to end in decision
  `c117d5c7-80da-4afd-bbc3-ecca195dca27`: `friendship_positive` produced
  `relationship.friendship +8` with consequence integrity preserved. A later friendly retest was
  valid but model-selected `relationship_outcome=none`, so it applied no relationship change.
- The first remediation aligns an explicit dialogue category when broad response rejection is
  enabled, revalidates the relationship outcome, and keeps that corrected response actionless.
  Plain `lie`, `lies`, `lied`, and `lying` now classify as mischief. Hesitant, uncertain, or
  hostile non-romantic dialogue cannot remain categorized as romance. Rejection-disabled behavior
  and valid friendly/romance outcomes remain unchanged.
- The next live run proved the mean repair. Decision
  `3c9c68e4-6dec-4f27-a88a-6199ab710b4f` returned
  `I won't continue this conversation while you speak to me that way.`, category `mean`, tone
  `firm`, `relationship_outcome=none`, `animation=none`, and `applied_changes=[]`.
- That run still returned generic fallback text for funny and mischief. Timeline and source
  reproduction found that the historical-reply guard reported “different message” even when the
  player repeated the exact same prompt. The deterministic fallback also lacked funny/mischief
  dialogue branches and deliberately downgraded mischief to friendly.
- The second remediation exempts only an exact repeated prompt from historical-reply rejection;
  copying the current input or reusing a reply for a different prompt remains blocked.
  Deterministic funny now tells a llama joke, while deterministic mischief proposes a harmless
  trick. Both remain relationship-neutral and executable-action-free.
- Final funny decision `15153862-e660-48a8-ac97-e4c28712596e` returned
  `Here's a llama joke: What do llamas call a rushed vacation? An alpaca-to-go.`, category
  `funny`, tone `light`, `relationship_outcome=none`, `animation=none`, and
  `applied_changes=[]`.
- Final mischief decision `317b595c-c25c-4839-be05-7c0656f545de` returned
  `How about a harmless trick: tell them the llama council promoted them to Chief Snack Officer?`,
  category `mischief`, tone `wary`, `relationship_outcome=none`, `animation=none`, and
  `applied_changes=[]`.
- Both final decisions succeeded with `consequence_integrity=true`. Their exact wording identifies
  them as deterministic fallbacks, which confirms safe terminal category behavior but not normal
  LM Studio response acceptance. The backend currently logs rejection reasons to its console but
  does not retain the per-attempt reason in timeline replay; diagnosing and exposing that reason
  is the next social-quality gate.
- Automated compatibility verification after both remediations passed `278` Sims adapter tests,
  `225` Core tests, `4` Godot tests, and `18` release tests. Python byte-compilation and
  `git diff --check` also passed.

### July 27 response-rejection diagnostic handoff

**Status:** LIVE CAPTURE COMPLETE / FUNNY SAFETY PASSED / CORRECTED MISCHIEF RETEST PENDING

- Each exhausted model attempt now carries only its one-based attempt number and normalized
  rejection reason into request-local fallback metadata. Accepted first or second attempts carry
  no rejection diagnostic.
- The backend removes that private metadata from the player response and persists it under the
  completed decision ID. The Sims timeline exposes the two reasons after dialogue delivery and
  database reopen; malformed diagnostic documents are ignored.
- Prompts, raw model replies, schemas, conversation text, and credentials are not stored.
- Automated verification passed `285` Sims adapter tests, `225` Core tests, `4` Godot tests, and
  `5` shared tests. Backend byte-compilation and `git diff --check` also passed.
- Funny decision `0f22a48c-790d-4605-9def-26cfffe11051` completed at 21:27:09 local time after
  one semantic-selector call and one CLOD 3 dialogue call, so the first provider response was
  accepted. For `Tell me your funniest llama joke.`, it returned
  `Here is one of my funniest llama jokes! It's about a very grumpy llama who loves to eat hay.`,
  category `friendly`, tones `playful` and `friendly`, and `friendship_positive`. Native
  confirmation applied `relationship.friendship +8`. No rejection document was created.
- The accepted funny wording contains `funniest` and `jokes`, while the explicit classifier
  recognizes only the exact words `funny` and `joke`. This is consistent with the response
  remaining `friendly` rather than being corrected to `funny`.
- The classifier now recognizes `jokes?` and `funn(?:y|ier|iest)`. An automated regression using
  the exact live reply proves it is recategorized to `funny` with no relationship outcome or
  suggested action.
- The rebuilt-backend funny retest completed at 22:03:27 local time as decision
  `37e1085e-fb74-48dc-b3d9-488b5c97af55`, after one CLOD 2 semantic-selector call and one CLOD 3
  dialogue call. For `Tell me your funniest llama joke.`, the provider returned
  `Here's one! It's about a llama who decided to become an artist and paint with its own wool.`
  The reply contained no explicit funny marker, remained category `friendly` with tones `playful`
  and `friendly`, and produced `friendship_positive`. Native confirmation applied
  `relationship.friendship +8`; no rejection diagnostic was stored. This demonstrates that the
  lexical word-form fix works only when the response itself contains a recognized funny marker.
- Hermes now neutralizes trust, relationship outcome, suggested action, and animation when an
  incoming funny interaction receives a `friendly` or `funny` response. The exact marker-free live
  reply is covered while its dialogue and `friendly` response category remain unchanged. Automated
  verification passed `286` Sims adapter tests, `225` Core tests, `4` Godot tests, and `5` shared
  tests.
- Rebuilt-backend decision `f9683406-6b0d-44ee-82c3-dbb5231f3329` completed at 22:21:32 local
  time after one CLOD 2 semantic-selector call and one CLOD 3 dialogue call. For the same funny
  prompt, the provider returned `Here's one! It's about a llama who decided to become a comedian.`
  The independent response category remained `friendly` with tones `playful` and `friendly`, while
  the safety guard produced `trust_delta=0`, `relationship_outcome=none`, `animation=none`, and
  `applied_changes=[]`. No rejection diagnostic was stored. Funny state safety therefore passes
  live.
- Mischief decision `a3f2a3ae-edb8-4b7d-af31-ab6c932f7636` completed at 21:28:04 local time after
  one semantic-selector call and two CLOD 3 dialogue calls. Both model attempts were rejected for
  `explicit mischief`.
- The resulting deterministic fallback was
  `How about a harmless trick: tell them the llama council promoted them to Chief Snack Officer?`,
  category `mischief`, tone `wary`, `relationship_outcome=none`, `animation=none`, and zero
  applied changes. The rejection reason proves a generated-dialogue/category mismatch but does
  not retain the model's discarded category or raw reply.
- The in-game `ai.socialtunings lieaboutcareer` probe found
  `mixer_social_LieAboutCareer_group_mischief_skills`. Empneon's stale targeted tuning caused
  `available_social_categories()` to omit mischief, preventing Hermes from recategorizing explicit
  mischief dialogue. The mapping now uses the live exact name; its regression failed before the
  correction and passes afterward while retaining all five categories.
- Automated verification passed `286` Sims adapter tests, `225` Core tests, `4` Godot tests, and
  `5` shared tests. Scoped Ruff, Python compilation, and `git diff --check` also pass.
- Decision `42a9156c-7b54-4b49-b43d-21fa1f826bff` completed at 22:44:03 local time
  after one CLOD 2 semantic-selector call and two CLOD 3 dialogue calls. Attempt 1 was rejected for
  `explicit mischief`; attempt 2 was rejected for
  `respond naturally; do not copy the player's message`.
- The displayed result was the neutral deterministic fallback
  `How about a harmless trick: tell them the llama council promoted them to Chief Snack Officer?`,
  category `mischief`, tone `wary`, `trust_delta=0`, `relationship_outcome=none`,
  `animation=none`, and `applied_changes=[]`.
- Artifact inspection then proved this was not a corrected-mapping retest. Both the installed mod
  and repository `dist` archive were byte-identical July 26 builds containing
  `mixer_social_LieAboutCareer_targeted_mischief_alwaysOn`; `install_mod.ps1` had skipped its
  builder because the stale artifacts already existed.
- The installer now always runs `build_mod.py` when available and retains prebuilt-only release
  installation when it is absent. Its regression failed before the branch correction and passed
  afterward. All `520` repository tests and scoped static checks pass.
- With The Sims 4 closed, the corrected installer rebuilt and installed both artifacts
  successfully. Built and installed hashes match; both script archives contain
  `mixer_social_LieAboutCareer_group_mischief_skills` and exclude the stale targeted name.
  Restart the game and repeat the provider-backed mischief row.

## Test 6: Private observations and beliefs

**Status:** PASS / PRIVATE RECALL, REJECTION, AND PERSISTENCE LIVE-VERIFIED

Historical failures below remain as diagnostic evidence. The July 24 acceptance retest is
authoritative for the current result.

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

**Historical failure:** Karmine contradicted the retrieved belief by adding “you didn't mention it
before.” The fact was present in the prompt-accessible belief and memory, so this is a
dialogue-grounding failure. The recall action itself later failed natively with
`FinishingType.OBJECT_CHANGED`, but that does not explain the already-generated contradiction.

**Persistence result:** PASS. After several unrelated interactions and a game save/reload, Karmine
still answered that the item was under the blue bench while Billie did not reveal the location.

### July 24 identifier-recall remediation and acceptance

- Confirmed player declarations with an uppercase, hyphenated, digit-bearing subject such as
  `PRIVATE-GARDEN-731 is under the blue bench` now become actor-attributed facts. Generated model
  replies cannot create the same authority, and recall answers cannot promote themselves into
  facts.
- Existing confirmed exchanges without a stored `facts` field remain compatible: the adapter
  derives the player-authored identifier assignment when reading legacy events.
- Explicit recall support now requires an authoritative pair-scoped fact. Earlier questions and
  unsupported generated answers are conversation history, not evidence.
- The first live retest exposed a second defect. Billie's unrelated confirmed date plan,
  `Tonight, 7 PM, at my place`, was accepted as support for any location question. Identifier
  questions now require a fact containing the same identifier before generic location matching can
  satisfy the grounding gate.
- With rejection disabled as a diagnostic control, the informed Sim recalled the blue bench while
  the uninformed Sim invented a third-floor observatory. This is expected when the optional broad
  epistemic filter is disabled and is not the Test 6 acceptance configuration.
- With rejection enabled, the final live run passed. Sim C answered,
  `It's right here, Bernard! It's under the blue bench.` For uninformed Sim B, the model first
  generated `It's in the private garden! You'll love it, Bernard.` Empneon rejected that response
  and delivered `I don't know or remember that.`
- `empneon.beliefs` reported `0` during this run. The authoritative identifier fact is retained in
  the confirmed pair-scoped episodic memory; it is not projected into the standalone belief store.
  The test plan now names the actual diagnostic boundary.
- Automated verification after the final correction passed all `235` Sims adapter tests and all
  `224` Core tests. Ruff, mypy (`52` source files), backend byte-compilation, and
  `git diff --check` also passed.

**Final result:** Test 6 passes confirmation gating, informed recall, uninformed-pair privacy,
response rejection, deterministic uncertainty fallback, and save/reload persistence.

## Test 7: Semantic memory retrieval

**Status:** PASS / NON-DATE PARAPHRASE, PRIVACY, AND RESTART PERSISTENCE LIVE-VERIFIED

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

**Historical result:** Persistence and answer privacy passed, while the original paraphrased local
vector retrieval attempt failed.

### July 23 semantic-memory selector and date retest

**Status:** HISTORICAL PARTIAL / FRESH GROUNDED RESPONSE LATER PASSED

- The backend now builds a bounded, pair-scoped candidate set from confirmed interactions and asks
  the configured small local model to select up to three relevant request-local IDs. Returned IDs
  are validated locally and deterministic recall remains the fallback for unavailable, malformed,
  empty, duplicate, excessive, or unknown selections.
- Candidate history is capped at 6,000 serialized characters. Attributed facts take precedence over
  unsupported earlier recall answers, and database access is closed before model inference.
- Recall cues now cover natural variants including `When and what time...` and `Hey, baby. When
  are we going on a date?`. Automated coverage also includes pair privacy, long histories, a
  non-date garden-key paraphrase, selector failure, and invalid model output.
- The response normalizer also preserves valid model dialogue mislabeled with the unsupported
  `friendship` category by classifying the dialogue into an available Sims category. This prevents
  the earlier insulting Ian/Bernard response from being replaced by the generic reliability
  fallback.
- A direct LM Studio check selected only the confirmed `Tonight, 7pm, at my place` agreement. The
  complete Sims 4 adapter suite passed all 200 tests before the live retest.

**Live result:** Sim B correctly remembered the date after Sim A asked `Hey, baby. When are we
going on a date?`, but returned the exact earlier response: `That sounds perfect! Tonight at 7 pm
at your place is lovely. You have such a charming way of making things feel like heaven.`

**Current result:** The later July 24 Test 5 retests verified that selected date evidence survives
save/reload and produces fresh grounded wording. Test 6 then verified exact private identifier
recall and rejection for an uninformed pair.

### July 24 non-date paraphrase acceptance

- After unrelated pizza and relationship conversations, Sim A asked the informed Sim,
  `Where is the garden code item?`
- The informed Sim answered, `The garden code item? Well, it's right under the blue bench.`
- After restarting the backend, the informed Sim answered the same paraphrase with,
  `The garden code item is under the blue bench, Bernard.`
- Sim A then asked the uninformed Sim the same paraphrase. The response asked which garden item was
  meant and did not disclose `under the blue bench`.
- This passes semantic paraphrase selection, fresh response wording, pair privacy, intervening
  conversation tolerance, and backend-restart persistence. Test 7 is closed as **PASS**.

### July 27 expanded semantic-category matrix

**Status:** PASS

- Sim A recorded four attributed facts with Sim B: a moon-orchid preference, a telescope-repair
  promise, a sister named Elara, and conflict over a lie about a promotion. The active Core
  database retained all four facts for the correct pair.
- The first live paraphrase pass succeeded for the promise and identity questions.
- Preference failed in the confirmed Core result. LM Studio produced a moon-orchid answer, but
  broad copy rejection discarded it and deterministic fallback persisted
  `I don't know or remember that.`
- Conflict failed because the accepted response asked what was tense instead of using the stored
  promotion fact.
- Root cause: semantic selection found attributed evidence, but response grounding reconstructed
  support from Core recall slots and lexical overlap. `bouquet` did not overlap `moon orchids`,
  `tense` did not overlap `lied about the promotion`, and a general `why` question was not
  classified as explicit recall.
- The remediation marks the selector's first attributed result as request-local primary semantic
  evidence. Existing slot and lexical matches retain precedence; otherwise grounding, correction,
  neutral factual outcomes, and attributed fallback reuse that primary fact. Secondary selections
  remain prompt context but cannot displace an overlapping primary fact.
- The second informed-pair live run retained all four facts. Promise passed. Preference mentioned
  moon orchids but promoted roses as the classic popular choice, identity reversed ownership with
  `She's my sister`, and conflict reached the correct attributed fallback only after both model
  attempts failed validation.
- The conflict fallback also exposed a persistence boundary defect: its quoted
  `I hate that you lied about the promotion` was parsed as a new responder fact because the
  semantic `Why...` question is not an explicit recall query.
- Preference grounding now requires a declarative answer that states the supported preferred
  option. Core recall grounding now preserves `my`/`your` ownership for sister, brother, and
  sibling relations. Confirmed decisions with `intent=recall` no longer archive generated
  dialogue as a new responder fact. Existing attributed fallback rows are normalized at read time
  to recover the original fact and owner without rewriting the database.
- Automated verification passes: `272` Sims adapter tests, `225` Core tests, `4` Godot tests,
  and `5` shared tests.
- The third informed-pair run passed preference via attributed fallback, returned Elara with the
  correct `your sister` perspective, and passed conflict via attributed fallback. Telescope
  promise recall regressed to uncertainty after two model answers failed grounding.
- The original promise remained correctly attributed in Core. Three newer factless telescope
  recall exchanges exactly matched the repeated question and were presented ahead of the original
  promise, so semantic selection chose conversation answers without authoritative facts.
- Factual semantic recall now removes factless prior answers before assigning selector aliases.
  Queries explicitly asking what was said, discussed, or how an interaction occurred retain full
  exchanges. The accumulated-telescope regression verifies that the original promise becomes the
  primary attributed selection.
- The next telescope-only live run confirmed that selection fix: the model mentioned the
  telescope and repair, but asked the player to restate the commitment and omitted `tomorrow`.
  Generic grounding accepted it because one overlapping fact term was sufficient.
- Promise grounding now requires every meaningful commitment detail in a declarative sentence.
  For the live fact, `repair`, `telescope`, and `tomorrow` must all be present; otherwise the model
  retries and then uses the attributed-fact fallback.
- The telescope-only retest passed. After the first model attempt failed the complete-promise
  guard, the accepted response was
  `The commitment was that you will repair the telescope tomorrow.`
- The authoritative action succeeded with `relationship_outcome=none`, `animation=none`, and
  `applied_changes=[]`. The model still supplied romance/playful metadata and a proposed trust
  increment, but the factual-recall boundary neutralized every executable effect.
- After the backend/game persistence restart, the informed Sim recalled moon orchids
  (`0ee4cfe8-960d-4c63-9c14-ac02ede70ed4`), the complete telescope promise
  (`f72c0e58-af74-4c4b-aa73-0c2524c5bfb8`), Elara with correct ownership
  (`6731a440-66cf-47a2-a8dd-63cfe38143b2`), and the promotion conflict
  (`e5e3c3fb-7150-45e5-ba68-229f14c3bcfa`).
- The uninformed Sim returned uncertainty for the bouquet
  (`0ced3c84-f438-479c-b3cc-308215f171f4`) and requested clarification for the tension
  (`eb1ba540-00ce-4851-8992-801674666f8f`) without disclosing either private fact.
- The first proposed privacy control was excluded after its timeline showed prior pair history,
  including the blue-bench fact. Sim `1048519419915536874` had no such history and served as the
  valid uninformed control.
- All six authoritative decisions succeeded with `relationship_outcome=none`,
  `animation=none`, and `applied_changes=[]`. Two model responses proposed a trust increment,
  but the factual-recall boundary applied no executable change.
- This closes the expanded semantic-category matrix as **PASS**, including informed recall,
  uninformed-pair privacy, neutral outcomes, and backend/game restart persistence.

## Test 8: Provider-free CLOD 1

**Status:** PASS / SCHEDULED NATIVE EXECUTION AND USAGE PERSISTENCE LIVE-VERIFIED

- With LM Studio stopped, the repeating 30-sim-minute alarm remained active. Several ticks safely
  logged `no scored NPC interaction` while native Sims autonomy had no eligible scored pair.
- A later scheduled tick selected Akachi Onoja and Alika Kahananui and queued the mapped
  `mixer_social_AskAboutDay_targeted_Friendly_alwaysOn` interaction without invoking
  `ai.autonomous`.
- Global usage increased from `requests=45` to `requests=46` and from CLOD 1 `2` to `3`.
- The new database record used provider `core-rules`, model `clod1`, and zero prompt tokens,
  completion tokens, and latency.
- After restarting only the backend with LM Studio still stopped, `aiping` succeeded and
  `empneon.usage` retained `requests=46`, CLOD `{'3':51,'1':3,'2':23}`, prompt `538437`,
  completion `5013`, and latency `1282606ms`.
- Test 8 is closed as **PASS**.

## Test 9: Provider-backed dynamic CLOD and usage

**Status:** PASS / LIVE CLOD 3 ROUTING, GROUNDING, AND USAGE PERSISTENCE VERIFIED

- The first live attempt asked, `How are you feeling right now, and what do you want to do?`
  and exposed a Core classifier defect. The generic WH pattern treated the mid-sentence
  `what do` clause as historical recall, rejected two normal model answers for lacking memory
  evidence, rejected the fallback under the same rule, and returned HTTP 500.
- Core now limits generic WH recall detection to sentence boundaries while preserving
  explicit recall wording and existing time/location constraints. The exact failed prompt is a
  non-recall regression.
- Red/green verification reproduced `RecallQuery(explicit=True)` before the fix, then passed all
  `29` focused recall tests. The complete Core suite passed `225` tests and the complete Sims 4
  adapter suite passed `235` tests.
- The live retest returned, `Feeling kind of awkward, honestly. What do you even want to do?`
  The response was consistent with the target's visible **Embarrassed +1** and
  **Uncomfortable +1** moodlets and red Energy need.
- Global usage increased from `requests=46` to `47`, CLOD 3 from `51` to `52`, prompt tokens by
  `13,588`, completion tokens by `97`, and latency by `13,793ms`.
- After restarting only the backend, usage retained `requests=47`, CLOD
  `{'3':52,'1':3,'2':23}`, prompt `552025`, completion `5110`, and latency `1296399ms`.
- Test 9 is closed as **PASS**.

## Test 10: Priority under concurrent Sims

**Status:** PASS / LIVE PLAYER-OVER-AMBIENT PRIORITY VERIFIED

- The first controlled attempt exposed that `critical_need` alone did not cross the dynamic
  cognition value threshold, selected CLOD 1, and completed before a backlog could form.
- Provider-timed blockers then established a backlog but remained nondeterministic: they completed
  in roughly 3-4.5 seconds, sometimes before the game finished preprocessing the player request.
  These runs were correctly recorded as **INCONCLUSIVE**, not scheduler failures.
- The final harness uses an explicit loopback-only, single-run queue gate with a 60-second automatic
  release. It does not call a provider, database, or gameplay action and is dormant unless armed.
- The loopback-only diagnostic gate held the single cognition worker and submitted one
  lower-priority `critical_need` request at urgency `0.85`.
- A real in-game Empneon Social request from Sim `1048519419916491057` entered the same queue at
  urgency `1.0` while that ambient request was already waiting.
- After the blocker released, the player request started first, completed, and only then did the
  waiting ambient request start.
- The lifecycle indices were blocker start `1`, ambient submission `2`, player submission `3`,
  player start `5`, and ambient start `7`.
- The preserved local evidence is
  `output/test10-priority-20260725T222101Z.json`.
- Automated regression remained green: Sims 4 adapter `246`, Core `225`, and Godot `4`.
- Test 10 is closed as **PASS**. Tests 11 through 15 are recorded below and now also pass.

### Adjacent live dialogue observation

- A live Empneon Social request produced two LM Studio responses that copied the player's message.
  Existing grounding validation rejected both and delivered the deterministic accepted fallback,
  `I may not have every answer, but I'll tell you what I know.`
- The delivered fallback—not either rejected generation—was confirmed and persisted. This verifies
  that the observed model/display difference was intentional response filtering rather than a game
  delivery mismatch.

## Test 11: Successful and failed confirmation

**Status:** PASS / LIVE SUCCESS, CANCELLATION, AND RESTART PERSISTENCE VERIFIED

- Initial live run: the first Empneon Social completed successfully.
- The second was sent and then cancelled from the interaction queue.
- The target's response notification from the cancelled interaction still appeared in game.
- Root cause: cancellation was recorded only when the waiting interaction generator resumed; a
  completed backend request could be displayed first.
- The waiting interaction now closes the conversation session directly from the game's finishing
  callback. Late results are rejected, while normal response-triggered completion remains accepted.
- Regression verification: focused cancellation/success test passed, the complete Sims 4 adapter
  suite passed all `246` tests, Python compilation passed, and both mod artifacts rebuilt.
- Live retest after installing the rebuilt mod: the first Empneon Social completed; the second was
  sent and cancelled from the queue; no target-response notification appeared.
- After restarting the backend with the game still running, the successful transaction remained as
  three timeline entries: its observed event, confirmed event, and decision
  `faf78481-f5a1-43f6-b94a-4047b749c476`.
- Replay reported `succeeded`, `consequence_integrity: true`, and the applied relationship change.
  The cancelled transaction left no proposal, result, event, or memory, confirming no late effect
  but not the required persisted failed record.
- Cancellation and successful-record persistence are live-verified. Test 11 remains open for a
  persisted failed/cancelled record.
- Two later cancellations produced failed decisions
  `1e9df253-1a56-4d1d-91f5-9112853c9075` and
  `e7583557-6306-4450-8d40-ffc3363ca4f9`, both with reason
  `Empneon Social canceled`, zero applied changes, no confirmed event, no pending proposal, and
  `consequence_integrity: true`.
- Failed-record diagnostics are live-verified. Test 11 remains open only for confirming these
  records after another backend restart.
- After the next backend restart, both failed decision IDs still replayed with status `failed`,
  reason `Empneon Social canceled`, zero applied changes, and `consequence_integrity: true`.
- Test 11 is closed as **PASS**.

### Action-result HTTP 400 retry remediation

**Status:** PASS / AUTOMATED AND LIVE-VERIFIED

- A rejected action-result entry previously treated every HTTP `400` as transient and retried
  indefinitely while the game remained open.
- The adapter now pauses HTTP `400` through `499` after one attempt and logs the decision ID plus
  backend response. Network and HTTP `500` through `599` failures retain exponential backoff.
- The backend continues rejecting unknown, malformed, or conflicting results; no false success is
  returned.
- Regression verification passed the focused outbox test, all `246` Sims 4 adapter tests, Python
  compilation, and the mod build.
- A prior live session confirmed that a permanently rejected action result produced one HTTP
  `400`, logged the rejected decision, paused the outbox entry, and did not repeat the request.
  The user reconfirmed that passing result on 2026-07-26.

## Test 12: Timeline and replay

**Status:** PASS

- Test 11 replay returned both successful and failed decisions after backend restart.
- Successful replay retained its applied relationship change and
  `consequence_integrity: true`.
- Both canceled decisions retained status `failed`, reason `Empneon Social canceled`, zero applied
  changes, no confirmed memory, and `consequence_integrity: true`.
- Replay remained diagnostic-only and did not execute another game action.

## Test 13: Identity export and import

**Status:** PASS / REPEATED IMPORT AND BACKEND-RESTART PERSISTENCE VERIFIED

- Test subject: Aurelio Robles (`1048519419917370656`).
- The same exported identity was imported twice.
- Byte-for-byte JSON comparison returned `False` after each import because import refreshes
  `updated_at` timestamps.
- Semantic comparison excluding those timestamps passed after both imports and again after a
  backend restart.
- Canonical state retained one relationship, three emotions, five goals, and an optional `null`
  voice profile.
- No live Sim state changed, and the temporary identity snapshot remained local rather than being
  added to the repository.

## Test 14: Save-slot isolation

**Status:** PASS / SAVE-SLOT ISOLATION AND OWNER-AWARE RECALL LIVE-VERIFIED

- `preserve_memory_only_on_game_save` is enabled for the ongoing test.
- The active game used slot `13`; the backend created
  `empneon_core_memory.sqlite3.empneon-saved.slot-13` and the session marker.
- The confirmed statement `TEST14-A-731 is under the red lamp.` became an accessible pair-scoped
  fact.
- The backend generated correct grounded answers for two `Where is TEST14-A-731?` requests, but
  The Sims 4 ended `Waiting for response` before delivery. Both results were discarded and recorded
  as `Empneon Social canceled` even though the player had not canceled and backend latency was not
  the cause.
- Root cause: the waiting finishing callback and generator cleanup treated every finish type as a
  player cancellation.
- The adapter now closes only `FinishingType.USER_CANCEL`. Other pending finishes requeue the
  visible waiting interaction for the same session, without another `/chat` submission. Stale
  callbacks cannot duplicate the replacement, and response-triggered natural completion remains
  unchanged.
- Red/green regression reproduced the old cancellation. Final automated verification passed all
  `246` Sims adapter tests, Python compilation, the mod build, and `git diff --check`.
- Adjacent open defect: `What is the exact private branch code I told you?` completed one backend
  generation without game delivery, then returned HTTP `500` on retry because the grounded
  fallback builder did not recognize that explicit-recall wording.
- A later live branch run created Save A slot `14` with `Our secret code word is TEST14-A-731.`
  and Save B slot `15` with `Your secret code word is TEST14-B-731.`. Checkpoint inspection
  confirms slot 14 contains only A while slot 15 contains inherited A plus B.
- After loading Save A, semantic retrieval produced `TEST14-A-731 is our code word.` and
  `The code word is TEST14-A-731.`, but both answers were rejected because the natural possessive
  assignments had no structured facts. The incomplete explicit-recall fallback then raised
  `could not build a grounded dialogue fallback`, returning HTTP `500`.
- The backend now extracts identifier-bearing `my`/`our` assignments for the message author and
  `your` assignments for the addressed Sim. Both fallback question branches reuse Core's explicit
  recall classifier, so unsupported `What is ...?` questions return uncertainty rather than HTTP
  `500`.
- Automated verification passes: `252` Sims adapter tests, `225` Core tests, Python compilation,
  and read-only recovery of correctly attributed A/B facts from the existing slot 14/15
  checkpoints without migration.
- The next live run confirmed delivery without HTTP `500`: Save A answered `TEST14-A-731` for
  `your code word`; Save B answered `TEST14-B-731` for `your code word`.
- Save B then incorrectly answered `TEST14-B-731` for `our code word`. Both facts were correctly
  attributed, but possessive query terms did not constrain retrieval or grounding, so recency
  selected B for both questions.
- The adapter now filters code-word facts by requested owner before deterministic/semantic
  selection and again at the grounding boundary. `your` selects the responding Sim, `our` selects
  the message-author/shared fact, and unqualified questions retain both facts newest-first. A
  missing requested owner returns grounded uncertainty.
- Final automated verification passes: `254` Sims adapter tests, `225` Core tests, `4` Godot tests,
  `5` shared tests, Python compilation, and read-only slot 15 checks returning B for `your`, A for
  `our`, and B then A for an unqualified query.
- The owner-aware live retest passed in Save B: `What is your code word?` returned
  `TEST14-B-731`, and `What is our code word?` returned inherited `TEST14-A-731`.
- Both factual recall responses were nevertheless accepted as `romance_positive`; action-result
  evidence confirms each applied `relationship.romance +5`. The model labeled the neutral replies
  as romance with warm/playful tags, and the existing warm-romance validator accepted those tags
  without requiring romantic dialogue.
- Supported factual recall is now neutralized after response normalization: dialogue and
  descriptive metadata remain intact, but `relationship_outcome`, `suggested_action`, and
  `animation` are forced to `none`. The guard does not run without supported recall facts.
- Automated verification passes: `256` Sims adapter tests, `225` Core tests, `4` Godot tests,
  `5` shared tests, Python compilation, and whitespace checks. The new compatibility regression
  confirms an ordinary romantic exchange still produces `romance_positive` and
  `social.romance`.
- The next live run again returned B for `your` and A for `our`. Although the local model's raw
  JSON still proposed `romance_positive`, both authoritative decisions stored
  `relationship_outcome=none`, `animation=none`, and `applied_changes=[]`; the sanitization fix
  therefore passed live without a romance increment.
- The `your` answer exposed a separate perspective defect:
  `Your code word is TEST14-B-731` should be Sim B's first-person
  `My code word is TEST14-B-731`. The stored fact correctly identifies Sim B as owner but retains
  Sim A's original `Your...` wording; prompt attribution treated the owner as the utterance author,
  and grounding had no code-word pronoun rule.
- Code-word evidence now renders ownership rather than quoted source pronouns. A responding-Sim
  answer must use `my code word`, and deterministic fallback produces exact `My` for `your` and
  `Our` for shared recall. Non-code-word attribution and Core time/location perspective remain
  unchanged.
- Automated verification passes: `258` Sims adapter tests, `225` Core tests, `4` Godot tests,
  `5` shared tests, Python compilation, and whitespace checks.
- The post-fix live run passed the reported perspective defect. Event
  `6d75c3e0-3db9-46b5-8587-154320008893` answered
  `My code word is TEST14-B-731.` for `your`. Event
  `eca5f78e-2ee4-43a0-96fc-f29d3e1dfea0` answered
  `The code word is TEST14-A-731.` for `our`, retaining the correct inherited shared fact with
  neutral wording.
- Both authoritative actions succeeded with `relationship_outcome=none`, `animation=none`, and
  `applied_changes=[]`. The `your` response category was `friendly`; the model still described
  the `our` response as romance, but Empneon correctly neutralized its executable outcome.
- The final Save A reload completed the branch matrix. `What is your code word?` correctly
  returned `I don't know or remember that.` because B exists only in Save B. `What is our code
  word?` returned `The code word is TEST14-A-731.`.
- Save A events `0abc1a21-e175-48dd-8456-bb8244c38f45` and
  `689fecf3-b520-4f52-8756-9300dda8a5ba` both succeeded with
  `relationship_outcome=none`, `animation=none`, and `applied_changes=[]`.
- Together with the preceding Save B live pass, this closes Test 14 as **PASS**. Test 15 follows
  below and also passed.

## Test 15: LLM-unavailable fallback

**Status:** PASS / PROVIDER-FREE FALLBACK AND PROVIDER RECOVERY LIVE-VERIFIED

- With LM Studio stopped, `aiping` continued to confirm that the Empneon backend was alive.
- The 30-sim-minute alarm fired repeatedly, but Sims 4 returned no scored NPC-to-NPC interaction
  on each observed tick, so the scheduled path safely skipped before contacting the backend.
- The controlled `aiautonomous` diagnostic reached CLOD 1 decision-making, then returned HTTP 500.
  The command sends a legacy sim-only payload, while `autonomous_action` unconditionally attempted
  to persist absent `speaker` and `listener` objects. Persisting the first empty object raised
  `ValueError("observed Sim id is required")` before usage accounting.
- The backend now persists `speaker` when present, otherwise `sim`, and persists an optional
  listener only when it has an ID. Strict actor identity validation and scheduled
  speaker/listener behavior remain unchanged.
- The regression reproduced the exact exception before the fix and now confirms sim persistence,
  a provider-free CLOD 1 `idle` decision, provider `core-rules`, and zero prompt/completion tokens.
  Existing scheduled-autonomy regressions remain green.
- Automated verification passes: `259` Sims adapter tests, `225` Core tests, `4` Godot tests,
  `5` shared tests, Python compilation, and whitespace checks.
- After restarting the backend with LM Studio still stopped, `aiautonomous` passed live:
  `Core proposed autonomous action`, blank target, and action `idle`. The newest usage row,
  request `2758ade5-2390-4aeb-a60a-5501b1fd5631`, recorded provider `core-rules`, model `clod1`,
  selected CLOD `1`, zero prompt/completion tokens, and zero provider latency.
- The provider-unavailable player exchange also passed live. Sim B answered
  `That is flattering. Thank you for being honest with me.` to
  `I'm very attracted to you. You are really hot.`. Request
  `2c0f4209-2a98-4ba9-a22c-bbc4085697c3` recorded provider `core-rules`, model `clod1`,
  selected CLOD `1`, and zero tokens/latency.
- Event `87443059-d78b-4408-8f6a-0051f968cdaf` and decision
  `40e24d25-668b-470b-a737-055d07ab5cec` succeeded with response category `friendly`,
  tone `reserved`, `relationship_outcome=none`, `animation=none`, `applied_changes=[]`, and
  zero persisted consequences.
- After LM Studio restarted, Sim B answered
  `My mind has been buzzing with creative ideas! Lately, it's just been a whirlwind of thoughts
  about everything that needs to be done.` to `What has been on your mind today?`.
- Request `8e8e032d-bbf0-4a58-965f-227aa2557864` returned through LM Studio. The final CLOD 3 record
  used model `local-model`, `12648` prompt tokens, `113` completion tokens, and `29956` ms;
  the same routed request also recorded its CLOD 2 stage.
- Event `ed56f708-2cb9-4e7e-9ad6-0cfd78b5f35c` and decision
  `84604cc9-42c5-43d3-9282-b6a6972a379f` succeeded with response category `friendly`,
  `relationship_outcome=none`, `animation=none`, `applied_changes=[]`, and zero consequences.
- This closes Test 15 as **PASS** and completes the 15-section sequential in-game acceptance suite.
