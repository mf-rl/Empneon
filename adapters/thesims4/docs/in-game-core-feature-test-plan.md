# Empneon Core Feature Test Plan for The Sims 4

This plan validates the Core integration through normal gameplay, the cheat console, and the
loopback diagnostics API. Run it against a disposable Sims save and back up existing Empneon
data first.

## Common setup

Test 5 is the exception to the release setup below: use the source-build development workflow in
`setup.md` so the installed mod and backend both come from the same repository checkout.

1. Extract the release, run `install_mod.ps1`, then run `run_backend.ps1`.
2. Enable **Custom Content and Mods** and **Script Mods Allowed**, restart the game, and load a
   household with two controllable Sims and at least one NPC.
3. Open the cheat console with `Ctrl+Shift+C` and run `aiping`, `ai.profile`, then
   `empneon.status`. The `ai.profile` command registers the selected Sim in Empneon Core before
   diagnostics are requested.
4. In PowerShell, set the backend URL for API checks:

   ```powershell
   $EmpneonUrl = 'http://127.0.0.1:8765'
   ```

The active database is `empneon_core_memory.sqlite3`. Stop the backend before copying, replacing,
or deleting it. Never perform migration or save-slot tests against the only copy of player data.

## Automated backend preflight

With the release backend and configured LLM provider running, execute this from
`adapters/thesims4` in a repository checkout:

```powershell
py -3.12 .\scripts\simulate_http_interactions.py `
  --database 'C:\Users\mauri\Downloads\Empneon-TheSims4-0.3.0\empneon_core_memory.sqlite3'
```

The harness sends the same `/chat` and `/action-result` payloads as Empneon Social, then verifies
Core state through the diagnostic endpoints. It adds uniquely named `empneon-test-*` records to
the active database and writes an untracked JSON report under `output/`; it does not delete or
rewrite existing game records.

Passing this preflight covers the backend portions of profiles, emotions, goals, confirmations,
private beliefs, vector retrieval, CLOD telemetry, timeline/replay, and identity round trips. It
does not replace these in-game checks:

- Accuracy of state extracted from live Sim objects.
- Native social selection, animation, queue completion, cancellation, and consequence capture.
- Priority behavior with concurrent live Sims.
- Persistence across actual game save/reload and save-slot changes.

## 1. Unified database and legacy migration

**Current status (2026-07-20): PASS**

- Prerequisite: a disposable copy of either `empneon_core.sqlite3` or
  `ai_sims_memory.sqlite3`; no active `empneon_core_memory.sqlite3`.
- Action: put the legacy copy beside the backend, start it, and run:

  ```powershell
  Invoke-RestMethod "$EmpneonUrl/diagnostics/migration"
  ```

- Expected game result: `aiping` succeeds and existing Sims can still be queried.
- Expected diagnostic result: `active_path` ends in `empneon_core_memory.sqlite3`, `completed` is
  true, the detected source is listed, and migration completion markers are present after an
  adapter import. The legacy source remains unchanged and has a `.pre-core-memory.bak` backup.
- Persistence: restart the backend; records are not duplicated and the same active path is shown.
- Cleanup: archive or remove only the disposable legacy copies and restore the original config.

## 2. Canonical Sim profile and OCEAN personality

**Current status (2026-07-20): PASS**

- Prerequisite: select a Sim with recognizable traits, for example Good, Creative, or Outgoing.
- Action: run `ai.profile`, then `empneon.status`.
- Expected game result: the active Sim's name and stable ID appear.
- Expected diagnostic result:

  ```powershell
  Invoke-RestMethod "$EmpneonUrl/diagnostics/sim?sim_id=<SIM_ID>" | ConvertTo-Json -Depth 8
  ```

  `agent.adapter` is `sims4`; `personality` contains normalized openness,
  conscientiousness, extraversion, agreeableness, and neuroticism. A Good Sim has higher
  agreeableness than the neutral `0.5`; a Creative Sim has higher openness.
- Persistence: save, restart the game and backend, and verify the same stable ID/profile.
- Cleanup: none.

## 3. Rich game state and emotional state

**Current status (2026-07-20): PASS**

- Prerequisite: make the active Sim hungry and apply a visible moodlet.
- Action: start **Empneon Social** and ask, "How are you feeling and what needs attention?"
- Expected game result: the answer reflects available needs/mood without inventing unavailable
  facts. Career, aspiration, skills, household, and nearby Sims may influence the answer when the
  installed game API exposes them.
- Expected diagnostic result: run `ai.emotion` and inspect `/diagnostics/sim`; normalized emotion
  entries are in `0.0..1.0` and the prompt-backed interaction appears in accessible memory only
  after game confirmation.
- Persistence: save/reload and run `ai.emotion` again.
- Cleanup: satisfy the need or remove the moodlet normally.

## 4. Aspirations and need-derived goals

**Current status (2026-07-20): PASS** — Aspiration ingestion, need-goal lifecycle, goal
coexistence, and persistence pass on a clean database.

- Prerequisite: an active aspiration and one need at or below 25 percent.
- Action: trigger an Empneon interaction, then run `empneon.goals`.
- Expected game result: the console lists an `Aspiration: ...` goal and `Restore <need>`.
- Expected diagnostic result: `/diagnostics/sim` lists deterministic goal IDs with `active`
  status. Raise the need above 25 percent and trigger another observation; the restore goal becomes
  `completed` instead of being duplicated.
- Persistence: save/reload; goal IDs and statuses remain stable.
- Cleanup: restore all needs to safe values.

## 5. Directed relationships and confirmed consequences

**Current status (2026-07-29): PASS** — The single-turn queue, cancelable waiting phase,
conversation animation, directed confirmed consequences, save/reload persistence, grounded recall,
portrait layout, and romance feedback all passed live testing. The final post-reload date question
retrieved Bernard's attributed `Tonight, 7pm, at my place` fact. Empneon rejected an incomplete
first model answer, accepted a fresh second answer—`It's happening tonight at 7pm at your
place`—and recorded successful delivery without promoting the recalled wording into a new
authoritative fact.

The implemented safeguards are game- and provider-independent where they belong in Core:
structured-output capability is explicit, LM Studio receives the supplied JSON Schema, semantic
selection cannot replace grounded deterministic recall with factless replies, requested time
values are normalized and checked for completeness, and attributed location ownership survives
prompting, retry, and fallback. The Sims adapter retains only its game-specific category aliases,
relationship effects, UI bridge, and animation fallback. Provider usage now includes semantic
selection and dialogue attempts; `empneon.usage` requests global telemetry while the HTTP
diagnostic can still be filtered by actor.

Live coverage includes positive friendship and romance, relationship-neutral friendly, funny,
mean, and mischief terminal behavior, correct two-portrait ordering, floating relationship icons,
continuous persistence, save/reload recall, and the initiator-only waiting visual when EA provides
no linked social group. Later rebuilt-package tests accepted provider-backed funny and mischief
dialogue while preserving safe terminal behavior.

The live tuning probe subsequently corrected mischief discovery to
`mixer_social_LieAboutCareer_group_mischief_skills`. The first follow-up still ran the stale
packaged script, so the installer now rebuilds source checkouts before copying. The July 29
fresh-package retest used CLOD 2 semantic selection and CLOD 3 dialogue, accepted a `mischief`
response without retry diagnostics, and completed with zero applied changes.

Warm, playful, or romantic reception in the `romance` response category now receives the existing
mild `romance_positive` outcome when the model returns `none`, provided the response is not
hesitant, neutral, uncertain, hostile, or an explicit rejection.

- Prerequisite: use a disposable save with Karmine and another Sim, install the source build, and
  start the source backend as documented in `setup.md` with
  `response_rejection_enabled` set to `true`.
- Run this matrix and capture every row:

  | Incoming message | Expected incoming category | Acceptable response categories |
  |---|---|---|
  | “I really enjoy talking with you. You're a good friend.” | `friendly` | `friendly`, or an intentional boundary |
  | “Tell me your funniest llama joke.” | `funny` | `funny`, or an intentional boundary |
  | “Would you go on a date with me?” | `romance` | any normalized category |
  | “I hate you. Go away.” | `mean` | `mean`, or an intentional boundary |
  | “Let's prank another Sim by lying about their career.” | `mischief` | `mischief`, or an intentional boundary |

  For each row record both actor snapshots, incoming and response category, tone tags, bounded
  `relationship_outcome`, displayed notifications, and relationship values before and after. The
  response category may differ from the incoming category. `none` is a valid relationship-neutral
  result. Record whether the final dialogue came from the model or deterministic fallback; a
  category-correct fallback verifies safety and availability but not provider acceptance.
- Attraction evidence: capture `ai.relationship Karmine` in both directions before dialogue. The
  command must show either `Sims attraction <normalized> (<source>: <label>)` or explicit
  `unavailable`. With supported WickedWhims attraction enabled, source must be `wickedwhims`; with
  it disabled and Lovestruck available, source must be `sims4_lovestruck`. Values may differ by
  direction. Confirm the prompt uses Karmine-to-Bernard attraction only, and that attraction shapes
  tone without forcing flirtation, consent, or a romance delta.
- Action: record `ai.relationship Karmine`, Karmine's reported life stage, gender, and traits, and
  Bernard's gender. Start **Empneon Social** with Karmine and submit a romantic invitation that
  includes an exact date such as `Saturday`. Start a new Empneon Social for a second message.
  Repeat once, manually cancelling **Waiting for response** while the backend is still working.
- Expected game result: **Start conversation** disappears when the input opens. The player's
  submitted text appears with Sim A as the primary portrait and Sim B as the secondary portrait.
  **Waiting for response** remains only until the response arrives and both Sims play a cosmetic
  conversation animation without another queue entry. The answer then appears with Sim B primary
  and Sim A secondary, and the waiting animation stops. A non-`none` outcome applies one mild
  native friendship or romance update without queueing another social, then shows the matching
  tuned headline above both Sims; `none` is dialogue-only. Only the observed native delta is
  reported. Manual cancellation suppresses the late dialogue, memory, trust, and relationship
  outcome.
- Low-grade romance check: submit a romantic compliment that receives a warm, playful, or romantic
  answer without rejection. Confirm romance changes by the observed mild amount and the native
  floating romance headline appears. Repeat with a hesitant or rejecting answer and confirm the
  positive fallback does not apply.
- Expected diagnostic result: `/diagnostics/sim?sim_id=<ACTOR_ID>` shows the actor-to-target Core
  relationship. Friendship/trust are normalized, and a confirmed positive romance consequence
  marks the relationship romantic. Query the target separately to verify that directed edges can
  differ.
- Evidence to capture for each run: exact player and response notification portrait order, queue
  task names and timing, waiting animation start/stop behavior, decision ID, bounded relationship
  outcome, before/after `ai.relationship` output, and the exact floating friendship/romance
  symbols above each Sim. Confirm no response-derived native social appears. For the cancellation
  run, record that the animation stops and no late dialogue, memory, trust, or relationship change
  appeared.
- Focused dialogue observations: record whether Karmine's reply is distinct from Bernard's current
  message, Bernard's earlier messages, and Karmine's earlier replies; whether Karmine uses
  `boyfriend` or neutral wording for male Bernard rather than `girlfriend`; whether the reply
  respects Karmine's reported life stage and traits without reciting trait labels; and whether
  exact facts such as `Saturday` remain usable when
  the surrounding response is distinct.
- Focused need/continuity assertions: capture Karmine's and Bernard's visible mood/need state before
  the conversation. Green needs do not force a need report; orange/red needs may influence natural
  wording without exposing numeric values or replacing a valid model reply. Continue enough turns
  to confirm replies introduce a new reaction, detail, question, or decision instead of recycling
  earlier inputs or replies.
- Focused queue/state assertions: **Start conversation** completes after input and **Waiting for
  response** remains cancelable without deadlocking. No response-derived native social is queued.
  A non-`none` relationship outcome is applied directly only after dialogue delivery, and only its
  observed friendship or romance delta is confirmed. Attraction remains game-owned and independent;
  Empneon trust changes only after dialogue is displayed.
- Persistence: save/reload and compare both directions again.
- Cleanup: none; use a disposable save if relationship changes matter.

## 6. Private observations and beliefs

**Current status (2026-07-24): PASS** — Confirmation gating, exact identifier recall, pair privacy,
response rejection, deterministic uncertainty fallback, and save/reload persistence passed live.

- Prerequisite: Sims A, B, and C are present. C must not participate in the first conversation.
- Action: as A, tell B a unique fact such as `PRIVATE-GARDEN-731 is under the blue bench`. Then ask
  B to recall it. Switch to C and ask for the same fact.
- Expected game result: B can use the supplied fact after confirmation; C says it does not know or
  remember rather than leaking it.
- Expected diagnostic result: B's confirmed accessible memory contains the actor-attributed fact;
  C has no matching fact or accessible memory. `empneon.beliefs` may remain `0` because the adapter
  stores this confirmed dialogue evidence in episodic memory rather than projecting it into the
  standalone belief store.
- Persistence: save/reload and repeat both questions.
- Cleanup: delete the disposable database after the plan if the unique fact should not remain.

## 7. Semantic memory retrieval

**Current status (2026-07-24): PASS** — Date recall passed across save/reload with correct
attributed time/location evidence in fresh wording. Exact private-identifier recall,
uninformed-pair rejection, and the non-date `garden code item` paraphrase also pass. The informed
Sim retrieved `under the blue bench` before and after a backend restart; the uninformed Sim did not
disclose the private location.

**Expanded status (2026-07-27): PASS** — After a backend/game restart, the informed Sim correctly
recalled a moon-orchid preference, telescope-repair promise, sister named Elara, and conflict over
a promotion lie from paraphrased questions. A genuinely uninformed Sim disclosed neither the
preference nor conflict fact. All six authoritative decisions remained relationship-neutral with
zero applied changes.

- Prerequisite: complete section 6 and add several unrelated confirmed conversations.
- Action: ask B, "Where is the garden code item?" without repeating the exact original sentence.
- Expected game result: B retrieves the topically related garden memory.
- Response-quality check: the answer must state the recalled fact in wording appropriate to the
  current question, not replay an earlier response verbatim.
- Expected diagnostic result: B's accessible memories contain the original event; C still cannot
  retrieve it. This verifies retrieval plus observation-based privacy filtering.
- Persistence: restart backend and repeat the paraphrased question.
- Cleanup: none beyond section 6.

## 8. Provider-free CLOD 1

**Current status (2026-07-24): PASS** — Scheduled provider-free autonomy queued a mapped native
**Ask About Day** social for two NPCs. Global usage increased from two to three CLOD 1 records with
provider `core-rules` and zero prompt, completion, or latency cost, then persisted across a backend
restart while LM Studio remained stopped.

- Prerequisite: leave normal autonomy enabled; the LLM may be stopped.
- Action: let 30 simulated minutes pass with two eligible NPCs on the lot.
- Expected game result: a mapped native social is proposed and queued without an LLM call.
- Expected diagnostic result: `empneon.usage` reports CLOD `1`, provider `core-rules`, and zero
  prompt/completion tokens.
- Persistence: restart backend; the usage totals remain available.
- Cleanup: cancel any unwanted native social in the Sims queue.

## 9. Provider-backed dynamic CLOD and usage

**Current status (2026-07-24): PASS** — A live current-state question routed through LM Studio at
CLOD 3, returned grounded dialogue, increased request, token, and latency telemetry, and retained
the same totals across a backend restart. The retest also closed a Core false-recall defect that
had rejected `what do you want to do?` as unsupported historical recall.

- Prerequisite: start the configured OpenAI-compatible provider with a model loaded.
- Action: use **Empneon Social** for a player-directed question involving mood, goals, or recent
  memory.
- Expected game result: a grounded model reply appears.
- Expected diagnostic result: `empneon.usage` and `/diagnostics/usage?sim_id=<SIM_ID>` show a
  provider/model attempt, selected CLOD (normally 3 for player dialogue), resource estimates,
  prompt/completion tokens, and latency.
- Persistence: restart backend and verify totals remain.
- Cleanup: none.

## 10. Priority under concurrent Sims

**Current status (2026-07-25): PASS** — A controlled live run queued lower-priority ambient work,
then submitted a real in-game player conversation. The player request started and completed before
the already-waiting ambient request.

- Prerequisite: set `active_agent_limit` to `1`, restart the source backend, load a disposable
  save, and confirm the configured provider is available.
- From `adapters/thesims4`, start the controlled priority harness:

  ```powershell
  py -3.12 .\scripts\test10_priority_harness.py
  ```

  At the first prompt, open **Empneon Social**, type the message without submitting it, then press
  Enter in the harness terminal. The harness arms a loopback-only diagnostic gate that holds one
  worker and queues one lower-priority ambient request. At the second prompt, submit the prepared
  in-game message and immediately press Enter in the harness terminal. The harness waits until the
  real player request is queued before releasing the blocker.
- Exit code `0` proves the player request started before the already-waiting ambient request.
  Exit code `1` records an observed ordering failure. Exit code `2` is inconclusive, normally
  because the real player request was not observed before the diagnostic gate's 60-second automatic
  release. Preserve `output/test10-priority-*.json`; reviewed reports may be committed as acceptance
  evidence because they contain queue identifiers and timestamps rather than dialogue or secrets.
- Expected game result: after the already-running work finishes, the player request completes
  before pending ambient work; the queue remains responsive rather than starting all requests.
- Expected diagnostic result: `/diagnostics/cognition-queue` and the harness report show the
  running blocker, the waiting ambient request, the submitted player request, then player
  start before waiting-ambient start. Timeline and usage remain consistent with that order.
- Persistence: restart the backend and confirm timeline ordering remains readable. Queue diagnostic
  history is intentionally process-local and clears on restart; the JSON report is the queue-order
  evidence.
- Cleanup: restore the preferred `active_agent_limit`.

## 11. Successful and failed confirmation

**Current status (2026-07-25): PASS** — Successful delivery and queue cancellation passed live.
The successful record and two failed cancellation records survived backend restarts with valid
replay integrity. Cancelled interactions produced zero applied changes and no confirmed memory.

- Prerequisite: two Sims and a baseline relationship diagnostic.
- Action: complete one native Empneon social. Then start another and cancel it from the interaction
  queue before completion.
- Expected game result: the first reports success; the cancelled one reports failure/cancellation.
- Expected diagnostic result: the successful record has applied changes and confirmed episodic
  evidence. The failed record has a reason and no applied changes, relationship mutation, or
  confirmed memory.
- Persistence: save/reload and verify both records remain in `empneon.timeline`.
- Cleanup: none.

## 12. Timeline and replay

**Current status (2026-07-20): PASS**

- Prerequisite: complete sections 8, 9, and 11.
- Action: run `empneon.timeline`, copy one decision ID, then run:

  ```powershell
  Invoke-RestMethod "$EmpneonUrl/diagnostics/replay?decision_id=<DECISION_ID>" |
    ConvertTo-Json -Depth 10
  ```

- Expected game result: the timeline command prints recent event, decision, and belief entries.
- Expected diagnostic result: replay returns the original event, decision, result, matched or
  unapplied deltas, and `consequence_integrity: true`. It does not execute another game action.
- Persistence: restart and replay the same ID; output remains equivalent.
- Cleanup: none.

## 13. Identity export and import

**Current status (2026-07-26): PASS** — Two imports and the post-restart export preserved all
canonical identity fields. Raw JSON differed only because `updated_at` timestamps were refreshed.

- Prerequisite: a Sim with goals, emotion, relationship, and optionally voice data.
- Action:

  ```powershell
  $Identity = Invoke-RestMethod "$EmpneonUrl/identity/export?sim_id=<SIM_ID>"
  $Identity | ConvertTo-Json -Depth 12 | Set-Content .\bella-identity.json
  Invoke-RestMethod "$EmpneonUrl/identity/import" -Method Post -ContentType application/json `
    -InFile .\bella-identity.json
  ```

- Expected game result: import returns the Sim ID and name without changing the live Sim.
- Expected diagnostic result: a second export matches the canonical agent, personality,
  relationships, emotions, goals, and voice profile. Importing the same file again is idempotent.
- Persistence: restart backend and export again.
- Cleanup: securely remove the exported JSON if it contains private player text or names.

## 14. Save-slot isolation

**Current status (2026-07-26): PASS** — Save B returned `My code word is TEST14-B-731` for
`your` and inherited A for `our`. After loading Save A, `your` correctly returned grounded
uncertainty because B was branch-absent, while `our` returned `TEST14-A-731`. All final actions
succeeded with `relationship_outcome=none`, `animation=none`, and no applied relationship changes.

- Prerequisite: set `preserve_memory_only_on_game_save` to `true` and restart.
- Action: in Save A, teach a unique fact and save. Use **Save As** to create Save B, teach a second
  unique fact, and save. Reload each branch.
- Expected game result: each branch recalls only facts retained in its own checkpoint history.
- Expected diagnostic result: timeline/beliefs match the loaded slot; checkpoint files named
  `.empneon-saved.slot-<id>` exist beside `empneon_core_memory.sqlite3`.
- Persistence: restart both game and backend before rechecking each branch.
- Cleanup: restore `preserve_memory_only_on_game_save`; retain or archive checkpoint files with the
  corresponding Sims saves.

## 15. LLM-unavailable fallback

**Current status (2026-07-26): PASS** — With LM Studio stopped, `aiping` confirmed the backend
remained alive, the corrected sim-only autonomy route completed as zero-token CLOD 1
`core-rules`, and player dialogue returned the conservative local fallback without consequences.
After LM Studio restarted, a new player exchange completed through the configured provider at
CLOD 3 with nonzero token usage.

- Prerequisite: stop the configured LLM server or temporarily configure an unreachable endpoint.
- Action: allow CLOD 1 autonomy, then attempt player **Empneon Social**.
- Expected game result: provider-free autonomy still works. Player dialogue returns a clear local
  fallback/error and does not fabricate confirmed memory.
- Expected diagnostic result: usage shows the attempted/fallback route as available; failed game
  actions have no consequences. `aiping` still confirms that the Empneon backend itself is alive.
- Persistence: restart the provider and verify a new player interaction succeeds normally.
- Cleanup: restore the provider endpoint and remove temporary configuration.

## Completion record

**Suite status (2026-07-26): COMPLETE** — All 15 sections have passed their live acceptance
checks. The corresponding sanitized evidence is retained in
`in-game-core-feature-test-results.md`.

Record the game version, Empneon release version, Python version, provider/model, save-slot IDs,
and pass/fail evidence for all 15 sections. Preserve only sanitized diagnostics: do not attach API
keys, configuration secrets, raw databases, or personally identifying conversation content to a
public issue.
