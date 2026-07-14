# Sims 4 POC Setup and Privacy

This guide covers the validated Windows 20-agent reference-adapter proof of concept and
its reproducible exit-gate procedure.

## Requirements

- The Sims 4 with **Custom Content and Mods** and **Script Mods Allowed** enabled
- PowerShell and the Windows Python launcher (`py`)
- Python 3.11 or newer for Empneon Core and the backend
- Python 3.7 for compiling the Sims 4 script mod
- An OpenAI-compatible provider for model-backed conversation; autonomous CLOD 1
  behavior remains provider-free

From the repository root, install Core and its SQLite vector dependency:

```powershell
py -3.12 -m pip install -e .
```

Python 3.12 may be replaced with any installed Python version supported by
`pyproject.toml`.

## Install and Run

1. Configure and start an OpenAI-compatible provider. The default is LM Studio at
   `http://127.0.0.1:1234`.
2. Install the script mod and interaction tuning:

   ```powershell
   .\poc\install_mod.ps1
   ```

   The script builds with Python 3.7, copies `AI_Sims_Agent.ts4script` and
   `AI_Sims_Agent.package` into the game's `Mods` directory, and clears the Sims thumbnail
   cache.
3. Start the backend from the repository root:

   ```powershell
   .\poc\run_backend.ps1
   ```

4. Restart The Sims 4 and load a household. Clicking another Sim exposes the
   **Empneon Social** pie-menu entry. The current entry records the selected actor and target;
   native message input and generated response feedback are not implemented yet.
5. Run `aiping` in the cheat console for backend diagnostics, then use
   `aichat Bella Goth | Hello` for the existing model-backed interaction. With a lot active,
   the mod also submits at most one non-player pair every 30 simulated minutes.

The mod currently connects to `http://127.0.0.1:8765`. Changing the backend host or
port requires changing `BACKEND_URL` in `poc/ts4script/ai_sims_agent.py` and rebuilding
the mod. Do not expose the POC HTTP server to another machine; it has no authentication.

## Configuration

The backend loads `poc/config/config.json` by default. Set `AI_SIM_CONFIG` to use another
JSON file. Environment variables override the loaded file.

| Setting | Purpose | Default |
|---|---|---|
| `host`, `AI_SIM_HOST` | Backend bind address | `127.0.0.1` |
| `port`, `AI_SIM_PORT` | Backend port | `8765` |
| `database`, `AI_SIM_DB` | POC profile, memory, relationship, and conversation database | `ai_sims_memory.sqlite3` |
| `core_database` | Core action and cognition database | `empneon_core.sqlite3` |
| `active_agent_limit` | Concurrent POC agent sessions and Core admissions | `5` |
| `agent_wake_timeout_seconds` | Wait for an agent-session slot | `60` |
| `provider`, `AI_SIM_PROVIDER` | Default provider entry | `lmstudio` |
| `AI_SIM_LLM_BASE_URL` | Override the selected provider endpoint | provider endpoint |
| `AI_SIM_MODEL` | Override both task model IDs | provider model |
| `AI_SIM_API_KEY` | Authorization bearer token | unset |
| `debug` | Verbose backend logging | `true` |

Relative database paths resolve from the backend process's working directory. If the
POC database is not writable and `AI_SIM_DB` is unset, it falls back to the operating
system's temporary directory. The Core database does not have that fallback.

Each entry under `providers` accepts `endpoint`, `model`, and optionally `api_key`.
Prefer `AI_SIM_API_KEY` over storing a secret in the tracked JSON file. `models.small`
and `models.large` may override `provider`, `endpoint`, `model`, `temperature`, and
`max_tokens` per task.

Memory settings:

- `recent_limit`: memories placed in a conversation context
- `summary_every`: number of pair memories before summarization is attempted
- `summary_limit`: maximum memories included in a summary request

TTS is off by default. Enabling `tts.enabled` and setting `tts.endpoint` sends dialogue,
voice identifiers, and voice settings to that endpoint.

## Privacy and Data Retention

The backend stores Sim identifiers and names, traits, moods, relationships, locations,
conversation text, generated dialogue, memories, decisions, and consequences in its
SQLite databases. Debug logs are written under `poc/logs`, with an operating system
temporary-directory fallback if that directory is unavailable.

For local providers, prompts remain on the local machine unless that provider performs
its own network calls. A remote provider receives the context needed for the request,
which may include NPC and player-controlled Sim names, traits, moods, relationships,
location, memories, and player-entered dialogue. A configured remote TTS endpoint receives
generated dialogue and voice settings. Review those services' retention policies before
enabling them.

The POC has no user accounts, encryption layer, retention scheduler, or authenticated
HTTP API. Keep the backend bound to loopback. To remove retained POC data, stop the game
and backend, then delete the configured SQLite databases and `poc/logs` files. Back up
save-related data first if continuity matters.

## Hardware Profiles

These are conservative operating profiles, not benchmark results:

| Profile | Provider | Starting limits | Intended use |
|---|---|---|---|
| Provider-free minimum | None required for CLOD 1 | `active_agent_limit: 1` | Connectivity and deterministic autonomy checks |
| Baseline validation target | Small local model | `active_agent_limit: 1`, default token limits | Ryzen 7 4800H, RTX 2060 Laptop 6 GB, 16 GB RAM with The Sims 4 running |
| Hosted-provider test | OpenAI-compatible remote endpoint | `active_agent_limit: 1` | Reduce local model pressure while accepting network privacy, latency, and cost |

No recommended hardware profile exists yet. The POC governor has initial admission
structures, but the Sims integration does not yet measure actual process RAM, VRAM, CPU,
or frame time. Increase concurrency only after observing the game and provider together.
Do not treat the default limit of five as a validated safe value. Stage 3 must publish raw
measurements before performance or scalability claims are made.

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
   Copy-Item .\poc\config\config.json .\stage2-config.json
   ```

4. Open `stage2-config.json`, set `core_database` to `stage2-core.sqlite3`, and keep
   `host`/`port` at `127.0.0.1:8765`. Then set the test paths:

   ```powershell
   $env:AI_SIM_DB = "$PWD\stage2-poc.sqlite3"
   $env:AI_SIM_CONFIG = "$PWD\stage2-config.json"
   ```

   `core_database` has no environment-variable override. With the copied config and a
   backend started from the repository root, Core writes to `$PWD\stage2-core.sqlite3`.
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
   dispatches and `poc/logs` for backend failures.
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

core = "stage2-core.sqlite3"
poc = "stage2-poc.sqlite3"
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
print("pending proposals:", scalar(core, "SELECT COUNT(*) FROM action_proposals"))
print("POC profiles:", scalar(poc, "SELECT COUNT(*) FROM sim_profiles"))
print("POC relationships:", scalar(poc, "SELECT COUNT(*) FROM relationships"))
print("POC memories:", scalar(poc, "SELECT COUNT(*) FROM memories"))
'@ | py -3 -
```

Save the output. For a passing run, `core agents` and distinct stable participants must
both be at least 20. Action results must correspond to actions the game attempted, and
consequences must reflect game-confirmed applied changes rather than proposed changes.
After queued interactions finish, `pending proposals` should return to zero; retained rows
identify actions that never received a game result.

### 5. Save, exit, and reload

1. Save the game under a new name after visible consequences occur.
2. Exit The Sims 4 completely and stop the backend cleanly. Do not remove either database.
3. Restart the backend with the same configuration, launch the game, and reload that save.
4. Bring the same agents onto the test lot and allow another automatic interval to run.
5. Verify the same stable Sim IDs are reused, prior Core and POC records are still present,
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
ordered consequences. The separate POC profile, relationship, and memory counts remained
zero for this autonomous path. A later 30-sim-minute regression run using
`stage2-6-config.json` completed one automatic NPC social, persisted one ordered
consequence, and left zero pending proposals without producing a new desync.

## Troubleshooting

- `aiping` fails: verify the backend is listening on `127.0.0.1:8765`.
- Backend import fails: install the project with Python 3.11 or newer.
- Mod build fails: verify `py -3.7` is installed and available.
- Commands are missing: enable script mods, reinstall, clear the cache, and restart the
  game.
- Provider calls fall back to generic dialogue: check the configured endpoint, loaded
  model, and `poc/logs/ai_provider.log`.
- Social enqueue failure: run `ai.socialtunings friendly` on an active lot and inspect
  `ai_sims_agent_loaded.txt`. The optional final word filters loaded tuning names, and all
  matches are written to the marker file even though console output is capped at 100.
- `_weakrefset.py:121` reports `frozenset` and `tuple`: reinstall the current mod and clear
  `localthumbcache.package`. The adapter must leave the full-autonomy request's
  `object_list` unset because current game builds use tuple motives on native object
  discovery but require set-compatible motives when a restricted list is injected.
