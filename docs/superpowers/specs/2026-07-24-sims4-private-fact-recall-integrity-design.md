# Sims 4 Private Fact Recall Integrity Design

**Status:** Implemented; automated and live acceptance verification passed

## Goal

Make confirmed concrete player declarations such as
`PRIVATE-GARDEN-731 is under the blue bench` authoritative recall evidence. An informed Sim must
answer from that evidence, while an uninformed Sim must not treat earlier questions or generated
answers as knowledge.

## Root Cause

The Sims fact extractor recognizes only a narrow set of first-person declarations, so the confirmed
identifier assignment is retained as conversation history but not as an authoritative fact. Recall
then falls back to token overlap across raw exchanges. That makes the informed fact unenforceable
and lets an uninformed Sim's earlier question look like supporting evidence.

Core's generic location slots intentionally recognize possessive `place`, `home`, and `house`
phrases. Expanding that grammar to every possible object-relative location would broaden Core
semantics unnecessarily.

The first live retest revealed a related false positive: an uninformed Sim's unrelated confirmed
date plan containing `at my place` satisfied the generic location slot for
`Where is PRIVATE-GARDEN-731?`. The identifier itself therefore also has to participate in
evidence selection.

## Design

Keep the correction in the Sims adapter:

1. Allow confirmed player messages with a concrete identifier subject and `is`/`are` predicate to
   become attributed facts. Do not broaden generated-model dialogue fact extraction.
2. When an explicit recall question has no fact matched by Core's specialized time/location slots,
   select authoritative facts whose meaningful terms overlap the question.
3. For explicit recall questions, raw conversation text is not evidence. Only selected authoritative
   facts make `_memory_supports_question` true.
4. Preserve pair scoping, confirmation gating, fact attribution, response correction, deterministic
   fallback, and the rule preventing recall answers from becoming new authoritative facts.
5. When the question contains a concrete identifier, accept only facts containing that same
   identifier before applying generic time/location validation. Unrelated location memories remain
   available for their own questions but cannot authorize an answer about another subject.

## Failure Handling

If an explicit recall question has no pair-scoped authoritative fact, model responses that claim
knowledge fail grounding and deterministic fallback states uncertainty. If a fact exists but both
model attempts fail grounding, the existing attributed deterministic fallback returns the fact.

## Verification

Add regressions proving:

- confirmed `PRIVATE-GARDEN-731 is under the blue bench` becomes attributed evidence;
- the informed pair recalls `under the blue bench`;
- an uninformed pair with earlier questions still has no evidence and receives uncertainty;
- an unrelated attributed location fact such as `Tonight, 7 PM, at my place` does not support the
  identifier question;
- unconfirmed declarations remain inaccessible;
- existing date/time constraints, possessive-location ownership, pair privacy, fresh response
  synthesis, and provider usage tests continue to pass.

Final verification passed `235` Sims adapter tests, `224` Core tests, Ruff, mypy across `52` source
files, and Python compilation. In the live acceptance run, the informed Sim answered `under the
blue bench`; the uninformed Sim's fabricated model response was rejected and replaced with
`I don't know or remember that.`
