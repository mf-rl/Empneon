"""Opt-in validation of decisions against the capabilities an adapter publishes.

An adapter may list `intents` (decision intents it can execute) and `state_paths` (allowed
`StateDelta.path` roots) in `AgentStateSnapshot.capabilities`. A published key restricts; an empty
list allows nothing; an absent key allows everything.
"""

from collections.abc import Mapping, Sequence

from empneon.core.contracts import Decision, validate_capability_lists

INTENTS_KEY = "intents"
STATE_PATHS_KEY = "state_paths"


def _published(capabilities: Mapping[str, object], key: str) -> Sequence[object] | None:
    """The validated list published under `key`, or None when the key is absent."""
    value = capabilities.get(key)
    return value if isinstance(value, (list, tuple)) else None


def validate_decision(
    decision: Decision, capabilities: Mapping[str, object] | None
) -> str | None:
    """Return a short rejection reason when `capabilities` exclude `decision`, else None.

    The intent is checked first, then each state delta in order. A path's root is the text before
    its first `.`, so `relationship.strength` is allowed by `relationship`. Raises `ValueError`
    when a published key is not a list of non-empty strings.
    """
    if not capabilities:
        return None
    validate_capability_lists(capabilities)
    intents = _published(capabilities, INTENTS_KEY)
    if intents is not None and decision.intent not in intents:
        return f"intent not supported: {decision.intent}"
    roots = _published(capabilities, STATE_PATHS_KEY)
    if roots is not None:
        for change in decision.state_changes:
            if change.path.split(".", 1)[0] not in roots:
                return f"state path not supported: {change.path}"
    return None
