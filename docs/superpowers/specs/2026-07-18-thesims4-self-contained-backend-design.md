# The Sims 4 self-contained backend release

## Goal

A user can extract `Empneon-TheSims4-X.Y.Z.zip`, install the prebuilt mod, and start the
backend without cloning or locating the Empneon source repository.

## Release layout

The existing runtime ZIP remains the distribution unit. It contains:

- prebuilt `dist/Empneon_TheSims4.ts4script` and `dist/Empneon_TheSims4.package` files;
- Core and The Sims 4 adapter wheels under `wheels/`;
- backend, configuration, setup documentation, `install_mod.ps1`, and `run_backend.ps1`.

Tests must continue rejecting missing runtime files and unrelated source, tests, caches,
databases, or secrets.

## Backend bootstrap

`run_backend.ps1` owns the release bootstrap. When run outside the source checkout, it:

1. Requires a Python 3.11 or newer launcher.
2. Creates `.venv` beside the script if it does not exist.
3. Installs or upgrades the two bundled wheels with the virtual environment's Python.
   Pip may obtain third-party dependencies, currently `sqlite-vec`, from PyPI.
4. Starts `backend/ai_sims_server.py` with the virtual environment's Python.

Every invocation installs the local wheels again. Pip treats an unchanged version as already
satisfied, while this also makes replacing an extracted release reliable without maintaining
custom installation state. A clear error is returned when the bundled wheels or Python are
missing.

Source-checkout development remains supported by using the existing editable environment when
the release `wheels/` directory is absent.

## Mod installation

`install_mod.ps1` continues copying only the prebuilt `.ts4script` and `.package` files into the
Sims 4 Mods directory. It must not build artifacts for a release ZIP. Missing artifacts produce
an instruction to download the complete release.

## Verification

- A contract test checks the release ZIP contains both wheels and both prebuilt mod artifacts.
- A PowerShell contract test checks `run_backend.ps1` creates/uses `.venv` and installs bundled
  wheels without referencing the monorepo Core path.
- The release workflow smoke test extracts the produced ZIP, invokes the bootstrap without
  starting the long-running server, and imports `empneon` and `empneon_thesims4` from its venv.
- Existing Core, adapter, packaging, archive allow-list, and metadata tests remain green.

## Scope

This change covers Windows and The Sims 4 only. It does not bundle Python or third-party wheels
for offline use. Godot bootstrap behavior will be designed after its installation model is
known.
