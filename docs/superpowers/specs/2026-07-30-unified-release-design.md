# Unified Release Design

## Goal

Add a release-published workflow that attaches runnable Empneon Core and The Sims 4 archives to
one GitHub release and publishes the matching Core distribution to PyPI. Keep the existing
independent component-release workflow unchanged.

## Trigger and version contract

The workflow lives at `.github/workflows/unified-release.yml` and runs on:

```yaml
on:
  release:
    types: [published]
```

Unified releases use tags in the exact form `vX.Y.Z`. The workflow rejects other tag shapes and
derives `X.Y.Z` from the tag. Before building, it validates that Core, The Sims 4 adapter, and
Godot adapter metadata all declare that same version. Godot is included in version validation but
does not receive a unified-release archive.

Using `published` covers stable and prerelease publications, including releases first saved as
drafts. GitHub does not reliably emit `created` workflows for draft releases.

## Archive boundaries

The workflow produces exactly two GitHub release assets.

### `empneon-core-vX.Y.Z.zip`

- `README.md`
- `LICENSE`
- `wheels/empneon-X.Y.Z-py3-none-any.whl`

The wheel is sufficient to install and run Core. The source distribution remains a PyPI artifact
but is not duplicated in the runnable ZIP.

### `empneon-thesims4-adapter-vX.Y.Z.zip`

- `README.md`
- `LICENSE`
- `install_mod.ps1`
- `run_backend.ps1`
- `config/config.json`
- `backend/agent_manager.py`
- `backend/ai_sims_server.py`
- `backend/cognition.py`
- `backend/config.py`
- `backend/db.py`
- `backend/empneon_state.py`
- `backend/server.py`
- `dist/Empneon_TheSims4.package`
- `dist/Empneon_TheSims4.ts4script`
- `wheels/empneon-X.Y.Z-py3-none-any.whl`
- `wheels/empneon_thesims4-X.Y.Z-py3-none-any.whl`

The Sims archive excludes tests, source-only build tooling, benchmark captures, databases, Godot
files, and development documentation. It retains the existing directly runnable release layout:
`install_mod.ps1` installs the prebuilt game artifacts, and `run_backend.ps1` creates a local
virtual environment and installs the bundled wheels.

## Packaging implementation

`scripts/release.py` remains the single packaging implementation. A unified-package command will:

1. reuse existing version validation;
2. locate exactly one matching Core wheel and Sims adapter wheel;
3. require both built Sims game artifacts;
4. create each ZIP from an explicit destination-to-source mapping;
5. validate the exact archive member set using the existing archive validator; and
6. return the two archive paths.

No generic recursive directory inclusion is allowed. Explicit mappings prevent local databases,
logs, captures, tests, secrets, or stale artifacts from entering a release.

## Workflow jobs and permissions

### Build

The Windows build job has `contents: read` and:

1. checks out the release tag;
2. installs Python 3.7 for the Sims script mod and Python 3.11 for packaging;
3. installs build, test, and metadata-validation tools;
4. validates the unified tag and repository versions;
5. runs the release-packaging tests;
6. builds Core and Sims wheel/source distributions;
7. validates distributions with Twine;
8. builds the `.package` and `.ts4script` files;
9. creates the two unified ZIPs;
10. smoke-installs Core from the expanded Core ZIP;
11. runs `run_backend.ps1 -InstallOnly` from the expanded Sims ZIP; and
12. uploads the ZIPs and Core distributions as separate internal workflow artifacts.

### Attach release assets

This job depends on Build, downloads only the ZIP artifact, has `contents: write`, and uploads both
ZIPs to the GitHub release that triggered the workflow. Uploading with replacement enabled makes a
failed workflow rerunnable without creating another release.

### Publish Core to PyPI

This job depends on successful release-asset attachment, uses the protected `pypi` GitHub
environment, and has only `id-token: write`. It downloads the already-built Core wheel and source
distribution, then runs:

```yaml
uses: pypa/gh-action-pypi-publish@release/v1
```

The publish job does not check out source or rebuild packages. PyPI must be configured with a
Trusted Publisher for repository `mf-rl/Empneon`, workflow `unified-release.yml`, and environment
`pypi`.

## Failure behavior

Invalid tags, version mismatches, missing or duplicate build artifacts, unexpected ZIP members,
failed package metadata checks, and smoke-install failures stop before external publication.

GitHub release attachment and PyPI publication cannot form one transaction. ZIPs are attached
first. If PyPI rejects the upload, the workflow fails visibly while the tested GitHub assets
remain available. A rerun may replace GitHub assets; PyPI remains authoritative and immutable for
an already-published version.

## Tests

`scripts/test_release.py` will verify:

- unified `vX.Y.Z` parsing and invalid-tag rejection;
- exact archive filenames and member sets;
- inclusion of all seven Sims backend modules and both matching wheels;
- exclusion of Godot, tests, databases, captures, and secrets;
- the `release: types: [published]` trigger;
- separate least-privilege GitHub and PyPI jobs;
- the `pypi` environment and OIDC publisher action;
- attachment to the triggering release rather than creation of another release; and
- preservation of the existing independent-release workflow contract.

CI continues running the release tests, so archive or workflow drift blocks merging.

## Non-goals

- Removing or changing the independent component-release workflow
- Publishing either adapter to PyPI
- Creating a Godot unified archive
- Building deployment infrastructure beyond GitHub Releases and PyPI
