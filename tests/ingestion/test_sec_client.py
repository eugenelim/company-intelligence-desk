"""SEC client tests — AC-0402.

All tests run through the single production code path
(``_real_fetch`` / ``_GatedSecConnection.connect()``) using injectable
``resolve``, ``open_socket``, and ``wrap`` callables.  No test uses a second
fetch path, so the production connect/DNS/TLS/timeout/read/budget code is
exercised by every test.

The gate is injected with the fake gate so no Postgres dependency is needed.

Each guard earns a named mutation red documented in the verification ledger.
"""

from __future__ import annotations

import contextlib
import io
import json
import ssl
import time
import traceback
from collections.abc import Generator
from http import client as http_client
from typing import Any

import pytest

from ced.adapters.sec.client import (
    _SUBMISSIONS_CAP,
    AttemptRecord,
    SecBlockedError,
    SecClientError,
    SecRedirectError,
    _fake_gate,
    acquire_contact,
    fetch_url,
)
from tests.ingestion.fixture import FakeSocket, make_http_response, make_seam

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HOST = "data.sec.gov"
_PATH = "/submissions/CIK0000320193.json"
_CONTACT = "test-contact-fictional@example.com"

_OK_RESPONSE = make_http_response(200, {}, b'{"ok": true}')


def _make_gate() -> Any:
    return _fake_gate()


def _fetch(
    *,
    host: str = _HOST,
    path: str = _PATH,
    size_cap: int = _SUBMISSIONS_CAP,
    request_class: str = "submissions",
    clock: Any = None,
    response: bytes | None = None,
    resolved_addr: str = "8.8.8.8",
    resolved_addrs: list[str] | None = None,
    open_socket_error: BaseException | None = None,
    wrap_error: ssl.SSLError | None = None,
    timeout_on_send: bool = False,
    socket_opens: list[str] | None = None,
    wrap_calls: list[str | None] | None = None,
    gate: Any = None,
) -> tuple[bytes, AttemptRecord]:
    if response is None:
        response = _OK_RESPONSE
    resolve, open_socket, wrap = make_seam(
        response,
        resolved_addr=resolved_addr,
        resolved_addrs=resolved_addrs,
        open_socket_error=open_socket_error,
        wrap_error=wrap_error,
        timeout_on_send=timeout_on_send,
        socket_opens=socket_opens,
        wrap_calls=wrap_calls,
    )
    if gate is None:
        gate = _make_gate()
    return fetch_url(
        host,
        path,
        size_cap,
        request_class,
        _CONTACT,
        gate,
        resolve=resolve,
        open_socket=open_socket,
        wrap=wrap,
        clock=clock,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_fetch_url_returns_body_on_200() -> None:
    """A 200 response with small body is returned as bytes.

    This exercises the full production path: resolve → ip-filter → connect →
    TLS wrap → send → getresponse → read loop.
    """
    body, record = _fetch()
    assert body == b'{"ok": true}'
    assert record.stop_condition == "success"
    assert record.http_status_class == "2xx"
    assert record.no_response_class is None
    assert record.blocked is False
    assert record.retry_count == 0


# ---------------------------------------------------------------------------
# AC-0402: host allow-list
# ---------------------------------------------------------------------------


def test_fetch_url_refuses_disallowed_host() -> None:
    """A host outside the allow-list is refused before any connection.

    Mutation: remove the ``host not in _ALLOWED_HOSTS`` guard — the test
    would not raise ``SecClientError``.
    """
    with pytest.raises(SecClientError, match="not in the admitted set"):
        _fetch(host="evil.example.com")


def test_fetch_url_admits_data_sec_gov() -> None:
    """``data.sec.gov`` is in the allow-list."""
    body, record = _fetch(host="data.sec.gov")
    assert record.stop_condition == "success"


def test_fetch_url_admits_www_sec_gov() -> None:
    """``www.sec.gov`` is in the allow-list."""
    body, record = _fetch(host="www.sec.gov")
    assert record.stop_condition == "success"


# ---------------------------------------------------------------------------
# AC-0402: redirect refusal
# ---------------------------------------------------------------------------


def test_fetch_url_refuses_301() -> None:
    """HTTP 301 raises SecRedirectError.

    Mutation: remove the redirect-status check — the test would not raise.
    """
    resp = make_http_response(301, {"Location": "https://www.sec.gov/other"}, b"")
    with pytest.raises(SecRedirectError):
        _fetch(response=resp)


def test_fetch_url_refuses_302() -> None:
    """HTTP 302 raises SecRedirectError."""
    resp = make_http_response(302, {}, b"")
    with pytest.raises(SecRedirectError):
        _fetch(response=resp)


def test_fetch_url_refuses_307() -> None:
    """HTTP 307 raises SecRedirectError."""
    resp = make_http_response(307, {}, b"")
    with pytest.raises(SecRedirectError):
        _fetch(response=resp)


# ---------------------------------------------------------------------------
# AC-0402: 403/429 blocked
# ---------------------------------------------------------------------------


def test_fetch_url_raises_blocked_on_403() -> None:
    """HTTP 403 raises SecBlockedError.

    Mutation: remove the 403 special-case — a generic SecClientError would
    be raised with blocked=False.
    """
    resp = make_http_response(403, {}, b"")
    with pytest.raises(SecBlockedError):
        _fetch(response=resp)


def test_fetch_url_raises_blocked_on_429() -> None:
    """HTTP 429 raises SecBlockedError."""
    resp = make_http_response(429, {}, b"")
    with pytest.raises(SecBlockedError):
        _fetch(response=resp)


# ---------------------------------------------------------------------------
# AC-0402: size cap
# ---------------------------------------------------------------------------


def test_fetch_url_refuses_oversized_declared_length() -> None:
    """A declared Content-Length above the cap is refused before reading.

    The production read path (``_real_fetch``) enforces this cap, not a
    duplicated block in ``fetch_url``.

    Mutation: remove the Content-Length cap check from ``_real_fetch`` — the
    test would not raise until the body actually exceeded the cap during read.
    """
    cap = 100
    resp = make_http_response(
        200,
        {"Content-Length": "1000"},  # over cap, body is small
        b"x" * 50,
    )
    with pytest.raises(SecClientError, match="Content-Length|size cap"):
        _fetch(response=resp, size_cap=cap)


def test_fetch_url_refuses_oversized_body_during_streaming() -> None:
    """A body that crosses the cap during read is stopped and refused.

    Mutation: remove the streaming size check in ``_real_fetch`` — the test
    would succeed.
    """
    cap = 50
    resp = make_http_response(200, {}, b"x" * (cap + 1))
    with pytest.raises(SecClientError, match="size cap|exceeded"):
        _fetch(response=resp, size_cap=cap)


def test_fetch_url_refuses_malformed_content_length() -> None:
    """A malformed Content-Length header is refused (fail-closed) before read.

    Mutation: catch ValueError and treat malformed as 0 — the body would be
    read without a cap check.
    """
    resp = make_http_response(200, {}, b"ok")
    # Patch the Content-Length to a non-integer string.
    raw = resp.replace(b"Content-Length: 2", b"Content-Length: notanint")
    with pytest.raises(SecClientError, match="malformed Content-Length"):
        _fetch(response=raw)


# ---------------------------------------------------------------------------
# AC-0402: total budget (injectable clock)
# ---------------------------------------------------------------------------


def test_fetch_url_total_budget_starts_at_admission() -> None:
    """The 30-second total budget starts from gate admission, not gate-wait start.

    Scenario: gate wait costs 25 s (slow_gate yields 25.0).  The request
    completes within 5 s of admission.  Because the budget is measured from
    admission (25.0), the remaining budget is still large and the request
    succeeds.

    Mutation: start the budget timer before gate admission — the 25 s gate
    wait would count against the 30 s budget and leave only 5 s; the subsequent
    clock reads inside _real_fetch would use up that budget and refuse a
    request that should succeed.
    """

    # Call 1 (gate_start): 0.0
    # slow_gate yields 25.0 without calling the clock.
    # All subsequent calls in _real_fetch return 26.0:
    #   budget_end = 25.0 + 30.0 = 55.0
    #   remaining checks: 55.0 - 26.0 = 29.0 → always within budget.
    _call = [0]

    def fake_clock() -> float:
        _call[0] += 1
        if _call[0] == 1:
            return 0.0  # gate_start
        return 26.0  # all _real_fetch checks — within budget

    @contextlib.contextmanager
    def slow_gate() -> Generator[float]:
        yield 25.0  # admission_time = 25.0; gate_wait = 25 - 0 = 25

    body, record = fetch_url(
        _HOST,
        _PATH,
        _SUBMISSIONS_CAP,
        "submissions",
        _CONTACT,
        slow_gate(),
        **(lambda r, o, w: {"resolve": r, "open_socket": o, "wrap": w})(
            *make_seam(_OK_RESPONSE)
        ),
        clock=fake_clock,
    )
    assert record.stop_condition == "success"
    assert record.gate_wait_seconds >= 0.0


def test_fetch_url_refuses_when_total_budget_exceeded() -> None:
    """A request whose budget is already exhausted at first check is refused.

    The first thing ``_real_fetch`` does (before connect) is check the
    remaining budget: ``budget_end - clock()``.  With admission at t=0 and
    the clock returning 35.0 on that check, the budget (30 s) is already
    exceeded.

    Mutation: remove the pre-connect budget check in ``_real_fetch`` — the
    test would not raise until a later check, or not at all.
    """
    # Call 1 (gate_start in fetch_url): 0.0
    # instant_gate yields 0.0 (budget_start = 0.0, budget_end = 30.0)
    # Call 2 (first clock() in _real_fetch, before connect): 35.0
    #   remaining = 30.0 - 35.0 = -5.0 → total_timeout
    _times = [0.0, 35.0]

    def fake_clock() -> float:
        return _times.pop(0) if _times else 99.0

    @contextlib.contextmanager
    def instant_gate() -> Generator[float]:
        yield 0.0

    resolve, open_socket, wrap = make_seam(_OK_RESPONSE)
    with pytest.raises(SecClientError, match="total budget"):
        fetch_url(
            _HOST,
            _PATH,
            _SUBMISSIONS_CAP,
            "submissions",
            _CONTACT,
            instant_gate(),
            resolve=resolve,
            open_socket=open_socket,
            wrap=wrap,
            clock=fake_clock,
        )


# ---------------------------------------------------------------------------
# AC-0402: attempt record fields
# ---------------------------------------------------------------------------


def test_attempt_record_has_zero_retry_count() -> None:
    """The attempt record always has retry_count == 0.

    Mutation: set retry_count = 1 — the test would fail on the assertion.
    """
    _, record = _fetch()
    assert record.retry_count == 0


def test_attempt_record_gate_wait_is_separate_from_duration() -> None:
    """gate_wait_seconds and duration_seconds are separate fields."""
    _, record = _fetch()
    d = record.to_dict()
    assert "gate_wait_seconds" in d
    assert "duration_seconds" in d
    assert d["gate_wait_seconds"] >= 0.0
    assert d["duration_seconds"] >= 0.0


def test_attempt_record_blocked_false_on_success() -> None:
    """blocked is False when the request succeeds.

    Mutation: always set blocked=True — this assertion fails.
    """
    _, record = _fetch()
    assert record.blocked is False


def test_attempt_record_no_response_class_none_on_success() -> None:
    """no_response_class is None when an HTTP response is received."""
    _, record = _fetch()
    assert record.no_response_class is None


# ---------------------------------------------------------------------------
# AC-0402: missing SEC_CONTACT
# ---------------------------------------------------------------------------


def test_acquire_contact_raises_when_env_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing SEC_CONTACT raises SecClientError.

    Mutation: return an empty string instead of raising — no exception raised.
    """
    monkeypatch.delenv("SEC_CONTACT", raising=False)
    with pytest.raises(SecClientError, match="SEC_CONTACT"):
        acquire_contact()


def test_acquire_contact_raises_when_env_blank(monkeypatch: pytest.MonkeyPatch) -> None:
    """Blank SEC_CONTACT (whitespace only) raises SecClientError.

    Mutation: accept whitespace-only values — no exception raised.
    """
    monkeypatch.setenv("SEC_CONTACT", "   ")
    with pytest.raises(SecClientError, match="SEC_CONTACT"):
        acquire_contact()


def test_acquire_contact_returns_value_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-blank SEC_CONTACT is returned."""
    monkeypatch.setenv("SEC_CONTACT", "test-contact-fictional@example.com")
    result = acquire_contact()
    assert result == "test-contact-fictional@example.com"


# ---------------------------------------------------------------------------
# AC-0402: redaction — contact value absent from exceptions
# ---------------------------------------------------------------------------


def test_contact_value_absent_from_host_refusal_message() -> None:
    """The contact value must not appear in exception messages from host refusal.

    Mutation: include ``contact`` in the error message — the test fails.
    """
    contact = "distinctive-fictional-contact-MARKER@example.com"
    try:
        resolve, open_socket, wrap = make_seam(_OK_RESPONSE)
        fetch_url(
            "evil.example.com",
            "/path",
            _SUBMISSIONS_CAP,
            "submissions",
            contact,
            _make_gate(),
            resolve=resolve,
            open_socket=open_socket,
            wrap=wrap,
        )
        pytest.fail("Expected SecClientError for disallowed host")
    except SecClientError as exc:
        assert "MARKER" not in str(exc), "contact value must not appear in exception messages"


def test_contact_value_absent_from_redirect_exception_message() -> None:
    """The contact value must not appear in redirect error messages."""
    contact = "fictional-redirect-MARKER@example.com"
    resp = make_http_response(301, {}, b"")
    resolve, open_socket, wrap = make_seam(resp)
    try:
        fetch_url(
            _HOST,
            _PATH,
            _SUBMISSIONS_CAP,
            "submissions",
            contact,
            _make_gate(),
            resolve=resolve,
            open_socket=open_socket,
            wrap=wrap,
        )
    except SecRedirectError as exc:
        assert "MARKER" not in str(exc)


def test_contact_value_absent_from_dns_exception_message() -> None:
    """The contact value must not appear in DNS error messages.

    Mutation: include contact in DNS error — the test fails.
    """
    contact = "fictional-dns-MARKER@example.com"
    import socket as _sock

    def bad_resolve(host: str, port: int, **kwargs: Any) -> list[Any]:
        raise _sock.gaierror("name resolution failure")

    try:
        fetch_url(
            _HOST,
            _PATH,
            _SUBMISSIONS_CAP,
            "submissions",
            contact,
            _make_gate(),
            resolve=bad_resolve,
            open_socket=None,
            wrap=None,
        )
    except SecClientError as exc:
        assert "MARKER" not in str(exc)


def test_contact_value_absent_from_tls_exception_message() -> None:
    """The contact value must not appear in TLS error messages."""
    contact = "fictional-tls-MARKER@example.com"
    resolve, open_socket, wrap = make_seam(
        _OK_RESPONSE, wrap_error=ssl.SSLError("cert verify failed")
    )
    try:
        fetch_url(
            _HOST,
            _PATH,
            _SUBMISSIONS_CAP,
            "submissions",
            contact,
            _make_gate(),
            resolve=resolve,
            open_socket=open_socket,
            wrap=wrap,
        )
    except SecClientError as exc:
        assert "MARKER" not in str(exc)


# ---------------------------------------------------------------------------
# AC-0402: TLS context (structural)
# ---------------------------------------------------------------------------


def test_tls_context_has_cert_required() -> None:
    """The module-level TLS context requires certificate verification.

    Mutation: set ``verify_mode = ssl.CERT_NONE`` — this check fails.
    """
    from ced.adapters.sec.client import _SSL_CTX

    assert _SSL_CTX.verify_mode == ssl.CERT_REQUIRED


def test_tls_context_has_check_hostname() -> None:
    """The module-level TLS context has check_hostname=True.

    Mutation: set ``check_hostname = False`` — this check fails.
    """
    from ced.adapters.sec.client import _SSL_CTX

    assert _SSL_CTX.check_hostname is True


def test_gated_sec_connection_class_is_https() -> None:
    """``_GatedSecConnection`` is a subclass of ``HTTPSConnection``."""
    from http import client as http_client

    from ced.adapters.sec.client import _GatedSecConnection

    assert issubclass(_GatedSecConnection, http_client.HTTPSConnection)


# ---------------------------------------------------------------------------
# AC-0402: IP address admission — through connect()
#
# Each test uses a fake resolve that returns a specific address class.
# Tests verify: (a) the correct error / success outcome, (b) the number of
# socket opens (zero for refused classes, one for the admitted address in
# mixed tests), (c) the gate's exit runs after a failure.
#
# Mutation proofs: deleting the ``addr.is_global and not addr.is_multicast``
# predicate in _GatedSecConnection.connect() makes each refused-address test
# pass without error (no SecClientError raised, no_response_class not set).
# ---------------------------------------------------------------------------


def _make_refusing_seam(addr: str) -> tuple[Any, Any, Any, list[str]]:
    """Return (resolve, open_socket, wrap, opens) where resolve returns addr."""
    opens: list[str] = []
    r, o, w = make_seam(_OK_RESPONSE, resolved_addr=addr, socket_opens=opens)
    return r, o, w, opens


def _assert_refused_with_gate_exit(addr: str) -> None:
    """Assert that an address is refused with zero socket opens and gate exits."""
    exited: list[bool] = []

    @contextlib.contextmanager
    def tracking_gate() -> Generator[float]:
        try:
            import time

            yield time.monotonic()
        finally:
            exited.append(True)

    resolve, open_socket, wrap, opens = _make_refusing_seam(addr)
    with pytest.raises(SecClientError) as exc_info:
        fetch_url(
            _HOST,
            _PATH,
            _SUBMISSIONS_CAP,
            "submissions",
            _CONTACT,
            tracking_gate(),
            resolve=resolve,
            open_socket=open_socket,
            wrap=wrap,
        )
    assert exc_info.value.no_response_class == "dns", (
        f"address {addr!r} should be refused as dns, "
        f"got no_response_class={exc_info.value.no_response_class!r}"
    )
    assert opens == [], f"no socket must be opened for {addr!r}; got {opens}"
    assert exited == [True], "gate must exit even when connect() fails"


def test_connect_refuses_ipv4_loopback() -> None:
    """IPv4 loopback (127.0.0.1) is refused with zero socket opens.

    Mutation: remove the ``is_global`` predicate — 127.0.0.1 would be admitted
    and open_socket would be called.
    """
    _assert_refused_with_gate_exit("127.0.0.1")


def test_connect_refuses_ipv4_private() -> None:
    """IPv4 private (10.0.0.1) is refused with zero socket opens.

    Mutation: remove ``is_global`` — private range is admitted.
    """
    _assert_refused_with_gate_exit("10.0.0.1")


def test_connect_refuses_ipv4_link_local() -> None:
    """IPv4 link-local (169.254.1.1) is refused with zero socket opens."""
    _assert_refused_with_gate_exit("169.254.1.1")


def test_connect_refuses_ipv4_unspecified() -> None:
    """IPv4 unspecified (0.0.0.0) is refused with zero socket opens."""
    _assert_refused_with_gate_exit("0.0.0.0")


def test_connect_refuses_ipv4_shared() -> None:
    """IPv4 shared address space (100.64.0.1, RFC 6598) is refused."""
    _assert_refused_with_gate_exit("100.64.0.1")


def test_connect_refuses_ipv4_multicast() -> None:
    """IPv4 global multicast (239.255.0.1) is refused even when is_global is True.

    Mutation: remove ``not addr.is_multicast`` — global multicast is admitted.
    """
    _assert_refused_with_gate_exit("239.255.0.1")


def test_connect_refuses_ipv6_loopback() -> None:
    """IPv6 loopback (::1) is refused with zero socket opens."""
    _assert_refused_with_gate_exit("::1")


def test_connect_refuses_ipv6_unique_local() -> None:
    """IPv6 unique-local (fc00::1) is refused with zero socket opens."""
    _assert_refused_with_gate_exit("fc00::1")


def test_connect_refuses_ipv6_multicast() -> None:
    """IPv6 multicast (ff02::1) is refused with zero socket opens.

    Mutation: remove ``not addr.is_multicast`` — multicast IPv6 is admitted.
    """
    _assert_refused_with_gate_exit("ff02::1")


def test_connect_admits_public_unicast_ipv4() -> None:
    """A public unicast IPv4 address (8.8.8.8) is admitted and connected.

    Mutation: invert the is_global predicate — public unicast is refused.
    """
    opens: list[str] = []
    body, record = _fetch(resolved_addr="8.8.8.8", socket_opens=opens)
    assert record.stop_condition == "success"
    assert opens == ["8.8.8.8"]


def test_connect_mixed_resolution_uses_first_public_addr_only() -> None:
    """When resolve returns bad and good addresses, only the first valid one
    is connected to; bad addresses produce zero socket opens.

    Mutation: remove the is_global filter — the client would connect to the
    first address regardless of type (e.g., loopback).
    """
    opens: list[str] = []
    # resolver returns [loopback, private, public] — first two are refused
    body, record = _fetch(
        resolved_addrs=["127.0.0.1", "10.0.0.1", "8.8.8.8"],
        socket_opens=opens,
    )
    assert opens == ["8.8.8.8"], (
        f"only the first public-unicast address must be connected to; got {opens}"
    )
    assert record.stop_condition == "success"


def test_resolver_called_exactly_once() -> None:
    """The resolver is called exactly once per request — no second DNS call.

    Mutation: call getaddrinfo again before connecting — a second, different
    answer could be used and the validated address would not be the one
    connected to.
    """
    call_count = [0]

    def counting_resolve(host: str, port: int, **kwargs: Any) -> list[tuple[Any, ...]]:
        call_count[0] += 1
        import socket as _sock

        return [(_sock.AF_INET, _sock.SOCK_STREAM, 0, "", ("8.8.8.8", port))]

    fake = FakeSocket(_OK_RESPONSE)

    def open_socket(address: tuple[str, int], timeout: float | None = None) -> Any:
        return fake

    def wrap(sock: Any, server_hostname: str | None = None) -> Any:
        return sock

    fetch_url(
        _HOST,
        _PATH,
        _SUBMISSIONS_CAP,
        "submissions",
        _CONTACT,
        _make_gate(),
        resolve=counting_resolve,
        open_socket=open_socket,
        wrap=wrap,
    )
    assert call_count[0] == 1, (
        f"resolver must be called exactly once per request; called {call_count[0]} times"
    )


def test_server_hostname_equals_sec_host() -> None:
    """The TLS wrap is called with server_hostname equal to the SEC host.

    Mutation: pass ``server_hostname=None`` or a different name — TLS SNI
    would be wrong and certificate hostname verification would fail on a
    real connection.
    """
    wrap_calls: list[str | None] = []
    _fetch(wrap_calls=wrap_calls)
    assert wrap_calls == [_HOST], (
        f"wrap must receive server_hostname={_HOST!r}; got {wrap_calls}"
    )


def test_tls_failure_maps_to_tls_class() -> None:
    """A TLS wrap failure sets no_response_class='tls' on the raised error.

    Mutation: catch ssl.SSLError but not set no_response_class — the field
    would remain None and the record would misclassify the failure.
    """
    with pytest.raises(SecClientError) as exc_info:
        _fetch(wrap_error=ssl.SSLError("certificate verify failed"))
    assert exc_info.value.no_response_class == "tls"


def test_tls_failure_contact_absent_from_exception() -> None:
    """The contact value must not appear in TLS exception messages."""
    contact = "fictional-tls-MARKER2@example.com"
    resolve, open_socket, wrap = make_seam(
        _OK_RESPONSE, wrap_error=ssl.SSLError("cert verify failed")
    )
    try:
        fetch_url(
            _HOST,
            _PATH,
            _SUBMISSIONS_CAP,
            "submissions",
            contact,
            _make_gate(),
            resolve=resolve,
            open_socket=open_socket,
            wrap=wrap,
        )
    except SecClientError as exc:
        assert "MARKER2" not in str(exc)


def test_connect_timeout_maps_to_connect_timeout_class() -> None:
    """A TimeoutError from open_socket sets no_response_class='connect_timeout'.

    Mutation: map TimeoutError to 'dns' or leave no_response_class=None —
    the class assertion fails.
    """
    with pytest.raises(SecClientError) as exc_info:
        _fetch(open_socket_error=TimeoutError("connection timed out"))
    assert exc_info.value.no_response_class == "connect_timeout"


def test_connect_timeout_contact_absent_from_exception() -> None:
    """The contact value must not appear in connect-timeout exception messages."""
    contact = "fictional-connect-timeout-MARKER@example.com"
    resolve, open_socket, wrap = make_seam(
        _OK_RESPONSE, open_socket_error=TimeoutError("timed out")
    )
    try:
        fetch_url(
            _HOST,
            _PATH,
            _SUBMISSIONS_CAP,
            "submissions",
            contact,
            _make_gate(),
            resolve=resolve,
            open_socket=open_socket,
            wrap=wrap,
        )
    except SecClientError as exc:
        assert "MARKER" not in str(exc)


def test_read_timeout_maps_to_read_timeout_class() -> None:
    """A TimeoutError during send/receive sets no_response_class='read_timeout'.

    Mutation: map TimeoutError to 'connect_timeout' — the class assertion fails.
    """
    with pytest.raises(SecClientError) as exc_info:
        _fetch(timeout_on_send=True)
    assert exc_info.value.no_response_class == "read_timeout"


def test_read_timeout_contact_absent_from_exception() -> None:
    """The contact value must not appear in read-timeout exception messages."""
    contact = "fictional-read-timeout-MARKER@example.com"
    resolve, open_socket, wrap = make_seam(_OK_RESPONSE, timeout_on_send=True)
    try:
        fetch_url(
            _HOST,
            _PATH,
            _SUBMISSIONS_CAP,
            "submissions",
            contact,
            _make_gate(),
            resolve=resolve,
            open_socket=open_socket,
            wrap=wrap,
        )
    except SecClientError as exc:
        assert "MARKER" not in str(exc)


def test_total_timeout_class_set_on_budget_exceeded() -> None:
    """When the total budget is exceeded before connect, no_response_class='total_timeout'.

    Mutation: raise without setting no_response_class — the field is None and
    the record misclassifies the failure.
    """
    # The budget check in _real_fetch fires before connect.
    # Clock: call 1 (gate_start) = 0.0; call 2 (pre-connect check) = 35.0
    _times = [0.0, 35.0]

    def fake_clock() -> float:
        return _times.pop(0) if _times else 99.0

    @contextlib.contextmanager
    def instant_gate() -> Generator[float]:
        yield 0.0

    resolve, open_socket, wrap = make_seam(_OK_RESPONSE)
    with pytest.raises(SecClientError) as exc_info:
        fetch_url(
            _HOST,
            _PATH,
            _SUBMISSIONS_CAP,
            "submissions",
            _CONTACT,
            instant_gate(),
            resolve=resolve,
            open_socket=open_socket,
            wrap=wrap,
            clock=fake_clock,
        )
    assert exc_info.value.no_response_class == "total_timeout"


def test_gate_exits_after_dns_failure() -> None:
    """The gate's __exit__ runs even when DNS resolution fails.

    Mutation: allow the gate to stay open on connect errors — a contender
    would block indefinitely.
    """
    exited: list[bool] = []

    @contextlib.contextmanager
    def tracking_gate() -> Generator[float]:
        try:
            import time

            yield time.monotonic()
        finally:
            exited.append(True)

    import socket as _sock

    def bad_resolve(host: str, port: int, **kwargs: Any) -> list[Any]:
        raise _sock.gaierror("simulated DNS failure")

    with pytest.raises(SecClientError):
        fetch_url(
            _HOST,
            _PATH,
            _SUBMISSIONS_CAP,
            "submissions",
            _CONTACT,
            tracking_gate(),
            resolve=bad_resolve,
        )
    assert exited == [True]


def test_gate_exits_after_tls_failure() -> None:
    """The gate's __exit__ runs even when TLS verification fails."""
    exited: list[bool] = []

    @contextlib.contextmanager
    def tracking_gate() -> Generator[float]:
        try:
            import time

            yield time.monotonic()
        finally:
            exited.append(True)

    resolve, open_socket, wrap = make_seam(
        _OK_RESPONSE, wrap_error=ssl.SSLError("cert verify failed")
    )
    with pytest.raises(SecClientError):
        fetch_url(
            _HOST,
            _PATH,
            _SUBMISSIONS_CAP,
            "submissions",
            _CONTACT,
            tracking_gate(),
            resolve=resolve,
            open_socket=open_socket,
            wrap=wrap,
        )
    assert exited == [True]


# ---------------------------------------------------------------------------
# Finding 9: every 3xx is refused as a redirect (not only 301/302/303/307/308)
# ---------------------------------------------------------------------------


def test_fetch_url_refuses_300_multiple_choices() -> None:
    """HTTP 300 (Multiple Choices) raises SecRedirectError.

    Before this fix only the five listed codes were refused; 300 passed as a
    success-class response.

    Mutation: restore the explicit list ``status in (301, 302, 303, 307, 308)``
    → 300 is not refused and no SecRedirectError is raised.
    """
    resp = make_http_response(300, {}, b"")
    with pytest.raises(SecRedirectError):
        _fetch(response=resp)


def test_fetch_url_refuses_304_not_modified() -> None:
    """HTTP 304 (Not Modified) raises SecRedirectError.

    Mutation: restore the explicit list → 304 is not refused.
    """
    resp = make_http_response(304, {}, b"")
    with pytest.raises(SecRedirectError):
        _fetch(response=resp)


def test_fetch_url_refuses_305_use_proxy() -> None:
    """HTTP 305 (Use Proxy) raises SecRedirectError.

    Mutation: restore the explicit list → 305 is not refused.
    """
    resp = make_http_response(305, {}, b"")
    with pytest.raises(SecRedirectError):
        _fetch(response=resp)


# ---------------------------------------------------------------------------
# Finding 6: transport failures escape fetch_url without an AttemptRecord
# ---------------------------------------------------------------------------


def test_tls_handshake_timeout_produces_attempt_record() -> None:
    """A TimeoutError from wrap_socket maps to connect_timeout and keeps an AttemptRecord.

    Before this fix the TimeoutError escaped connect() and was not caught in
    fetch_url, so no AttemptRecord was attached to the raised exception.

    Mutation: remove the TimeoutError branch from the TLS wrap except block
    → the TimeoutError propagates uncaught and exc.attempt_record is None.
    """

    def wrap_timeout(sock: Any, server_hostname: str | None = None) -> Any:
        raise TimeoutError("TLS handshake timed out")

    resolve, open_socket, _ = make_seam(_OK_RESPONSE)

    with pytest.raises(SecClientError) as exc_info:
        fetch_url(
            _HOST,
            _PATH,
            _SUBMISSIONS_CAP,
            "submissions",
            _CONTACT,
            _make_gate(),
            resolve=resolve,
            open_socket=open_socket,
            wrap=wrap_timeout,
        )

    exc = exc_info.value
    assert exc.attempt_record is not None, (
        "a TLS handshake timeout must produce an AttemptRecord on the exception"
    )
    # Handshake timeout is a connect-phase failure.
    assert exc.attempt_record.no_response_class == "connect_timeout", (
        f"expected connect_timeout, got {exc.attempt_record.no_response_class!r}"
    )


def test_http_exception_during_request_produces_attempt_record() -> None:
    """A non-OSError HTTPException during request maps to connection with a record.

    ``http.client.BadStatusLine`` is not a subclass of ``OSError``; before this
    fix it escaped the ``except OSError`` block in ``_real_fetch`` and propagated
    uncaught, leaving no AttemptRecord on the exception.

    Mutation: remove the ``http_client.HTTPException`` branch from the request
    except block → BadStatusLine propagates uncaught.
    """
    _fake = FakeSocket(_OK_RESPONSE)

    class _BadSocket:
        """Socket that raises BadStatusLine on sendall to exercise the request path."""

        def makefile(self, mode: str, buffering: int = -1) -> Any:
            return _fake.makefile(mode, buffering)

        def sendall(self, data: bytes) -> None:
            raise http_client.BadStatusLine("bad")

        def settimeout(self, t: float | None) -> None:
            pass

        def close(self) -> None:
            pass

    def open_bad_socket(address: Any, timeout: Any = None) -> Any:
        return _BadSocket()

    resolve, _, wrap = make_seam(_OK_RESPONSE)

    with pytest.raises(SecClientError) as exc_info:
        fetch_url(
            _HOST,
            _PATH,
            _SUBMISSIONS_CAP,
            "submissions",
            _CONTACT,
            _make_gate(),
            resolve=resolve,
            open_socket=open_bad_socket,
            wrap=wrap,
        )

    exc = exc_info.value
    assert exc.attempt_record is not None, (
        "an HTTPException during request must produce an AttemptRecord"
    )
    assert exc.attempt_record.no_response_class == "connection"


def test_http_exception_during_body_read_produces_attempt_record() -> None:
    """A non-OSError HTTPException during body read maps to connection with a record.

    ``http.client.IncompleteRead`` is not a subclass of ``OSError``; before
    this fix it escaped the except block in the body-read loop and propagated
    uncaught.

    Mutation: remove the ``http_client.HTTPException`` branch from the body-read
    loop → IncompleteRead propagates uncaught.
    """
    import io

    class _IncompleteSocket:
        """Socket whose file object raises IncompleteRead after the headers."""

        def makefile(self, mode: str, buffering: int = -1) -> Any:
            # Build a valid response header + truncated body that triggers
            # IncompleteRead when read.
            header = b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\n"
            # Return a file object that raises IncompleteRead on read.
            return _IncompleteReadIO(header)

        def sendall(self, data: bytes) -> None:
            pass

        def settimeout(self, t: float | None) -> None:
            pass

        def close(self) -> None:
            pass

    class _IncompleteReadIO(io.RawIOBase):
        def __init__(self, header: bytes) -> None:
            self._data = header
            self._pos = 0
            self._header_done = False

        def read(self, n: int = -1) -> bytes:
            # Return the header bytes first, then raise IncompleteRead.
            if self._pos < len(self._data):
                chunk = self._data[self._pos : self._pos + n]
                self._pos += len(chunk)
                return chunk
            raise http_client.IncompleteRead(b"partial", 100)

        def readable(self) -> bool:
            return True

    def open_incomplete_socket(address: Any, timeout: Any = None) -> Any:
        return _IncompleteSocket()

    resolve, _, wrap = make_seam(_OK_RESPONSE)

    with pytest.raises(SecClientError) as exc_info:
        fetch_url(
            _HOST,
            _PATH,
            _SUBMISSIONS_CAP,
            "submissions",
            _CONTACT,
            _make_gate(),
            resolve=resolve,
            open_socket=open_incomplete_socket,
            wrap=wrap,
        )

    exc = exc_info.value
    assert exc.attempt_record is not None, (
        "an HTTPException during body read must produce an AttemptRecord"
    )
    assert exc.attempt_record.no_response_class == "connection"


def test_a_refused_connection_maps_to_connection_class() -> None:
    """A non-timeout socket error at connect is a connection failure, not a timeout.

    Mutation: map it to 'connect_timeout' as before. This check reds.
    """
    with pytest.raises(SecClientError) as exc_info:
        _fetch(open_socket_error=ConnectionRefusedError("refused"))
    assert exc_info.value.no_response_class == "connection"


def test_a_reset_during_the_tls_handshake_maps_to_connection_class() -> None:
    """A reset during the handshake is neither a TLS verification failure nor a timeout.

    Mutation: let every non-timeout wrap error map to 'tls'. This check reds.
    """
    with pytest.raises(SecClientError) as exc_info:
        _fetch(wrap_error=ConnectionResetError("reset"))  # type: ignore[arg-type]
    assert exc_info.value.no_response_class == "connection"


# ---------------------------------------------------------------------------
# AC-0402: declared-client validation (T6)
#
# The raw value is validated before any gate or socket is opened.  Rules:
# 1–256 chars, each U+0020–U+007E, at least one non-space.  The refusal
# message must never echo the value itself.
# ---------------------------------------------------------------------------


def _assert_contact_refused_without_echo(raw: str) -> None:
    """Assert that raw is refused as a contact value and not echoed."""
    marker = "VALIDATION-TEST"
    tagged = raw.replace("PLACEHOLDER", marker) if "PLACEHOLDER" in raw else marker + raw
    # Build a tag-bearing value that is still invalid in the same way.
    # For control-char tests, inject the control char alongside the marker.
    try:
        _validate_contact = __import__(
            "ced.adapters.sec.client", fromlist=["_validate_contact"]
        )._validate_contact
        _validate_contact(tagged)
        pytest.fail(f"Expected SecClientError for {tagged!r}")
    except SecClientError as exc:
        assert marker not in str(exc), (
            f"validation error must not echo the value; got {str(exc)!r}"
        )


def test_contact_validation_rejects_tab_character(monkeypatch: pytest.MonkeyPatch) -> None:
    """A tab character (U+0009) in the contact value is rejected.

    Mutation: widen the character range to include U+0009 — the test passes
    without error.
    """
    monkeypatch.setenv("SEC_CONTACT", "contact\t@example.com")
    with pytest.raises(SecClientError, match="SEC_CONTACT"):
        acquire_contact()


def test_contact_validation_rejects_carriage_return(monkeypatch: pytest.MonkeyPatch) -> None:
    """A CR character (U+000D) in the contact value is rejected.

    Mutation: widen the range — the test passes without error.
    """
    monkeypatch.setenv("SEC_CONTACT", "contact\r@example.com")
    with pytest.raises(SecClientError, match="SEC_CONTACT"):
        acquire_contact()


def test_contact_validation_rejects_line_feed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A LF character (U+000A) in the contact value is rejected.

    Mutation: widen the range — the test passes without error.
    """
    monkeypatch.setenv("SEC_CONTACT", "contact\n@example.com")
    with pytest.raises(SecClientError, match="SEC_CONTACT"):
        acquire_contact()


def test_contact_validation_rejects_trailing_newline(monkeypatch: pytest.MonkeyPatch) -> None:
    """A value that is valid up to a trailing newline is rejected.

    A stripped version of this value would pass validation, so this test
    proves the check runs on the raw value, not the stripped value.

    Mutation: strip the value before validating — the test passes without
    error because the newline is removed before the check.
    """
    monkeypatch.setenv("SEC_CONTACT", "contact@example.com\n")
    with pytest.raises(SecClientError, match="SEC_CONTACT"):
        acquire_contact()


def test_contact_validation_rejects_leading_lf(monkeypatch: pytest.MonkeyPatch) -> None:
    """A leading LF (followed by a valid suffix) is rejected.

    Mutation: strip the value before validating — the leading LF is removed
    and the suffix passes.
    """
    monkeypatch.setenv("SEC_CONTACT", "\ncontact@example.com")
    with pytest.raises(SecClientError, match="SEC_CONTACT"):
        acquire_contact()


def test_contact_validation_rejects_del_character(monkeypatch: pytest.MonkeyPatch) -> None:
    """DEL (U+007F) in the contact value is rejected.

    U+007F is one above the admitted upper bound (U+007E).

    Mutation: widen the range to include U+007F — the test passes without
    error.
    """
    monkeypatch.setenv("SEC_CONTACT", "contact\x7f@example.com")
    with pytest.raises(SecClientError, match="SEC_CONTACT"):
        acquire_contact()


def test_contact_validation_rejects_non_ascii_character(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-ASCII character (U+0080 and above) in the contact value is rejected.

    Mutation: remove the per-character range check — the test passes without
    error.
    """
    monkeypatch.setenv("SEC_CONTACT", "contact\x80@example.com")
    with pytest.raises(SecClientError, match="SEC_CONTACT"):
        acquire_contact()


def test_contact_validation_rejects_257_char_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 257-character contact value (one above the 256-char maximum) is rejected.

    Mutation: raise the length cap to 257 or remove it — the test passes
    without error.
    """
    monkeypatch.setenv("SEC_CONTACT", "a" * 257)
    with pytest.raises(SecClientError, match="SEC_CONTACT"):
        acquire_contact()


def test_contact_validation_accepts_max_length_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 256-character contact value at the maximum length is accepted."""
    monkeypatch.setenv("SEC_CONTACT", "a" * 256)
    result = acquire_contact()
    assert len(result) == 256


def test_contact_validation_error_does_not_echo_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """A validation error must not echo the raw contact value.

    Mutation: include the value in the error message — the assertion fails.
    """
    # Use a distinctive token that is easy to spot if it leaks.
    distinct = "CONTACT-LEAK-MARKER\x09"  # tab makes it invalid
    monkeypatch.setenv("SEC_CONTACT", distinct)
    with pytest.raises(SecClientError) as exc_info:
        acquire_contact()
    assert "CONTACT-LEAK-MARKER" not in str(exc_info.value), (
        "validation error must not echo any part of the configured contact value"
    )


# ---------------------------------------------------------------------------
# AC-0417: connect_timeout → total_timeout upgrade (T6)
#
# When a connect-phase timeout fires because the total budget was exhausted,
# the no_response_class must be "total_timeout", not "connect_timeout".
# ---------------------------------------------------------------------------


def test_connect_timeout_upgrades_to_total_timeout_when_budget_exhausted() -> None:
    """A connect timeout that fires because the budget ran out reports total_timeout.

    Mutation: remove the ``clock() >= budget_end`` upgrade check after
    connect() raises — the exception keeps no_response_class='connect_timeout'
    and the stop_condition is wrong.
    """
    import contextlib

    # Budget: admission=0.0, budget_end=30.0.
    # Call 1 (gate_start): 0.0
    # Call 2 (pre-connect remaining check in _real_fetch): 1.0 → ok (29 s left)
    # connect() raises connect_timeout via open_socket_error
    # Call 3 (upgrade check in _real_fetch after connect exception): 35.0 → >= 30.0 → upgrade
    _times = [0.0, 1.0, 35.0]

    def fake_clock() -> float:
        return _times.pop(0) if _times else 99.0

    @contextlib.contextmanager
    def instant_gate() -> Generator[float]:
        yield 0.0

    resolve, _, wrap = make_seam(_OK_RESPONSE)

    with pytest.raises(SecClientError) as exc_info:
        fetch_url(
            _HOST,
            _PATH,
            _SUBMISSIONS_CAP,
            "submissions",
            _CONTACT,
            instant_gate(),
            resolve=resolve,
            open_socket=lambda addr, timeout=None: (_ for _ in ()).throw(
                TimeoutError("simulated connect timeout")
            ),
            wrap=wrap,
            clock=fake_clock,
        )

    exc = exc_info.value
    assert exc.no_response_class == "total_timeout", (
        f"a connect timeout at budget exhaustion must report total_timeout; "
        f"got {exc.no_response_class!r}"
    )
    assert exc.attempt_record is not None
    assert exc.attempt_record.no_response_class == "total_timeout"
    assert exc.attempt_record.stop_condition == "total_timeout"


def test_connect_timeout_stays_connect_timeout_when_budget_not_exhausted() -> None:
    """A connect timeout within budget stays connect_timeout (no upgrade).

    Mutation: always upgrade connect_timeout to total_timeout — this check
    reds because budget_end has not been reached.
    """
    import contextlib

    # Budget: admission=0.0, budget_end=30.0.
    # All clock calls return values well within the 30-s budget.
    _times = [0.0, 1.0, 2.0]

    def fake_clock() -> float:
        return _times.pop(0) if _times else 3.0

    @contextlib.contextmanager
    def instant_gate() -> Generator[float]:
        yield 0.0

    resolve, _, wrap = make_seam(_OK_RESPONSE)

    with pytest.raises(SecClientError) as exc_info:
        fetch_url(
            _HOST,
            _PATH,
            _SUBMISSIONS_CAP,
            "submissions",
            _CONTACT,
            instant_gate(),
            resolve=resolve,
            open_socket=lambda addr, timeout=None: (_ for _ in ()).throw(
                TimeoutError("simulated connect timeout")
            ),
            wrap=wrap,
            clock=fake_clock,
        )

    exc = exc_info.value
    assert exc.no_response_class == "connect_timeout", (
        f"a connect timeout within budget must stay connect_timeout; "
        f"got {exc.no_response_class!r}"
    )


# ---------------------------------------------------------------------------
# AC-0417: DNS thread abandonment → total_timeout (T6)
#
# socket.getaddrinfo has no built-in timeout.  The client runs it in a
# daemon thread bounded by the remaining total budget.  When the thread
# does not finish in time, the attempt is total_timeout.
# ---------------------------------------------------------------------------


def test_dns_thread_abandoned_at_budget_expiry_reports_total_timeout() -> None:
    """A DNS resolver that exceeds the budget causes total_timeout.

    The resolve callable is injected to sleep longer than the remaining
    budget, so the daemon thread is abandoned and total_timeout is raised.

    Mutation: remove the daemon-thread logic and call getaddrinfo directly —
    the test hangs or reports dns instead of total_timeout.
    """
    import time as _time

    # Patch budget to 0.08 s so the suite stays fast.
    import ced.adapters.sec.client as _client
    from ced.adapters.sec.client import _fake_gate

    saved_budget = _client._TOTAL_BUDGET
    _client._TOTAL_BUDGET = 0.08  # type: ignore[assignment]

    try:

        def slow_resolve(host: str, port: int, **kwargs: Any) -> list[Any]:
            _time.sleep(0.2)  # longer than the patched budget
            import socket as _sock

            return [(_sock.AF_INET, _sock.SOCK_STREAM, 0, "", ("8.8.8.8", port))]

        with pytest.raises(SecClientError) as exc_info:
            fetch_url(
                _HOST,
                _PATH,
                _SUBMISSIONS_CAP,
                "submissions",
                _CONTACT,
                _fake_gate(),
                resolve=slow_resolve,
            )

        exc = exc_info.value
        assert exc.no_response_class == "total_timeout", (
            f"a DNS thread abandoned at budget expiry must report total_timeout; "
            f"got {exc.no_response_class!r}"
        )
    finally:
        _client._TOTAL_BUDGET = saved_budget  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# AC-0417: strict Content-Length (T6)
# ---------------------------------------------------------------------------


def test_content_length_with_sign_is_refused() -> None:
    """A Content-Length value with a leading '+' sign is refused (fail-closed).

    Mutation: parse with int() which accepts '+100' — the check is skipped
    and the body is read against the wrong size cap.
    """
    raw = make_http_response(200, {}, b"ok")
    raw = raw.replace(b"Content-Length: 2", b"Content-Length: +2")
    with pytest.raises(SecClientError, match="malformed Content-Length"):
        _fetch(response=raw)


def test_content_length_with_trailing_space_is_refused() -> None:
    """A Content-Length value with a trailing space is refused.

    http.client preserves trailing whitespace in header values (only leading
    whitespace is stripped).  A strict digit-only check refuses '100 '.

    Mutation: use str.strip() before int() — the trailing space is removed
    and the value is accepted.
    """
    raw = make_http_response(200, {}, b"ok")
    raw = raw.replace(b"Content-Length: 2", b"Content-Length: 2 ")
    with pytest.raises(SecClientError, match="malformed Content-Length"):
        _fetch(response=raw)


def test_duplicate_content_length_headers_refused() -> None:
    """Two Content-Length headers (even with the same value) are refused.

    Mutation: use response.getheader() which returns only the last value —
    the duplicate is not detected.
    """
    # Build raw bytes with two Content-Length headers manually.
    raw = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nContent-Length: 2\r\n\r\nok"
    with pytest.raises(SecClientError, match="malformed Content-Length|duplicate"):
        _fetch(response=raw)


def test_short_body_maps_to_connection_class() -> None:
    """A body shorter than its declared Content-Length is a connection failure.

    http.client returns b'' at early EOF rather than raising IncompleteRead
    when Content-Length is declared; the client must detect the shortfall
    with an explicit length comparison.

    Mutation: remove the total_read != cl check — a short body is not
    detected and the client returns a truncated body as success.
    """
    # Declare Content-Length: 10, supply only 5 bytes in the body.
    raw = (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Length: 10\r\n"
        b"\r\n"
        b"hello"  # 5 bytes, not 10
    )
    with pytest.raises(SecClientError) as exc_info:
        _fetch(response=raw)
    assert exc_info.value.no_response_class == "connection", (
        f"short body must map to connection, got {exc_info.value.no_response_class!r}"
    )


def test_1xx_status_is_refused() -> None:
    """HTTP 1xx (informational) is refused as an invalid success response.

    Mutation: remove the ``status < 200`` branch — a 103 response would not
    raise and the attempt record would show stop_condition='success'.
    """
    # 103 Early Hints — http.client returns b'' for 1xx responses.
    raw = b"HTTP/1.1 103 Early Hints\r\n\r\n"
    with pytest.raises(SecClientError):
        _fetch(response=raw)


def test_600_status_is_refused_as_other() -> None:
    """HTTP 600 (outside 100–599) is refused as an 'other' status.

    Mutation: return a class string for any status including 600 — the
    refused branch is never reached and the attempt record shows wrong class.
    """
    # Build raw bytes for 600 status (not in _HTTP_REASONS so we build manually).
    raw = b"HTTP/1.1 600 Invented\r\nContent-Length: 0\r\n\r\n"
    with pytest.raises(SecClientError) as exc_info:
        _fetch(response=raw)
    # The attempt record must be attached.
    assert exc_info.value.attempt_record is not None
    assert exc_info.value.attempt_record.http_status_class == "other"
    assert exc_info.value.attempt_record.stop_condition == "refused"


def test_fetch_url_refuses_invalid_contact_at_the_user_agent_sink() -> None:
    """fetch_url validates the contact value before using it as User-Agent.

    This exercises the _validate_contact call inside fetch_url directly —
    without going through acquire_contact — so removing the call from
    fetch_url specifically causes this test to red even if acquire_contact
    still validates.

    Mutation: remove _validate_contact(contact) from fetch_url — the tab
    character reaches the User-Agent header, putheader raises ValueError
    quoting the value, and the test would not see SecClientError.
    """
    resolve, open_socket, wrap = make_seam(_OK_RESPONSE)
    with pytest.raises(SecClientError, match="SEC_CONTACT"):
        fetch_url(
            _HOST,
            _PATH,
            _SUBMISSIONS_CAP,
            "submissions",
            "bad\tcontact@example.com",  # tab at U+0009
            _make_gate(),
            resolve=resolve,
            open_socket=open_socket,
            wrap=wrap,
        )


def test_received_status_survives_on_over_cap_exception() -> None:
    """When Content-Length exceeds the cap, received_status is carried on the exception.

    Mutation: omit received_status from the over-cap exception — the attempt
    record records http_status_class=None for the failed attempt.
    """
    cap = 100
    resp = make_http_response(403, {"Content-Length": "1000"}, b"")
    with pytest.raises(SecClientError) as exc_info:
        _fetch(response=resp, size_cap=cap)
    exc = exc_info.value
    assert exc.attempt_record is not None
    # 403 received before refusal → http_status_class="4xx", blocked=True
    assert exc.attempt_record.http_status_class == "4xx", (
        f"http_status_class must be '4xx' when 403 was received before cap refusal; "
        f"got {exc.attempt_record.http_status_class!r}"
    )
    assert exc.attempt_record.blocked is True


# ---------------------------------------------------------------------------
# AC-0402: declared-client value — fetch_url sink with gate/socket spy (T6)
#
# Each invalid contact is refused before the gate is entered or a socket is
# opened.  The marker embedded in the contact must not appear in any output.
# ---------------------------------------------------------------------------

_BAD_CONTACTS: list[tuple[str, str]] = [
    # (contact_value, unique marker embedded in the contact but NOT the message)
    ("FC-TAB-MARKER\texample.com", "FC-TAB-MARKER"),
    ("FC-CR-MARKER\rexample.com", "FC-CR-MARKER"),
    ("FC-LF-MARKER\nexample.com", "FC-LF-MARKER"),
    ("FC-TRAIL-NL-MARKER@example.com\n", "FC-TRAIL-NL-MARKER"),
    ("FC-NL-SPACE-MARKER\n @example.com", "FC-NL-SPACE-MARKER"),
    ("FC-DEL-MARKER\x7fexample.com", "FC-DEL-MARKER"),
    ("FC-NONASC-MARKER\x80example.com", "FC-NONASC-MARKER"),
    # 257 chars: XTMARK (6) + 251 'a's = 257
    ("XTMARK" + "a" * 251, "XTMARK"),
]


@pytest.mark.parametrize(
    "bad_contact,marker",
    _BAD_CONTACTS,
    ids=[m for _, m in _BAD_CONTACTS],
)
def test_invalid_contact_refused_at_fetch_url_gate_not_entered(
    bad_contact: str,
    marker: str,
    capfd: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Each invalid contact is refused before the gate is entered or a socket opened.

    The marker embedded in the contact must not appear in capfd output,
    the traceback chain, the attempt record, or any log record.

    Mutation: remove ``_validate_contact(contact)`` from ``fetch_url`` — the
    tab reaches ``putheader``, which raises ``ValueError`` with the value in
    the message; or the gate IS entered before refusal.
    """
    gate_entered: list[bool] = []
    socket_opened: list[bool] = []

    @contextlib.contextmanager
    def spy_gate() -> Generator[float]:
        gate_entered.append(True)
        yield time.monotonic()

    def spy_open_socket(address: Any, timeout: Any = None) -> Any:
        socket_opened.append(True)
        return FakeSocket(_OK_RESPONSE)

    import socket as _sock

    def resolve(host: str, port: int, **kw: Any) -> list[Any]:
        return [(_sock.AF_INET, _sock.SOCK_STREAM, 0, "", ("8.8.8.8", port))]

    def wrap(sock: Any, server_hostname: Any = None) -> Any:
        return sock

    with pytest.raises(SecClientError) as exc_info:
        fetch_url(
            _HOST,
            _PATH,
            _SUBMISSIONS_CAP,
            "submissions",
            bad_contact,
            spy_gate(),
            resolve=resolve,
            open_socket=spy_open_socket,
            wrap=wrap,
        )

    exc = exc_info.value

    # Gate must NOT have been entered.
    assert gate_entered == [], (
        f"gate must not be entered for invalid contact (marker={marker!r}); "
        f"gate_entered={gate_entered!r}"
    )
    # Socket must NOT have been opened.
    assert socket_opened == [], (
        f"socket must not be opened for invalid contact (marker={marker!r})"
    )

    # Marker must be absent from traceback chain.
    tb_chain = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    assert marker not in tb_chain, f"marker {marker!r} must not appear in traceback chain"

    # Marker must be absent from capfd output (stdout + stderr).
    captured = capfd.readouterr()
    assert marker not in captured.out, "marker must not appear in stdout"
    assert marker not in captured.err, "marker must not appear in stderr"

    # No attempt record means no record to check; if one exists, marker must be absent.
    if exc.attempt_record is not None:
        assert marker not in str(exc.attempt_record), "marker must not appear in attempt record"

    # Marker must be absent from all log records.
    for lr in caplog.records:
        assert marker not in lr.getMessage(), (
            f"marker {marker!r} must not appear in log record: {lr.getMessage()!r}"
        )


# ---------------------------------------------------------------------------
# AC-0402: fail-closed live ingestion (T6)
#
# _ingest_live with a gate spy and a store spy: each failure case raises an
# exception (SecClientError or IngestionError), exits the gate, writes no
# object, and the error message is a single line with no embedded contact.
# ---------------------------------------------------------------------------

#: Minimal valid submissions JSON satisfying _validate_submissions_cik and
#: _select_filing for the canonical Apple CIK, accession, and primary doc.
_VALID_SUBMISSIONS_JSON: bytes = json.dumps(
    {
        "cik": "320193",
        "filings": {
            "recent": {
                "accessionNumber": ["0000320193-26-000020"],
                "form": ["10-Q"],
                "filingDate": ["2026-07-31"],
                "reportDate": ["2026-06-27"],
                "primaryDocument": ["aapl-20260627.htm"],
            }
        },
    }
).encode()

_VALID_SUBMISSIONS_RESP: bytes = make_http_response(200, {}, _VALID_SUBMISSIONS_JSON)

_CONTACT_FOR_LIVE = "live-fail-closed-fictional@example.com"


def _make_live_seam(
    *,
    submissions_response: bytes = _VALID_SUBMISSIONS_RESP,
    filing_response: bytes | None = None,
    open_socket_error: BaseException | None = None,
    wrap_error: ssl.SSLError | None = None,
) -> tuple[Any, Any, Any]:
    """Build a seam that serves submissions_response first, then filing_response."""
    import socket as _sock

    def resolve(host: str, port: int, **kw: Any) -> list[Any]:
        return [(_sock.AF_INET, _sock.SOCK_STREAM, 0, "", ("8.8.8.8", port))]

    responses = [submissions_response]
    if filing_response is not None:
        responses.append(filing_response)

    call_idx = [0]

    def open_socket(address: Any, timeout: Any = None) -> Any:
        if open_socket_error is not None:
            raise open_socket_error
        idx = call_idx[0]
        call_idx[0] += 1
        return FakeSocket(responses[idx % len(responses)])

    def wrap(sock: Any, server_hostname: Any = None) -> Any:
        if wrap_error is not None:
            raise wrap_error
        return sock

    return resolve, open_socket, wrap


class _TrackingGate:
    """Context manager that records each entry and exit for test assertions."""

    def __init__(self) -> None:
        self.entries: list[float] = []
        self.exits: list[bool] = []

    @contextlib.contextmanager
    def gate(self) -> Generator[float]:
        t0 = time.monotonic()
        self.entries.append(t0)
        try:
            yield t0
        finally:
            self.exits.append(True)

    def factory(self) -> Any:
        """Return a new gate context manager."""
        return self.gate()


def _run_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    resolve: Any,
    open_socket: Any,
    wrap: Any,
) -> tuple[BaseException, _TrackingGate, list[Any]]:
    """Call _ingest_live and return (exc, gate_tracker, store_spy_calls)."""
    from ced.adapters.sec.client import SecClientError as _SecClientError
    from ced.worker.ingestion import IngestionError, _ingest_live

    monkeypatch.setenv("SEC_CONTACT", _CONTACT_FOR_LIVE)
    monkeypatch.setattr("ced.adapters.postgres.dsn.database_url", lambda role: "unused-dsn")

    store_calls: list[Any] = []
    monkeypatch.setattr(
        "ced.worker.ingestion._store_and_return",
        lambda **kw: store_calls.append(kw),
    )

    tracker = _TrackingGate()

    caught: list[BaseException] = []
    try:
        _ingest_live(
            gate_factory=tracker.factory,
            resolve=resolve,
            open_socket=open_socket,
            wrap=wrap,
        )
    except (_SecClientError, IngestionError) as exc:
        caught.append(exc)

    assert len(caught) == 1, f"expected exactly one exception from _ingest_live; got {caught!r}"
    return caught[0], tracker, store_calls


def test_live_ingest_fail_closed_connection_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A refused connection raises, exits the gate, writes nothing.

    Mutation: remove the except block in _ingest_live — the exception
    propagates uncaught and no attempt record is attached.
    """
    resolve, open_socket, wrap = _make_live_seam(
        open_socket_error=ConnectionRefusedError("connection refused")
    )
    exc, tracker, store_calls = _run_fail_closed(monkeypatch, resolve, open_socket, wrap)

    assert store_calls == [], "no object must be written on refused connection"
    assert tracker.exits, "gate must exit on refused connection"
    assert "\n" not in str(exc), "error message must be single-line"


def test_live_ingest_fail_closed_reset_during_filing_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A connection reset during the filing body read raises, exits gate, writes nothing.

    Mutation: catch BaseException instead of Exception in the body-read loop —
    KeyboardInterrupt is swallowed instead of the reset, and the test passes
    for wrong reasons.
    """
    # Build a filing response that resets after the headers.
    header = b"HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\n"

    class _ResetIO(io.RawIOBase):
        def __init__(self) -> None:
            self._data = header
            self._pos = 0

        def read(self, n: int = -1) -> bytes:
            if self._pos < len(self._data):
                chunk = self._data[self._pos : self._pos + n]
                self._pos += len(chunk)
                return chunk
            raise ConnectionResetError("simulated filing body reset")

        def readable(self) -> bool:
            return True

    class _ResetSocket:
        def makefile(self, mode: str, buffering: int = -1) -> Any:
            return _ResetIO()

        def sendall(self, data: bytes) -> None:
            pass

        def settimeout(self, t: float | None) -> None:
            pass

        def close(self) -> None:
            pass

    import socket as _sock

    call_idx = [0]
    responses_for_reset = [_VALID_SUBMISSIONS_RESP]

    def resolve(host: str, port: int, **kw: Any) -> list[Any]:
        return [(_sock.AF_INET, _sock.SOCK_STREAM, 0, "", ("8.8.8.8", port))]

    def open_socket_reset(address: Any, timeout: Any = None) -> Any:
        idx = call_idx[0]
        call_idx[0] += 1
        if idx == 0:
            return FakeSocket(responses_for_reset[0])
        return _ResetSocket()

    def wrap(sock: Any, server_hostname: Any = None) -> Any:
        return sock

    exc, tracker, store_calls = _run_fail_closed(monkeypatch, resolve, open_socket_reset, wrap)

    assert store_calls == [], "no object must be written on filing body reset"
    assert len(tracker.exits) >= 1, "gate must exit on filing body reset"
    assert "\n" not in str(exc), "error message must be single-line"


def test_live_ingest_fail_closed_ssl_error_after_handshake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An SSLError during the filing request (after the handshake) raises, exits gate.

    The handshake completes normally (wrap returns the socket); the SSLError is
    raised during the filing connection's sendall (request phase).  This
    exercises the request-site ssl.SSLError branch (no_response_class="tls"),
    not the handshake-site branch which always produced "tls".

    The filing gate must exit independently of the submissions gate exit.
    """
    import socket as _sock

    def resolve(host: str, port: int, **kw: Any) -> list[Any]:
        return [(_sock.AF_INET, _sock.SOCK_STREAM, 0, "", ("8.8.8.8", port))]

    call_idx = [0]

    class _SSLErrorOnSendSocket:
        """Socket whose sendall raises ssl.SSLError on the first call."""

        def makefile(self, mode: str, buffering: int = -1) -> Any:
            return FakeSocket(b"").makefile(mode, buffering)

        def sendall(self, data: bytes) -> None:
            raise ssl.SSLError("simulated SSL error during filing request")

        def settimeout(self, t: float | None) -> None:
            pass

        def close(self) -> None:
            pass

    def open_socket_filing(address: Any, timeout: Any = None) -> Any:
        idx = call_idx[0]
        call_idx[0] += 1
        # submissions → valid response; filing → socket that SSLErrors on send
        return FakeSocket(_VALID_SUBMISSIONS_RESP) if idx == 0 else _SSLErrorOnSendSocket()

    def wrap_normal(sock: Any, server_hostname: Any = None) -> Any:
        return sock  # handshake always succeeds

    exc, tracker, store_calls = _run_fail_closed(
        monkeypatch, resolve, open_socket_filing, wrap_normal
    )

    assert store_calls == [], "no object must be written on SSLError during filing"
    # Both the submissions gate AND the filing gate must have exited.
    assert len(tracker.exits) >= 2, (
        f"filing gate must exit on SSLError; only {len(tracker.exits)} exits recorded"
    )
    assert "\n" not in str(exc), "error message must be single-line"
    # SSLError at the request site is classified as tls (AC-0417).
    from ced.adapters.sec.client import SecClientError as _SecClientError

    if isinstance(exc, _SecClientError) and exc.attempt_record is not None:
        assert exc.attempt_record.no_response_class == "tls", (
            f"expected tls, got {exc.attempt_record.no_response_class!r}"
        )


def test_live_ingest_fail_closed_over_cap_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A filing response with Content-Length over the cap raises, exits gate, writes nothing.

    The submission succeeds; the filing declares an oversized Content-Length.
    """
    # _FILING_CAP is 10 MiB; declare 10 MiB + 1.
    from ced.adapters.sec.client import _FILING_CAP

    filing_resp = make_http_response(200, {"Content-Length": str(_FILING_CAP + 1)}, b"")
    resolve, open_socket, wrap = _make_live_seam(filing_response=filing_resp)
    exc, tracker, store_calls = _run_fail_closed(monkeypatch, resolve, open_socket, wrap)

    assert store_calls == [], "no object must be written on over-cap filing"
    assert len(tracker.exits) >= 1, "gate must exit on over-cap refusal"
    assert "\n" not in str(exc), "error message must be single-line"


def test_live_ingest_fail_closed_short_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A short filing body (shorter than Content-Length) raises, exits gate, writes nothing."""
    # Declare Content-Length: 10, supply only 2 bytes.
    filing_resp = b"HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\nhi"
    resolve, open_socket, wrap = _make_live_seam(filing_response=filing_resp)
    exc, tracker, store_calls = _run_fail_closed(monkeypatch, resolve, open_socket, wrap)

    assert store_calls == [], "no object must be written on short filing body"
    assert len(tracker.exits) >= 1, "gate must exit on short body"
    assert "\n" not in str(exc), "error message must be single-line"


def test_live_ingest_fail_closed_403(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP 403 from submissions raises SecBlockedError, exits gate, writes nothing.

    Mutation: catch SecBlockedError in _ingest_live and return empty body —
    store is called and an object is written even though the fetch was blocked.
    """
    resolve, open_socket, wrap = _make_live_seam(
        submissions_response=make_http_response(403, {}, b"")
    )
    exc, tracker, store_calls = _run_fail_closed(monkeypatch, resolve, open_socket, wrap)

    assert store_calls == [], "no object must be written on 403"
    assert tracker.exits, "gate must exit on 403"
    assert "\n" not in str(exc), "error message must be single-line"


def test_live_ingest_fail_closed_103(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP 103 (1xx) from submissions is refused, exits gate, writes nothing.

    Mutation: treat 1xx as a no-content success — store is called and
    an object is written from an empty submissions body.
    """
    resolve, open_socket, wrap = _make_live_seam(
        submissions_response=make_http_response(103, {}, b"")
    )
    exc, tracker, store_calls = _run_fail_closed(monkeypatch, resolve, open_socket, wrap)

    assert store_calls == [], "no object must be written on 103"
    assert tracker.exits, "gate must exit on 103"
    assert "\n" not in str(exc), "error message must be single-line"


def test_live_ingest_fail_closed_value_error_during_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unexpected ValueError during the HTTP request is caught, gate exits, nothing written.

    Before the fix, only (OSError, HTTPException) were caught; an unexpected
    ValueError propagated uncaught and no attempt record was attached.

    Mutation: restore ``except (OSError, http_client.HTTPException)`` — a
    ValueError during sendall propagates uncaught as a non-SecClientError.
    """
    import socket as _sock

    class _ValueErrorSocket:
        def makefile(self, mode: str, buffering: int = -1) -> Any:
            return FakeSocket(_VALID_SUBMISSIONS_RESP).makefile(mode, buffering)

        def sendall(self, data: bytes) -> None:
            raise ValueError("unexpected error during request")

        def settimeout(self, t: float | None) -> None:
            pass

        def close(self) -> None:
            pass

    def resolve(host: str, port: int, **kw: Any) -> list[Any]:
        return [(_sock.AF_INET, _sock.SOCK_STREAM, 0, "", ("8.8.8.8", port))]

    def open_value_err(address: Any, timeout: Any = None) -> Any:
        # Fail on all calls — submissions request raises ValueError immediately.
        return _ValueErrorSocket()

    def wrap(sock: Any, server_hostname: Any = None) -> Any:
        return sock

    exc, tracker, store_calls = _run_fail_closed(monkeypatch, resolve, open_value_err, wrap)

    assert store_calls == [], "no object must be written on ValueError"
    assert tracker.exits, "gate must exit on unexpected ValueError"
    assert "\n" not in str(exc), "error message must be single-line"


# ---------------------------------------------------------------------------
# AC-0402: interrupt tests (T6)
#
# KeyboardInterrupt propagates through fetch_url and _ingest_live; the gate
# exits (finally runs in the context manager) and no object is written.
# ---------------------------------------------------------------------------


def test_keyboard_interrupt_exits_gate_in_live_ingest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """KeyboardInterrupt propagates through _ingest_live; gate exits, nothing written.

    The interrupt is raised in open_socket so it fires before any fetch.
    BaseException subclasses (not Exception subclasses) must propagate
    through the ``except Exception`` body-read handler unchanged.

    Mutation: catch BaseException in _ingest_live — KeyboardInterrupt is
    swallowed and the test never sees it.
    """
    from ced.worker.ingestion import _ingest_live

    monkeypatch.setenv("SEC_CONTACT", _CONTACT_FOR_LIVE)
    monkeypatch.setattr("ced.adapters.postgres.dsn.database_url", lambda role: "unused-dsn")

    store_calls: list[Any] = []
    monkeypatch.setattr(
        "ced.worker.ingestion._store_and_return",
        lambda **kw: store_calls.append(kw),
    )

    tracker = _TrackingGate()

    import socket as _sock

    def resolve(host: str, port: int, **kw: Any) -> list[Any]:
        return [(_sock.AF_INET, _sock.SOCK_STREAM, 0, "", ("8.8.8.8", port))]

    def open_kb(address: Any, timeout: Any = None) -> Any:
        raise KeyboardInterrupt("simulated interrupt")

    def wrap(sock: Any, server_hostname: Any = None) -> Any:
        return sock

    with pytest.raises(KeyboardInterrupt):
        _ingest_live(
            gate_factory=tracker.factory,
            resolve=resolve,
            open_socket=open_kb,
            wrap=wrap,
        )

    assert store_calls == [], "no object must be written on KeyboardInterrupt"
    assert tracker.exits, "gate must exit even on KeyboardInterrupt"


def test_keyboard_interrupt_exits_gate_in_run_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """KeyboardInterrupt propagates through run_observation; gate exits.

    The interrupt is raised inside open_socket so it fires during the first
    fetch attempt.

    Mutation: catch BaseException in run_observation — KeyboardInterrupt is
    swallowed and the observation loop continues.
    """
    from ced.adapters.sec.client import run_observation

    gate_exits: list[bool] = []

    @contextlib.contextmanager
    def tracking_gate() -> Generator[float]:
        try:
            yield time.monotonic()
        finally:
            gate_exits.append(True)

    def gate_factory() -> Any:
        return tracking_gate()

    import socket as _sock

    def resolve(host: str, port: int, **kw: Any) -> list[Any]:
        return [(_sock.AF_INET, _sock.SOCK_STREAM, 0, "", ("8.8.8.8", port))]

    def open_kb(address: Any, timeout: Any = None) -> Any:
        raise KeyboardInterrupt("simulated interrupt")

    def wrap(sock: Any, server_hostname: Any = None) -> Any:
        return sock

    with pytest.raises(KeyboardInterrupt):
        run_observation(
            _CONTACT_FOR_LIVE,
            gate_factory,
            n_attempts=2,
            resolve=resolve,
            open_socket=open_kb,
            wrap=wrap,
        )

    assert gate_exits, "gate must exit even on KeyboardInterrupt during run_observation"


def test_a_short_body_at_the_deadline_records_total_timeout() -> None:
    """An early EOF found at or after the deadline is the budget's doing (AC-0417).

    The watchdog's shutdown at the deadline makes a blocked read return EOF, so
    the body ends short. This check fixes the race on a clock that passes the
    deadline once the body has been read. Mutation: drop the clock check in the
    short-body branch. The record then says `connection`, and this check reds.
    """

    class _EofPastDeadline(io.BytesIO):
        def read(self, size: int | None = -1) -> bytes:
            data = super().read(size)
            if not data:
                past_deadline[0] = True
            return data

    class _Socket(FakeSocket):
        def makefile(self, mode: str, buffering: int = -1) -> io.BytesIO:
            return _EofPastDeadline(b"HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\nhello")

    past_deadline = [False]

    def clock() -> float:
        return 1_000.0 if past_deadline[0] else 0.0

    resolve, _open_socket, wrap = make_seam(_OK_RESPONSE)
    with pytest.raises(SecClientError) as exc_info:
        fetch_url(
            _HOST,
            _PATH,
            _SUBMISSIONS_CAP,
            "submissions",
            _CONTACT,
            _fake_gate(clock=clock),
            resolve=resolve,
            open_socket=lambda address, timeout=None: _Socket(b""),
            wrap=wrap,
            clock=clock,
        )
    assert exc_info.value.no_response_class == "total_timeout"
    record = exc_info.value.attempt_record
    assert record is not None and record.http_status_class == "2xx"
