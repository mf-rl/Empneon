# AI Sims Agent

Local AI dialogue/story prototype for The Sims 4.

## Run

Requires Python 3.11 or newer.

1. Start LM Studio's local server at `http://127.0.0.1:1234`.
2. Load a model in LM Studio. The backend reads loaded models from `/api/v1/models` and sends chat through `/v1/chat/completions`.
3. Run the backend:

```powershell
.\run_backend.ps1
```

4. Install the script mod:

```powershell
.\install_mod.ps1
```

5. In The Sims 4, enable script mods, restart the game, open the cheat console, and use:

```text
ai.loaded
ailoaded
aiping
aichat Bella Goth | Why have you been avoiding me?
aidirector
```

## Configuration

Optional environment variables:

- `AI_SIM_MODEL`: LM Studio model id. Default: auto-detect the loaded model, falling back to `local-model`
- `AI_SIM_LLM_BASE_URL`: LM Studio API URL. Default: `http://127.0.0.1:1234/api/v1`
- `AI_SIM_PORT`: backend port. Default: `8765`
- `AI_SIM_DB`: memory database path. Default: workspace DB, with temp-folder fallback if SQLite cannot write there

## Files

- `backend/ai_sims_server.py`: local AI backend; `/autonomous` runs through Empneon Core
- `ts4script/ai_sims_agent.py`: Sims 4 cheat commands
- `build_mod.py`: builds `dist/AI_Sims_Agent.ts4script`
- `test.py`: smoke test for `/chat`
