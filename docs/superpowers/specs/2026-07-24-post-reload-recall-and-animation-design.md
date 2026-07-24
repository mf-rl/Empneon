# Post-Reload Recall and Waiting Animation Design

**Status:** Implemented; post-reload recall and animation live-verified
**Scope:** Sims adapter recall evidence and waiting-animation fallback

## Problem

The latest live test established two independent failures after a Sims save was
reloaded:

1. The confirmed date fact remained persisted and accessible to both actors,
   but the reply did not recall it.
2. The waiting animation repeatedly raised
   `UnboundLocalError: listen_animation_factory` inside EA's
   `SocialMixerInteraction.build_basic_elements`.

The persistence database itself passed. The recall failure occurred because
`recalled_memories()` selected a time-bearing event for a `when` question, then
removed its facts because `date` did not lexically overlap `Tonight, 7pm`.

The animation failure occurred when EA's social-group state was absent by the
time the mapped mixer built listener elements. EA's method leaves its local
listener factory uninitialized in that state.

## Recall design

Keep the existing pair, privacy, confirmation, ranking, deduplication, and
three-result limits.

When a memory qualifies through the existing `answers_when` rule, retain its
time-bearing facts even if normal recall terms do not overlap. All other
memories continue using the existing fact-level lexical filter.

This changes no persistence format and does not expose unrelated or
unobserved memories.

## Animation design

Keep the existing paired native animation path when the mapped mixer's linked
super interaction still has a social group.

When that social group is absent, do not call EA's unsafe
`build_basic_elements` method. Use the already-built visual outcome sequence as
an initiator-only fallback, then continue the waiting sequence normally.

Record one diagnostic and cache the selected initiator-only mode so later
waiting ticks continue using the safe path without retrying EA's unsafe method
or flooding the marker file. Do not recreate, replace, or mutate EA social
groups.

If visual-outcome construction itself fails, record one failure, disable later
animation attempts for that waiting interaction, and continue waiting without
blocking dialogue delivery.

## Non-regression requirements

- Same-session and post-reload recall must use the same persisted evidence.
- Pair scoping, observer privacy, fact deduplication, and result limits remain
  unchanged.
- Existing paired waiting animations remain unchanged when their social group
  is available.
- Dialogue delivery, cancellation, relationship effects, floating headlines,
  structured provider output, and persistence behavior remain unchanged.
- No new dependencies, Core gameplay concepts, or provider-specific behavior.
- No commit or push until explicitly requested.

## Verification

Tests will reproduce the live date query against a confirmed
`Tonight, 7pm, at my place` fact and assert that the selected recalled memory
retains that fact. Existing recall privacy and scoping tests will run unchanged.

Animation tests will cover both branches:

- a valid social group still uses `build_basic_elements` and the paired path;
- a missing social group uses the visual outcome directly, emits one
  diagnostic, and never retries EA's unsafe method or raises.

Run focused red-green tests, then the complete Core and Sims adapter suites,
Python compilation, the Python 3.7 mod build, and diff checks. Live verification
remains pending installation and game/backend restart.
