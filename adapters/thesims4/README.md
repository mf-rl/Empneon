# Empneon for The Sims 4

The Sims 4 adapter, script mod, and local bridge for Empneon Core.

## Install a release

Download `Empneon-TheSims4-X.Y.Z.zip` from GitHub Releases and extract it. From the extracted
directory:

```powershell
.\install_mod.ps1
.\run_backend.ps1
```

The release already contains `Empneon_TheSims4.ts4script` and
`Empneon_TheSims4.package`; gamers do not need Python 3.7. The installer also removes legacy
`AI_Sims_Agent.*` files so only one copy of the mod remains. On first launch,
`run_backend.ps1` creates a local `.venv` and installs the bundled Empneon wheels. Python 3.11+
and an internet connection for third-party dependencies are required.

## Run from source

Requires Python 3.11 or newer for the backend. Python 3.7 is needed only to build the Sims
script mod from source.
From the public monorepo, install Core and this adapter first:

```powershell
py -3.12 -m pip install -e ..\..\core -e .
```

1. Start LM Studio's local server at `http://127.0.0.1:1234` or select another provider
   in `config/config.json`.
2. Load a model when using LM Studio. Core discovers the loaded model and uses LM Studio's
   native `/api/v1/chat` endpoint.
3. Run the backend:

```powershell
.\run_backend.ps1
```

4. Install the script mod and interaction tuning:

```powershell
.\install_mod.ps1
```

5. In The Sims 4, enable custom content and script mods, then restart the game. Clicking another
   Sim now shows **Empneon Social** in the pie menu. **Start conversation** routes to the target
   and opens one native input box. Sending displays the player's message with their portrait and
   queues **Waiting for response**, where both Sims play a cosmetic conversation animation. The
   reply is a notification with the target Sim's portrait and ends the interaction. A new message
   requires a new Empneon Social. The current animation may occasionally include a bored-looking
   gesture from the target Sim; it has no intended gameplay effect. Safe cancellation, relationship
   feedback, and save/reload continuity are documented in the
   [setup guide](docs/setup.md).

   Confirmed pair history is selected through a bounded semantic-memory request, with deterministic
   recall as fallback. Shared Core constraints keep attributed facts ahead of newer factless
   replies and validate requested time and location evidence. Live save/reload testing retrieved
   the correct `Tonight at 7 pm at your place` plan and delivered it in fresh wording. If both
   corrected model attempts remain unsupported, the adapter returns an attributed quotation
   instead of inventing or reversing the fact. Concrete identifiers such as
   `PRIVATE-GARDEN-731` require evidence containing the same identifier; an uninformed pair
   receives an uncertainty response rather than a location inferred from unrelated memories.
   Live testing also retrieved `under the blue bench` from the non-date paraphrase
   `Where is the garden code item?` before and after backend restart, while the uninformed pair
   disclosed no location.

   The existing diagnostic commands remain available through the cheat console:

```text
ai.loaded
ailoaded
aiping
aichat Bella Goth | Why have you been avoiding me?
aidirector
empneon.status
empneon.timeline
empneon.beliefs
empneon.goals
empneon.usage
```

With a lot active, the mod also submits one NPC-to-NPC interaction every 30 simulated
minutes. Player-controlled Sims are excluded, and a new request is skipped while the
previous one is still running. Autonomous proposals are restricted to mapped base-game
**Ask About Day**, **Apologize**, and **Compliment Appearance** socials; queuing the selected
mapping is reported back to Core only after the native interaction completes. Live validation
confirmed scheduled provider-free CLOD 1 with zero tokens and persistent usage telemetry.
Provider-backed player dialogue likewise records dynamic CLOD, tokens, and latency persistently.

## Configuration

See the complete [installation, configuration, privacy, and hardware guide](docs/setup.md).
Use the [in-game Core feature test plan](docs/in-game-core-feature-test-plan.md) to validate every
implemented identity, memory, cognition, confirmation, portability, and persistence capability.
The packaged mod currently requires the backend at `127.0.0.1:8765`.

## Files

- `backend/ai_sims_server.py`: local game bridge; `/chat` and `/autonomous` run through Core
- `backend/empneon_state.py`: unified Core identity, memory, migration, and diagnostics integration
- `ts4script/ai_sims_agent.py`: Sims 4 interaction, autonomy bridge, and diagnostic commands
- `tuning/empneon_social_interaction.xml`: custom pie-menu interaction tuning
- `build_mod.py`: builds `Empneon_TheSims4.ts4script` and `Empneon_TheSims4.package`
- `test.py`: smoke test for `/chat`
