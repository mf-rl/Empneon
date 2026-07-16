# Empneon for The Sims 4

The Sims 4 adapter, script mod, and local bridge for Empneon Core.

## Run

Requires Python 3.11 or newer for the backend and Python 3.7 to build the Sims script mod.
In the private monorepo, install Core and this adapter first:

```powershell
py -3.12 -m pip install -e ..\core -e .
```

1. Start LM Studio's local server at `http://127.0.0.1:1234`.
2. Load a model in LM Studio. The backend reads `/api/v1/models` and sends chat through
   `/v1/chat/completions`.
3. Run the backend:

```powershell
.\run_backend.ps1
```

4. Install the script mod and interaction tuning:

```powershell
.\install_mod.ps1
```

5. In The Sims 4, enable custom content and script mods, then restart the game. Clicking another
   Sim now shows **Empneon Social** in the pie menu. It opens a native transcript dialog for
   repeated messages and generated replies; progress and errors remain notifications. Safe
   cancellation and save/reload continuity are documented in the
   [setup guide](docs/setup.md).

   The existing diagnostic commands remain available through the cheat console:

```text
ai.loaded
ailoaded
aiping
aichat Bella Goth | Why have you been avoiding me?
aidirector
```

With a lot active, the mod also submits one NPC-to-NPC interaction every 30 simulated
minutes. Player-controlled Sims are excluded, and a new request is skipped while the
previous one is still running. Autonomous proposals are restricted to mapped base-game
**Ask About Day**, **Apologize**, and **Compliment Appearance** socials; queuing the selected
mapping is reported back to Core only after the native interaction completes.

## Configuration

See the complete [installation, configuration, privacy, and hardware guide](docs/setup.md).
The packaged mod currently requires the backend at `127.0.0.1:8765`.

## Files

- `backend/ai_sims_server.py`: local AI backend; `/chat` and `/autonomous` run through Core
- `ts4script/ai_sims_agent.py`: Sims 4 interaction, autonomy bridge, and diagnostic commands
- `tuning/empneon_social_interaction.xml`: custom pie-menu interaction tuning
- `build_mod.py`: builds the `.ts4script` and `.package` mod artifacts
- `test.py`: smoke test for `/chat`
