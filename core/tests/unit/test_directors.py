import asyncio
import dataclasses
import logging
import sqlite3

import pytest

from empneon.core.clod import resolve_clod1
from empneon.core.contracts import (
    ActionResult,
    AgentStateSnapshot,
    CognitiveRequest,
    Decision,
    WorldEvent,
)
from empneon.core.directors import (
    DirectorView,
    IdleCheckInDirector,
    Opportunity,
    run_directors,
    to_request,
)
from empneon.core.runtime import ActionRecordStore, CognitiveRuntime
from empneon.core.scheduler import PriorityScheduler
from empneon.core.scheduler.resources import ResourceBudget, ResourceGovernor
from empneon.db.connection import open_db

SECRET = "super-secret-director-fact"


def snapshot(agent_id: str = "agent-a", **capabilities: object) -> AgentStateSnapshot:
    return AgentStateSnapshot(1, "test", agent_id, capabilities=dict(capabilities))


def view(*agents: str, now: int = 1_000, events: tuple[WorldEvent, ...] = ()) -> DirectorView:
    return DirectorView(now, tuple(snapshot(agent) for agent in agents or ("agent-a",)), events)


def opportunity(**overrides: object) -> Opportunity:
    values: dict[str, object] = {
        "director_id": "d1",
        "kind": "idle",
        "agent_id": "agent-a",
        "urgency": 0.2,
        "deadline_ms": 2_000,
    }
    values.update(overrides)
    return Opportunity(**values)  # type: ignore[arg-type]


class Fixed:
    max_opportunities = 10
    max_urgency = 1.0

    def __init__(self, director_id: str, *items: Opportunity) -> None:
        self.id = director_id
        self.items = items

    def propose(self, view: DirectorView) -> tuple[Opportunity, ...]:
        return self.items


class Raising:
    id = "boom"
    max_opportunities = 5
    max_urgency = 1.0

    def propose(self, view: DirectorView) -> tuple[Opportunity, ...]:
        raise RuntimeError(SECRET)


@pytest.mark.parametrize(
    "overrides",
    [
        {"director_id": " "},
        {"kind": ""},
        {"agent_id": ""},
        {"urgency": 1.5},
        {"urgency": -0.1},
        {"deadline_ms": 0},
        {"facts": {"x": float("nan")}},
        {"facts": {"x": object()}},
        {"id": " "},
    ],
)
def test_opportunity_validates_its_fields(overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        opportunity(**overrides)


def test_opportunity_cannot_express_a_decision_or_state_change() -> None:
    fields = {field.name for field in dataclasses.fields(Opportunity)}
    assert not fields & {"intent", "target_id", "state_changes", "evidence_ids", "decision"}


def test_view_rejects_negative_time_and_duplicate_agents() -> None:
    with pytest.raises(ValueError):
        DirectorView(-1, (), ())
    with pytest.raises(ValueError, match="duplicate"):
        DirectorView(0, (snapshot(), snapshot()), ())


def test_conversion_builds_a_traceable_request_with_agent_state() -> None:
    current = view()
    request = to_request(opportunity(facts={"note": "hi"}), current, preferred_clod=2)

    assert isinstance(request, CognitiveRequest)
    assert (request.agent_id, request.preferred_clod) == ("agent-a", 2)
    assert (request.urgency, request.deadline_ms) == (0.2, 2_000)
    assert request.event.type == "opportunity.idle"
    assert request.event.actor_ids == ("agent-a",)
    assert request.event.happened_at == 1_000
    assert request.event.facts == {"note": "hi", "director_id": "d1"}
    assert request.event.agent_state == current.agents[0]


def test_conversion_is_deterministic_and_ids_differ_by_inputs() -> None:
    first = to_request(opportunity(), view(), preferred_clod=1)
    again = to_request(opportunity(), view(), preferred_clod=1)
    later = to_request(opportunity(), view(now=1_001), preferred_clod=1)
    other = to_request(opportunity(director_id="d2"), view(), preferred_clod=1)

    assert first == again
    assert len({first.id, later.id, other.id}) == 3
    assert first.event.id != first.id
    assert to_request(opportunity(id="given"), view(), preferred_clod=1).id == "given"


def test_conversion_rejects_an_agent_missing_from_the_view() -> None:
    with pytest.raises(ValueError, match="not in the view"):
        to_request(opportunity(agent_id="ghost"), view(), preferred_clod=1)


def test_conversion_does_not_alias_the_directors_facts() -> None:
    facts = {"n": 1}
    request = to_request(opportunity(facts=facts), view(), preferred_clod=1)
    facts["n"] = 2
    assert request.event.facts["n"] == 1


def test_run_returns_requests_in_director_then_proposal_order() -> None:
    first = Fixed("d1", opportunity(kind="a"), opportunity(kind="b"))
    second = Fixed("d2", opportunity(director_id="d2", kind="c"))

    requests = run_directors((first, second), view())

    assert [request.event.type for request in requests] == [
        "opportunity.a",
        "opportunity.b",
        "opportunity.c",
    ]
    assert all(request.preferred_clod == 1 for request in requests)
    assert run_directors((first, second), view()) == requests


def test_run_is_bounded_per_director_and_logs_only_counts(
    caplog: pytest.LogCaptureFixture,
) -> None:
    director = Fixed("d1", *(opportunity(kind=f"k{i}") for i in range(5)))
    director.max_opportunities = 2
    caplog.set_level(logging.DEBUG)

    requests = run_directors((director,), view())

    assert len(requests) == 2
    assert "truncated 3" in caplog.text


def test_run_clamps_urgency_to_the_directors_ceiling() -> None:
    director = Fixed("d1", opportunity(urgency=0.9), opportunity(kind="low", urgency=0.1))
    director.max_urgency = 0.3

    assert [request.urgency for request in run_directors((director,), view())] == [0.3, 0.1]


def test_a_raising_director_is_skipped_without_leaking_its_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    requests = run_directors((Raising(), Fixed("d1", opportunity())), view())

    assert len(requests) == 1
    assert "RuntimeError" in caplog.text
    assert SECRET not in caplog.text


def test_invalid_output_is_skipped_not_converted() -> None:
    class Bad(Fixed):
        def propose(self, view: DirectorView) -> tuple[Opportunity, ...]:
            return (Decision("agent-a", "attack"),)  # type: ignore[return-value]

    assert run_directors((Bad("bad"),), view()) == ()


def test_opportunities_must_be_attributed_to_their_own_director() -> None:
    impostor = Fixed("d1", opportunity(director_id="someone-else"))
    assert run_directors((impostor,), view()) == ()


def test_opportunities_for_unknown_agents_are_dropped() -> None:
    director = Fixed("d1", opportunity(agent_id="ghost"), opportunity(kind="ok"))
    assert [r.event.type for r in run_directors((director,), view())] == ["opportunity.ok"]


def test_duplicate_requests_are_collapsed() -> None:
    director = Fixed("d1", opportunity(), opportunity())
    assert len(run_directors((director,), view())) == 1


@pytest.mark.parametrize("attribute", ["max_opportunities", "max_urgency"])
def test_invalid_director_limits_are_a_caller_error(attribute: str) -> None:
    director = Fixed("d1", opportunity())
    setattr(director, attribute, -1)
    with pytest.raises(ValueError, match=attribute):
        run_directors((director,), view())


def test_running_directors_touches_no_store() -> None:
    conn = open_db(":memory:")
    before = [tuple(row) for row in conn.execute("SELECT name FROM sqlite_master")]
    counts = _row_counts(conn)

    run_directors((Fixed("d1", opportunity()),), view())

    assert _row_counts(conn) == counts
    assert [tuple(row) for row in conn.execute("SELECT name FROM sqlite_master")] == before


def _row_counts(conn: sqlite3.Connection) -> dict[str, int]:
    tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    return {
        name: conn.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0]  # noqa: S608 - names come from sqlite_master
        for name in tables
        if not name.startswith(("vec_", "sqlite_"))
    }


class _Adapter:
    def __init__(self) -> None:
        self.executed: list[Decision] = []

    def observe(self) -> tuple[WorldEvent, ...]:
        return ()

    def execute(self, decision: Decision, /) -> ActionResult:
        self.executed.append(decision)
        return ActionResult(decision.id, "succeeded", ())


async def _resolve(request: CognitiveRequest) -> Decision:
    return resolve_clod1(request)


def _runtime() -> CognitiveRuntime:
    actions = ActionRecordStore(open_db(":memory:"))
    return CognitiveRuntime(ResourceGovernor(ResourceBudget(256, 0)), actions)


def test_converted_request_flows_through_scheduler_and_runtime() -> None:
    current = DirectorView(1_000, (snapshot("agent-a", intents=["acknowledge"]),), ())
    (request,) = run_directors((Fixed("d1", opportunity(facts={"note": "hi"})),), current)
    scheduler = PriorityScheduler(4)
    scheduler.submit(request)
    popped = scheduler.pop()
    assert popped is request
    assert popped.event.facts == {"note": "hi", "director_id": "d1"}

    adapter = _Adapter()
    record = asyncio.run(_runtime().process(popped, adapter, _resolve))

    assert record.decision.evidence_ids == (popped.event.id,)
    assert record.result.status == "succeeded"
    assert adapter.executed == [record.decision]


def test_adapter_capabilities_still_reject_unsupported_intents() -> None:
    strict = DirectorView(1_000, (snapshot("agent-a", intents=["dance"]),), ())
    (request,) = run_directors((Fixed("d1", opportunity()),), strict)
    adapter = _Adapter()

    record = asyncio.run(_runtime().process(request, adapter, _resolve))

    assert record.result.status == "rejected"
    assert adapter.executed == []


def _event(agent: str, at: int) -> WorldEvent:
    return WorldEvent("chat", (agent, "other"), happened_at=at)


def test_idle_director_fires_for_agents_idle_long_enough() -> None:
    director = IdleCheckInDirector(idle_after_s=60)
    current = view("agent-a", "agent-b", now=1_000, events=(_event("agent-a", 900),
                                                           _event("agent-b", 990)))

    (found,) = director.propose(current)

    assert (found.director_id, found.kind, found.agent_id) == (director.id, "idle", "agent-a")
    assert found.facts == {"idle_seconds": 100}


def test_idle_director_uses_each_agents_latest_event_and_skips_agents_without_evidence() -> None:
    director = IdleCheckInDirector(idle_after_s=60)
    events = (_event("agent-a", 100), _event("agent-a", 990))
    assert director.propose(view("agent-a", "agent-c", now=1_000, events=events)) == ()


def test_idle_director_defaults_keep_urgency_low_and_bounded() -> None:
    director = IdleCheckInDirector(idle_after_s=10)
    (found,) = director.propose(view(now=100, events=(_event("agent-a", 0),)))
    assert found.urgency <= director.max_urgency < 0.5
    assert director.max_opportunities >= 1


@pytest.mark.parametrize(
    "options",
    [
        {"idle_after_s": 0},
        {"idle_after_s": 5, "urgency": 2.0},
        {"idle_after_s": 5, "deadline_ms": 0},
    ],
)
def test_idle_director_rejects_invalid_options(options: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        IdleCheckInDirector(**options)  # type: ignore[arg-type]


def test_idle_director_is_deterministic_for_a_fixed_view() -> None:
    director = IdleCheckInDirector(idle_after_s=10)
    events = (_event("agent-a", 0), _event("agent-b", 0))
    current = view("agent-a", "agent-b", now=500, events=events)
    assert director.propose(current) == director.propose(current)
    assert run_directors((director,), current) == run_directors((director,), current)
