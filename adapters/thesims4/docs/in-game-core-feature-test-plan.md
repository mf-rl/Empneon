# Empneon Core Feature Test Plan for The Sims 4

This plan validates the Core integration through normal gameplay, the cheat console, and the
loopback diagnostics API. Run it against a disposable Sims save and back up existing Empneon
data first.

## Common setup

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

**Current status (2026-07-20): PARTIAL** — Name resolution and a confirmed friendship consequence
now pass in the release retest. Directed storage and persistence already pass; a confirmed native
romance consequence remains unverified. Semantic classification, near-copy rejection, clean
repetition retries, and relevant offline responses pass automated tests but require a new release
retest before Test 5 can pass.

- Prerequisite: two Sims with a known relationship.
- Action: note `ai.relationship <Target Name>`, complete an Empneon Social, then run it again.
- Expected game result: the native social completes before Empneon reports success.
- Expected diagnostic result: `/diagnostics/sim?sim_id=<ACTOR_ID>` shows the actor-to-target Core
  relationship. Friendship/trust are normalized, and a confirmed positive romance consequence
  marks the relationship romantic. Query the target separately to verify that directed edges can
  differ.
- Persistence: save/reload and compare both directions again.
- Cleanup: none; use a disposable save if relationship changes matter.

## 6. Private observations and beliefs

**Current status (2026-07-20): PARTIAL** — Confirmation gating, privacy, and persistence pass;
recall dialogue contradicts stored memory.

- Prerequisite: Sims A, B, and C are present. C must not participate in the first conversation.
- Action: as A, tell B a unique fact such as `PRIVATE-GARDEN-731 is under the blue bench`. Then ask
  B to recall it. Switch to C and ask for the same fact.
- Expected game result: B can use the supplied fact after confirmation; C says it does not know or
  remember rather than leaking it.
- Expected diagnostic result: `empneon.beliefs` on B lists the fact. B's `/diagnostics/sim` has an
  observation-backed belief; C's response contains no such belief or accessible memory.
- Persistence: save/reload and repeat both questions.
- Cleanup: delete the disposable database after the plan if the unique fact should not remain.

## 7. Local vector retrieval

**Current status (2026-07-20): PARTIAL** — Exact recall, privacy, and persistence pass;
paraphrased retrieval fails.

- Prerequisite: complete section 6 and add several unrelated confirmed conversations.
- Action: ask B, "Where is the garden code item?" without repeating the exact original sentence.
- Expected game result: B retrieves the topically related garden memory.
- Expected diagnostic result: B's accessible memories contain the original event; C still cannot
  retrieve it. This verifies retrieval plus observation-based privacy filtering.
- Persistence: restart backend and repeat the paraphrased question.
- Cleanup: none beyond section 6.

## 8. Provider-free CLOD 1

**Current status (2026-07-20): PARTIAL** — Backend CLOD 1 telemetry passes; live native execution
and restart persistence remain.

- Prerequisite: leave normal autonomy enabled; the LLM may be stopped.
- Action: let 30 simulated minutes pass with two eligible NPCs on the lot.
- Expected game result: a mapped native social is proposed and queued without an LLM call.
- Expected diagnostic result: `empneon.usage` reports CLOD `1`, provider `core-rules`, and zero
  prompt/completion tokens.
- Persistence: restart backend; the usage totals remain available.
- Cleanup: cancel any unwanted native social in the Sims queue.

## 9. Provider-backed dynamic CLOD and usage

**Current status (2026-07-20): PARTIAL** — LM Studio routing and latency pass; live token counts
and restart persistence remain.

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

**Current status (2026-07-20): PENDING**

- Prerequisite: set `active_agent_limit` to `1`, restart, and place several eligible NPCs on the
  lot.
- Action: allow an autonomous request to begin, then immediately start a player **Empneon Social**
  while further ambient requests are waiting.
- Expected game result: after the already-running work finishes, the player request completes
  before pending ambient work; the queue remains responsive rather than starting all requests.
- Expected diagnostic result: timeline and usage timestamps place the player interaction ahead of
  ambient requests that were waiting at the same time.
- Persistence: restart and confirm timeline ordering remains readable.
- Cleanup: restore the preferred `active_agent_limit`.

## 11. Successful and failed confirmation

**Current status (2026-07-20): PARTIAL** — Automated success/failure passes; deliberate live queue
cancellation and persistence remain.

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

**Current status (2026-07-20): PARTIAL** — Automated round trip passes; repeated import and restart
persistence remain.

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

**Current status (2026-07-20): PENDING**

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

**Current status (2026-07-20): PENDING**

- Prerequisite: stop the configured LLM server or temporarily configure an unreachable endpoint.
- Action: allow CLOD 1 autonomy, then attempt player **Empneon Social**.
- Expected game result: provider-free autonomy still works. Player dialogue returns a clear local
  fallback/error and does not fabricate confirmed memory.
- Expected diagnostic result: usage shows the attempted/fallback route as available; failed game
  actions have no consequences. `aiping` still confirms that the Empneon backend itself is alive.
- Persistence: restart the provider and verify a new player interaction succeeds normally.
- Cleanup: restore the provider endpoint and remove temporary configuration.

## Completion record

Record the game version, Empneon release version, Python version, provider/model, save-slot IDs,
and pass/fail evidence for all 15 sections. Preserve only sanitized diagnostics: do not attach API
keys, configuration secrets, raw databases, or personally identifying conversation content to a
public issue.
