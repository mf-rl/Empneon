# Sims 4 Keyboard-Interrupt Shutdown Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the Sims 4 backend after Ctrl+C without a traceback while closing
the HTTP server.

**Architecture:** Handle `KeyboardInterrupt` only around the blocking
`serve_forever()` call in the existing `run()` lifecycle. Use `finally` for
socket cleanup so unrelated exceptions still propagate after cleanup.

**Tech Stack:** Python 3.12, standard-library `http.server`, pytest.

## Global Constraints

- Preserve all startup, HTTP, cognition, and error behavior except the expected
  keyboard-interrupt shutdown.
- Add no dependency or abstraction.
- Leave all changes uncommitted until the user requests a commit.

---

### Task 1: Handle keyboard-interrupt shutdown

**Files:**

- Modify: `adapters/thesims4/tests/test_sims4_backend.py`
- Modify: `adapters/thesims4/backend/ai_sims_server.py:1265-1281`

**Interfaces:**

- Consumes: existing `run()`, `EmpneonHTTPServer.serve_forever()`, and
  `EmpneonHTTPServer.server_close()`.
- Produces: clean Ctrl+C output:
  `Empneon backend stopped by keyboard interrupt.`

- [x] **Step 1: Write the failing regression**

Add a test that patches startup collaborators, makes `serve_forever()` raise
`KeyboardInterrupt`, and asserts both the output and cleanup:

```python
def test_run_handles_keyboard_interrupt_and_closes_server(
    monkeypatch, capsys
) -> None:
    calls = []

    class Status:
        completed = True
        error = None

    class Connection:
        def close(self):
            calls.append("database closed")

    class Server:
        def __init__(self, address, handler):
            calls.append(("server created", address, handler))

        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            calls.append("server closed")

    monkeypatch.setattr(ai_sims_server, "setup_logging", lambda: None)
    monkeypatch.setattr(
        ai_sims_server.empneon_state,
        "prepare_database",
        lambda *_args: Status(),
    )
    monkeypatch.setattr(
        ai_sims_server.empneon_state,
        "import_legacy_adapter",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        ai_sims_server,
        "db_session",
        lambda *_args: contextlib.nullcontext(object()),
    )
    monkeypatch.setattr(ai_sims_server, "open_db", lambda *_args: Connection())
    monkeypatch.setattr(ai_sims_server, "EmpneonHTTPServer", Server)

    ai_sims_server.run()

    assert "Empneon backend stopped by keyboard interrupt." in capsys.readouterr().out
    assert calls[-1] == "server closed"
```

- [x] **Step 2: Verify RED**

Run from `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider `
  tests/test_sims4_backend.py::test_run_handles_keyboard_interrupt_and_closes_server
```

Expected: fail because `KeyboardInterrupt` propagates from `serve_forever()`.

- [x] **Step 3: Implement the minimal lifecycle handling**

Replace the bare `server.serve_forever()` call with:

```python
try:
    server.serve_forever()
except KeyboardInterrupt:
    print("Empneon backend stopped by keyboard interrupt.")
finally:
    server.server_close()
```

- [x] **Step 4: Verify GREEN**

Run the focused command from Step 2. Expected: `1 passed`.

- [x] **Step 5: Verify the adapter**

Run from `adapters/thesims4`:

```powershell
$env:PYTHONPATH='..\..\core\src;src'
py -3.12 -m pytest -q -p no:cacheprovider tests
```

Expected: all Sims adapter tests pass.

- [x] **Step 6: Run static and diff checks**

Run from the repository root:

```powershell
py -3.12 -m ruff check `
  adapters/thesims4/backend/ai_sims_server.py `
  adapters/thesims4/tests/test_sims4_backend.py
py -3.12 -m py_compile adapters/thesims4/backend/ai_sims_server.py
git diff --check
```

Expected: all commands exit successfully. Leave the changes uncommitted.
