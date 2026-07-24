# Sims 4 Semantic Memory Selector Design

**Date:** 2026-07-23
**Status:** Implemented; date recall live-passed, response synthesis remains partial

## Goal

Recall confirmed shared memories when the player paraphrases a question, without adding every past
interaction to the dialogue prompt. The design must apply to plans, preferences, promises,
introductions, conflicts, locations, and other remembered scenarios rather than special-casing
dates.

Perfect recall is not guaranteed by a local generative model. Success means that semantically
equivalent questions select the same supporting memories despite having little or no word overlap.

## Current limitation

Confirmed interactions are persisted and pair-scoped correctly. Retrieval currently relies on
token overlap, regular-expression recall cues, and a token-hash vector. The token hash is not a
semantic embedding, so different wording can miss a stored fact even when the fact is present.
Adding more question phrasings to regular expressions cannot solve the general problem.

## Retrieval design

Before the main dialogue generation, Empneon builds a bounded candidate list from confirmed
interactions observed by both Sims. Candidate collection remains deterministic and pair-scoped:

1. Include older lexical matches.
2. Include the newest interactions containing attributed durable facts.
3. Fill remaining space with the newest confirmed exchanges.
4. Stop before the serialized candidate JSON exceeds 6,000 characters.

Each candidate contains only a short request-local memory ID, timestamp, attributed facts, player
message, and model dialogue. It does not contain profiles, game state, relationship state, or the
main dialogue prompt. Empneon maps selected memory IDs back to stored event IDs locally so the model
cannot alter or shorten database identifiers.

Empneon sends the candidate list and current player message through the configured `small` LM Studio
task. The selector returns strict JSON containing zero to three candidate memory IDs. Empneon
rejects unknown IDs, duplicates, and more than three results. When a selection includes attributed
facts, selected no-fact recall answers are removed before prompt assembly. Only the selected full
memories enter
`Recalled long-term history` in the existing main dialogue request.

The selector prompt distinguishes evidence types:

- Attributed facts are preferred for questions about world state, agreements, preferences, plans,
  identity, and past events.
- Full exchanges may be selected when the player asks what somebody previously said or how a
  conversation occurred.
- A previous answer to a memory question with no supporting fact is not authoritative evidence.
- Relevance is semantic; matching exact words is not required.

The 6,000-character candidate limit leaves room for selector instructions inside the configured
2,048-token small-model context. Request size therefore does not grow indefinitely with the
relationship history.

## Failure behavior

The current deterministic retrieval remains the fallback. Empneon uses it when there are no
candidates, LM Studio is unavailable, the selector response is malformed, or no returned ID belongs
to the candidate set. Selector failure must not prevent the main dialogue request.

No stored events are deleted or rewritten. Incorrect historical replies remain audit records but
are not preferred over attributed supporting facts.

## Scope boundaries

This iteration reuses the configured LM Studio model and existing episodic database. It does not add
an embedding-model dependency, stateful LM Studio chat, an attached Markdown memory file, or a new
database schema. True embedding-based RAG remains the upgrade path if histories become too large for
the bounded candidate strategy.

## Verification

Automated tests will cover:

- Equivalent paraphrases selecting the same date-and-time agreement.
- An unrelated scenario, such as asking indirectly where an item was hidden.
- Pair isolation so one Sim cannot retrieve another pair's memories.
- Unsupported prior recall answers losing to attributed facts.
- Unknown, duplicate, excessive, malformed, and empty selector IDs.
- Provider failure falling back to deterministic retrieval.
- A fixed candidate-prompt size with a long synthetic history.
- The complete Sims 4 adapter test suite.

In-game verification will repeat the existing date test with several phrasings and test at least one
non-date memory after restarting the backend.

The implementation passes all 200 Sims 4 adapter tests. A direct request through the configured LM
Studio model selected only the stored `Tonight, 7pm, at my place` agreement for the indirect date
question. Live testing with `Hey, baby. When are we going on a date?` also recalled that plan, but
the main dialogue model repeated the stored acceptance response verbatim. Retrieval therefore
passes for this date case while fresh, question-specific response synthesis remains the next task.
The remaining manual checks are:

- `When is our date?`
- `Can you tell the day and time we're going on a date?`
- `Any idea where I put the thing that opens the garden?`
