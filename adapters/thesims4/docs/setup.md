# Empneon for The Sims 4 Setup and Privacy

This guide covers the validated Windows 20-agent reference-adapter proof of concept and
its reproducible exit-gate procedure.

## Requirements

- The Sims 4 with **Custom Content and Mods** and **Script Mods Allowed** enabled
- PowerShell and the Windows Python launcher (`py`)
- Python 3.11 or newer for Empneon Core and the backend
- Python 3.7 only when compiling the Sims 4 script mod from source
- An OpenAI-compatible provider for model-backed conversation; autonomous CLOD 1
  behavior remains provider-free

For a gamer installation, download and extract `Empneon-TheSims4-X.Y.Z.zip`, then run:

```powershell
.\install_mod.ps1
.\run_backend.ps1
```

The release includes prebuilt `Empneon_TheSims4.ts4script` and
`Empneon_TheSims4.package` files, so this path does not require Python 3.7.
`run_backend.ps1` creates a local `.venv` and installs the bundled Empneon wheels; its first run
requires internet access for third-party dependencies.

For development from the public monorepo, install Core and The Sims 4 adapter:

```powershell
py -3.12 -m pip install -e .\core -e .\adapters\thesims4
```

Python 3.12 may be replaced with any installed Python version supported by
`pyproject.toml`.

### Source-build development run

To test the current worktree without creating a release, run from `adapters/thesims4`:

```powershell
.\install_mod.ps1
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 .\backend\ai_sims_server.py
```

When `build_mod.py` is present, `install_mod.ps1` always rebuilds the current
`Empneon_TheSims4.ts4script` and `Empneon_TheSims4.package` before installing them. The explicit
`PYTHONPATH` makes the backend import Core and the adapter from this worktree. This workflow does
not build or install a release archive.

For agent-assisted development, the source backend is not left running after automated work. Start
it yourself for an in-game test. If an automated check must start it, that check stops it before
handoff so the next manual run cannot connect to a stale process.

## Install and Run

1. Configure and start an OpenAI-compatible provider. The default is LM Studio at
   `http://127.0.0.1:1234`.
2. Install the script mod and interaction tuning:

   ```powershell
   .\adapters\thesims4\install_mod.ps1
   ```

   Close The Sims 4 before installing so it does not lock the package. In a source checkout the
   script always rebuilds with Python 3.7; a release ZIP without `build_mod.py` uses its bundled
   prebuilt files. It copies `Empneon_TheSims4.ts4script` and
   `Empneon_TheSims4.package` into the game's `Mods` directory, removes legacy
   `AI_Sims_Agent.*` files, and clears the Sims thumbnail cache.
3. Start the backend from the repository root:

   ```powershell
   .\adapters\thesims4\run_backend.ps1
   ```

4. Restart The Sims 4 and load a household. Clicking another Sim exposes the
   **Empneon Social** pie-menu entry. **Start conversation** routes to the target and opens one
   native message field. Sending removes that task, shows the player's message as a portrait
   notification, and queues the cancelable **Waiting for response** task. The target's answer is a
   portrait notification and ends the transaction; select Empneon Social again for another turn.
   Only an explicit player cancellation closes a pending session. If the game finishes the waiting
   task for another reason before the backend reply, the adapter queues a replacement tied to the
   same request.
   While waiting, both Sims play a cosmetic EA conversation animation. Sim B may occasionally use
   a bored-looking gesture; this is a known visual limitation and does not select a mean interaction.
   A delivered answer may apply one mild (`5` point) friendship or romance outcome directly
   through the native relationship tracker. Autonomous Empneon decisions still queue their mapped
   base-game social through the game's native interaction context.
5. Run `aiping` in the cheat console for backend diagnostics, then use
   `aichat Bella Goth | Hello` for the existing model-backed interaction. With a lot active,
   the mod also submits at most one non-player pair every 30 simulated minutes. Autonomous
   proposals are restricted to mapped **Ask About Day**, **Apologize**, and **Compliment
   Appearance** base-game socials. A generic autonomous acknowledgement selects **Apologize**
   while the game's retained aggregate relationship score is negative and **Ask About Day** once
   it is non-negative. Core receives the result only after the queued interaction finishes; a
   proposal or queue acceptance is not treated as a confirmed outcome. Confirmed friendship
   changes also update Core's actor-to-target relationship strength.

For cognitive-state inspection, use `empneon.status`, `empneon.timeline`,
`empneon.beliefs`, `empneon.goals`, and `empneon.usage`. The complete verification procedure is
the [in-game Core feature test plan](in-game-core-feature-test-plan.md).

The mod currently connects to `http://127.0.0.1:8765`. Changing the backend host or
port requires changing `BACKEND_URL` in `ts4script/ai_sims_agent.py` and rebuilding
the mod. Do not expose the reference HTTP server to another machine; it has no authentication.

## Configuration

The backend loads `config/config.json` by default. Set `AI_SIM_CONFIG` to use another
JSON file. Environment variables override the loaded file.

| Setting | Purpose | Default |
|---|---|---|
| `host`, `AI_SIM_HOST` | Backend bind address | `127.0.0.1` |
| `port`, `AI_SIM_PORT` | Backend port | `8765` |
| `memory_database` | Single active identity, memory, action, and cognition database | `empneon_core_memory.sqlite3` |
| `database`, `AI_SIM_DB` | Former adapter database imported once for compatibility | `ai_sims_memory.sqlite3` |
| `core_database` | Former Core database adopted once for compatibility | `empneon_core.sqlite3` |
| `preserve_memory_only_on_game_save` | Roll back unsaved Sims narrative state at the next game session | `true` |
| `response_rejection_enabled` | Reject and retry ungrounded, copied, role-confused, or contradictory model replies | `true` |
| `active_agent_limit` | Concurrent reference-adapter sessions and Core admissions | `1` |
| `agent_wake_timeout_seconds` | Wait for an agent-session slot | `60` |
| `provider`, `AI_SIM_PROVIDER` | Default provider entry | `lmstudio` |
| `AI_SIM_LLM_BASE_URL` | Override the selected provider endpoint | provider endpoint |
| `AI_SIM_MODEL` | Override both task model IDs | provider model |
| `AI_SIM_API_KEY` | Authorization bearer token | unset |
| `debug` | Verbose backend logging | `true` |

Relative database paths resolve from the backend process's working directory. Both former
database paths are read-only migration sources. All current state is written to the single active
`empneon_core_memory.sqlite3` database; legacy sources are never deleted automatically.

The shipped configuration enables `response_rejection_enabled`. With it set to `false`, Empneon
skips the optional broad copying, role-confusion, and conversational grounding filters. Supported
factual recall remains
deterministically constrained: answers must preserve selected attributed time and location
evidence, receive one corrected model attempt when necessary, and fall back to an attributed
quotation rather than inventing a fact. JSON/plain-text parsing and response normalization always
run because the game adapter requires a stable response object. Keep the value at `true` for
privacy and epistemic-recall acceptance tests: unsupported answers are rejected and replaced with
an uncertainty fallback. Restart the backend after changing this setting; the game does not need
to restart.

When response rejection is enabled, explicit wording may correct a mismatched model category
without executing a social action. Relationship outcomes are revalidated after correction.
Identical repeated prompts may reuse a relevant prior-shaped reply, while a reply recycled for a
different prompt is still rejected. After two rejected or failed model attempts, deterministic
fallbacks remain actionless: funny returns a light llama joke, mean sets a firm boundary, and
mischief suggests a harmless prank. Live July 27 validation confirmed these terminal behaviors
with `relationship_outcome=none`, `animation=none`, and no applied game changes. The funny and
mischief live rows reached fallback, so they do not yet demonstrate accepted provider dialogue.

Each entry under `providers` accepts `endpoint`, `model`, and optionally `api_key`.
Prefer `AI_SIM_API_KEY` over storing a secret in the tracked JSON file. `models.small`
and `models.large` may override `provider`, `endpoint`, `model`, `temperature`, and
`max_tokens` per task.

For OpenRouter, set `provider` to `openrouter`, optionally replace its configured model,
and set `AI_SIM_API_KEY`. Core uses `https://openrouter.ai/api/v1` through the
OpenAI-compatible provider; the game adapter contains no OpenRouter-specific behavior.

### Native social UI validation

Live validation completed on 2026-07-15 with The Sims 4 `1.125.59.1030`. **Empneon Social** enters
the active Sim's queue, routes to the target, and opens its input after arrival. A mapped **Ask
About Day** completed with a native `+5` friendship consequence confirmed to Core. Canceling the
queued interaction before arrival opened no input and created no backend request or action
proposal. After save/reload, a fresh conversation recalled the retained pizza plan at 7 PM the
next day. The raw recent-conversation context and prompt guide replies when switching providers.
The optional provider-independent speaker/listener and grounding guard is active only when
`response_rejection_enabled` is `true`. Stage 6.5 is complete.

The single-turn **Start conversation** / **Waiting for response** redesign and its waiting
conversation animation passed live testing on 2026-07-23. The mild romance path also passed with
observed game-side increases. On July 24, live testing confirmed the primary/secondary portrait
layout and floating relationship icons for romance conversations. A relationship-neutral friendly
introduction correctly displayed no icon. The waiting animation also completed after save/reload
through its initiator-only visual fallback when no linked social group was available. Stronger
`+++` feedback and relationship milestones such as best friends, first kisses, and proposals are
deferred and must not be triggered by this implementation.

On July 27, positive friendship had already been observed with a native `+8` result. A new social
breadth run safely handled friendship, mean, funny, and mischief. Mean returned a firm boundary;
funny returned an actual joke; mischief proposed a harmless trick. Every final mean/funny/mischief
decision was relationship-neutral and actionless. Funny and mischief used deterministic fallback,
which remains visible as a provider-acceptance gap rather than a safety failure.

Later July 27 diagnostics captured only the two normalized rejection reasons for exhausted funny
and mischief attempts. Funny state safety then passed live with zero trust, relationship outcome,
animation, or applied changes even when the provider categorized marker-free joke dialogue as
friendly. The live tuning probe identified
`mixer_social_LieAboutCareer_group_mischief_skills`; source and automated discovery now use that
exact name. The first attempted retest still loaded a stale July 26 archive. Source installation
now rebuilds unconditionally, and the corrected archive has been installed for the next
game-restart mischief row.

On July 26, automated regression covered a later game-driven waiting-task cancellation that had
discarded completed backend answers during Test 14. Non-user finishes now requeue the same session,
stale callbacks cannot create duplicate tasks, and only `FinishingType.USER_CANCEL` suppresses a
late reply. The rebuilt mod still requires a live in-game retest.

On July 24, the in-game Core matrix also closed Tests 7 through 9. A non-date paraphrase retrieved
the informed pair's private `under the blue bench` location before and after backend restart while
an uninformed pair disclosed no location. Scheduled CLOD 1 autonomy queued a mapped NPC social with
LM Studio stopped and retained a zero-token `core-rules` usage record after restart. A
provider-backed current-state question then completed at CLOD 3 with grounded mood dialogue,
positive token/latency accounting, and persistent telemetry.

Memory settings:

- `recent_limit`: memories placed in a conversation context
- `summary_every`: number of pair memories before summarization is attempted
- `summary_limit`: maximum memories included in a summary request

When `preserve_memory_only_on_game_save` is `false`, memories, conversations,
emotions, profiles, and relationships are written continuously to
`empneon_core_memory.sqlite3`;
save slots are ignored. When it is `true`, the backend keeps those changes as the current
session state and maintains an independent checkpoint for each The Sims 4 save slot.
The mod checkpoints that state only after The Sims 4 successfully completes `save_game_gen` for
a real save slot; temporary scratch-slot saves are ignored. This includes any autosave
implementation that uses the same real-save path. Returning to the Main Menu and loading a save,
or restarting the game, begins another session and discards changes after the last checkpoint.
Traveling between lots remains part of the current session. Core cognition and memory records
share the checkpoint and roll back together.

The model is instructed to use two to four natural sentences shaped by the Sim's personality,
emotion, and relationship. It is also instructed to ground factual recall in player-provided facts
and retained memory and to admit when evidence is absent. Enable `response_rejection_enabled` only
when deterministic enforcement and correction retries are preferred over accepting every model
reply.

Live validation on 2026-07-16 confirmed that an unsaved codeword was removed after returning to
the Main Menu, a normal save retained `PERSIST-GREEN-963` for Nanami Ito after reload, scratch-slot
saves did not checkpoint memory, and separate Save As branches restored their own histories.

Checkpoints and the session marker are stored beside the configured active database with
`.empneon-saved.slot-<id>` and `.empneon-session` suffixes. The former single
`.empneon-saved` checkpoint is migrated to its recorded slot when possible. Preserve these files
when backing up retained memory. Stop the game and backend before deleting them.

TTS is off by default. Enabling `tts.enabled` and setting `tts.endpoint` sends dialogue,
voice identifiers, and voice settings to that endpoint.

## Privacy and Data Retention

Core stores Sim identifiers and names, traits, moods, relationships, locations,
conversation text, generated dialogue, memories, decisions, and consequences in its
SQLite database. Debug logs are written under `logs`, with an operating system
temporary-directory fallback if that directory is unavailable.

For local providers, prompts remain on the local machine unless that provider performs
its own network calls. A remote provider receives the context needed for the request,
which may include NPC and player-controlled Sim names, traits, moods, relationships,
location, memories, and player-entered dialogue. A configured remote TTS endpoint receives
generated dialogue and voice settings. Review those services' retention policies before
enabling them.

The adapter backend has no user accounts, encryption layer, retention scheduler, or authenticated
HTTP API. Keep the backend bound to loopback. To remove retained reference data, stop the game
and backend, then delete the configured `empneon_core_memory.sqlite3`, legacy migration sources,
Empneon checkpoint/session files,
and `logs` files. Back up
save-related data first if continuity matters.

## Hardware Profiles

These are conservative operating profiles, not benchmark results:

| Profile | Provider | Starting limits | Intended use |
|---|---|---|---|
| Provider-free minimum | None required for CLOD 1 | `active_agent_limit: 1` | Connectivity and deterministic autonomy checks |
| Baseline validation target | Small local model | `active_agent_limit: 1`, default token limits | Ryzen 7 4800H, RTX 2060 Laptop 6 GB, 16 GB RAM with The Sims 4 running |
| Remote-provider test | OpenAI-compatible remote endpoint | `active_agent_limit: 1` | Reduce local model pressure while accepting network privacy, latency, and cost |

No recommended hardware profile exists yet. The Core governor has initial admission structures
but does not continuously measure actual process RAM, VRAM, CPU, or frame time. The on-demand
capture below records those values for a controlled request. Increase concurrency only after
observing the game and provider together. Do not increase the default limit of one without a new
concurrent in-game measurement.

The accepted [conservative resource proposal](../../../docs/superpowers/specs/2026-07-29-sims4-conservative-resource-budget-design.md)
therefore retains `active_agent_limit: 1`, the Core `256 MiB` incremental RAM ceiling,
`64/128 MiB` small/large route estimates, and `30/90` second latency estimates. VRAM admission
remains unknown and unenforced because the published captures report total device use rather than
provider-attributable memory.

### Live resource capture

With The Sims 4, the Empneon backend, and LM Studio already running, capture one normal
player-triggered Empneon Social from `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 .\scripts\capture_live_resources.py
```

The command also requires `nvidia-smi` and PresentMon and must run from an elevated terminal so
PresentMon can capture The Sims 4. The backend must be idle and configured with
`active_agent_limit: 1`. After the script prints `ARMED`, start exactly one Empneon Social,
submit a representative message, and wait for its reply. The script stops when the matching
cognition-queue request completes and writes JSON resource samples plus raw PresentMon CSV
evidence under `output/`. Failed attempts retain `.failed.json` and, when available,
`.failed.presentmon.csv` evidence for diagnosis.

The evidence contains machine-specific process IDs and is not committed automatically. Successful
reports retain only the request UUID, not the Sim identifier, prompt, or response. One run does not
define a safe budget, justify higher concurrency, or establish acceptable performance.

## Stage 2 Exit-Gate Test

This test must run with The Sims 4. Unit tests can verify contracts and persistence, but
they cannot prove a playable session, real game consequences, or save/reload continuity.

The current build persists observed identities and pending proposals, attempts the
base-game social super-interaction on the simulation thread, and sends the finishing
result and observed relationship delta back to Core. This code path is not validated until
the following in-game procedure passes. If the installed game exposes different tuning or
callback APIs, the result must remain failed and the Stage 2 checklist must stay open.

### 1. Prepare an isolated test

1. Back up the Sims save and use a dedicated test save.
2. Stop any existing Empneon backend.
3. From the repository root, copy the configuration for the test:

   ```powershell
   Copy-Item .\adapters\thesims4\config\config.json .\stage2-config.json
   ```

4. Open `stage2-config.json`, set `memory_database` to
   `stage2-empneon_core_memory.sqlite3`, and keep
   `host`/`port` at `127.0.0.1:8765`. Then set the test paths:

   ```powershell
   $env:AI_SIM_CONFIG = "$PWD\stage2-config.json"
   ```

   `memory_database` has no environment-variable override. With the copied config and a
   backend started from the repository root, Core writes to
   `$PWD\stage2-empneon_core_memory.sqlite3`.
5. Preserve any existing files with these names if they contain wanted data. Do not delete
   an unverified database.
6. Install Core and the mod, then start the backend as described in **Install and Run**.
7. Confirm `aiping` succeeds.

### 2. Assemble 20 test agents

1. Load one lot or venue containing at least 20 instantiated, non-player Sims. Use normal
   gameplay, a dedicated test save, or trusted test tooling to bring them onto the lot.
2. Keep the player-controlled household separate from the 20 counted NPCs.
3. Record the save name, lot, in-game time, game version, mod commit, provider/model, and
   hardware profile.
4. Take a screenshot or video showing the test population. The current mod has no command
   that proves the candidate count, so visual evidence is required.

### 3. Run autonomous interactions

1. Let game time advance in 30-simulated-minute intervals. Do not invoke `ai.autonomous`;
   the gate requires behavior without a player command.
2. Continue until Core has observed at least 20 distinct NPC IDs and each intended agent
   has participated in an autonomous event.
3. Watch for visible Sims interactions and record before/after relationship or mood state.
4. Check `Documents\Electronic Arts\The Sims 4\ai_sims_agent_loaded.txt` for autonomous
   dispatches and `logs` for backend failures.
5. A `queued` entry proves the game accepted the interaction. A later `confirmed` entry
   proves Core received its finishing result. A proposal or queue entry alone does not
   pass.

### 4. Capture the database evidence

Run this from the same directory used to start the backend:

```powershell
@'
import sqlite3

def scalar(db, sql):
    with sqlite3.connect(db) as connection:
        return connection.execute(sql).fetchone()[0]

core = "stage2-empneon_core_memory.sqlite3"
participants = """
    SELECT actor_id AS id FROM action_results
    UNION
    SELECT target_id AS id FROM action_results WHERE target_id IS NOT NULL
"""
with sqlite3.connect(core) as connection:
    participant_ids = [row[0] for row in connection.execute(participants)]
print("core agents:", scalar(core, "SELECT COUNT(*) FROM agents"))
print("distinct action participants:", len(participant_ids))
print("participant IDs:", sorted(participant_ids))
print("action results:", scalar(core, "SELECT COUNT(*) FROM action_results"))
print("ordered consequences:", scalar(core, "SELECT COUNT(*) FROM action_consequences"))
print("core relationships:", scalar(core, "SELECT COUNT(*) FROM relationships"))
print("pending proposals:", scalar(core, "SELECT COUNT(*) FROM action_proposals"))
print("memory documents:", scalar(core, "SELECT COUNT(*) FROM memory_documents"))
'@ | py -3 -
```

Save the output. For a passing run, `core agents` and distinct stable participants must
both be at least 20. Action results must correspond to actions the game attempted, and
consequences must reflect game-confirmed applied changes rather than proposed changes.
After queued interactions finish, `pending proposals` should return to zero; retained rows
identify actions that never received a game result.

### 5. Save, exit, and reload

1. Save the game under a new name after visible consequences occur.
2. Exit The Sims 4 completely and stop the backend cleanly. Do not remove the active database.
3. Restart the backend with the same configuration, launch the game, and reload that save.
4. Bring the same agents onto the test lot and allow another automatic interval to run.
5. Verify the same stable Sim IDs are reused, prior Core records are still present,
   and new records append rather than replace the earlier evidence.
6. Verify at least one earlier relationship, mood, memory, or other visible social
   consequence is still observable after reload.
7. Run the database report again and save the second output.

### 6. Pass criteria

Mark the Stage 2 exit gate complete only when all are true:

- at least 20 non-player agents have stable persisted identities;
- autonomous interactions occur without a player command;
- the game visibly attempts validated actions;
- Core stores game-confirmed results and ordered consequences;
- at least one social consequence remains observable after save/reload;
- the same agent IDs and prior records survive backend and game restart;
- no provider failure or resource pressure crashes the game;
- the test record includes configuration, hardware, timings, logs, database counts, and
  screenshots or video.

If any condition fails, retain the evidence, leave the exit gate unvalidated, and fix the
failing path before beginning Stage 3.

### Recorded validation

The exit gate passed across a game restart using `stage2-5-config.json`: 20 persistent
Core agents all participated in automatic events, 15 actions succeeded, one failed safely
with `FinishingType.DISPLACED`, zero proposals remained pending, and Core stored 16
ordered consequences. A later 30-sim-minute regression run using
`stage2-6-config.json` completed one automatic NPC social, persisted one ordered
consequence, and left zero pending proposals without producing a new desync.

## Troubleshooting

- `aiping` fails: verify the backend is listening on `127.0.0.1:8765`.
- Backend import fails: install the project with Python 3.11 or newer.
- Mod build fails: verify `py -3.7` is installed and available.
- Commands are missing: enable script mods, reinstall, clear the cache, and restart the
  game.
- Provider calls fall back to generic dialogue: check the configured endpoint, loaded
  model, and `logs/ai_provider.log`.
- Social enqueue failure: run `ai.socialtunings friendly` on an active lot and inspect
  `ai_sims_agent_loaded.txt`. The optional final word filters loaded tuning names, and all
  matches are written to the marker file even though console output is capped at 100.
- Repeated backend `POST /action-result` status `400`: reinstall the current mod and restart the
  game. Current builds treat HTTP `400` through `499` as permanent, log the rejected decision ID
  and backend response in `ai_sims_agent_loaded.txt`, and pause after one attempt. Network and
  HTTP `500` through `599` failures continue retrying with exponential backoff.
- `_weakrefset.py:121` reports `frozenset` and `tuple`: reinstall the current mod and clear
  `localthumbcache.package`. The adapter must leave the full-autonomy request's
  `object_list` unset because current game builds use tuple motives on native object
  discovery but require set-compatible motives when a restricted list is injected.
