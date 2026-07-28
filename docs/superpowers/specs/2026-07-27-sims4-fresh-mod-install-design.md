# Sims 4 Fresh Mod Install Design

**Status:** Implemented, automated-verified, rebuilt, and installed

## Problem

`install_mod.ps1` rebuilds only when packaged artifacts are missing. During
development, existing `dist` files can therefore be older than the source. The
July 27 mischief source correction was installed from a July 26 archive that
still contained the stale tuning value.

## Design

When `build_mod.py` is present, the installer always runs it before copying
artifacts. A release ZIP without the builder continues to install its two
prebuilt artifacts and still reports a clear error if either artifact is
missing.

No backend, dialogue, social-category, or game behavior changes. The installer
only guarantees that a source checkout packages its current source.

## Verification

Update the existing installer contract regression first and confirm it fails
against the old missing-artifact-only condition. Apply the minimal branch
change, rerun the focused and full suites, then run the installer and verify
both the rebuilt archive and installed copy contain the live mischief tuning
and have identical hashes.

The regression failed against the old branch and passed after the correction.
All `520` repository tests and scoped static checks pass. With the game closed,
the installer rebuilt and installed matching artifacts containing only the live
mischief tuning name.
