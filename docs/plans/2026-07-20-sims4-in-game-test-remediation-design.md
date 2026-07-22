# Sims 4 In-Game Test Remediation Design

## Scope

Fix the defects recorded during in-game Tests 3 through 7 before beginning Test 8:

- ingest the active aspiration;
- keep current dialogue independent from irrelevant historical needs;
- make supported factual recall consistent, including paraphrased queries;
- require direct handling of romantic invitations without forcing consent;
- replace generic confirmed-memory summaries with concrete exchange summaries.

`FinishingType.OBJECT_CHANGED` remains a game cancellation, not an Empneon retry condition.
Automatic retry could duplicate a social the game already started.

## Design

### Aspiration ingestion

The script mod will probe both known aspiration attributes and callable tracker APIs, including
`get_primary_aspiration`. The first non-empty tuning name remains the canonical aspiration sent in
the existing Sim payload. Core goal synchronization is unchanged because it already converts a
non-unknown aspiration into a stable `Aspiration: ...` goal.

### Relevant private memory

Memory retrieval will rank the Sim's observable memories before the caller applies its pair filter,
without allowing globally similar but inaccessible events to consume the result window. The chat
prompt's memory summary will be derived from the query-relevant pair memories rather than the
unfiltered recent pair history. Existing observation-based privacy remains the authority boundary.

### Response grounding

The existing shared response validator will reject model output that:

- reports a critical need absent from current game state;
- claims not to know a fact supported by prompt-accessible memory;
- ignores an explicit romantic invitation.

For a romantic invitation, the Sim may accept or decline. An acceptance must use romantic intent
and a positive proposed romance delta so the script selects `flirt`; a decline must be explicit and
must not propose romance. Core still applies only consequences reported by the completed native
interaction.

### Deterministic fallback

After the existing two grounded generation attempts, the fallback will answer a supported factual
question from its best relevant memory. Other fallback branches will store a concrete summary made
from the player's message and the generated reply. Romantic fallback declines explicitly and
proposes no romance when the model cannot produce a reliable accept-or-decline response.

## Verification

Regression tests will cover each failing observation before implementation:

- aspiration exposed through a tracker method;
- pair retrieval after unrelated memories crowd the vector result window;
- stale critical needs rejected;
- supported-memory denial rejected and grounded fallback recall;
- romantic acceptance/decline contract and action selection;
- concrete fallback summary.

Then run the Sims 4 backend, script-mod, adapter, release-contract, Core, lint, and type-check suites.
Tests 4 through 7 remain marked partial/failed until the user repeats their in-game steps with a new
release.

## Test 5 follow-up: dialogue repetition and relationship lookup

The clean-database retest exposed two additional defects. `ai.relationship <name>` passes the
display name as a Core agent ID and therefore shows default values, while dialogue validation can
miss romantic invitations phrased as `go out`, `girlfriend`, or `boyfriend`. The model can then
copy the current message or recycle an earlier answer without being rejected.

The script mod will resolve a supplied display name through its existing SimInfo lookup and send
the numeric Sim ID to Core. Numeric IDs remain valid input. No database or API change is needed.

The shared response validator will recognize the additional direct romantic phrases and reject:

- a near-verbatim copy of a sufficiently long current player message;
- reuse of an earlier generated reply for a different player message.

Rejected output follows the existing behavior: one grounded retry, then the deterministic safe
fallback. The model otherwise retains control of wording, tone, personality, emotion, intent, and
relationship proposals. These checks are integrity boundaries, not dialogue templates: the model
must respond rather than echo, address a romantic invitation directly, and keep factual claims
grounded, but it remains free to accept or decline and to express that choice naturally.

Native action selection remains unchanged. `OBJECT_CHANGED` and the absence of a compatible game
social are safe game-state cancellations; retrying them automatically could duplicate or force a
social. Regression tests will cover name-to-ID resolution, the additional romantic phrases,
current-message echo rejection, prior-reply reuse rejection, and preservation of a distinct valid
response.

## Test 5 follow-up: semantic interaction classification

The release retest showed that keyword-based romantic detection remains too narrow and that a
grounding retry can reuse the same contaminated conversation history. A near-copy also escaped the
exact-word-list comparison after adding only one word. The model should interpret social meaning;
the adapter should enforce integrity and provide deterministic degradation.

### Model-available path

The existing dialogue generation call will also return one `player_interaction_kind` value:

- `friendly`;
- `romantic_compliment`;
- `romantic_invitation`;
- `hostile`;
- `informational`;
- `neutral`.

This is not a second model or a second request. The same model classifies the player's message and
writes the reply together. A romantic compliment may receive any distinct, relevant response and
does not require acceptance or a romance delta. A romantic invitation must still be accepted or
declined explicitly; acceptance requires flirt intent and a positive proposed romance delta.

The adapter retains a small local classifier as a safety and offline fallback. It overrides the
model only for an unmistakable direct romantic invitation or another existing integrity boundary.
It does not prescribe wording for valid model output.

### Repetition retry

Echo detection will compare normalized ordered word sequences rather than require exact equality.
For messages of at least six meaningful words, a similarity of `0.8` or greater is an echo. When
the model copies the current message or reuses a prior reply, the one existing retry rebuilds the
prompt with `Recent conversation: None yet` while retaining the Sim profile, current game state,
pair-scoped memories, relationship, and current player message. This removes the repetition source
without reducing the model to a template or adding another model call.

### Model-unavailable path

When Core degrades the request to provider-free CLOD 1, the Sims adapter will convert its local
classification into the existing deterministic response shape before the action proposal is
stored. Offline responses remain conservative and non-creative but relevant:

- needs questions report current critical needs;
- supported factual questions use accessible memory and unsupported ones admit uncertainty;
- romantic invitations establish a polite boundary with no romance consequence;
- romantic compliments acknowledge the sentiment without copying it;
- hostile messages establish a boundary;
- friendly and neutral messages acknowledge the speaker naturally.

Core remains responsible for routing, usage telemetry, action records, and confirmation gating.
The adapter remains responsible for Sims-specific interpretation and dialogue. No database, API,
provider, or persistence change is required.

### Verification

Regression tests will reproduce Karmine's near-copy and repeated-history fallback, verify that the
retry prompt omits conversation history, distinguish a romantic compliment from an invitation,
confirm that an unavailable provider records CLOD 1 while returning a relevant adapter fallback,
and preserve all existing privacy, consent, and native-confirmation tests.
