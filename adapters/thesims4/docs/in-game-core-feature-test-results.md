# Empneon Core In-Game Test Results

Test evidence for `in-game-core-feature-test-plan.md`. Raw diagnostic responses remain local;
this record contains only the evidence needed to determine pass/fail status.

## Test 2: Canonical Sim profile and OCEAN personality

**Status:** PASS

**Procedure:** Saved the game, restarted the game, and queried the same Sim profile.

**Evidence:**

- Stable Sim: Bernard Jaeger (`1048519419914027021`).
- Adapter: `sims4`; age: `16`.
- Profile persisted after save and game restart.
- OCEAN: openness `0.75`, conscientiousness `0.5`, extraversion `0.8`,
  agreeableness `0.75`, neuroticism `0.5`.
- Openness and agreeableness are above the neutral `0.5` baseline; extraversion is also
  distinctly non-neutral.
- Emotion was normalized as `fine` with value `0.75`.

**Notes:** `occupation` was unavailable (`null`), which is permitted by the plan and does not
affect the profile/personality result.

## Test 3: Rich game state and emotional state

**Status:** PASS

**Procedure:** Made Bernard hungry, captured diagnostics, saved the game, then restarted both the
game and backend and queried the same Sim again.

**Evidence passed:**

- Canonical `uncomfortable` emotion was recorded at `0.75`.
- Need-derived state included active `Restore hunger` (priority `1.0`) and `Restore hygiene`
  (priority `0.6`) goals.
- After reloading the game and backend, Empneon Social answered: “I'm uncomfortable because my
  hygiene and hunger need is critical.” This is grounded in the captured mood and critical needs.
- Agent, personality, relationship, emotions, goal IDs, statuses, and timestamps were identical
  after game/backend restart.
- After native completion, diagnostics contained confirmed event
  `8a6a9e77-9007-4373-88c1-d3308b826959:confirmed` with the submitted question and exact grounded
  reply. The event appears in both observations and accessible memories.
- Relationship strength moved from `0.50` to `0.52`, providing additional evidence that the
  confirmed native interaction applied its consequence.

**Quality note:** The stored summary was the generic “The conversation needed a careful
response.” The full confirmed memory still contains the concrete question and dialogue, so this
does not fail Test 3, but summary quality should be improved separately.

## Test 4: Aspirations and need-derived goals

**Status:** FAIL / PARTIAL

**Evidence passed:**

- `empneon.goals` exposes active `Restore hunger` and `Restore hygiene` goals for critical needs.
- The need-derived goal IDs and statuses persisted across game/backend restart.
- After leaving only energy low and triggering another Empneon interaction, the hunger, hygiene,
  bladder, and fun restore goals were `completed`; the energy restore goal remained `active`.
  This verifies that goal status follows current need state instead of leaving satisfied needs
  active.

**Failure:**

- `empneon.goals` does not expose any `Aspiration: ...` goal. This fails the aspiration criterion
  and indicates that the live aspiration is not reaching or not being converted by the Core sync
  path.

**Remaining defect:** Aspiration ingestion is the only observed Test 4 failure. Exact goal IDs can
be compared in diagnostics during the fix verification, but no duplicate goals were reported by
`empneon.goals`.

## Test 5: Directed relationships and confirmed consequences

**Status:** PARTIAL / DIALOGUE AND ROMANCE FAILED

**Procedure:** Recorded `ai.relationship Billie Jang`, asked Billie on a date through Empneon
Social, then queried the relationship again.

**Evidence:**

- Before: Billie Jang → Bernard Jaeger had friendship `0`, romance `0`, trust `50`, respect `50`,
  resentment `0`.
- Billie's reply discussed critical hygiene and hunger instead of addressing the date request.
- After: every displayed relationship value was unchanged.

**Failures:**

- Dialogue was not relevant to the player's date request.
- `ai.relationship` displayed no before/after change, and no romance consequence was proposed or
  confirmed despite the explicit date request.

**Timeline evidence:**

- Decision `c2fcd1c8-8962-45ee-abb0-edfd8f68e522` completed with status `succeeded`.
- The model proposed intent `agree`, `friendship +10`, `trust +10`, romance `0`, and
  `friendly_chat`.
- Native confirmation applied `friendly_chat` and observed `friendship +2`; no trust or romance
  consequence was confirmed. This correctly preserves game-observed effects instead of applying
  the model's unverified proposed values.
- The confirmed memory repeated irrelevant hygiene/hunger context from earlier conversations.
  This confirms a retrieval/grounding defect rather than a native-action failure.

**Directed-edge result:**

- Billie → Bernard: strength `0.56`, trust `0.50`, updated by the successful date interaction at
  `1784525512`.
- Bernard → Billie: strength `0.53`, trust `0.50`, last updated earlier at `1784525002`.
- The distinct values, IDs, and timestamps verify independent directed Core edges. The confirmed
  interaction updated Billie's edge without overwriting Bernard's reverse edge.

**Persistence result:** PASS. After saving and restarting both game and backend, both directed
relationship IDs, strengths, trust values, and timestamps were unchanged (`0.56` Billie → Bernard
and `0.53` Bernard → Billie).

**Final Test 5 result:** Native confirmation, directed storage, and persistence pass. Dialogue
relevance and the expected positive romance consequence remain defects.

## Test 6: Private observations and beliefs

**Status:** PARTIAL / RECALL CONSISTENCY FAILED

**Procedure:** Bernard taught Karmine `PRIVATE-GARDEN-731 is under the blue bench`, asked Karmine
to recall it, taught it again, and asked uninvolved Billie for the same fact.

**Confirmation analysis:**

- The first teaching event (`104c15f9-1c7a-4957-855f-9f2d622ce3ec`) was observed but never
  confirmed by a completed native action. Core therefore created no belief or accessible memory;
  Karmine's subsequent “I don't know or remember that” was correct for confirmation-gated memory.
- The second teaching completed successfully as decision
  `eaea5766-c0ea-4c11-9950-5494cf488799`, applying `friendly_chat` and observed `friendship +1`.
- Successful confirmation created Karmine's private belief with confidence `0.9` and a confirmed
  accessible memory containing the exact fact.

**Evidence passed:**

- Confirmed facts become observation-backed beliefs and accessible memories.
- Unconfirmed facts do not become durable memory.
- Billie has no matching belief or accessible memory and answered “I don't know or remember
  that.” Privacy isolation therefore passed.
- Karmine's later reply retrieved the correct location, “under the blue bench.”

**Failure:** Karmine contradicted the retrieved belief by adding “you didn't mention it before.”
The fact was present in the prompt-accessible belief and memory, so this is a dialogue-grounding
failure. The recall action itself later failed natively with `FinishingType.OBJECT_CHANGED`, but
that does not explain the already-generated contradiction.

**Persistence result:** PASS. After several unrelated interactions and a game save/reload, Karmine
still answered that the item was under the blue bench while Billie did not reveal the location.

**Remaining defect:** A clean, non-contradictory recall remains to be retested after the grounding
defect is fixed.

## Test 7: Local vector retrieval

**Status:** FAIL

**Procedure:** After several additional Empneon interactions, Bernard asked both Karmine and
Billie `Where is the PRIVATE-GARDEN-731?`, then saved/reloaded and repeated both questions.

**Evidence passed:**

- Karmine retrieved “under the blue bench” before and after save/reload.
- Billie did not disclose the private location before or after save/reload.
- Several intervening interactions did not displace Karmine's confirmed memory.
- Retrieval/privacy state persisted across game and backend restart.

**Additional failure:** After reload, Billie's response repeated irrelevant hygiene/hunger content
from an earlier conversation. It did not leak the private location, but confirms the existing
retrieval/grounding relevance defect.

**Paraphrased-query result:**

- Karmine answered: “The garden code item? What are you talking about now? Where exactly is it
  located?” Although the confirmed fact remained stored and exact-code recall worked, semantic
  retrieval from the paraphrase failed.
- Billie answered: “The garden code item? Where is the PRIVATE-GARDEN-731?” Billie did not reveal
  `under the blue bench`. Mentioning the identifier is not location leakage because Bernard had
  previously asked Billie about that exact identifier; Billie may remember the question while
  remaining uninformed about its answer.

**Final result:** Persistence and answer privacy pass. Paraphrased local vector retrieval fails and
requires a fix.
