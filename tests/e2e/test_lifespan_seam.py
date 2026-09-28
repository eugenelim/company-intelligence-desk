"""AC-0303 / entry 7: the lifespan wires CED_REQUIRE_DISTINCT_APPROVER to app.state.

Deletion mutant: remove ``lifespan=_lifespan,`` from the ``FastAPI(...)``
constructor at ``main.py:91``. After deletion:
- The env var is never read at startup.
- ``app.state.require_distinct_approver`` keeps whatever value was last written
  (the conftest sets it to ``False``).
- The malformed-value startup refusal disappears — a server that set its own
  env var to ``"maybe"`` would start instead of refusing.

These two tests are the composed-path assertions the deletion mutant must red:
1. With the env var set to ``"1"`` and lifespan enabled, ``app.state`` reflects
   the env var after server startup.
2. With the env var set to ``"maybe"`` and lifespan enabled, the server refuses
   to start (uvicorn exits before accepting connections).
"""

from __future__ import annotations

import socket
import threading
import time

import pytest
import uvicorn

from ced.api.main import _parse_require_distinct_approver, app


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


# ── offline: _parse_require_distinct_approver and _lifespan direct tests ────


def test_parse_require_distinct_approver_absent_returns_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Absent CED_REQUIRE_DISTINCT_APPROVER defaults to False."""
    monkeypatch.delenv("CED_REQUIRE_DISTINCT_APPROVER", raising=False)
    assert _parse_require_distinct_approver() is False


def test_parse_require_distinct_approver_truthy_returns_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """'1', 'true', 'yes' (case-insensitive) return True."""
    for val in ("1", "true", "True", "TRUE", "yes", "YES", "Yes"):
        monkeypatch.setenv("CED_REQUIRE_DISTINCT_APPROVER", val)
        assert _parse_require_distinct_approver() is True, f"expected True for {val!r}"


def test_parse_require_distinct_approver_falsy_returns_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """'0', 'false', 'no' (case-insensitive) return False."""
    for val in ("0", "false", "False", "FALSE", "no", "NO", "No"):
        monkeypatch.setenv("CED_REQUIRE_DISTINCT_APPROVER", val)
        assert _parse_require_distinct_approver() is False, f"expected False for {val!r}"


def test_parse_require_distinct_approver_malformed_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unrecognised values raise ValueError naming the variable."""
    for val in ("maybe", "2", "enabled", "on", "off", "yes!", "ture"):
        monkeypatch.setenv("CED_REQUIRE_DISTINCT_APPROVER", val)
        with pytest.raises(ValueError, match="CED_REQUIRE_DISTINCT_APPROVER"):
            _parse_require_distinct_approver()


# ── composed path: start a server with the real lifespan ─────────────────────


def test_lifespan_sets_require_distinct_approver_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The lifespan wires the env var to app.state (Entry 7, composed path).

    Starting uvicorn with lifespan='on' and CED_REQUIRE_DISTINCT_APPROVER='1'
    causes the server to set app.state.require_distinct_approver = True.

    Deletion mutant: remove ``lifespan=_lifespan,`` from FastAPI(...)  —
    the lifespan never runs, app.state keeps its old value (False from the
    e2e conftest), and this assertion reds.
    """
    monkeypatch.setenv("CED_REQUIRE_DISTINCT_APPROVER", "1")

    # Reset app.state to a known starting value so the test is not
    # accidentally passing from a previous session's write.
    app.state.require_distinct_approver = False

    port = _free_port()
    config = uvicorn.Config(
        app, host="127.0.0.1", port=port, log_level="warning", lifespan="on"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if server.started:
            break
        time.sleep(0.05)
    else:
        server.should_exit = True
        thread.join(timeout=5)
        pytest.fail("uvicorn did not start within 10 s")

    try:
        # The lifespan ran and should have set require_distinct_approver from env.
        assert app.state.require_distinct_approver is True, (
            "lifespan must write CED_REQUIRE_DISTINCT_APPROVER='1' to "
            "app.state.require_distinct_approver; if lifespan=_lifespan is deleted "
            "from FastAPI(...), the value stays False and this assertion reds"
        )
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        # Restore to a safe default so other tests are not affected.
        app.state.require_distinct_approver = False


def test_lifespan_refuses_malformed_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A malformed CED_REQUIRE_DISTINCT_APPROVER prevents the server from starting.

    The lifespan raises ValueError before yielding; uvicorn exits before
    accepting connections.

    Deletion mutant: remove ``lifespan=_lifespan,`` — no exception fires,
    the server starts normally, ``server.started`` becomes True, and this
    test's 'server must not have started' assertion reds.

    The ValueError is caught inside the thread target so it does not escape
    as an unhandled thread exception (which would be an unrelated signal).
    The test additionally asserts it was a ValueError naming the env var, so
    it distinguishes "refused for the intended reason" from "crashed for any
    reason at all".
    """
    monkeypatch.setenv("CED_REQUIRE_DISTINCT_APPROVER", "maybe")

    port = _free_port()
    config = uvicorn.Config(
        app, host="127.0.0.1", port=port, log_level="warning", lifespan="on"
    )
    server = uvicorn.Server(config)
    thread_exc: list[BaseException] = []

    def _run_capturing() -> None:
        try:
            server.run()
        except (SystemExit, ValueError) as exc:
            # uvicorn calls sys.exit(3) on startup failure; the ValueError
            # may bubble in some configurations.  Both are expected here.
            thread_exc.append(exc)
        except BaseException as exc:
            thread_exc.append(exc)

    thread = threading.Thread(target=_run_capturing, daemon=True)
    thread.start()

    # Give uvicorn time to attempt startup.
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if server.started or not thread.is_alive():
            break
        time.sleep(0.05)

    thread.join(timeout=5)

    assert not server.started, (
        "server must not start when CED_REQUIRE_DISTINCT_APPROVER is malformed; "
        "if lifespan=_lifespan is absent from FastAPI(...), the server starts "
        "and this assertion reds"
    )
    # The thread must have exited with the ValueError (or SystemExit wrapping it),
    # not silently or with an unrelated exception.
    assert thread_exc, (
        "expected the thread to raise ValueError (or SystemExit wrapping it); "
        "got no exception — the lifespan may not have fired"
    )
