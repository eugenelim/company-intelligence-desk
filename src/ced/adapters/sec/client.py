"""Bounded, rate-gated SEC EDGAR HTTP client.

Design constraints (AC-0402, AC-0403, AC-0417):

- HTTPS only, to the two admitted hosts (``data.sec.gov``, ``www.sec.gov``).
- TLS certificate verification is always on; ``check_hostname=True``,
  ``CERT_REQUIRED``; no parameter disables it.
- DNS resolution uses ``socket.getaddrinfo`` run in a daemon thread; the
  thread is abandoned when the total budget expires (``total_timeout``).  Only
  public unicast non-multicast addresses are admitted.  Connection uses
  ``socket.create_connection`` to one validated address with the SEC hostname
  retained for TLS (``wrap_socket(server_hostname=host)``).  All three socket
  operations are injectable for tests; the single production code path always
  runs.
- Connect timeout: 5 s, clamped to remaining total budget.  Read timeout:
  15 s, clamped to remaining total budget per chunk.  Total budget: 30 s from
  gate admission through the end of the bounded body read; refused as
  ``total_timeout`` when remaining budget reaches zero before any operation.
  A phase timeout that fires because the budget was shortened is also
  reported as ``total_timeout`` (AC-0417: total_timeout wins).
- Response size caps: 5 MiB for submissions, 10 MiB for filings.  A declared
  ``Content-Length`` above the cap refuses before reading; a malformed
  ``Content-Length`` is refused (fail-closed) before reading; a duplicate
  ``Content-Length`` header is refused; a stream first crossing the cap is
  stopped and refused.  A body shorter than its declared length is a
  transport failure (``connection``).
- No automatic retry.  ``403`` / ``429`` are recorded as ``blocked``.
- The runtime declared-client value (``SEC_CONTACT``) must be 1–256 printable
  ASCII characters (U+0020–U+007E), with at least one non-space.  It is
  validated on the raw value before any trimming, before the gate is entered
  or a socket is opened.  It must never appear in exceptions, logs, records,
  stdout / stderr, or stored objects.
- Every SEC request passes through the shared Postgres rate gate, which
  acquires a session-level advisory lock, records the admission time, and
  holds the lock for at least ``_GATE_INTERVAL`` seconds after admission.
- ``status_class`` (``http_status_class``) is the class of any HTTP status
  received: ``"1xx"``–``"5xx"``, or ``"other"`` for any status outside
  100–599.  ``no_response_class`` is set for any transport failure: one of
  ``"dns"``, ``"tls"``, ``"connect_timeout"``, ``"read_timeout"``,
  ``"total_timeout"``, or ``"connection"``.  Every attempt carries at least
  one of the two.  ``blocked`` is true when a received status is 403 or 429,
  whatever ends the attempt.  Stop condition follows AC-0417's fixed order.

Injection seam for tests: ``_GatedSecConnection`` accepts optional ``resolve``,
``open_socket``, and ``wrap`` callables that replace ``socket.getaddrinfo``,
``socket.create_connection``, and ``ssl.SSLContext.wrap_socket`` respectively.
Tests inject fake callables; the live code passes ``None`` and the real
platform functions are used.  The single production code path (``_real_fetch`` /
``_GatedSecConnection``) therefore runs in every test.

The gate is injectable too: callers pass a context manager obtained from
``open_postgres_gate`` (real) or ``_fake_gate`` (tests).  This avoids a database
dependency in offline unit tests.

``no_response_class`` on ``SecClientError``: every failure that produces no HTTP
response carries a string class (``"dns"``, ``"tls"``, ``"connect_timeout"``,
``"read_timeout"``, ``"total_timeout"``, ``"connection"``).  The ``AttemptRecord``
field of the same name is populated from this attribute in the catch block of
``fetch_url``.

``received_status`` on ``SecClientError``: when the status line has been parsed
before the failure, this carries the HTTP status integer so the catch block in
``fetch_url`` can record ``http_status_class`` and ``blocked`` correctly.
"""

from __future__ import annotations

import contextlib
import dataclasses
import ipaddress
import logging
import os
import socket
import ssl
import threading
import time
from collections.abc import Callable, Generator
from http import client as http_client
from typing import Any

_log = logging.getLogger(__name__)

__all__ = [
    "SEC_CONTACT_ENV",
    "AttemptRecord",
    "SecBlockedError",
    "SecClientError",
    "SecRedirectError",
    "acquire_contact",
    "fetch_filing",
    "fetch_submissions",
    "open_postgres_gate",
    "run_observation",
]

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

#: Environment variable holding the runtime declared-client value (User-Agent).
#: Read-only on first use; never stored, logged, or included in records.
SEC_CONTACT_ENV: str = "SEC_CONTACT"

# ---------------------------------------------------------------------------
# Private constants
# ---------------------------------------------------------------------------

#: The two admitted SEC hostnames.
_ALLOWED_HOSTS: frozenset[str] = frozenset({"data.sec.gov", "www.sec.gov"})

#: Response-size caps.
_SUBMISSIONS_CAP: int = 5 * 1024 * 1024  # 5 MiB
_FILING_CAP: int = 10 * 1024 * 1024  # 10 MiB

#: Socket-level timeouts (clamped to remaining budget at call time).
_CONNECT_TIMEOUT: float = 5.0
_READ_TIMEOUT: float = 15.0

#: Total per-request budget, measured from gate admission.
_TOTAL_BUDGET: float = 30.0

#: Minimum interval between admitted request starts (AC-0403).
_GATE_INTERVAL: float = 0.125

#: Fixed Postgres advisory lock key.  Must be a signed 64-bit integer.
#: Chosen to be unique and stable; not a credential.
_GATE_LOCK_KEY: int = 6_842_130_421_987_654_321

# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


class SecClientError(Exception):
    """A non-HTTP failure: DNS, TLS, timeout, size cap, or configuration.

    Network-level failures set ``no_response_class`` to one of:
    ``"dns"``, ``"tls"``, ``"connect_timeout"``, ``"read_timeout"``,
    ``"total_timeout"``, or ``"connection"`` for a refused, reset or garbled
    connection.  HTTP-level failures and configuration errors
    leave it ``None``.

    When the HTTP status line was received before the failure,
    ``received_status`` carries the integer status code so the caller can
    record ``http_status_class`` and ``blocked`` even for a failed attempt.
    """

    def __init__(
        self,
        msg: str,
        *,
        no_response_class: str | None = None,
        received_status: int | None = None,
    ) -> None:
        super().__init__(msg)
        self.no_response_class: str | None = no_response_class
        self.received_status: int | None = received_status
        #: The attempt as ``fetch_url`` recorded it, so a caller keeps the real
        #: gate wait and stop condition of a failed attempt.
        self.attempt_record: AttemptRecord | None = None


class SecRedirectError(SecClientError):
    """The server returned a redirect; this client follows none."""


class SecBlockedError(SecClientError):
    """HTTP 403 or 429: the declared client was blocked or rate-limited."""


# ---------------------------------------------------------------------------
# Attempt record
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class AttemptRecord:
    """Redacted metadata for one SEC fetch attempt.

    Fields that could identify the caller (``User-Agent``, full URL, headers)
    are deliberately absent. ``request_class`` names the operation class
    ("submissions" or "filing") rather than the URL.
    """

    request_class: str
    """One of "submissions" or "filing"."""

    gate_wait_seconds: float
    """Seconds spent waiting for the shared rate gate."""

    duration_seconds: float
    """Seconds from gate admission to completion or failure."""

    retry_count: int
    """Always 0 — this client never retries."""

    stop_condition: str
    """AC-0417 stop condition: "success", "blocked", "redirect", "refused",
    "http_4xx", "http_5xx", or a no-response class string."""

    http_status_class: str | None
    """"1xx" to "5xx", "other", or ``None`` when no HTTP response was received."""

    no_response_class: str | None
    """One of "dns", "tls", "connect_timeout", "read_timeout", "total_timeout",
    "connection", or ``None`` when an HTTP response was received."""

    blocked: bool
    """True when HTTP 403 or 429 was received, whatever ends the attempt."""

    def to_dict(self) -> dict[str, object]:
        """Canonical serialisation for JSON records."""
        return {
            "request_class": self.request_class,
            "gate_wait_seconds": self.gate_wait_seconds,
            "duration_seconds": self.duration_seconds,
            "retry_count": self.retry_count,
            "stop_condition": self.stop_condition,
            "http_status_class": self.http_status_class,
            "no_response_class": self.no_response_class,
            "blocked": self.blocked,
        }


# ---------------------------------------------------------------------------
# Injectable callable type aliases
# ---------------------------------------------------------------------------

#: Resolver: same signature as socket.getaddrinfo (subset used here).
_ResolveFn = Callable[..., list[tuple[Any, ...]]]

#: Socket factory: same signature as socket.create_connection (subset).
_OpenSocketFn = Callable[..., Any]

#: TLS wrap: same signature as ssl.SSLContext.wrap_socket (subset).
_WrapFn = Callable[..., Any]

#: Monotonic clock callable.
_ClockFn = Callable[[], float]

# ---------------------------------------------------------------------------
# TLS context (one per process — ssl.create_default_context() is thread-safe)
# ---------------------------------------------------------------------------


def _tls_context() -> ssl.SSLContext:
    """Return a default TLS context with certificate verification always on."""
    ctx = ssl.create_default_context()
    # These are the defaults; stated explicitly so a future reader cannot
    # remove them without this comment explaining why they exist.
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx


_SSL_CTX: ssl.SSLContext = _tls_context()

# ---------------------------------------------------------------------------
# Custom HTTPSConnection subclass — overrides connect() to pin one validated
# public-unicast address while retaining the SEC hostname for TLS.
# ---------------------------------------------------------------------------


class _GatedSecConnection(http_client.HTTPSConnection):
    """HTTPSConnection that resolves once (in a thread) and connects to one
    validated public-unicast address.

    ``connect()`` is overridden so there is no second DNS resolution while the
    socket is being created.  The original hostname is retained for TLS
    certificate verification (``wrap(sock, server_hostname=host)``).

    DNS resolution runs in a daemon thread so it can be abandoned when the
    total budget expires.  Callers set ``_dns_timeout`` before calling
    ``connect()`` to bound the wait.

    The three injectable callables replace the real platform operations in
    tests so the production code path runs without a live network:

    - ``resolve`` — replaces ``socket.getaddrinfo``; returns a list of
      ``(family, type, proto, canonname, sockaddr)`` tuples.
    - ``open_socket`` — replaces ``socket.create_connection``; accepts
      ``(address, timeout=...)`` and returns a socket-like object.
    - ``wrap`` — replaces ``ssl.SSLContext.wrap_socket``; accepts
      ``(sock, server_hostname=...)`` and returns a socket-like object.
    """

    def __init__(
        self,
        host: str,
        *,
        resolve: _ResolveFn | None = None,
        open_socket: _OpenSocketFn | None = None,
        wrap: _WrapFn | None = None,
    ) -> None:
        # Pass context so the base class records it; our connect() does not
        # call super().connect(), but the attribute is used by close().
        super().__init__(host, 443, context=_SSL_CTX)
        self._sec_host = host  # preserved for TLS, separate from self.host
        self._validated_addr: str | None = None
        self._resolve: _ResolveFn = resolve if resolve is not None else socket.getaddrinfo
        self._open_socket: _OpenSocketFn = (
            open_socket if open_socket is not None else socket.create_connection
        )
        self._wrap: _WrapFn = wrap if wrap is not None else _SSL_CTX.wrap_socket
        #: DNS timeout in seconds; set by _real_fetch before calling connect().
        #: None means no timeout (should not occur in production).
        self._dns_timeout: float | None = None
        #: Budget deadline (monotonic); set by _real_fetch so connect() can
        #: recompute the connect timeout after DNS returns and can classify
        #: failures that arrive at or after the deadline as total_timeout.
        self._budget_end: float | None = None
        #: The watchdog's wall-clock deadline. The handshake timeout is clamped to
        #: it, because wrapping detaches the raw socket from the watchdog's reach.
        self._wall_deadline: float | None = None
        #: Injected clock function; mirrors the one used in _real_fetch.
        self._clock: _ClockFn | None = None

    def connect(self) -> None:
        """Resolve (in a thread), validate, and connect to one public-unicast address.

        DNS resolution runs in a daemon thread bounded by ``self._dns_timeout``.
        A thread that does not finish in time causes a ``total_timeout`` error;
        the thread may continue running after abandonment and its result is
        discarded.

        Uses ``self.timeout`` for the connect-level deadline so callers can
        clamp it to the remaining total budget before calling this method.
        """
        # --- DNS resolution in a daemon thread ---
        _results: list[list[tuple[Any, ...]]] = []
        _error: list[Exception] = []

        def _resolve_thread() -> None:
            try:
                _results.append(self._resolve(self._sec_host, 443, type=socket.SOCK_STREAM))
            except socket.gaierror as exc:
                _error.append(exc)
            except Exception as exc:  # noqa: BLE001
                _error.append(exc)

        t = threading.Thread(target=_resolve_thread, daemon=True)
        t.start()
        t.join(timeout=self._dns_timeout)

        if t.is_alive():
            raise SecClientError(
                "DNS resolution did not complete within the total budget",
                no_response_class="total_timeout",
            )

        if _error:
            exc = _error[0]
            if isinstance(exc, socket.gaierror):
                raise SecClientError(
                    "DNS resolution failed",
                    no_response_class="dns",
                ) from exc
            raise SecClientError(
                "DNS resolution error",
                no_response_class="dns",
            ) from exc

        results = _results[0] if _results else []

        # --- Address filtering: public unicast only ---
        valid: list[str] = []
        for _af, _socktype, _proto, _canonname, sockaddr in results:
            # sockaddr is (host_str, port) for IPv4;
            # (host_str, port, flow, scope) for IPv6.
            addr_str = str(sockaddr[0])
            try:
                addr = ipaddress.ip_address(addr_str)
            except ValueError:
                continue
            if addr.is_global and not addr.is_multicast:
                valid.append(addr_str)

        if not valid:
            raise SecClientError(
                "no public unicast address resolved for the SEC host; "
                "all resolved addresses failed the is_global / not is_multicast check",
                no_response_class="dns",
            )

        chosen = valid[0]
        self._validated_addr = chosen

        # Recompute connect timeout after DNS returned: DNS may have consumed
        # a significant portion of the budget, so the connect phase must use
        # whatever remains rather than the full pre-DNS remainder (AC-0402).
        if self._budget_end is not None and self._clock is not None:
            _post_dns_remaining = self._budget_end - self._clock()
            if _post_dns_remaining <= 0:
                raise SecClientError(
                    "DNS resolution consumed the entire budget",
                    no_response_class="total_timeout",
                )
            _cur = self.timeout if self.timeout is not None else _CONNECT_TIMEOUT
            self.timeout = min(_cur, _post_dns_remaining)

        try:
            raw_sock = self._open_socket((chosen, 443), timeout=self.timeout)
        except TimeoutError as exc:
            raise SecClientError(
                "connect timeout",
                no_response_class="connect_timeout",
            ) from exc
        except OSError as exc:
            raise SecClientError(
                "connect failed",
                no_response_class="connection",
            ) from exc
        except Exception as exc:  # noqa: BLE001 — any unexpected Exception → connection
            raise SecClientError(
                "unexpected error during connect",
                no_response_class="connection",
            ) from exc

        # The handshake must also end by the deadline (AC-0402 hard bound). The
        # watchdog cannot reach it: wrapping detaches the raw socket's
        # descriptor, so shutting the raw object down does nothing. Give the
        # handshake only the wall-clock time the watchdog has left instead.
        if self._wall_deadline is not None:
            _handshake_left = self._wall_deadline - time.monotonic()
            if _handshake_left <= 0:
                try:
                    raw_sock.close()
                except Exception:  # noqa: BLE001
                    pass
                raise SecClientError(
                    "the connect consumed the entire budget",
                    no_response_class="total_timeout",
                )
            try:
                raw_sock.settimeout(min(_CONNECT_TIMEOUT, _handshake_left))
            except OSError:
                try:
                    raw_sock.close()
                except Exception:  # noqa: BLE001
                    pass
                if time.monotonic() >= self._wall_deadline:
                    raise SecClientError(
                        "settimeout failed after budget exhausted",
                        no_response_class="total_timeout",
                    ) from None
                raise SecClientError(
                    "settimeout failed",
                    no_response_class="connection",
                ) from None

        # Retain the original SEC hostname for TLS certificate verification.
        try:
            self.sock = self._wrap(raw_sock, server_hostname=self._sec_host)
        except (ssl.SSLError, TimeoutError, OSError) as exc:
            try:
                raw_sock.close()
            except Exception:  # noqa: BLE001
                pass
            # A handshake timeout is a connect timeout, an ssl.SSLError is a
            # TLS failure, and any other socket error is a dropped connection.
            if isinstance(exc, TimeoutError):
                raise SecClientError(
                    "TLS handshake timeout",
                    no_response_class="connect_timeout",
                ) from exc
            if not isinstance(exc, ssl.SSLError):
                raise SecClientError(
                    "connection failed during TLS handshake",
                    no_response_class="connection",
                ) from exc
            raise SecClientError(
                "TLS verification failed",
                no_response_class="tls",
            ) from exc
        except Exception as exc:  # noqa: BLE001 — any unexpected Exception → connection
            try:
                raw_sock.close()
            except Exception:  # noqa: BLE001
                pass
            raise SecClientError(
                "unexpected error during TLS handshake",
                no_response_class="connection",
            ) from exc

    def set_read_timeout(self, seconds: float) -> None:
        """Set the socket read timeout after connect() has run."""
        if self.sock is not None:
            self.sock.settimeout(seconds)


# ---------------------------------------------------------------------------
# Rate gate
# ---------------------------------------------------------------------------

#: Context manager yielding the gate admission time (monotonic).
_GateCtx = contextlib.AbstractContextManager[float]


@contextlib.contextmanager
def open_postgres_gate(dsn: str) -> Generator[float]:
    """Acquire the shared Postgres session-level advisory lock and yield the
    admission time.

    The lock is held until at least ``_GATE_INTERVAL`` seconds after admission,
    then released. Session-level advisory locks are automatically released when
    the connection closes (crash-safe from the contender's perspective).

    Uses a **dedicated** connection so the gate connection's lifetime is the
    lock's lifetime and a normal application connection cannot accidentally
    hold or release the lock.
    """
    import psycopg

    with psycopg.connect(dsn) as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", [_GATE_LOCK_KEY])
        conn.commit()
        t0 = time.monotonic()
        try:
            yield t0
        finally:
            elapsed = time.monotonic() - t0
            remaining = _GATE_INTERVAL - elapsed
            if remaining > 0:
                time.sleep(remaining)
            try:
                conn.execute("SELECT pg_advisory_unlock(%s)", [_GATE_LOCK_KEY])
                conn.commit()
            except psycopg.Error:
                # Connection loss already releases the advisory lock (AC-0403).
                # Swallow so the original outcome reaches the caller; log at
                # warning without the error value to avoid leaking session state.
                _log.warning(
                    "open_postgres_gate: release failed; lock released by connection close"
                )


@contextlib.contextmanager
def _fake_gate(
    clock: _ClockFn | None = None,
) -> Generator[float]:
    """Offline gate for tests: no Postgres, returns admission time immediately."""
    t0 = (clock or time.monotonic)()
    yield t0


# ---------------------------------------------------------------------------
# Contact value validation
# ---------------------------------------------------------------------------


def _validate_contact(contact: str) -> None:
    """Validate the declared-client value before it becomes the User-Agent header.

    Rules (AC-0402): 1 to 256 characters, each in U+0020–U+007E (printable
    ASCII, no control characters), with at least one character that is not a
    space (U+0020).

    Raises ``SecClientError`` naming the environment variable without echoing
    the value itself.  The check runs on the raw value before any trimming.
    """
    if not (1 <= len(contact) <= 256):
        raise SecClientError(f"{SEC_CONTACT_ENV} value must be 1 to 256 characters")
    for ch in contact:
        if not ("\x20" <= ch <= "\x7e"):
            raise SecClientError(
                f"{SEC_CONTACT_ENV} value contains a character outside "
                f"U+0020 to U+007E; each character must be a printable ASCII byte"
            )
    if all(ch == "\x20" for ch in contact):
        raise SecClientError(
            f"{SEC_CONTACT_ENV} value must contain at least one non-space character"
        )


def acquire_contact() -> str:
    """Read the runtime declared-client value from the environment.

    Raises ``SecClientError`` naming the variable when it is absent or when the
    raw value fails the AC-0402 character and length rules.  The returned value
    is used only as the ``User-Agent`` header and must never be copied into an
    exception message, log record, stored object, or output.

    The check runs on the raw (unstripped) value, as required by AC-0402.
    """
    raw = os.environ.get(SEC_CONTACT_ENV)
    if raw is None:
        raise SecClientError(
            f"{SEC_CONTACT_ENV} is unset; set it to the declared "
            f"User-Agent string required by SEC developer policy before "
            f"making any live request"
        )
    _validate_contact(raw)
    return raw


# ---------------------------------------------------------------------------
# HTTP status class helper
# ---------------------------------------------------------------------------


def _http_status_class(status: int) -> str:
    """Return the AC-0417 status class for an HTTP status code.

    Returns ``"1xx"``–``"5xx"`` for statuses 100–599, and ``"other"`` for any
    status outside that range.
    """
    if 100 <= status <= 599:
        return f"{status // 100}xx"
    return "other"


# ---------------------------------------------------------------------------
# Core fetch implementation
# ---------------------------------------------------------------------------


def fetch_url(
    host: str,
    path: str,
    size_cap: int,
    request_class: str,
    contact: str,
    gate: _GateCtx,
    *,
    resolve: _ResolveFn | None = None,
    open_socket: _OpenSocketFn | None = None,
    wrap: _WrapFn | None = None,
    clock: _ClockFn | None = None,
) -> tuple[bytes, AttemptRecord]:
    """Fetch one SEC URL through the shared gate, return body and attempt record.

    Parameters
    ----------
    host:
        One of the admitted SEC hostnames.
    path:
        The path component of the URL.
    size_cap:
        Maximum body size in bytes.
    request_class:
        ``"submissions"`` or ``"filing"`` — recorded in the attempt record.
    contact:
        The runtime declared-client value, used only as the ``User-Agent``
        header.  Validated on the raw value before the gate is entered.
        Must not appear in any exception, log, or record.
    gate:
        A context manager (open or fake) that yields the admission time.
    resolve:
        Optional injectable resolver (replaces ``socket.getaddrinfo``).
    open_socket:
        Optional injectable socket factory (replaces
        ``socket.create_connection``).
    wrap:
        Optional injectable TLS wrap (replaces ``ssl.SSLContext.wrap_socket``).
    clock:
        Optional monotonic clock callable, injectable for tests.
    """
    _clock = clock or time.monotonic

    if host not in _ALLOWED_HOSTS:
        raise SecClientError(
            f"host {host!r} is not in the admitted set; "
            f"only {sorted(_ALLOWED_HOSTS)} are permitted"
        )

    # Validate the declared-client value on the raw value, before the gate
    # is entered or any socket is opened (AC-0402).
    _validate_contact(contact)

    headers: dict[str, str] = {
        "User-Agent": contact,
        "Accept": "application/json, text/html, */*",
        "Host": host,
    }

    gate_start = _clock()
    with gate as admission_time:
        gate_wait = admission_time - gate_start

        # Total budget starts at gate admission.
        budget_start = admission_time

        no_response_class: str | None = None
        http_status_class: str | None = None
        stop_condition: str = "success"
        blocked = False

        try:
            status, resp_headers, body = _real_fetch(
                host,
                path,
                headers,
                size_cap,
                budget_start,
                _clock,
                resolve,
                open_socket,
                wrap,
            )

            # Set http_status_class and blocked immediately from the received
            # status, before any check that might raise.
            cls = _http_status_class(status)
            http_status_class = cls
            if status in (403, 429):
                blocked = True

            # Final budget gate after _real_fetch returns (covers the gap
            # between the last chunk read and here; _real_fetch already
            # enforces the budget internally).
            if _clock() - budget_start > _TOTAL_BUDGET:
                raise SecClientError(
                    "total budget exceeded",
                    no_response_class="total_timeout",
                )

            # AC-0417 stop condition order (for statuses from _real_fetch):
            # 1. no-response class — N/A here (_real_fetch returned normally)
            # 2. blocked (403 or 429)
            # 3. redirect (3xx)
            # 4. refused (length/cap, size) — N/A here (_real_fetch returned)
            # 5. http_4xx or http_5xx
            # 6. refused (1xx or other)
            # 7. success (2xx only)
            if 300 <= status <= 399:
                stop_condition = "redirect"
                raise SecRedirectError(
                    f"server returned HTTP {status} (redirect); this client follows no redirect"
                )
            if blocked:
                stop_condition = "blocked"
                raise SecBlockedError(
                    "SEC returned HTTP status indicating the declared client is blocked"
                )
            if 400 <= status <= 599:
                stop_condition = f"http_{cls}"
                raise SecClientError(f"SEC returned HTTP {status}")
            if status < 200 or status > 599:
                # 1xx and status outside 100–599 ("other") are refused.
                stop_condition = "refused"
                raise SecClientError(
                    f"SEC returned HTTP {status}; 1xx and status outside 100–599 are refused"
                )

            # Only 2xx reaches here.
            duration = _clock() - budget_start
            record = AttemptRecord(
                request_class=request_class,
                gate_wait_seconds=gate_wait,
                duration_seconds=duration,
                retry_count=0,
                stop_condition=stop_condition,
                http_status_class=http_status_class,
                no_response_class=None,
                blocked=blocked,
            )
            return body, record

        except SecClientError as exc:
            # Carry received_status from _real_fetch exceptions so
            # http_status_class and blocked survive transport failures.
            _recv = exc.received_status
            if _recv is not None and http_status_class is None:
                http_status_class = _http_status_class(_recv)
            if _recv is not None and _recv in (403, 429):
                blocked = True

            # For network-level failures, carry the no_response_class through
            # to the record.  SecRedirectError and SecBlockedError are HTTP-
            # level failures and leave no_response_class as None.
            if not isinstance(exc, (SecRedirectError, SecBlockedError)):
                _nrc = exc.no_response_class
                no_response_class = _nrc

            # Determine stop_condition using AC-0417 order if not already set.
            if stop_condition == "success":
                if no_response_class is not None:
                    # Step 1: transport failure.
                    stop_condition = no_response_class
                elif blocked:
                    # Step 2: blocked (403/429 received), no transport failure.
                    stop_condition = "blocked"
                elif _recv is not None and 300 <= _recv <= 399:
                    # Step 3: redirect (from _real_fetch size/length refusal on
                    # a 3xx response — unusual but handled).
                    stop_condition = "redirect"
                else:
                    # Step 4/6: length/cap refusal or 1xx/other.
                    stop_condition = "refused"

            duration = _clock() - budget_start
            record = AttemptRecord(
                request_class=request_class,
                gate_wait_seconds=gate_wait,
                duration_seconds=duration,
                retry_count=0,
                stop_condition=stop_condition,
                http_status_class=http_status_class,
                no_response_class=no_response_class,
                blocked=blocked,
            )
            exc.attempt_record = record
            raise


def _real_fetch(
    host: str,
    path: str,
    headers: dict[str, str],
    size_cap: int,
    budget_start: float,
    clock: _ClockFn,
    resolve: _ResolveFn | None,
    open_socket: _OpenSocketFn | None,
    wrap: _WrapFn | None,
) -> tuple[int, dict[str, str], bytes]:
    """Execute the HTTPS request using the injectable connection class.

    All budget enforcement, timeout clamping, size-cap checks, and strict
    Content-Length parsing live here so there is exactly one production fetch
    path.

    When an exception is raised after the HTTP status line has been parsed,
    ``exc.received_status`` carries the integer status so the caller can record
    the status class and ``blocked`` flag even for a failed attempt.
    """
    budget_end = budget_start + _TOTAL_BUDGET

    conn = _GatedSecConnection(host, resolve=resolve, open_socket=open_socket, wrap=wrap)
    # Pass budget deadline and clock to connect() so it can recompute the
    # connect timeout after DNS returns and classify deadline failures.
    conn._budget_end = budget_end
    conn._clock = clock

    # Watchdog: shut the TLS socket at the budget deadline to unblock any
    # in-flight recv/send (AC-0402 hard wall-clock bound).  The handshake is
    # not reachable from here — wrapping detaches the raw socket's descriptor,
    # so shutting the raw object down does nothing — so a clamp before the
    # wrap bounds it instead.  Cancelled in finally regardless of outcome.
    def _watchdog() -> None:
        # Closing a socket from another thread does not interrupt a blocked
        # recv; shutting it down does, on every platform this runs on.
        sock = conn.sock
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except (OSError, AttributeError):
                # Already closed, or a socket-like object with no shutdown.
                pass

    _wt: threading.Timer | None = None
    try:
        # Check budget before connect; clamp connect timeout to remaining.
        remaining = budget_end - clock()
        if remaining <= 0:
            raise SecClientError(
                "total budget exceeded before connect",
                no_response_class="total_timeout",
            )
        conn.timeout = min(_CONNECT_TIMEOUT, remaining)
        # Pass remaining budget as DNS timeout for the threaded resolver.
        conn._dns_timeout = remaining

        # Arm the watchdog after computing the initial remaining budget.
        conn._wall_deadline = time.monotonic() + remaining
        _wt = threading.Timer(remaining, _watchdog)
        _wt.daemon = True
        _wt.start()

        # connect() converts DNS/TLS/OS errors to SecClientError with
        # no_response_class already set; propagate, upgrading phase timeouts
        # to total_timeout when the budget was exhausted.
        try:
            conn.connect()
        except SecClientError as exc:
            # total_timeout wins over a connect-phase timeout or a connection
            # failure when the deadline was reached (AC-0417).
            if exc.no_response_class in ("connect_timeout", "connection") and (
                clock() >= budget_end
            ):
                raise SecClientError(
                    "total budget exceeded during connect phase",
                    no_response_class="total_timeout",
                ) from exc
            raise

        # Check budget before issuing the request; clamp read timeout.
        remaining = budget_end - clock()
        if remaining <= 0:
            raise SecClientError(
                "total budget exceeded before request",
                no_response_class="total_timeout",
            )
        conn.set_read_timeout(min(_READ_TIMEOUT, remaining))

        # The HTTP status received before any body failure; None until parsed.
        _received_status: int | None = None

        try:
            conn.request("GET", path, headers=headers)
            response = conn.getresponse()
        except TimeoutError as exc:
            nrc = "total_timeout" if clock() >= budget_end else "read_timeout"
            raise SecClientError("timeout during request", no_response_class=nrc) from exc
        except ssl.SSLError as exc:
            # ssl.SSLError is a subclass of OSError; classify as tls per AC-0417.
            raise SecClientError(
                "SSL error during request",
                no_response_class="tls",
            ) from exc
        except Exception as exc:  # noqa: BLE001 — any unexpected Exception → connection
            # Only Exception subclasses become connection; KeyboardInterrupt /
            # SystemExit (BaseException, not Exception) propagate past this catch.
            # When the deadline has been reached (e.g. watchdog fired), upgrade
            # to total_timeout (AC-0417 precedence).
            nrc = "total_timeout" if clock() >= budget_end else "connection"
            raise SecClientError(
                "request failed",
                no_response_class=nrc,
            ) from exc

        _received_status = response.status
        all_headers = response.getheaders()
        resp_headers: dict[str, str] = {k.lower(): v for k, v in all_headers}

        # --- Strict Content-Length check (AC-0417 "well-formed length") ---
        # A response without Content-Length is read under the stream cap.
        # A response with one must carry exactly one header whose value is
        # ASCII digits alone; otherwise its length is malformed (refused).
        all_cl_values = [v for k, v in all_headers if k.lower() == "content-length"]
        if len(all_cl_values) > 1:
            sec_exc = SecClientError(
                "malformed Content-Length: duplicate headers; refusing before read"
            )
            sec_exc.received_status = _received_status
            raise sec_exc

        cl: int | None = None
        if all_cl_values:
            cl_str = all_cl_values[0]
            # ASCII digits only: no sign, no whitespace, no non-ASCII digit.
            if not cl_str or not cl_str.isascii() or not cl_str.isdigit():
                sec_exc = SecClientError(
                    "malformed Content-Length header; refusing before read"
                )
                sec_exc.received_status = _received_status
                raise sec_exc
            cl = int(cl_str)
            if cl > size_cap:
                sec_exc = SecClientError(
                    f"declared Content-Length {cl} exceeds size cap {size_cap}"
                )
                sec_exc.received_status = _received_status
                raise sec_exc

        # --- Read with size cap and per-chunk budget enforcement ---
        chunks: list[bytes] = []
        total_read = 0
        while True:
            remaining = budget_end - clock()
            if remaining <= 0:
                sec_exc = SecClientError(
                    "total budget exceeded during read",
                    no_response_class="total_timeout",
                )
                sec_exc.received_status = _received_status
                raise sec_exc
            if conn.sock is not None:
                conn.sock.settimeout(min(_READ_TIMEOUT, remaining))
            try:
                chunk = response.read(65536)
            except TimeoutError as exc:
                nrc = "total_timeout" if clock() >= budget_end else "read_timeout"
                sec_exc = SecClientError("timeout during body read", no_response_class=nrc)
                sec_exc.received_status = _received_status
                raise sec_exc from exc
            except ssl.SSLError as exc:
                # ssl.SSLError is a subclass of OSError; classify as tls per AC-0417.
                sec_exc = SecClientError(
                    "SSL error during body read",
                    no_response_class="tls",
                )
                sec_exc.received_status = _received_status
                raise sec_exc from exc
            except Exception as exc:  # noqa: BLE001 — any unexpected Exception → connection
                # Only Exception subclasses become connection; KeyboardInterrupt /
                # SystemExit (BaseException, not Exception) propagate past this catch.
                # When the deadline has been reached (e.g. watchdog fired), upgrade
                # to total_timeout (AC-0417 precedence).
                nrc = "total_timeout" if clock() >= budget_end else "connection"
                sec_exc = SecClientError(
                    "read error during body",
                    no_response_class=nrc,
                )
                sec_exc.received_status = _received_status
                raise sec_exc from exc
            if not chunk:
                break
            total_read += len(chunk)
            if total_read > size_cap:
                sec_exc = SecClientError(
                    f"response body exceeded size cap {size_cap} during read"
                )
                sec_exc.received_status = _received_status
                raise sec_exc
            chunks.append(chunk)

        # --- Short body detection (AC-0417 "connection") ---
        # http.client returns b"" at early EOF of a fixed-length body, so an
        # explicit comparison is required (AC-0402 contract fact).
        if cl is not None and total_read != cl:
            # The watchdog's shutdown at the deadline also ends the read early,
            # so a short body at or past the deadline is the budget's doing.
            sec_exc = SecClientError(
                "response body shorter than declared Content-Length",
                no_response_class="total_timeout" if clock() >= budget_end else "connection",
            )
            sec_exc.received_status = _received_status
            raise sec_exc

        body = b"".join(chunks)
        assert _received_status is not None  # set by response.status above
        return _received_status, resp_headers, body

    finally:
        if _wt is not None:
            _wt.cancel()
        conn.close()


# ---------------------------------------------------------------------------
# Convenience wrappers used by ingestion
# ---------------------------------------------------------------------------


def fetch_submissions(
    cik_padded: str,
    contact: str,
    gate: _GateCtx,
    *,
    resolve: _ResolveFn | None = None,
    open_socket: _OpenSocketFn | None = None,
    wrap: _WrapFn | None = None,
    clock: _ClockFn | None = None,
) -> tuple[bytes, AttemptRecord]:
    """Fetch the SEC submissions JSON for ``cik_padded``."""
    host = "data.sec.gov"
    path = f"/submissions/CIK{cik_padded}.json"
    return fetch_url(
        host,
        path,
        _SUBMISSIONS_CAP,
        "submissions",
        contact,
        gate,
        resolve=resolve,
        open_socket=open_socket,
        wrap=wrap,
        clock=clock,
    )


def fetch_filing(
    archive_url: str,
    contact: str,
    gate: _GateCtx,
    *,
    resolve: _ResolveFn | None = None,
    open_socket: _OpenSocketFn | None = None,
    wrap: _WrapFn | None = None,
    clock: _ClockFn | None = None,
) -> tuple[bytes, AttemptRecord]:
    """Fetch a filing document from the SEC archives."""
    prefix = "https://www.sec.gov"
    if not archive_url.startswith(prefix):
        raise SecClientError(f"archive URL must start with {prefix!r}; got {archive_url!r}")
    path = archive_url[len(prefix) :]
    host = "www.sec.gov"
    return fetch_url(
        host,
        path,
        _FILING_CAP,
        "filing",
        contact,
        gate,
        resolve=resolve,
        open_socket=open_socket,
        wrap=wrap,
        clock=clock,
    )


# ---------------------------------------------------------------------------
# Observation mode (AC-0417)
# ---------------------------------------------------------------------------

#: The submissions URL is used for the observation (natural choice: small,
#: fast, representative of real API traffic).
_OBSERVATION_REQUEST_CLASS = "submissions"

#: The observation uses the submissions endpoint for CIK 0000320193.
_OBSERVATION_HOST = "data.sec.gov"
_OBSERVATION_PATH = "/submissions/CIK0000320193.json"


def run_observation(
    contact: str,
    gate_factory: Callable[[], _GateCtx],
    *,
    n_attempts: int = 60,
    interval_seconds: float = 1.0,
    resolve: _ResolveFn | None = None,
    open_socket: _OpenSocketFn | None = None,
    wrap: _WrapFn | None = None,
    clock: _ClockFn | None = None,
) -> dict[str, Any]:
    """Run the bounded SEC observation and return the result record.

    Schedules ``n_attempts`` request starts at ``interval_seconds`` apart.
    Fails (raises ``SecClientError``) when the started count is not
    ``n_attempts`` or when any observed start interval is below 1 second.

    A ``403`` / ``429`` sets ``blocked=True`` and is a valid observed outcome
    rather than a failure. No retry is ever performed.

    Returns the record dict (caller writes it as JSON).
    """
    _clock = clock or time.monotonic

    attempts: list[dict[str, object]] = []
    start_times: list[float] = []
    outcome_counts: dict[str, int] = {}
    any_blocked = False
    t_schedule_start = _clock()

    for i in range(n_attempts):
        # Start on the schedule, but never sooner than one interval after the
        # previous start: a slow response delays the rest rather than letting
        # the next start catch up early.
        scheduled_at = t_schedule_start + i * interval_seconds
        if start_times:
            scheduled_at = max(scheduled_at, start_times[-1] + interval_seconds)
        now = _clock()
        wait = scheduled_at - now
        if wait > 0:
            time.sleep(wait)

        start_times.append(_clock())
        gate = gate_factory()
        try:
            _body, record = fetch_url(
                _OBSERVATION_HOST,
                _OBSERVATION_PATH,
                _SUBMISSIONS_CAP,
                _OBSERVATION_REQUEST_CLASS,
                contact,
                gate,
                resolve=resolve,
                open_socket=open_socket,
                wrap=wrap,
                clock=_clock,
            )
            stop = record.stop_condition
        except SecClientError as exc:
            # A failed attempt is an observed outcome, blocked or not. Keep the
            # record fetch_url made, with its real gate wait; an error raised
            # before any attempt was recorded is a configuration fault.
            if exc.attempt_record is None:
                raise
            record = exc.attempt_record
            stop = record.stop_condition
            any_blocked = any_blocked or record.blocked

        outcome_counts[stop] = outcome_counts.get(stop, 0) + 1
        attempts.append(record.to_dict())

    started = len(start_times)

    # Compute minimum observed start interval.
    min_interval: float | None = None
    if len(start_times) >= 2:
        intervals = [start_times[j] - start_times[j - 1] for j in range(1, len(start_times))]
        min_interval = min(intervals)

    first_to_last = start_times[-1] - start_times[0] if len(start_times) >= 2 else 0.0

    # Validate: started must equal n_attempts.
    if started != n_attempts:
        raise SecClientError(f"observation started {started} of {n_attempts} planned attempts")

    # Validate: min observed interval must be >= 1 s.
    if min_interval is not None and min_interval < interval_seconds:
        raise SecClientError(
            f"minimum observed start interval {min_interval:.3f}s is below "
            f"the required {interval_seconds}s"
        )

    return {
        "planned_attempts": n_attempts,
        "started_attempts": started,
        "target_start_interval_seconds": interval_seconds,
        "min_observed_start_interval_seconds": min_interval,
        "first_to_last_start_duration_seconds": first_to_last,
        "outcome_counts": outcome_counts,
        "blocked": any_blocked,
        "per_attempt": attempts,
        "statement": (
            "This short observation does not settle sustained fleet behaviour. "
            "It demonstrates the declared client is admitted or blocked over "
            f"{n_attempts} attempts at one start per second; it cannot "
            "establish rate-of-service across a sustained fleet workload."
        ),
    }
