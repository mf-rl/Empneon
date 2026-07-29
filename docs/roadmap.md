# Empneon Open-Source Roadmap

This roadmap records implemented work and the next verifiable engineering gates. It is not a
feature promise.

## Implemented

- Generic game contracts and structural `GameAdapter` protocol
- The Sims 4 reference adapter and Godot 4 portability adapter
- Game-confirmed action proposals, results, consequences, timeline, and replay
- Persistent identity, relationships, emotions, goals, voice, episodic memory, observations,
  beliefs, provenance, contradictions, and revisions
- Provider-independent request/result contracts
- Native LM Studio and OpenAI-compatible providers selected by Core configuration, with explicit
  structured-output capability enforcement and LM Studio JSON Schema transport
- Deterministic CLOD 1 fallback, bounded scheduling, resource admission, and usage telemetry
- SocietyBench scenarios, raw benchmark artifacts, and regression fixtures
- Versioned SQLite migrations and Core-owned adapter memory documents
- Save-aware The Sims 4 memory checkpoints and one-time legacy memory import
- Single-turn The Sims 4 player dialogue with cancelable waiting, cosmetic conversation animation,
  and bounded game-observed relationship outcomes; live cancellation suppresses late effects and
  preserves zero-change failed records across backend restart; non-user queue finishes now requeue
  the visible waiting interaction without duplicating the backend request
- The Sims dialogue boundary aligns explicit generated wording with friendly, funny, romance,
  mean, and mischief categories, neutralizes incompatible relationship outcomes, permits a
  relevant reply when the player repeats the same prompt, and supplies actionless category-specific
  funny, mean, and mischief fallbacks; all five categories have safe live terminal behavior
- Bounded, pair-scoped semantic memory selection with deterministic fallback and shared recall
  constraints; live date-plan recall succeeds across paraphrasing and save/reload while preserving
  exact time and attributed location ownership in fresh wording
- Confirmed Sims identifier assignments become pair-scoped attributed evidence; live testing
  preserves exact private recall for the informed Sim and rejects an uninformed Sim's fabricated
  answer in favor of explicit uncertainty
- Provider-neutral usage accounting for semantic selection and dialogue generation, with global or
  actor-filtered diagnostics
- The Sims 4 model-backed dialogue path uses Core dynamic cognition routing; live CLOD 3 requests
  and scheduled provider-free CLOD 1 requests retain usage telemetry across backend restart
- Bounded Sims cognition exposes non-sensitive lifecycle diagnostics; a loopback-only,
  auto-releasing acceptance gate live-verifies that real player dialogue preempts already-waiting
  lower-priority ambient cognition without changing scheduler ordering
- Live non-date semantic recall retrieves a paraphrased private location before and after backend
  restart while withholding that location from an uninformed pair
- Live semantic recall preserves preference, promise, sibling ownership, and conflict evidence
  across backend/game restart while withholding preference and conflict facts from an uninformed
  pair and applying no executable changes
- Repeated identity import is semantically idempotent across backend restart for canonical agent,
  personality, relationship, emotion, goal, and optional voice state
- The Sims 4 15-section in-game acceptance suite passes provider-backed and provider-free
  cognition, save-slot isolation, grounded owner-aware recall, neutral factual outcomes, action
  confirmation, replay, cancellation, and persistence
- Exhausted Sims dialogue attempts persist only their normalized rejection reasons and expose
  them on the matching completed timeline decision; prompts and raw model replies are not stored
- Funny interactions remain relationship-neutral even when marker-free provider dialogue is
  independently categorized as friendly
- Exact Sims tuning discovery uses the live
  `mixer_social_LieAboutCareer_group_mischief_skills` mapping for mischief; a fresh-package live
  retest accepted provider dialogue through CLOD 2 selection and CLOD 3 generation, preserved the
  `mischief` category, and applied no relationship changes
- Source-checkout mod installation always rebuilds current source before copying artifacts;
  prebuilt-only release installation remains supported

## Next gates

- A more consistently neutral waiting animation remains optional polish.

### Core integration

- Measure route estimates on the baseline hardware and tune dynamic selection only from observed
  resource and quality evidence.
- Replace remaining adapter metadata documents with typed Core concepts only when a second game
  demonstrates a shared concept.

### Resource evidence

- Measure process RAM, provider VRAM, latency, and Sims frame time for the current single-request
  default on the stated baseline.
- Define safe budgets from measurements before increasing concurrency or claiming scalability.

### Portability

- Keep shared contract tests passing for both adapters.
- Add another adapter only when it exercises a materially different integration boundary.

### Developer experience

- Publish tagged monorepo releases with built Core and adapter artifacts.
- Add concise migration notes whenever a supported API or database schema changes.

## Project boundary

If separate deployment infrastructure becomes viable in the future, it should live in an
independent repository and must not change Core's open-source contracts.
