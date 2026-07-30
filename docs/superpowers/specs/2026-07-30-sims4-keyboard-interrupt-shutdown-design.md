# Sims 4 Backend Keyboard-Interrupt Shutdown Design

**Date:** 2026-07-30

## Goal

Stop the Sims 4 backend cleanly after Ctrl+C without displaying a Python
traceback.

## Design

`run()` will catch `KeyboardInterrupt` only around
`EmpneonHTTPServer.serve_forever()`, print
`Empneon backend stopped by keyboard interrupt.`, and close the server in a
`finally` block.

All startup failures and non-keyboard exceptions will continue to propagate.
HTTP routes, request handling, cognition workers, configuration, and normal
server output will remain unchanged.

## Verification

A regression test will use the existing façade monkeypatch surface to replace
the HTTP server with a test double whose `serve_forever()` raises
`KeyboardInterrupt`. The test will verify that:

- `run()` does not propagate the interrupt;
- the shutdown message is printed;
- `server_close()` is called.

The focused regression and complete Sims adapter test suite will run after the
change.
