# Sims 4 POC Setup and Privacy

This guide covers the current Windows proof of concept. It is not yet the validated
20-agent reference-adapter release.

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
2. Install the script mod:

   ```powershell
   .\poc\install_mod.ps1
   ```

   The script builds with Python 3.7, copies
   `AI_Sims_Agent.ts4script` into the game's `Mods` directory, and clears the Sims
   thumbnail cache.
3. Start the backend from the repository root:

   ```powershell
   .\poc\run_backend.ps1
   ```

4. Restart The Sims 4, load a household, and run `aiping` in the cheat console.
5. Use `aichat Bella Goth | Hello` for a model-backed interaction. With a lot active,
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

## Troubleshooting

- `aiping` fails: verify the backend is listening on `127.0.0.1:8765`.
- Backend import fails: install the project with Python 3.11 or newer.
- Mod build fails: verify `py -3.7` is installed and available.
- Commands are missing: enable script mods, reinstall, clear the cache, and restart the
  game.
- Provider calls fall back to generic dialogue: check the configured endpoint, loaded
  model, and `poc/logs/ai_provider.log`.
