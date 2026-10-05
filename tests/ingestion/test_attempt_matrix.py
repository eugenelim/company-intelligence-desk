"""Exhaustive attempt-record matrix — AC-0402 and AC-0417.

Rows are generated programmatically from two axes:
  - received status: 200, 103, 301, 304, 403, 429, 404, 500, 600
  - ending (with-status body path): 17 categories (see _BODY_ENDINGS)
  - no-status site: 17 categories across resolution, connect, handshake, request

The oracle is written directly from the AC-0417 text; it does not call
any client code.

Stop condition order (AC-0417):
  1. no-response class  (transport failure — wins over everything)
  2. blocked            (403 or 429 received)
  3. redirect           (3xx received)
  4. refused            (length/cap refusal — no transport failure, not blocked/redirect)
  5. http_4xx / http_5xx
  6. refused            (1xx or status outside 100-599)
  7. success            (2xx only)

Unreachable cells (http.client cannot produce them; each is listed in
_UNREACHABLE with its stdlib reason):
  - Any status 1xx or 304 paired with fault_*, stream_over_cap: http.client
    sets length=0 for 1xx/304 and returns b'' immediately from read(); the
    socket data-read path is never reached.

Real-clock rows (per-phase budget cap, dns_timeout, watchdog trickle):
  - _TOTAL_BUDGET is patched per-test to ≤ 0.5 s so each row finishes fast.
  - Each asserts wall time < patched budget + 0.2 s and gate release.
"""

from __future__ import annotations

import io
import ssl
import threading
import time
from collections.abc import Iterator
from http import client as http_client
from typing import Any

import pytest

from ced.adapters.sec.client import (
    SecClientError,
    _fake_gate,
    fetch_url,
)
from tests.ingestion.fixture import FakeSocket, make_http_response, make_seam

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HOST = "data.sec.gov"
_PATH = "/submissions/CIK0000320193.json"
_CONTACT = "matrix-test-fictional@example.com"
_CAP = 50  # small cap so over-cap/stream-cap rows work with tiny bodies

# ---------------------------------------------------------------------------
# Statuses under test
# ---------------------------------------------------------------------------

_STATUSES = [200, 103, 301, 304, 403, 429, 404, 500, 600]

# ---------------------------------------------------------------------------
# Body-side endings
# ---------------------------------------------------------------------------

#: All endings for the body side. For 1xx and 304, some are unreachable.
_BODY_ENDINGS = [
    "complete",
    "short_body",
    "over_cap",
    "mal_sign",
    "mal_sep",
    "mal_ws",
    "mal_non_ascii",
    "mal_two_agreeing",
    "mal_two_disagreeing",
    "stream_over_cap",
    "fault_reset",
    "fault_exc",
    "fault_ssl",
    "fault_timeout",
    "fault_value",
    "budget_read",
    "budget_post_read",
]

#: Endings that require actually reading body bytes from the socket.
#: http.client never reads body bytes for 1xx or 304 (length=0).
_NEEDS_BODY_READ = frozenset(
    [
        "stream_over_cap",
        "fault_reset",
        "fault_exc",
        "fault_ssl",
        "fault_timeout",
        "fault_value",
    ]
)

#: Statuses for which http.client returns b'' from read() immediately.
_ZERO_BODY_STATUSES = frozenset([103, 304])

#: Unreachable cells with stdlib reason.
_UNREACHABLE: dict[tuple[int, str], str] = {}
for _s in _ZERO_BODY_STATUSES:
    for _e in _NEEDS_BODY_READ:
        _UNREACHABLE[(_s, _e)] = (
            f"http.client sets length=0 for {_s}; response.read() returns b'' "
            f"immediately without reading from the socket, so {_e} cannot be triggered"
        )

# ---------------------------------------------------------------------------
# No-status site rows
# ---------------------------------------------------------------------------

#: All no-status rows: (site_id, no_response_class).
_NO_STATUS_ROWS: list[tuple[str, str]] = [
    # Resolution
    ("dns_failure", "dns"),
    ("dns_no_public", "dns"),
    ("dns_timeout", "total_timeout"),
    # Connect
    ("connect_refused", "connection"),
    ("connect_timeout", "connect_timeout"),
    ("connect_value", "connection"),  # unexpected Exception at open_socket
    ("budget_pre_connect", "total_timeout"),
    # Handshake
    ("handshake_ssl", "tls"),
    ("handshake_reset", "connection"),
    ("handshake_timeout", "connect_timeout"),
    ("handshake_value", "connection"),  # unexpected Exception at wrap
    # Request
    ("request_reset", "connection"),
    ("request_exc", "connection"),
    ("request_ssl", "tls"),  # ssl.SSLError → tls per AC-0417
    ("request_timeout", "read_timeout"),
    ("request_value", "connection"),
    ("budget_pre_request", "total_timeout"),
]

# ---------------------------------------------------------------------------
# Independent oracle (written from AC-0417 text; no client code)
# ---------------------------------------------------------------------------


def _classify(status: int) -> str:
    """http_status_class per AC-0417: '1xx'–'5xx' for 100–599, 'other' outside."""
    if 100 <= status <= 599:
        return f"{status // 100}xx"
    return "other"


#: No-response class for each body-side ending that is a transport failure.
#: short_body: a body shorter than Content-Length is a transport failure (AC-0417).
_BODY_NRC: dict[str, str] = {
    "short_body": "connection",
    "fault_reset": "connection",
    "fault_exc": "connection",
    "fault_ssl": "tls",  # ssl.SSLError during body read → tls per AC-0417
    "fault_timeout": "read_timeout",
    "fault_value": "connection",
    "budget_read": "total_timeout",
    "budget_post_read": "total_timeout",
}

#: Body-side endings that are refused (no transport failure).
_REFUSED_ENDINGS = frozenset(
    [
        "over_cap",
        "mal_sign",
        "mal_sep",
        "mal_ws",
        "mal_non_ascii",
        "mal_two_agreeing",
        "mal_two_disagreeing",
        "stream_over_cap",
    ]
)


def _oracle(
    status: int | None,
    ending: str,
) -> tuple[str | None, str | None, bool, str]:
    """Return (http_status_class, no_response_class, blocked, stop_condition).

    For no-status rows, pass status=None and ending=site_id.
    """
    if status is None:
        # No-status row: ending IS the site_id; look up nrc from _NO_STATUS_ROWS.
        nrc = dict(_NO_STATUS_ROWS)[ending]
        return (None, nrc, False, nrc)

    http_class = _classify(status)
    blocked = status in (403, 429)
    nrc = _BODY_NRC.get(ending)

    # AC-0417 stop order:
    if nrc is not None:  # Step 1: transport failure wins all
        return (http_class, nrc, blocked, nrc)
    if blocked:  # Step 2
        return (http_class, None, True, "blocked")
    if 300 <= status <= 399:  # Step 3
        return (http_class, None, False, "redirect")
    if ending in _REFUSED_ENDINGS:  # Step 4
        return (http_class, None, False, "refused")
    if 400 <= status <= 499:  # Step 5a
        return (http_class, None, False, "http_4xx")
    if 500 <= status <= 599:  # Step 5b
        return (http_class, None, False, "http_5xx")
    if status < 200 or status > 599:  # Step 6: 1xx or other
        return (http_class, None, False, "refused")
    return (http_class, None, False, "success")  # Step 7: 2xx


# ---------------------------------------------------------------------------
# Response / socket builders for each body ending
# ---------------------------------------------------------------------------


def _resp_bytes(status: int, ending: str) -> bytes:
    """Build raw HTTP bytes for a given (status, ending) cell."""
    body = b"ok"
    if ending == "complete":
        # http.client sets length=0 for 1xx and 304, ignoring any Content-Length.
        # Use an empty body so our strict CL check (cl=0, total_read=0) passes.
        if status in _ZERO_BODY_STATUSES:
            return make_http_response(status, {}, b"")
        return make_http_response(status, {}, body)

    if ending == "short_body":
        # Declare Content-Length: N+5, supply only N bytes.
        declared = len(body) + 5
        return f"HTTP/1.1 {status} X\r\nContent-Length: {declared}\r\n\r\n".encode() + body

    if ending == "over_cap":
        return f"HTTP/1.1 {status} X\r\nContent-Length: {_CAP + 1}\r\n\r\n".encode()

    if ending == "mal_sign":
        return f"HTTP/1.1 {status} X\r\nContent-Length: +{len(body)}\r\n\r\n".encode() + body

    if ending == "mal_sep":
        return f"HTTP/1.1 {status} X\r\nContent-Length: 1,0\r\n\r\n".encode() + body

    if ending == "mal_ws":
        return f"HTTP/1.1 {status} X\r\nContent-Length: {len(body)} \r\n\r\n".encode() + body

    if ending == "mal_non_ascii":
        # 0xa0 is non-ASCII (non-breaking space in Latin-1).
        return f"HTTP/1.1 {status} X\r\nContent-Length: {len(body)}\xa0\r\n\r\n".encode() + body

    if ending == "mal_two_agreeing":
        n = str(len(body))
        hdr = f"HTTP/1.1 {status} X\r\nContent-Length: {n}\r\nContent-Length: {n}\r\n\r\n"
        return hdr.encode() + body

    if ending == "mal_two_disagreeing":
        return (
            f"HTTP/1.1 {status} X\r\nContent-Length: {len(body)}\r\n"
            f"Content-Length: {len(body) + 1}\r\n\r\n".encode()
            + body
        )

    if ending == "stream_over_cap":
        big = b"x" * (_CAP + 1)
        return make_http_response(status, {}, big, omit_content_length=True)

    # fault_* and budget_* are handled via special sockets, not raw bytes.
    # Return a plain response as fallback (the socket will override).
    return make_http_response(status, {}, body)


def _make_fault_socket(status: int, ending: str) -> Any:
    """Return an open_socket callable that serves valid headers then raises.

    Used for fault_reset, fault_exc, fault_ssl, fault_timeout, fault_value.
    """
    # Use a small Content-Length (within _CAP) so the cap check passes and
    # the body-read fault is what terminates the request.
    header = f"HTTP/1.1 {status} X\r\nContent-Length: 10\r\n\r\n".encode()

    class _FaultIO(io.RawIOBase):
        def __init__(self) -> None:
            self._data = header
            self._pos = 0

        def read(self, n: int = -1) -> bytes:
            if self._pos < len(self._data):
                chunk = self._data[self._pos : self._pos + n]
                self._pos += len(chunk)
                return chunk
            # Body read: raise the per-ending exception.
            if ending == "fault_reset":
                raise ConnectionResetError("simulated reset")
            if ending == "fault_exc":
                raise http_client.IncompleteRead(b"partial", 100)
            if ending == "fault_ssl":
                raise ssl.SSLError("simulated SSL error during read")
            if ending == "fault_timeout":
                raise TimeoutError("simulated timeout during body read")
            if ending == "fault_value":
                raise ValueError("simulated unexpected error during body read")
            # Should not reach here.
            raise AssertionError(f"_FaultIO used for unexpected ending {ending!r}")

        def readable(self) -> bool:
            return True

    class _FaultSocket:
        def makefile(self, mode: str, buffering: int = -1) -> Any:
            return _FaultIO()

        def sendall(self, data: bytes) -> None:
            pass

        def settimeout(self, t: float | None) -> None:
            pass

        def close(self) -> None:
            pass

    _sock = _FaultSocket()

    def open_socket(address: Any, timeout: Any = None) -> Any:
        return _sock

    return open_socket


# ---------------------------------------------------------------------------
# Clock sequences for budget rows
# ---------------------------------------------------------------------------


class _SeqClock:
    """Returns values from a list in order; returns 999.0 when exhausted."""

    def __init__(self, values: list[float]) -> None:
        self._v = list(values)

    def __call__(self) -> float:
        return self._v.pop(0) if self._v else 999.0


# ---------------------------------------------------------------------------
# Core assertion helper
# ---------------------------------------------------------------------------


def _assert_matrix_row(
    status: int | None,
    ending: str,
    *,
    response: bytes | None = None,
    open_socket_fn: Any = None,
    resolve_fn: Any = None,
    open_socket_error: BaseException | None = None,
    wrap_error: Any = None,
    clock: Any = None,
    size_cap: int = _CAP,
) -> None:
    """Run one matrix row and assert the attempt record matches the oracle."""
    exp_http, exp_nrc, exp_blocked, exp_stop = _oracle(status, ending)

    if response is None and open_socket_fn is None and open_socket_error is None:
        response = make_http_response(status or 200, {}, b"ok") if status else b""

    if open_socket_fn is not None:
        r, _, w = make_seam(b"", resolved_addr="8.8.8.8")
        resolve = r if resolve_fn is None else resolve_fn
        open_sk = open_socket_fn
        wrap = w
    elif resolve_fn is not None:
        r, o, w = make_seam(response or b"", resolved_addr="8.8.8.8")
        resolve = resolve_fn
        open_sk = o
        wrap = w
    elif wrap_error is not None:
        resolve, open_sk, wrap = make_seam(
            response or b"",
            resolved_addr="8.8.8.8",
            wrap_error=wrap_error,
        )
    else:
        resolve, open_sk, wrap = make_seam(
            response or b"",
            resolved_addr="8.8.8.8",
            open_socket_error=open_socket_error,
        )

    gate = _fake_gate(clock=clock)
    try:
        _body, record = fetch_url(
            _HOST,
            _PATH,
            size_cap,
            "submissions",
            _CONTACT,
            gate,
            resolve=resolve,
            open_socket=open_sk,
            wrap=wrap,
            clock=clock,
        )
        got_http = record.http_status_class
        got_nrc = record.no_response_class
        got_blocked = record.blocked
        got_stop = record.stop_condition
    except SecClientError as exc:
        assert exc.attempt_record is not None, (
            f"({status}, {ending!r}) SecClientError has no attempt_record attached"
        )
        got_http = exc.attempt_record.http_status_class
        got_nrc = exc.attempt_record.no_response_class
        got_blocked = exc.attempt_record.blocked
        got_stop = exc.attempt_record.stop_condition

    assert got_http == exp_http, (
        f"({status}, {ending!r}) http_status_class: expected {exp_http!r}, got {got_http!r}"
    )
    assert got_nrc == exp_nrc, (
        f"({status}, {ending!r}) no_response_class: expected {exp_nrc!r}, got {got_nrc!r}"
    )
    assert got_blocked == exp_blocked, (
        f"({status}, {ending!r}) blocked: expected {exp_blocked!r}, got {got_blocked!r}"
    )
    assert got_stop == exp_stop, (
        f"({status}, {ending!r}) stop_condition: expected {exp_stop!r}, got {got_stop!r}"
    )


# ---------------------------------------------------------------------------
# No-status site rows
# ---------------------------------------------------------------------------


def test_matrix_no_status_dns_failure() -> None:
    """DNS gaierror → dns."""
    import socket as _sock

    def bad_resolve(host: str, port: int, **kw: Any) -> list[Any]:
        raise _sock.gaierror("simulated failure")

    _assert_matrix_row(None, "dns_failure", response=b"", resolve_fn=bad_resolve)


def test_matrix_no_status_dns_no_public() -> None:
    """DNS returns only loopback → dns."""
    import socket as _sock

    def private_resolve(host: str, port: int, **kw: Any) -> list[Any]:
        return [(_sock.AF_INET, _sock.SOCK_STREAM, 0, "", ("127.0.0.1", port))]

    _assert_matrix_row(None, "dns_no_public", response=b"", resolve_fn=private_resolve)


def test_matrix_no_status_dns_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """DNS thread abandoned at budget expiry → total_timeout, gate released.

    Real-clock row: _TOTAL_BUDGET patched to 0.05 s; resolver sleeps 0.3 s.
    Without the threaded-DNS mechanism, the resolver runs inline for 0.3 s,
    which exceeds the budget + 0.15 s margin → test reds.
    With the thread, the thread is abandoned at the budget and the attempt
    raises immediately; elapsed < 0.15 s.
    """
    _patch_budget(monkeypatch, 0.05)
    import socket as _s

    def slow_resolve(host: str, port: int, **kw: Any) -> list[Any]:
        time.sleep(0.3)
        return [(_s.AF_INET, _s.SOCK_STREAM, 0, "", ("8.8.8.8", port))]

    t0 = time.monotonic()
    _assert_matrix_row(None, "dns_timeout", response=b"", resolve_fn=slow_resolve)
    elapsed = time.monotonic() - t0
    # Gate must be released within budget + 0.15 s; inline-resolver mutant
    # takes ≥ 0.3 s, which exceeds this margin.
    assert elapsed < 0.05 + 0.15, (
        f"DNS-timeout row took {elapsed:.3f}s; expected < 0.20s with budget=0.05s"
    )


def test_matrix_no_status_connect_refused() -> None:
    """ConnectionRefusedError from open_socket → connection."""
    _assert_matrix_row(
        None,
        "connect_refused",
        open_socket_error=ConnectionRefusedError("refused"),
        response=b"",
    )


def test_matrix_no_status_connect_timeout() -> None:
    """TimeoutError from open_socket (within budget) → connect_timeout."""
    _assert_matrix_row(
        None,
        "connect_timeout",
        open_socket_error=TimeoutError("timed out"),
        response=b"",
    )


def test_matrix_no_status_connect_value() -> None:
    """ValueError (unexpected exception) from open_socket → connection (AC-0417)."""
    _assert_matrix_row(
        None,
        "connect_value",
        open_socket_error=ValueError("unexpected error from open_socket"),
        response=b"",
    )


def test_matrix_no_status_handshake_value() -> None:
    """ValueError (unexpected exception) from wrap → connection (AC-0417)."""
    import socket as _sock

    def resolve(host: str, port: int, **kw: Any) -> list[Any]:
        return [(_sock.AF_INET, _sock.SOCK_STREAM, 0, "", ("8.8.8.8", port))]

    _fake_sock = FakeSocket(b"")

    def open_sk(address: Any, timeout: Any = None) -> Any:
        return _fake_sock

    class _ValueWrap:
        def __call__(self, sock: Any, server_hostname: Any = None) -> Any:
            raise ValueError("unexpected error from wrap")

    wrap = _ValueWrap()
    gate = _fake_gate()
    with pytest.raises(SecClientError) as exc_info:
        fetch_url(
            _HOST,
            _PATH,
            _CAP,
            "submissions",
            _CONTACT,
            gate,
            resolve=resolve,
            open_socket=open_sk,
            wrap=wrap,
        )
    exc = exc_info.value
    assert exc.attempt_record is not None
    assert exc.attempt_record.no_response_class == "connection"
    assert exc.attempt_record.stop_condition == "connection"


def test_matrix_no_status_budget_pre_connect() -> None:
    """Budget exhausted before connect → total_timeout."""
    clock = _SeqClock([0.0, 35.0])
    _assert_matrix_row(None, "budget_pre_connect", response=b"", clock=clock)


def test_matrix_no_status_handshake_ssl() -> None:
    """ssl.SSLError from wrap → tls."""
    _assert_matrix_row(
        None,
        "handshake_ssl",
        wrap_error=ssl.SSLError("cert verify failed"),
        response=b"",
    )


def test_matrix_no_status_handshake_reset() -> None:
    """ConnectionResetError from wrap → connection."""
    _assert_matrix_row(
        None,
        "handshake_reset",
        wrap_error=ConnectionResetError("reset"),  # type: ignore[arg-type]
        response=b"",
    )


def test_matrix_no_status_handshake_timeout() -> None:
    """TimeoutError from wrap → connect_timeout."""

    class _TimeoutWrap:
        def __call__(self, sock: Any, server_hostname: Any = None) -> Any:
            raise TimeoutError("TLS handshake timeout")

    import socket as _sock

    def resolve(host: str, port: int, **kw: Any) -> list[Any]:
        return [(_sock.AF_INET, _sock.SOCK_STREAM, 0, "", ("8.8.8.8", port))]

    _fake_sock = FakeSocket(b"")

    def open_sk(address: Any, timeout: Any = None) -> Any:
        return _fake_sock

    wrap = _TimeoutWrap()
    gate = _fake_gate()
    with pytest.raises(SecClientError) as exc_info:
        fetch_url(
            _HOST,
            _PATH,
            _CAP,
            "submissions",
            _CONTACT,
            gate,
            resolve=resolve,
            open_socket=open_sk,
            wrap=wrap,
        )
    exc = exc_info.value
    assert exc.attempt_record is not None
    assert exc.attempt_record.no_response_class == "connect_timeout"
    assert exc.attempt_record.stop_condition == "connect_timeout"


def _make_request_fault_socket(fault: str) -> Any:
    """Return an open_socket callable whose socket raises in sendall."""
    _ok_header = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok"
    _fake = FakeSocket(_ok_header)

    class _FaultSendSocket:
        def makefile(self, mode: str, buffering: int = -1) -> Any:
            return _fake.makefile(mode, buffering)

        def sendall(self, data: bytes) -> None:
            if fault == "request_reset":
                raise ConnectionResetError("reset")
            if fault == "request_exc":
                raise http_client.BadStatusLine("bad")
            if fault == "request_ssl":
                raise ssl.SSLError("ssl error during send")
            if fault == "request_timeout":
                raise TimeoutError("send timed out")
            if fault == "request_value":
                raise ValueError("unexpected value error during request")
            raise AssertionError(f"unexpected fault {fault!r}")

        def settimeout(self, t: float | None) -> None:
            pass

        def close(self) -> None:
            pass

    _sock_inst = _FaultSendSocket()

    def open_socket(address: Any, timeout: Any = None) -> Any:
        return _sock_inst

    return open_socket


def test_matrix_no_status_request_reset() -> None:
    """ConnectionResetError during sendall → connection."""
    _assert_matrix_row(
        None,
        "request_reset",
        open_socket_fn=_make_request_fault_socket("request_reset"),
    )


def test_matrix_no_status_request_exc() -> None:
    """BadStatusLine (HTTPException) during request → connection."""
    _assert_matrix_row(
        None,
        "request_exc",
        open_socket_fn=_make_request_fault_socket("request_exc"),
    )


def test_matrix_no_status_request_ssl() -> None:
    """ssl.SSLError during sendall → tls (AC-0417: tls for any ssl.SSLError)."""
    _assert_matrix_row(
        None,
        "request_ssl",
        open_socket_fn=_make_request_fault_socket("request_ssl"),
    )


def test_matrix_no_status_request_timeout() -> None:
    """TimeoutError during sendall (within budget) → read_timeout."""
    clock = _SeqClock([0.0, 0.0, 1.0, 2.0, 3.0, 4.0])
    _assert_matrix_row(
        None,
        "request_timeout",
        open_socket_fn=_make_request_fault_socket("request_timeout"),
        clock=clock,
    )


def test_matrix_no_status_request_value() -> None:
    """ValueError during sendall (unexpected) → connection."""
    _assert_matrix_row(
        None,
        "request_value",
        open_socket_fn=_make_request_fault_socket("request_value"),
    )


def test_matrix_no_status_budget_pre_request() -> None:
    """Budget exhausted before request → total_timeout."""
    # [0]=gate_start, [1]=admission, [2]=pre-connect, [3]=post-DNS (in connect()),
    # [4]=pre-request check → 35.0 > budget_end=30.0 → total_timeout.
    clock = _SeqClock([0.0, 0.0, 1.0, 2.0, 35.0])
    _assert_matrix_row(None, "budget_pre_request", response=b"", clock=clock)


# ---------------------------------------------------------------------------
# Parametrized status × ending matrix
#
# Build the full cross product, skip unreachable cells, and generate one
# pytest test case per reachable (status, ending) pairing.
# ---------------------------------------------------------------------------


def _build_matrix_params() -> list[tuple[int, str]]:
    params = []
    for status in _STATUSES:
        for ending in _BODY_ENDINGS:
            if (status, ending) not in _UNREACHABLE:
                params.append((status, ending))
    return params


_MATRIX_PARAMS = _build_matrix_params()


def _clock_for_budget_row(needs_status: bool, zero_body: bool = False) -> _SeqClock:
    """Return a clock sequence that fires a budget timeout at the right phase.

    Parameters
    ----------
    needs_status:
        True → budget fires on the first per-chunk check inside _real_fetch
        (budget_read); False → budget fires on the post-read check in fetch_url
        (budget_post_read).
    zero_body:
        True for statuses where http.client reads 0 body bytes (1xx, 304).
        The read loop runs only once (reads b'' immediately), so one fewer
        clock call is consumed inside the loop.
    """
    # Clock sequence legend (admission = 0.0, budget_end = 30.0):
    #   [0] gate_start        [1] fake_gate → admission
    #   [2] pre-connect       [3] post-DNS (connect(), after DNS thread)
    #   [4] pre-request       [5..] per-chunk budget checks in the read loop
    #   last: the check that fires budget exhaustion
    if needs_status:
        # Budget fires on the first per-chunk check ([5] = 35.0).
        return _SeqClock([0.0, 0.0, 1.0, 2.0, 3.0, 35.0])
    if zero_body:
        # http.client reads 0 bytes: loop runs once (reads b''), breaks.
        # One per-chunk check ([5] = 4.0, reads b'' → break).
        # Post-read check in fetch_url ([6] = 35.0) → total_timeout.
        return _SeqClock([0.0, 0.0, 1.0, 2.0, 3.0, 4.0, 35.0])
    else:
        # Normal body: loop runs twice (reads body, then reads b'' → break).
        # [5]=4.0 reads body bytes; [6]=5.0 reads b'' → break.
        # Post-read check in fetch_url ([7] = 35.0) → total_timeout.
        return _SeqClock([0.0, 0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 35.0])


@pytest.mark.parametrize(
    "status,ending", _MATRIX_PARAMS, ids=[f"{s}x{e}" for s, e in _MATRIX_PARAMS]
)
def test_matrix_status_ending(status: int, ending: str) -> None:  # noqa: C901
    """One matrix cell: verify the attempt record matches the oracle."""
    response: bytes | None = None
    open_socket_fn: Any = None
    clock: Any = None

    if ending in _NEEDS_BODY_READ:
        # fault_* and stream_over_cap need the socket for body-read injection.
        if ending == "stream_over_cap":
            response = _resp_bytes(status, ending)
        else:
            open_socket_fn = _make_fault_socket(status, ending)

        if ending == "fault_timeout":
            # Timeout within budget: all clock checks < budget_end=30.
            # [0]=gate_start, [1]=admission, [2]=pre-connect, [3]=post-DNS,
            # [4]=pre-request, [5]=body-read loop budget check,
            # [6]=TimeoutError handler → 5.0 < 30.0 → "read_timeout".
            clock = _SeqClock([0.0, 0.0, 1.0, 2.0, 3.0, 4.0, 5.0])
        # Other fault_* rows use real monotonic clock (fast, no sleep).

    elif ending == "budget_read":
        response = _resp_bytes(status, "complete")
        clock = _clock_for_budget_row(needs_status=True)

    elif ending == "budget_post_read":
        response = _resp_bytes(status, "complete")
        clock = _clock_for_budget_row(
            needs_status=False, zero_body=status in _ZERO_BODY_STATUSES
        )

    else:
        response = _resp_bytes(status, ending)

    _assert_matrix_row(
        status,
        ending,
        response=response,
        open_socket_fn=open_socket_fn,
        clock=clock,
        size_cap=_CAP,
    )


# ---------------------------------------------------------------------------
# Unreachable-cell documentation
# ---------------------------------------------------------------------------


def test_unreachable_cells_are_documented() -> None:
    """Every unreachable cell has a stdlib reason recorded in _UNREACHABLE."""
    # Verify every entry mentions the relevant status and a reason.
    for (status, ending), reason in _UNREACHABLE.items():
        assert str(status) in reason or "1xx" in reason or "304" in reason, (
            f"Unreachable entry ({status}, {ending!r}) reason does not mention "
            f"the status: {reason!r}"
        )
        assert "http.client" in reason, (
            f"Unreachable entry ({status}, {ending!r}) reason should cite http.client: "
            f"{reason!r}"
        )


# ---------------------------------------------------------------------------
# Per-phase real-clock cap rows  (AC-0417 budget-cap mutant proofs)
#
# Each row uses a total budget of 0.5 s; the phase's uncapped timeout is much
# longer (5 s for connect, 15 s for request/body).  The row asserts that
# fetch_url returns within 2 × budget (1.0 s).
#
# Mutant: remove the `min(_PHASE_TIMEOUT, remaining)` clamp for that phase.
# The socket/file then sleeps the full uncapped timeout, and the assertion
# fails (elapsed > 1.0 s).
# ---------------------------------------------------------------------------

_CAP_BUDGET = 0.5  # patched _TOTAL_BUDGET for real-clock cap rows
_CAP_MARGIN = _CAP_BUDGET + 0.2  # wall-time limit: gate must release within budget


def _patch_budget(monkeypatch: pytest.MonkeyPatch, budget: float) -> None:
    import ced.adapters.sec.client as _c

    monkeypatch.setattr(_c, "_TOTAL_BUDGET", budget)


class _ConnectCapSocket:
    """Sleeps for `timeout` seconds then raises TimeoutError, proving the cap."""

    def __init__(self) -> None:
        self._fake = FakeSocket(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")

    def makefile(self, mode: str, buffering: int = -1) -> Any:
        return self._fake.makefile(mode, buffering)

    def sendall(self, data: bytes) -> None:
        pass

    def settimeout(self, t: float | None) -> None:
        pass

    def close(self) -> None:
        pass


def test_connect_phase_budget_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """Connect timeout is clamped to remaining budget.

    With budget=0.5 s, the clamped connect timeout is ≤0.5 s, so fetch_url
    returns within 1.5 s despite the 5-second uncapped connect timeout.

    Mutant: remove ``min(_CONNECT_TIMEOUT, remaining)`` — ``conn.timeout``
    becomes 5.0 s; ``open_socket`` sleeps 5.0 s; elapsed > 1.5 s → reds.
    """
    _patch_budget(monkeypatch, _CAP_BUDGET)
    import socket as _sock

    def resolve(host: str, port: int, **kw: Any) -> list[Any]:
        return [(_sock.AF_INET, _sock.SOCK_STREAM, 0, "", ("8.8.8.8", port))]

    def open_socket(address: Any, timeout: float | None = None) -> Any:
        # Simulate a connect that takes exactly `timeout` seconds then times out.
        t = timeout or 5.0
        time.sleep(t)
        raise TimeoutError("connect timed out")

    def wrap(sock: Any, server_hostname: Any = None) -> Any:
        return sock

    t0 = time.monotonic()
    with pytest.raises(SecClientError) as exc_info:
        fetch_url(
            _HOST,
            _PATH,
            _CAP,
            "submissions",
            _CONTACT,
            _fake_gate(),
            resolve=resolve,
            open_socket=open_socket,
            wrap=wrap,
        )
    elapsed = time.monotonic() - t0
    assert elapsed < _CAP_MARGIN, (
        f"connect-phase cap row took {elapsed:.2f}s; expected < {_CAP_MARGIN}s "
        f"with budget={_CAP_BUDGET}s"
    )
    rec = exc_info.value.attempt_record
    assert rec is not None
    assert rec.no_response_class in ("connect_timeout", "total_timeout")


def test_request_phase_budget_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """Read timeout (request phase) is clamped to remaining budget.

    With budget=0.5 s, the clamped timeout for sendall is ≤0.5 s.

    Mutant: remove ``min(_READ_TIMEOUT, remaining)`` for the pre-request
    ``set_read_timeout`` — the socket timeout stays at 15 s; sendall sleeps
    15 s; elapsed > 1.5 s → reds.
    """
    _patch_budget(monkeypatch, _CAP_BUDGET)
    import socket as _sock

    def resolve(host: str, port: int, **kw: Any) -> list[Any]:
        return [(_sock.AF_INET, _sock.SOCK_STREAM, 0, "", ("8.8.8.8", port))]

    class _SlowSendSocket:
        _timeout: float | None = None

        def makefile(self, mode: str, buffering: int = -1) -> Any:
            return io.BytesIO(b"")

        def settimeout(self, t: float | None) -> None:
            self._timeout = t

        def sendall(self, data: bytes) -> None:
            t = self._timeout if self._timeout is not None else 15.0
            time.sleep(t)
            raise TimeoutError("request timed out")

        def close(self) -> None:
            pass

    _s = _SlowSendSocket()

    def open_socket(address: Any, timeout: float | None = None) -> Any:
        return _s

    def wrap(sock: Any, server_hostname: Any = None) -> Any:
        return sock

    t0 = time.monotonic()
    with pytest.raises(SecClientError) as exc_info:
        fetch_url(
            _HOST,
            _PATH,
            _CAP,
            "submissions",
            _CONTACT,
            _fake_gate(),
            resolve=resolve,
            open_socket=open_socket,
            wrap=wrap,
        )
    elapsed = time.monotonic() - t0
    assert elapsed < _CAP_MARGIN, (
        f"request-phase cap row took {elapsed:.2f}s; expected < {_CAP_MARGIN}s"
    )
    rec = exc_info.value.attempt_record
    assert rec is not None
    assert rec.no_response_class in ("read_timeout", "total_timeout")


def test_body_read_phase_budget_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """Read timeout (body-read phase) is clamped to remaining budget per chunk.

    With budget=0.5 s, the clamped timeout for response.read is ≤0.5 s.

    Mutant: remove ``min(_READ_TIMEOUT, remaining)`` from the body-read loop
    — the socket timeout stays at 15 s; the body-read sleeps 15 s; elapsed > 1.5 s.
    """
    _patch_budget(monkeypatch, _CAP_BUDGET)
    import socket as _sock

    def resolve(host: str, port: int, **kw: Any) -> list[Any]:
        return [(_sock.AF_INET, _sock.SOCK_STREAM, 0, "", ("8.8.8.8", port))]

    header = b"HTTP/1.1 200 OK\r\n\r\n"

    class _SlowBodyIO(io.RawIOBase):
        def __init__(self, outer: Any) -> None:
            self._data = header
            self._pos = 0
            self._outer = outer

        def read(self, n: int = -1) -> bytes:
            if self._pos < len(self._data):
                chunk = self._data[self._pos : self._pos + n]
                self._pos += len(chunk)
                return chunk
            # Body read: sleep for the capped timeout then raise TimeoutError.
            t = self._outer._timeout if self._outer._timeout is not None else 15.0
            time.sleep(t)
            raise TimeoutError("body read timed out")

        def readable(self) -> bool:
            return True

    class _SlowBodySocket:
        _timeout: float | None = None

        def makefile(self, mode: str, buffering: int = -1) -> Any:
            return _SlowBodyIO(self)

        def settimeout(self, t: float | None) -> None:
            self._timeout = t

        def sendall(self, data: bytes) -> None:
            pass

        def close(self) -> None:
            pass

    _s = _SlowBodySocket()

    def open_socket(address: Any, timeout: float | None = None) -> Any:
        return _s

    def wrap(sock: Any, server_hostname: Any = None) -> Any:
        return sock

    t0 = time.monotonic()
    with pytest.raises(SecClientError) as exc_info:
        fetch_url(
            _HOST,
            _PATH,
            _CAP,
            "submissions",
            _CONTACT,
            _fake_gate(),
            resolve=resolve,
            open_socket=open_socket,
            wrap=wrap,
        )
    elapsed = time.monotonic() - t0
    assert elapsed < _CAP_MARGIN, (
        f"body-read-phase cap row took {elapsed:.2f}s; expected < {_CAP_MARGIN}s"
    )
    rec = exc_info.value.attempt_record
    assert rec is not None
    assert rec.no_response_class in ("read_timeout", "total_timeout")


# ---------------------------------------------------------------------------
# total_timeout precedence over read_timeout at request and body-read phases
# (AC-0417: total_timeout wins over a phase timeout when budget is exhausted)
# ---------------------------------------------------------------------------


def test_request_phase_timeout_at_budget_end(monkeypatch: pytest.MonkeyPatch) -> None:
    """TimeoutError during request at budget_end → total_timeout, not read_timeout.

    Mutant: replace ``clock() >= budget_end`` with False at client.py request site.
    That mutant always records ``read_timeout``; this test reds it.
    """
    _patch_budget(monkeypatch, _CAP_BUDGET)
    import socket as _sock

    def resolve(host: str, port: int, **kw: Any) -> list[Any]:
        return [(_sock.AF_INET, _sock.SOCK_STREAM, 0, "", ("8.8.8.8", port))]

    class _TimeoutAtBudgetSocket:
        _timeout: float | None = None

        def makefile(self, mode: str, buffering: int = -1) -> Any:
            return io.BytesIO(b"")

        def settimeout(self, t: float | None) -> None:
            self._timeout = t

        def sendall(self, data: bytes) -> None:
            raise TimeoutError("timeout fires at budget end")

        def close(self) -> None:
            pass

    _s = _TimeoutAtBudgetSocket()

    def open_socket(address: Any, timeout: float | None = None) -> Any:
        return _s

    def wrap(sock: Any, server_hostname: Any = None) -> Any:
        return sock

    # [0]=gate_start, [1]=admission → budget_end=0.5,
    # [2]=pre-connect, [3]=post-DNS, [4]=pre-request,
    # [5]=TimeoutError handler: 0.6 >= 0.5 → total_timeout.
    clock = _SeqClock([0.0, 0.0, 0.0, 0.0, 0.0, 0.6])
    with pytest.raises(SecClientError) as exc_info:
        fetch_url(
            _HOST,
            _PATH,
            _CAP,
            "submissions",
            _CONTACT,
            _fake_gate(clock=clock),
            resolve=resolve,
            open_socket=open_socket,
            wrap=wrap,
            clock=clock,
        )
    rec = exc_info.value.attempt_record
    assert rec is not None
    assert rec.no_response_class == "total_timeout", (
        f"expected total_timeout, got {rec.no_response_class!r}"
    )


def test_body_read_phase_timeout_at_budget_end(monkeypatch: pytest.MonkeyPatch) -> None:
    """TimeoutError during body read at budget_end → total_timeout, not read_timeout.

    Mutant: replace ``clock() >= budget_end`` with False at client.py body-read site.
    That mutant always records ``read_timeout``; this test reds it.
    """
    _patch_budget(monkeypatch, _CAP_BUDGET)
    import socket as _sock

    def resolve(host: str, port: int, **kw: Any) -> list[Any]:
        return [(_sock.AF_INET, _sock.SOCK_STREAM, 0, "", ("8.8.8.8", port))]

    _header = b"HTTP/1.1 200 OK\r\n\r\n"

    class _TimeoutBodyIO(io.RawIOBase):
        def __init__(self) -> None:
            self._pos = 0

        def read(self, n: int = -1) -> bytes:
            if self._pos < len(_header):
                chunk = _header[self._pos : self._pos + n]
                self._pos += len(chunk)
                return chunk
            raise TimeoutError("body read timeout at budget end")

        def readable(self) -> bool:
            return True

    class _TimeoutBodySocket:
        _timeout: float | None = None

        def makefile(self, mode: str, buffering: int = -1) -> Any:
            return _TimeoutBodyIO()

        def settimeout(self, t: float | None) -> None:
            self._timeout = t

        def sendall(self, data: bytes) -> None:
            pass

        def close(self) -> None:
            pass

    _s = _TimeoutBodySocket()

    def open_socket(address: Any, timeout: float | None = None) -> Any:
        return _s

    def wrap(sock: Any, server_hostname: Any = None) -> Any:
        return sock

    # [0]=gate_start, [1]=admission → budget_end=0.5,
    # [2]=pre-connect, [3]=post-DNS, [4]=pre-request,
    # [5]=body-read loop budget check, [6]=TimeoutError handler: 0.6 >= 0.5 → total_timeout.
    clock = _SeqClock([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.6])
    with pytest.raises(SecClientError) as exc_info:
        fetch_url(
            _HOST,
            _PATH,
            _CAP,
            "submissions",
            _CONTACT,
            _fake_gate(clock=clock),
            resolve=resolve,
            open_socket=open_socket,
            wrap=wrap,
            clock=clock,
        )
    rec = exc_info.value.attempt_record
    assert rec is not None
    assert rec.no_response_class == "total_timeout", (
        f"expected total_timeout, got {rec.no_response_class!r}"
    )


# ---------------------------------------------------------------------------
# AC-0402 hard bound: slow DNS followed by a blocking connect
# ---------------------------------------------------------------------------

_TRICKLE_BUDGET = 0.15  # patched budget for the slow-DNS row


def test_slow_dns_then_blocking_connect_released_within_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DNS consuming half the budget leaves the correct remainder for connect.

    Without post-DNS timeout recomputation, the connect uses the full pre-DNS
    remaining (0.5 s), so total = DNS (0.25 s) + connect (0.5 s) = 0.75 s >
    budget + 0.2 s = 0.7 s → test reds.  With recomputation, connect uses
    post-DNS remaining (≈0.25 s), so total ≈ 0.5 s < 0.7 s.

    Mutant: remove the post-DNS ``self.timeout = min(...)`` recomputation.
    """
    _patch_budget(monkeypatch, _CAP_BUDGET)  # 0.5 s total budget
    import socket as _sock

    dns_sleep = _CAP_BUDGET / 2  # 0.25 s → leaves ≈0.25 s for connect

    def slow_resolve(host: str, port: int, **kw: Any) -> list[Any]:
        time.sleep(dns_sleep)
        return [(_sock.AF_INET, _sock.SOCK_STREAM, 0, "", ("8.8.8.8", port))]

    def open_socket(address: Any, timeout: float | None = None) -> Any:
        # Sleep for exactly the given timeout then raise TimeoutError.
        t = timeout if timeout is not None else 5.0
        time.sleep(t)
        raise TimeoutError("connect timed out")

    def wrap(sock: Any, server_hostname: Any = None) -> Any:
        return sock

    t0 = time.monotonic()
    with pytest.raises(SecClientError) as exc_info:
        fetch_url(
            _HOST,
            _PATH,
            _CAP,
            "submissions",
            _CONTACT,
            _fake_gate(),
            resolve=slow_resolve,
            open_socket=open_socket,
            wrap=wrap,
        )
    elapsed = time.monotonic() - t0
    rec = exc_info.value.attempt_record
    assert rec is not None
    # Without recomputation: connect uses pre-DNS remaining (0.5 s); total ≈ 0.75 s > 0.7 s.
    # With recomputation: connect uses post-DNS remaining (≈0.25 s); total ≈ 0.5 s < 0.7 s.
    assert elapsed < _CAP_BUDGET + 0.2, (
        f"slow-DNS+connect row held gate for {elapsed:.3f}s; "
        f"expected < {_CAP_BUDGET + 0.2:.2f}s with budget={_CAP_BUDGET}s"
    )
    assert rec.no_response_class in ("connect_timeout", "total_timeout"), (
        f"unexpected no_response_class {rec.no_response_class!r}"
    )


# ---------------------------------------------------------------------------
# AC-0402 hard bound against a real trickling peer
#
# A fake socket cannot show whether the watchdog unblocks a real `recv`: the
# kernel does not wake a blocked `recv` when another thread closes the socket.
# These rows use a real loopback server, so they red when the watchdog closes
# instead of shutting the socket down, or when it is removed.
# ---------------------------------------------------------------------------


def _serve_trickle(kind: str) -> int:
    """Start a one-shot loopback server that trickles headers or body; return its port."""
    import socket as _sock

    server = _sock.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)

    def serve() -> None:
        conn, _ = server.accept()
        conn.recv(4096)
        try:
            if kind == "body":
                conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 1000\r\n\r\n")
                for _ in range(40):
                    time.sleep(0.05)
                    conn.sendall(b"x")
            else:
                conn.sendall(b"HTTP/1.1 200 OK\r\n")
                for i in range(40):
                    time.sleep(0.05)
                    conn.sendall(b"X-T%d: v\r\n" % i)
        except OSError:
            pass
        finally:
            conn.close()
            server.close()

    threading.Thread(target=serve, daemon=True).start()
    return int(server.getsockname()[1])


@pytest.mark.parametrize("kind", ["header", "body"])
def test_a_real_trickling_peer_is_cut_off_at_the_budget(
    monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    """A peer sending one byte every 50 ms ends at the budget, gate released.

    Mutant: the watchdog calls `conn.close()` instead of shutting the socket
    down, or is removed. The attempt then runs about 2 s against a 0.5 s budget,
    and this check reds.
    """
    import contextlib
    import socket as _sock

    _patch_budget(monkeypatch, 0.5)
    port = _serve_trickle(kind)
    exits: list[float] = []

    @contextlib.contextmanager
    def gate() -> Iterator[float]:
        try:
            yield time.monotonic()
        finally:
            exits.append(time.monotonic())

    t0 = time.monotonic()
    with pytest.raises(SecClientError) as exc_info:
        fetch_url(
            _HOST,
            _PATH,
            10**6,
            "submissions",
            _CONTACT,
            gate(),
            resolve=lambda host, p, **kw: [
                (_sock.AF_INET, _sock.SOCK_STREAM, 0, "", ("8.8.8.8", p))
            ],
            open_socket=lambda address, timeout=None: _sock.create_connection(
                ("127.0.0.1", port), timeout=timeout
            ),
            wrap=lambda sock, server_hostname=None: sock,
        )
    elapsed = time.monotonic() - t0
    assert elapsed < 0.5 + 0.2, f"{kind} trickle held the attempt for {elapsed:.2f}s"
    assert exits and exits[0] - t0 < 0.5 + 0.2, "the gate was not released within the budget"
    assert exc_info.value.attempt_record is not None
    assert exc_info.value.attempt_record.no_response_class == "total_timeout"
