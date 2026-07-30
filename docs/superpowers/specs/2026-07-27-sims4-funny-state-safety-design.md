# Sims 4 Funny State Safety Design

## Status

Implemented, automated-verified, and live-verified on 2026-07-27.

## Problem

The live funny interaction reached the backend with `incoming_category=funny`,
but its marker-free provider reply normalized as `friendly`. Outgoing-only
validation accepted `friendship_positive`, and the adapter converted that
outcome into `relationship.friendship +8`.

## Design

At the runtime boundary, where both incoming and outgoing categories are
available, make `friendly` and `funny` responses to an incoming funny
interaction state-neutral:

- preserve dialogue, intent, emotion, tones, and response category;
- set `trust_delta` to `0`;
- set `relationship_outcome` to `none`;
- set suggested action and animation to `none`.

Mean, mischief, and romance responses remain category-independent and retain
their validated effects. All responses to non-funny incoming interactions
remain unchanged.

## Testing

An automated regression will reproduce the exact latest live reply as
`friendly`, `friendship_positive`, and `trust_delta=1`, then verify that the runtime
preserves the reply/category while neutralizing every state effect. Existing
social-category coverage and the complete repository suites protect working
behavior.
