# README Boundary and Markdown Reference Cleanup Design

## Goal

Keep the repository documentation internally valid and give each README one clear owner:

- the root `README.md` documents Empneon Core;
- `adapters/thesims4/README.md` owns The Sims 4 information;
- `adapters/godot/README.md` owns Godot information.

The root README may contain a short navigation section linking to the two adapter READMEs, but no
adapter-specific setup, features, status, validation, hardware, compatibility, or release details.

## Documentation boundaries

### Root README

Retain:

- Empneon Core's purpose and beta status;
- Core capabilities and architecture;
- cognitive levels, memory, grounding, providers, telemetry, and replay;
- Core-only development and test commands;
- Core status, roadmap, release format, documentation, license, and responsible-use guidance;
- links to the Sims 4 and Godot adapter READMEs as navigation only.

Remove or relocate:

- adapter badges and feature summaries;
- Sims and Godot implementation details;
- adapter installation and configuration;
- adapter-specific validation, hardware measurements, compatibility warnings, release tags, and
  affiliation disclaimers.

### The Sims 4 README

Make the adapter README the authoritative entry point for:

- supported gameplay and runtime behavior;
- installation, configuration, privacy, compatibility, and diagnostics;
- backend architecture;
- hardware measurements and validation status;
- Sims release naming and EA/Maxis affiliation disclaimer;
- links to the surviving Sims setup, benchmark, test-results, and artifact documentation.

Detailed evidence may remain in adapter-local documents. The README summarizes and indexes it.

### Godot README

Make the adapter README the authoritative entry point for:

- release installation and development;
- current portability scope and validation evidence;
- Godot release naming;
- links to relevant adapter files and commands.

## Reference cleanup

Inspect every surviving Markdown file, including hidden repository directories.

- Update Markdown links whose targets moved.
- Replace references to the two former Sims test files with
  `adapters/thesims4/docs/in-game-core-feature-tests.md`.
- Replace deleted historical design, plan, audit, and report paths with accurate wording or a
  surviving equivalent; do not recreate removed files merely to satisfy a link.
- Keep external URLs unchanged unless they are malformed.
- Preserve historical claims while removing assertions that a deleted document still exists.

## Verification

The completed cleanup must satisfy:

1. Every local Markdown link and image target resolves.
2. Repository-looking `.md` paths in surviving Markdown do not identify deleted files.
3. Root README adapter terms appear only in the approved navigation links or generic descriptions
   of the Core adapter contract.
4. Sims-specific content is discoverable from `adapters/thesims4/README.md`.
5. Godot-specific content is discoverable from `adapters/godot/README.md`.
6. `git diff --check` reports no whitespace errors.

No application code or runtime behavior changes are in scope.
