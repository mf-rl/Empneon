# Sims 4 Mod-Aware Social Execution and Identity Grounding

## Goal

Fix two Test 5 defects without changing the common social-category contract:

1. A valid `social.romance` decision must be able to execute when a relationship-unlocking mod makes the native interaction valid even though the selected social super-interaction does not enumerate the hardcoded official mixer.
2. A generated reply must not ask for the Listener's name when that name is already present in the conversation context.

## Native social execution

The adapter keeps its exact category-to-native-affordance mapping. It first uses the existing advertised-affordance lookup. If no advertised super-interaction contains the mapped affordance, it attempts the same affordance against the target's available interaction supers and accepts only a pair that passes The Sims 4 native interaction test and factory creation.

This preserves the model-selected category, lets installed mods participate through the game's final compatibility test, and does not infer categories from tuning names or add mod-specific dependencies. Failure remains explicit when every native test rejects the interaction.

## Identity grounding

The shared response-grounding validator rejects a direct request for the known Listener's name, including forms such as `What is your name?` and `Tell me your name.` The existing provider correction and retry flow then requests a replacement response. Questions about nicknames or preferred forms of address remain valid.

## Tests

- Reproduce a mapped Romance affordance that is absent from `all_affordances_gen` but passes native AOP testing; execution must start and report its observed relationship result normally.
- Preserve failure when the native AOP test rejects every candidate.
- Reject `It's nice to meet you, Bernard! What is your name then?` when Bernard is the known Listener.
- Preserve valid nickname/preferred-name questions and existing Speaker self-identification behavior.

## Non-goals

- No social-category substitution.
- No tuning-name category heuristics.
- No integration with a particular relationship mod.
- No changes to attraction normalization or model-owned relationship state.
