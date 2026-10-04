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
import ssl
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
