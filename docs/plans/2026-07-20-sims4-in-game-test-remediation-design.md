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
