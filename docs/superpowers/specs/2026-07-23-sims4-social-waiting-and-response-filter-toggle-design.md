# Sims 4 Social Waiting and Response Filter Toggle Design

**Date:** 2026-07-23
**Status:** Implemented and live-tested. Waiting animation is visible; occasional bored-looking
target gestures are accepted cosmetic behavior. Response rejection defaults to disabled.

## Goal

Make `Waiting for response` a real two-Sim social interaction so its native
conversation animation can run, and make model-response rejection optional and
disabled by default.

## Interaction design

`Start conversation` remains the short routing/input interaction. After the
player submits text, it ends and queues the existing `Waiting for response`
interaction.

`EmpneonWaitingInteraction` becomes a Sims 4 `SocialSuperInteraction`. Its tuning uses the
base-game chat social group and native non-touching listen/idle animation factories. The initiating
and linked target interactions share the Empneon conversation-session ID. Only the initiating
interaction creates a non-queued friendly mixer and builds its visual outcome sequence; gameplay
fields and the normal outcome element are disabled. The linked interaction keeps the target Sim
participating in the social group.

The waiting tuning contains no loot or native relationship outcome. Empneon
continues to apply its own friendship/romance result after the reply appears.
The initiating waiting interaction is canceled naturally when the response is
displayed, and the linked interaction ends with it.

## Response rejection toggle

Add a top-level boolean configuration value:

```json
"response_rejection_enabled": false
```

When `false`, the first structurally usable provider response is returned after
normalization. Grounding, dialogue-copy, role-confusion, and response-category
rejection do not retry or replace it. JSON extraction and normalization remain
active because the Sims adapter requires a stable response object; plain-text
model output remains accepted through the existing plain-text fallback.

When `true`, the current validation, retry, correction-prompt, and deterministic
fallback behavior remains unchanged.

The backend validates that the configured value is a JSON boolean during
startup. Changing it requires restarting the backend, not the game.

## Verification

Automated tests cover the social base class, linked session propagation,
initiator-only animation, loot-free native tuning, default-off configuration,
disabled-filter first-response acceptance, and enabled-filter retry behavior.
The complete Sims 4 test suite and mod build must pass before installation.

In-game verification confirmed one visible `Waiting for response` task on Sim A, both Sims animate
while waiting, and the task ends when the reply appears. Automated coverage confirms that an
otherwise rejectable model reply is displayed unchanged with filtering off.
