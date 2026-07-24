# Global In-Game Usage Diagnostic Implementation Plan

**Status:** Completed; checklist retained as the original execution record

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `empneon.usage` display recorded telemetry regardless of which Sim initiated the latest cognition request.

**Architecture:** Reuse Core's existing unfiltered `UsageStore.telemetry(None)` behavior through the Sims backend when `/diagnostics/usage` has no `sim_id`. Keep explicit actor filtering and every other active-Sim diagnostic unchanged.

**Tech Stack:** Python 3.11+, standard-library HTTP handling, SQLite, pytest, The Sims 4 Python mod API.

## Global Constraints

- Do not change Core usage ownership, persistence, or aggregation.
- Preserve `/diagnostics/usage?sim_id=<ACTOR_ID>` actor filtering and validation.
- Preserve the `empneon.usage` output format.
- Do not change other diagnostic commands.
- Do not commit or push until the user explicitly requests it.

---

### Task 1: Route the in-game usage command to global telemetry

**Files:**
- Modify: `adapters/thesims4/backend/ai_sims_server.py:2996-3029`
- Modify: `adapters/thesims4/ts4script/ai_sims_agent.py:2711-2726`
- Test: `adapters/thesims4/tests/test_sims4_backend.py`
- Test: `adapters/thesims4/tests/test_sims4_mod_autonomy.py`

**Interfaces:**
- Consumes: `UsageStore.telemetry(agent_id: str | None = None) -> dict[str, object]`
- Produces: unfiltered `GET /diagnostics/usage`; filtered `GET /diagnostics/usage?sim_id=<ACTOR_ID>` remains unchanged.
- Produces: `empneon_usage(_connection=None)` calling `query_json("/diagnostics/usage", {})`.

- [x] **Step 1: Add failing backend route tests**

Add tests that replace only the persistence boundary and exercise the real HTTP route:

```python
def test_usage_diagnostics_without_sim_id_returns_global_telemetry(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(ai_sims_server, "CORE_DB_PATH", str(tmp_path / "memory.db"))
    requested_agent_ids = []
    monkeypatch.setattr(
        ai_sims_server.UsageStore,
        "telemetry",
        lambda _store, agent_id=None: (
            requested_agent_ids.append(agent_id) or {"requests": 2}
        ),
    )
    handler = ai_sims_server.Handler.__new__(ai_sims_server.Handler)
    handler.path = "/diagnostics/usage"
    responses = []
    monkeypatch.setattr(
        handler, "send_json", lambda status, body: responses.append((status, body))
    )

    handler.do_GET()

    assert responses == [(200, {"requests": 2})]
    assert requested_agent_ids == [None]


def test_usage_diagnostics_with_sim_id_remains_actor_filtered(
    tmp_path, monkeypatch
) -> None:
    database = str(tmp_path / "memory.db")
    monkeypatch.setattr(ai_sims_server, "CORE_DB_PATH", database)
    with open_db(database) as conn:
        ai_sims_server.empneon_state.sync_sim(
            conn, {"id": "karmine", "name": "Karmine"}
        )
    requested_agent_ids = []
    monkeypatch.setattr(
        ai_sims_server.UsageStore,
        "telemetry",
        lambda _store, agent_id=None: (
            requested_agent_ids.append(agent_id) or {"requests": 1}
        ),
    )
    handler = ai_sims_server.Handler.__new__(ai_sims_server.Handler)
    handler.path = "/diagnostics/usage?sim_id=karmine"
    responses = []
    monkeypatch.setattr(
        handler, "send_json", lambda status, body: responses.append((status, body))
    )

    handler.do_GET()

    assert responses == [(200, {"requests": 1})]
    assert requested_agent_ids == ["karmine"]
```

- [x] **Step 2: Add a failing mod behavior check**

```python
usage_output = []
monkeypatch.setattr(
    agent,
    "active_diagnostic",
    lambda *_args: {"requests": 0, "by_clod": {}, "actual": {}},
)
monkeypatch.setattr(
    agent,
    "query_json",
    lambda path, params: {
        "requests": 2,
        "by_clod": {"2": 1, "3": 1},
        "actual": {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "latency_ms": 300,
        },
    },
)
monkeypatch.setattr(agent, "out", lambda _connection, text: usage_output.append(text))

agent.empneon_usage()

assert usage_output == [
    "Usage: requests=2 CLOD={'2': 1, '3': 1} "
    "prompt=100 completion=20 latency=300ms"
]
```

- [x] **Step 3: Run the focused tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests/test_sims4_backend.py::test_usage_diagnostics_without_sim_id_returns_global_telemetry tests/test_sims4_backend.py::test_usage_diagnostics_with_sim_id_remains_actor_filtered tests/test_sims4_mod_autonomy.py::test_conversation_session_and_alarm_submit_without_overlap
```

Expected: the unfiltered route test fails with HTTP 400 and the in-game behavior check displays zero because `empneon_usage` still calls `active_diagnostic`; the filtered route test passes.

- [x] **Step 4: Implement the minimal backend route**

At the start of `Handler._send_diagnostic`, after the migration branch, add:

```python
        if path == "/diagnostics/usage" and not str(
            query.get("sim_id", [""])[0]
        ).strip():
            with open_db(CORE_DB_PATH) as conn:
                body = UsageStore(conn).telemetry()
            self.send_json(200, body)
            return
```

Leave the existing identifier validation and filtered usage branch unchanged.

- [x] **Step 5: Point only `empneon.usage` at the global route**

Replace its first line with:

```python
    try:
        data = query_json("/diagnostics/usage", {})
    except Exception as exc:
        out(_connection, "Empneon diagnostic error: {}".format(exc))
        return
```

Retain the existing output formatting exactly.

- [x] **Step 6: Run the focused tests and verify GREEN**

Run the command from Step 3.

Expected: `3 passed`.

- [x] **Step 7: Run regression verification**

Run:

```powershell
$env:PYTHONPATH='..\..\core\src;src'; py -3.12 -m pytest -q -p no:cacheprovider tests
```

from `adapters/thesims4`, followed by:

```powershell
$env:PYTHONPATH='src'; py -3.12 -m pytest -q -p no:cacheprovider tests
```

from `core`. Both suites must pass.

- [x] **Step 8: Build and syntax-check the mod without installing it**

Run:

```powershell
py -3.12 -m py_compile backend/ai_sims_server.py
py -3.12 build_mod.py
```

from `adapters/thesims4`. Do not install the artifact, restart processes, commit, or push.
