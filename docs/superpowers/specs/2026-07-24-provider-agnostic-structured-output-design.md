# Provider-Agnostic Structured Output Design

**Status:** Implemented; automated transport coverage and live LM Studio dialogue verified
**Scope:** Empneon Core provider contract, current provider implementations, and
Sims 4 response-category compatibility

## Problem

Empneon Core already exposes a provider-independent `GenerationRequest.schema`,
but its behavior is inconsistent. The OpenAI-compatible provider sends the
schema as structured output, while `LMStudioProvider` ignores it.

This means callers cannot rely on the Core contract. A game adapter may provide
a valid enum, yet provider- or model-specific behavior can return a value
outside it.

## Core contract

`GenerationRequest.schema` will remain the single game- and model-independent
way to request structured output.

Every provider implementation must do one of two things when a schema is
present:

1. translate it to that provider's native constrained-output mechanism; or
2. report that structured output is unsupported instead of silently ignoring
   the schema.

`ModelCapabilities.structured_output` will truthfully advertise which behavior
is available. This contract contains no game categories or model-specific
vocabulary.

## Current provider implementations

The generic OpenAI-compatible provider already sends JSON Schema through
`/v1/chat/completions`; its behavior remains unchanged.

For schema requests, the LM Studio provider will use LM Studio's
OpenAI-compatible `/v1/chat/completions` endpoint and send the same standard
`response_format` contract. Schema-free requests will retain the current
native `/api/v1/chat` behavior.

LM Studio will then advertise structured-output support. Network, payload,
unsupported-schema, and malformed-response failures will continue to surface as
`ProviderError`.

Future providers must implement the same Core contract using their own native
API. Adding a provider will not require changes to any game adapter.

## Defensive category compatibility

Provider enforcement does not replace validation at the game boundary. The
Sims 4 adapter will consistently apply only its existing unambiguous legacy
aliases to `response_category`:

- `friendship` to `friendly`;
- `hostile` to `mean`;
- `romantic_compliment` to `romance`;
- `romantic_invitation` to `romance`;
- the existing `informational` and `neutral` aliases to `friendly`.

It will no longer infer an alias category from words in the generated dialogue.
After alias normalization, categories not present in the game-provided valid
list will still be rejected.

Other games may define different schemas and compatibility rules without Core
knowing their vocabulary.

## Verification

Tests will prove that:

1. The provider-independent schema survives routing unchanged.
2. Providers do not silently discard a requested schema.
3. LM Studio schema requests use `/v1/chat/completions` and include the exact
   caller-supplied schema.
4. LM Studio requests without a schema retain `/api/v1/chat`.
5. The exact failed live friendship response normalizes to `friendly` without
   replacing its dialogue.
6. Known mean and romantic aliases normalize correctly.
7. Unknown or unavailable categories still raise validation errors.

Run the focused Core provider and Sims adapter tests, followed by both complete
test suites and Python compilation checks.
