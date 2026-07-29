# Sims 4 Mischief Tuning Mapping Design

**Status:** Implemented, rebuilt, installed, and live-verified

## Problem

The live `ai.socialtunings lieaboutcareer` command reports
`mixer_social_LieAboutCareer_group_mischief_skills`, while
`NATIVE_SOCIAL_TUNINGS` expects a stale targeted tuning name. Exact tuning
discovery therefore removes `mischief` from the provider's available response
categories.

## Design

Replace only the stale `social.mischief` mapping with the live tuning name.
Update the existing affordance-discovery test fixture to use that literal name,
so the test proves all five social categories remain discoverable.

Aliases and fuzzy matching are intentionally excluded: the live game exposes
one verified tuning, and broader matching could select the wrong interaction.

## Verification

Run the focused discovery test red before the mapping change and green after it,
then run every repository test suite plus the scoped lint, compilation, and
diff checks.

The focused test failed with only `mischief` missing, then passed after the
mapping correction. All `520` repository tests and the scoped static checks
pass. The next live request completed safely but used a stale archive, so it did
not validate this correction. After the fresh archive was installed and the
game restarted, decision `0f649c50-8e69-44c5-8fe4-a103b9582cc5` used LM Studio
at CLOD 2 and CLOD 3, accepted a `mischief` response without retries, and
completed with zero applied changes.
