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

   Close The Sims 4 before installing. In a source checkout, the installer always rebuilds current
   source first. A release ZIP without `build_mod.py` continues to use its bundled prebuilt
   artifacts.

5. In The Sims 4, enable custom content and script mods, then restart the game. Clicking another
   Sim now shows **Empneon Social** in the pie menu. **Start conversation** routes to the target
   and opens one native input box. Sending displays the player's message with their portrait and
   queues **Waiting for response**, where both Sims play a cosmetic conversation animation. The
   reply is a notification with the target Sim's portrait and ends the interaction. A new message
   requires a new Empneon Social. The current animation may occasionally include a bored-looking
   gesture from the target Sim; it has no intended gameplay effect. Safe cancellation, relationship
   feedback, and save/reload continuity are documented in the
   [setup guide](docs/setup.md).

   Explicitly cancelling **Waiting for response** suppresses late dialogue and consequences.
   Game-driven finishes while the backend is still working requeue the same waiting session without
   sending another backend request; the task ends naturally after response delivery. Failed
   cancellation records retain zero applied changes across backend restart. Permanent HTTP client
   errors while confirming an action result pause after one attempt and include their decision ID
   and backend response in `ai_sims_agent_loaded.txt`; network and server failures retain bounded
   exponential backoff.

   Confirmed pair history is selected through a bounded semantic-memory request, with deterministic
   recall as fallback. Recall constraints keep attributed facts ahead of newer factless
   replies and validate requested time and location evidence. Live save/reload testing retrieved
   the correct `Tonight at 7 pm at your place` plan and delivered it in fresh wording. If both
   corrected model attempts remain unsupported, the adapter returns an attributed quotation
   instead of inventing or reversing the fact. Concrete identifiers such as
   `PRIVATE-GARDEN-731` require evidence containing the same identifier; an uninformed pair
   receives an uncertainty response rather than a location inferred from unrelated memories.
   Possessive code-word facts retain their owner across save branches: `your code word` resolves
   to the responding Sim and is answered as `my code word`, while `our code word` resolves to the
   shared/message-author fact. Supported factual recall is always relationship-neutral even if a
   model labels the wording as romantic.
   Live testing also retrieved `under the blue bench` from the non-date paraphrase
   `Where is the garden code item?` before and after backend restart, while the uninformed pair
   disclosed no location.

   The July 27 expanded matrix passes semantic preference, promise, identity, and conflict recall
   across backend/game restart. Primary attributed evidence survives paraphrased questions;
   factless prior answers cannot displace it; preference, complete-promise, and sibling-owner
   checks reject superficially related but incorrect replies. Generated recall text is not
   promoted to a new responder fact, historical attributed fallbacks recover the quoted fact owner
   at read time, and an uninformed pair discloses neither the preference nor conflict fact. All
   authoritative factual decisions remain relationship-neutral and apply no executable changes.

   The July 27 social-category retest also exercised friendly, funny, mean, and mischief player
   messages. Explicit dialogue/category mismatches are corrected conservatively, incompatible
   relationship outcomes become `none`, hesitant non-romantic replies cannot remain positive
   romance, and an exact repeated prompt may receive a relevant repeated answer without weakening
   the guard against recycling replies for different prompts. Mean, funny, and mischief terminal
   behavior passed live with no relationship mutation. Later rebuilt-package tests accepted normal
   LM Studio funny and mischief dialogue while preserving relationship-neutral outcomes.

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
If the configured provider is unavailable, player dialogue returns a conservative local CLOD 1
response without relationship consequences. The `aiautonomous` diagnostic accepts both legacy
sim-only and scheduled speaker/listener payloads.

## Configuration

See the complete [installation, configuration, privacy, and hardware guide](docs/setup.md).
Use the [in-game Core feature test plan](docs/in-game-core-feature-test-plan.md) to validate every
implemented identity, memory, cognition, confirmation, portability, and persistence capability.
All 15 sections of that plan passed live acceptance on 2026-07-26. The expanded July 27 semantic
category matrix also passed informed recall, uninformed-pair privacy, neutral outcomes, and final
backend/game restart persistence. The July 27 social breadth retest established safe live terminal
behavior for all five social categories. A later provider-backed funny response was accepted but
remained categorized as friendly and applied positive friendship; both initial provider-backed
mischief attempts were rejected for `explicit mischief` before the neutral deterministic
fallback. The live tuning probe then confirmed the mischief mapping was stale: the game loads
`mixer_social_LieAboutCareer_group_mischief_skills`. Empneon now maps that exact tuning, and the
discovery regression proves all five categories remain advertised. An intermediate mischief
attempt completed safely through the neutral deterministic fallback, but artifact inspection
proved the game was still running the stale July 26 archive. The installer now rebuilds source
checkouts before copying. After a fresh install and game restart, provider-backed decision
`0f649c50-8e69-44c5-8fe4-a103b9582cc5` used CLOD 2 semantic selection and CLOD 3 dialogue,
returned an accepted `mischief` response, and applied no relationship changes. The
funny classifier now recognizes the observed `funniest` and `jokes` forms and automated coverage
proves that reply is recategorized to relationship-neutral `funny`. A rebuilt-backend live retest
then returned a joke without any explicit funny marker, kept category `friendly`, and again applied
positive friendship. Hermes now makes `friendly` or `funny` responses to incoming funny
interactions relationship-neutral and actionless while preserving their dialogue and response
category. Automated regression and rebuilt-backend live confirmation both pass.
The packaged mod currently requires the backend at `127.0.0.1:8765`.

## Files

- `backend/ai_sims_server.py`: local game bridge; `/chat` and `/autonomous` run through Core
- `backend/empneon_state.py`: unified Core identity, memory, migration, and diagnostics integration
- `ts4script/ai_sims_agent.py`: Sims 4 interaction, autonomy bridge, and diagnostic commands
- `tuning/empneon_social_interaction.xml`: custom pie-menu interaction tuning
- `build_mod.py`: builds `Empneon_TheSims4.ts4script` and `Empneon_TheSims4.package`
- `install_mod.ps1`: rebuilds source checkouts, installs both artifacts, and removes legacy copies
- `test.py`: smoke test for `/chat`
