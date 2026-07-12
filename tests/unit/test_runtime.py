import asyncio

from empneon.adapters.sims4 import Sims4PocAdapter
from empneon.core.contracts import CognitiveRequest, Decision
from empneon.core.runtime import ActionRecordStore, CognitiveRuntime
from empneon.core.scheduler.resources import ResourceBudget, ResourceGovernor
from empneon.db.connection import open_db


def test_sims_event_executes_and_persists_through_core() -> None:
    adapter = Sims4PocAdapter({"sim": {"id": "bella-goth", "name": "Bella Goth"}})
    event = adapter.observe()[0]
    request = CognitiveRequest("bella-goth", 1, event)
    actions = ActionRecordStore(open_db(":memory:"))
    runtime = CognitiveRuntime(ResourceGovernor(ResourceBudget(256, 0)), actions)

    async def unused_resolver(_: CognitiveRequest) -> Decision:
        raise AssertionError("CLOD 1 must not call a provider")

    record = asyncio.run(runtime.process(request, adapter, unused_resolver))

    assert record.result.status == "succeeded"
    assert record.decision.intent == "acknowledge"
    assert actions.get(record.decision.id) == record
