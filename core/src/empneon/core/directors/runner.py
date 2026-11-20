"""Bounded, failure-isolated execution of directors."""

import logging
from collections.abc import Sequence
from dataclasses import replace

from empneon.core.contracts import Clod, CognitiveRequest, validate_clod
from empneon.core.directors.protocol import Director, DirectorView, Opportunity, to_request

_log = logging.getLogger(__name__)


def _validate_limits(director: Director) -> None:
    if director.max_opportunities < 0:
        raise ValueError("director max_opportunities must not be negative")
    if not 0 <= director.max_urgency <= 1:
        raise ValueError("director max_urgency must be between 0 and 1")


def _proposals(director: Director, view: DirectorView) -> tuple[Opportunity, ...]:
    try:
        proposed = tuple(director.propose(view))
    except Exception as exc:
        _log.warning("director skipped after failure: %s", type(exc).__name__)
        return ()
    if not all(isinstance(item, Opportunity) for item in proposed):
        _log.warning("director skipped for returning a non-opportunity value")
        return ()
    if len(proposed) > director.max_opportunities:
        excess = len(proposed) - director.max_opportunities
        _log.warning("director output truncated %d opportunities", excess)
        proposed = proposed[: director.max_opportunities]
    return proposed


def run_directors(
    directors: Sequence[Director],
    view: DirectorView,
    *,
    preferred_clod: int = Clod.RULES,
) -> tuple[CognitiveRequest, ...]:
    """Ask each director for opportunities and convert them to requests for the host to submit.

    Pure and synchronous: no clock, I/O, scheduler, store, or model call. A raising director is
    skipped; output is truncated to `max_opportunities`, urgency is clamped to `max_urgency`,
    opportunities attributed to another director or to an agent outside the view are dropped, and
    duplicates collapse. Results keep director order, then proposal order. Only counts and
    exception type names are logged.
    """
    validate_clod(preferred_clod, "preferred_clod")
    requests: dict[str, CognitiveRequest] = {}
    dropped = 0
    for director in directors:
        _validate_limits(director)
        for item in _proposals(director, view):
            if item.director_id != director.id or view.agent(item.agent_id) is None:
                dropped += 1
                continue
            clamped = item
            if item.urgency > director.max_urgency:
                clamped = replace(item, urgency=director.max_urgency)
            request = to_request(clamped, view, preferred_clod=preferred_clod)
            requests.setdefault(request.id, request)
    if dropped:
        _log.warning("dropped %d unattributable opportunities", dropped)
    return tuple(requests.values())
