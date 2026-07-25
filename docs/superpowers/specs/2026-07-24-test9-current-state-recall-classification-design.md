# Test 9 Current-State Recall Classification Design

**Status:** Implemented, automated suites passing, and live-verified

## Problem

Core classifies `How are you feeling right now, and what do you want to do?` as explicit
memory recall because its generic WH-question pattern matches `what do` anywhere in a sentence.
The Sims adapter consequently rejects ordinary state-based model answers for lacking historical
evidence, rejects its fallback for the same reason, and returns HTTP 500.

## Design

Restrict generic `what`, `when`, `where`, `who`, and `which` recall detection to the beginning of
a sentence. Keep the existing independent detection for:

- explicit `remember`, `recall`, and `did I say` requests;
- requested time and location slots;
- generic WH questions that begin a sentence or follow sentence punctuation.

This changes only shared Core query classification. Provider routing, Sims fallback behavior,
fact selection, time validation, location ownership, and private-memory filtering remain
unchanged.

## Verification

Add the exact failed Test 9 message to the Core recall-classification matrix as non-recall and
first verify that it fails. Preserve all existing positive recall cases, including generic
sentence-leading WH questions, time/location questions, and explicit recall wording. After the
minimal classifier change, run:

1. focused Core recall constraints;
2. the complete Core test suite;
3. the complete Sims 4 adapter test suite.

The exact regression passed with all `29` focused recall tests. The complete Core and Sims 4
adapter suites passed `225` and `235` tests. Live Test 9 then returned grounded dialogue at CLOD 3,
recorded positive token and latency usage, and retained the totals after backend restart.
