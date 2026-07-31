# Empneon for The Sims 4

The Sims 4 adapter, script mod, and local bridge for Empneon Core.

## Install a release

From a unified `vX.Y.Z` release, download
`empneon-thesims4-adapter-vX.Y.Z.zip`. The existing independent
`thesims4-vX.Y.Z` release archive remains supported.

Download the `thesims4-vX.Y.Z` release and extract `Empneon-TheSims4-X.Y.Z.zip`. The archive
contains the adapter wheel, matching Core wheel, mod artifacts, and `SHA256SUMS.txt`. From the
extracted directory:

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
Use the [in-game Core tests and results](docs/in-game-core-feature-tests.md) to validate every
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
positive friendship. The runtime now makes `friendly` or `funny` responses to incoming funny
interactions relationship-neutral and actionless while preserving their dialogue and response
category. Automated regression and rebuilt-backend live confirmation both pass.
The July 29 request-scoped resource capture now records system, Sims, backend, provider, GPU, and
PresentMon evidence without retaining conversation content or Sim identity. One initial run and a
three-request thinking-disabled neutral/recall matrix are published in the
[benchmark results](docs/benchmark-results.md); they establish baseline evidence but do not yet
justify a hardware recommendation or higher concurrency. The accepted conservative resource
decision retains one concurrent request and the existing incremental RAM and latency estimates;
no runtime setting changed, and provider-attributable VRAM remains unknown.
The packaged mod currently requires the backend at `127.0.0.1:8765`.
Set `AI_SIM_API_TOKEN` in both the backend and game launch environments to require the shipped
clients to authenticate with the loopback API. Leaving it unset preserves the existing local
development behavior.

Confirmed pair recall now retrieves capped SQL relevance and first/latest windows instead of
materializing complete agent history in Python. Deterministic ranking still preserves old
relevant facts, first/last questions, attributed evidence, and large multi-term queries. SQLite
term matching remains a pair-history scan; add an FTS index only if measured databases make that
scan a latency bottleneck.

## Current status and validation

The adapter is an experimental alpha reference integration. It supports contextual player
dialogue, persistent identity and relationships, pair-scoped confirmed-memory recall, grounded
action proposals with game-confirmed results, save-aware database checkpoints, and provider-free
deterministic autonomy at lower cognitive levels.

The primary local validation machine is:

- Ryzen 7 4800H
- RTX 2060 Laptop GPU with 6 GB VRAM
- 16 GB RAM
- The Sims 4 running concurrently

Request-scoped captures showed significant RAM, GPU, latency, and frame-time pressure while the
game and a local model ran together. The default remains one concurrent agent request. These
measurements are baseline evidence, not a general hardware recommendation or proof of production
scalability.

Evidence and operating guidance:

- [Installation, configuration, privacy, and compatibility](docs/setup.md)
- [Benchmark results](docs/benchmark-results.md)
- [In-game Core feature tests and results](docs/in-game-core-feature-tests.md)
- [Captured artifact manifest](output/README.md)

## Backend architecture

`backend/ai_sims_server.py` remains the executable entry point and compatibility façade. It owns
composition, compatibility exports, process-wide singletons, `run()`, and `self_test()`. Existing
imports and façade-level monkeypatch targets remain supported except for the deliberate cognition
runtime rename to `CognitionRuntime` / `COGNITION_RUNTIME`.

The five extracted modules are inert when imported:

- `backend/config.py`: configuration merging, environment overrides, and logging setup
- `backend/db.py`: SQLite schema and memory-session compatibility helpers
- `backend/agent_manager.py`: agent lifecycle, cognition queue, and Test 10 queue gate
- `backend/cognition.py`: response schemas, prompts, validation, fallback, and cognition runtime
- `backend/server.py`: loopback HTTP server, authentication, validation, and route dispatch

Importing an extracted module does not read configuration, attach log handlers, open a database,
start a worker, or bind a socket. Cognition workers still start on first submission; database
migration/opening remains in `run()` or explicit database calls.

## Files

- `backend/ai_sims_server.py`: executable local bridge and compatibility façade
- `backend/config.py`: inert configuration and logging helpers
- `backend/db.py`: inert database and memory-session compatibility helpers
- `backend/agent_manager.py`: lazy cognition scheduling and agent management
- `backend/cognition.py`: response processing and `CognitionRuntime`
- `backend/server.py`: loopback HTTP request handling and dispatch
- `backend/empneon_state.py`: unified Core identity, memory, migration, and diagnostics integration
- `ts4script/ai_sims_agent.py`: Sims 4 interaction, autonomy bridge, and diagnostic commands
- `tuning/empneon_social_interaction.xml`: custom pie-menu interaction tuning
- `build_mod.py`: builds `Empneon_TheSims4.ts4script` and `Empneon_TheSims4.package`
- `install_mod.ps1`: rebuilds source checkouts, installs both artifacts, and removes legacy copies
- `scripts/capture_live_resources.py`: captures one request-scoped live resource and frame trace
- `test.py`: smoke test for `/chat`

## Affiliation

Empneon is an independent open-source project. It is not affiliated with, endorsed by, or
sponsored by Electronic Arts or Maxis.

Users are responsible for complying with game terms, provider terms, applicable laws, and the
policies of communities where the adapter is distributed.

## License

Licensed under the [Apache License 2.0](../../LICENSE).
