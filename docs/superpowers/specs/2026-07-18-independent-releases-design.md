# Independent Releases Design

## Goal

Publish Empneon Core, the The Sims 4 adapter, and the Godot adapter as independent,
installable GitHub Releases without external repository credentials. A Core release also
publishes matching adapter releases so every supported adapter is built against the same Core
version.

## Versioning

The monorepo uses one synchronized semantic version for all three Python distributions and
release artifacts. A release version `X.Y.Z` has these tags:

- `core-vX.Y.Z`
- `thesims4-vX.Y.Z`
- `godot-vX.Y.Z`

The tag version must equal `empneon.__version__`, `empneon_thesims4.__version__`,
`empneon_godot.__version__`, and the corresponding package metadata. Adapter dependencies use
the exact compatible Core minor line, `empneon>=X.Y.Z,<X.(Y+1)`. Prerelease identifiers follow
Python package and SemVer syntax when supported by both.

## Triggers and Selection

One `.github/workflows/release.yml` workflow owns releases.

- A pushed `core-v*` tag validates, builds, and publishes Core, The Sims 4, and Godot.
- A pushed `thesims4-v*` or `godot-v*` tag publishes only that adapter.
- `workflow_dispatch` accepts a component (`all`, `core`, `thesims4`, or `godot`) and version.
- A published `core-v*` GitHub Release publishes only missing adapter releases. This supports
  Core releases created manually in GitHub and avoids recreating Core.
- Existing releases are detected before publishing. A matching existing release is left intact;
  mismatched or duplicate assets fail rather than being overwritten silently.

Tags are the preferred automation path. `core-v*` is the single release-train trigger because it
validates all components before any GitHub Release is created.

## Workflow Architecture

The workflow has three phases:

1. `prepare` validates the selected tag or manual inputs and emits the normalized version and
   selected components.
2. Component build jobs run their own tests and metadata checks, then upload immutable workflow
   artifacts. Core and Godot run on Ubuntu. The Sims 4 runs on Windows because its script mod is
   compiled for Python 3.7.
3. Component publish jobs download only their matching artifact and create a GitHub Release with
   generated notes plus component-specific installation text.

The workflow defaults to `permissions: contents: read`. Only publish jobs receive
`contents: write`. It uses the repository `GITHUB_TOKEN`; no PAT, cross-repository token, signing
secret, or external publishing credential is introduced. Official GitHub actions are pinned to
major versions already used by the repository.

## Core Artifact

Core runs its full test suite and scenario regressions, builds with `python -m build`, validates
wheel and sdist metadata with `twine check`, and installs the wheel into a clean virtual
environment for an import/version smoke test.

The `core-vX.Y.Z` release contains:

- the `empneon-X.Y.Z` wheel
- the `empneon-X.Y.Z` source distribution
- `SHA256SUMS.txt`

This makes Core directly installable with `pip install <downloaded-wheel>` or from the GitHub
asset URL. Publishing to PyPI is outside this design because it would require a separate trusted
publisher configuration and is not needed for pip installability.

## The Sims 4 Artifact

The Sims job runs adapter and backend tests, builds its Python wheel, validates metadata, installs
the wheel in a clean environment, and compiles the script mod with Python 3.7. The gamer-facing
archive is `Empneon-TheSims4-X.Y.Z.zip` and contains only:

- `dist/Empneon_TheSims4.ts4script`
- `dist/Empneon_TheSims4.package`
- `backend/ai_sims_server.py`
- `config/config.json`
- `install_mod.ps1`
- `run_backend.ps1`
- `README.md`
- `docs/setup.md`
- the adapter wheel and required Core wheel

`build_mod.py` produces the new Empneon artifact names. `install_mod.ps1` installs the prebuilt
files when present and compiles only as a development fallback. It removes both the old
`AI_Sims_Agent.*` files and the new Empneon files before copying, preventing duplicate mods.
Internal module names, diagnostic commands, tuning identifiers, and the legacy database name stay
unchanged to preserve game and migration compatibility. Visible game messages use Empneon.

The ZIP excludes source tests, caches, benchmark output, local databases, environment files,
secrets, build tooling not required to install, and other adapters.

## Godot Artifact

The Godot job runs adapter tests, builds and validates its wheel, installs it in a clean virtual
environment, and packages `Empneon-Godot-X.Y.Z.zip` with only:

- the adapter wheel and required Core wheel
- `portability/main.gd`
- `portability/main.tscn`
- `portability/project.godot`
- `portability/scenario.json`
- `README.md`

Tests, caches, local databases, development metadata, benchmark output, and unrelated adapters are
excluded. The workflow validates the expected ZIP member list exactly.

## Packaging Validation

A small standard-library release checker is shared by local tests and GitHub Actions. It:

- parses and validates component/tag/version selection
- checks project metadata and imported package versions
- verifies archive members against explicit allowlists
- rejects unsafe paths, secrets, databases, caches, tests, and unrelated adapter paths
- writes SHA-256 checksums for the final release assets

The checker does not become a generic packaging framework. It supports exactly `core`,
`thesims4`, and `godot`; a future adapter adds one explicit component definition and tests.

## Release Notes

Each release uses GitHub-generated notes and prepends a short component-specific template:

- Core: supported Python version and wheel installation command.
- The Sims 4: extract, run `install_mod.ps1`, install the included wheels, and start the backend.
- Godot: install included wheels and open/import the `portability` project.

The notes link back to the component README and state the matching Core version. Checksums are a
release asset, not pasted into mutable notes.

## Failure Handling

No release is published until every component selected by a Core release train has built and
validated successfully. Build artifacts are passed through GitHub workflow artifacts, not rebuilt
in publish jobs. A failed test, version mismatch, unexpected archive member, failed clean install,
or metadata error stops publication. Individual adapter releases only gate on Core plus that
adapter's relevant checks.

GitHub Releases cannot provide an atomic multi-release transaction. If GitHub fails after one
release is created, rerunning is safe: already matching releases are skipped and missing releases
are created.

## Tests and Documentation

Repository tests cover version parsing, selected components, forbidden files, exact archive
contents, checksums, and Sims legacy cleanup/new artifact naming. CI continues to run the existing
monorepo suites. The root and adapter READMEs document tag conventions, manual dispatch, release
contents, checksum verification, and gamer installation.

## Non-Goals

- PyPI publication
- package signing or provenance beyond GitHub's release and artifact records
- external repositories or external repository tokens
- automatic version bump commits
- support for adapters other than The Sims 4 and Godot
