"""Bounded, rate-gated SEC EDGAR HTTP client.

Design constraints (AC-0402, AC-0403, AC-0417):

- HTTPS only, to the two admitted hosts (``data.sec.gov``, ``www.sec.gov``).
- TLS certificate verification is always on; ``check_hostname=True``,
  ``CERT_REQUIRED``; no parameter disables it.
- DNS resolution uses ``socket.getaddrinfo``; only public unicast non-multicast
  addresses are admitted. Connection uses ``socket.create_connection`` to one
  validated address with the SEC hostname retained for TLS
  (``wrap_socket(server_hostname=host)``).  All three socket operations are
  injectable for tests; the single production code path always runs.
- Connect timeout: 5 s, clamped to remaining total budget. Read timeout: 15 s,
  clamped to remaining total budget per chunk. Total budget: 30 s from gate
  admission through the end of the bounded body read; refused as
  ``total_timeout`` when remaining budget reaches zero before any operation.
- Response size caps: 5 MiB for submissions, 10 MiB for filings.  A declared
  ``Content-Length`` above the cap refuses before reading; a malformed
  ``Content-Length`` is refused (fail-closed) before reading; a stream first
  crossing the cap is stopped and refused.
- No automatic retry. ``403`` / ``429`` are recorded as ``blocked``.
- The runtime declared-client value (``SEC_CONTACT``) is read only when building
  the ``User-Agent`` header and must never appear in exceptions, logs, records,
  stdout / stderr, or stored objects.
- Every SEC request passes through the shared Postgres rate gate, which
  acquires a session-level advisory lock, records the admission time, and holds
  the lock for at least ``_GATE_INTERVAL`` seconds after admission.

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
``"read_timeout"``, ``"total_timeout"``).  The ``AttemptRecord`` field of the
same name is populated from this attribute in the catch block of ``fetch_url``.
"""

from __future__ import annotations

import contextlib
import dataclasses
import ipaddress
import os
import socket
import ssl
import time
from collections.abc import Callable, Generator
from http import client as http_client
from typing import Any

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
    ``"total_timeout"``.  HTTP-level failures and configuration errors
    leave it ``None``.
    """

    def __init__(self, msg: str, *, no_response_class: str | None = None) -> None:
        super().__init__(msg)
        self.no_response_class: str | None = no_response_class


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
    """One of "success", "blocked", "redirect", or a no-response class string."""

    http_status_class: str | None
    """"2xx", "4xx", "5xx", or ``None`` when no HTTP response was received."""

    no_response_class: str | None
    """One of "dns", "tls", "connect_timeout", "read_timeout", "total_timeout",
    or ``None`` when an HTTP response was received."""

    blocked: bool
    """True when HTTP 403 or 429 was received."""

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
    """HTTPSConnection that resolves once and connects to one validated address.

    ``connect()`` is overridden so there is no second DNS resolution while the
    socket is being created. The original hostname is retained for TLS
    certificate verification (``wrap(sock, server_hostname=host)``).

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

    def connect(self) -> None:
        """Resolve, validate, and connect to one public-unicast address.

        Uses ``self.timeout`` for the connect-level deadline so callers can
        clamp it to the remaining total budget before calling this method.
        """
        try:
            results = self._resolve(self._sec_host, 443, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise SecClientError(
                "DNS resolution failed",
                no_response_class="dns",
            ) from exc

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
                no_response_class="connect_timeout",
            ) from exc

        # Retain the original SEC hostname for TLS certificate verification.
        try:
            self.sock = self._wrap(raw_sock, server_hostname=self._sec_host)
        except ssl.SSLError as exc:
            try:
                raw_sock.close()
            except Exception:
                pass
            raise SecClientError(
                "TLS verification failed",
                no_response_class="tls",
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
            conn.execute("SELECT pg_advisory_unlock(%s)", [_GATE_LOCK_KEY])
            conn.commit()


@contextlib.contextmanager
def _fake_gate(
    clock: _ClockFn | None = None,
) -> Generator[float]:
    """Offline gate for tests: no Postgres, returns admission time immediately."""
    t0 = (clock or time.monotonic)()
    yield t0


# ---------------------------------------------------------------------------
# Contact value
# ---------------------------------------------------------------------------


def acquire_contact() -> str:
    """Read the runtime declared-client value from the environment.

    Raises ``SecClientError`` naming the variable when it is absent or blank.
    The returned value is used only as the ``User-Agent`` header and must never
    be copied into an exception message, log record, stored object, or output.
    """
    raw = os.environ.get(SEC_CONTACT_ENV)
    if not raw or not raw.strip():
        raise SecClientError(
            f"{SEC_CONTACT_ENV} is unset or blank; set it to the declared "
            f"User-Agent string required by SEC developer policy before "
            f"making any live request"
        )
    return raw.strip()


# ---------------------------------------------------------------------------
# Core fetch implementation
# ---------------------------------------------------------------------------


def _http_status_class(status: int) -> str:
    """Return the class string ("1xx"–"5xx") for an HTTP status code."""
    return f"{status // 100}xx"


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
        header. Must not appear in any exception, log, or record.
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

            # Final budget gate after _real_fetch returns (covers the gap
            # between the last chunk read and here; _real_fetch already
            # enforces the budget internally).
            if _clock() - budget_start > _TOTAL_BUDGET:
                raise SecClientError(
                    "total budget exceeded",
                    no_response_class="total_timeout",
                )

            cls = _http_status_class(status)
            http_status_class = cls

            if status in (301, 302, 303, 307, 308):
                stop_condition = "redirect"
                raise SecRedirectError(
                    f"server returned HTTP {status} (redirect); this client follows no redirect"
                )
            if status in (403, 429):
                blocked = True
                stop_condition = "blocked"
                raise SecBlockedError(
                    "SEC returned HTTP status indicating the declared client is blocked"
                )
            if status >= 400:
                stop_condition = f"http_{cls}"
                raise SecClientError(f"SEC returned HTTP {status}")

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
            # For network-level failures, carry the no_response_class through
            # to the record.  SecRedirectError and SecBlockedError are HTTP-
            # level failures and leave no_response_class as None.
            if not isinstance(exc, (SecRedirectError, SecBlockedError)):
                nrc = exc.no_response_class
                no_response_class = nrc
                if nrc is not None and stop_condition == "success":
                    stop_condition = nrc
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

    All budget enforcement, timeout clamping, and size-cap checks live here
    so there is exactly one production fetch path.
    """
    budget_end = budget_start + _TOTAL_BUDGET

    conn = _GatedSecConnection(host, resolve=resolve, open_socket=open_socket, wrap=wrap)
    try:
        # Check budget before connect; clamp connect timeout to remaining.
        remaining = budget_end - clock()
        if remaining <= 0:
            raise SecClientError(
                "total budget exceeded before connect",
                no_response_class="total_timeout",
            )
        conn.timeout = min(_CONNECT_TIMEOUT, remaining)

        # connect() converts DNS/TLS/OS errors to SecClientError with
        # no_response_class already set; propagate unchanged.
        conn.connect()

        # Check budget before issuing the request; clamp read timeout.
        remaining = budget_end - clock()
        if remaining <= 0:
            raise SecClientError(
                "total budget exceeded before request",
                no_response_class="total_timeout",
            )
        conn.set_read_timeout(min(_READ_TIMEOUT, remaining))

        try:
            conn.request("GET", path, headers=headers)
            response = conn.getresponse()
        except TimeoutError as exc:
            raise SecClientError(
                "read timeout",
                no_response_class="read_timeout",
            ) from exc
        except OSError as exc:
            raise SecClientError(
                "request failed",
                no_response_class="read_timeout",
            ) from exc

        status = response.status
        resp_headers: dict[str, str] = {k.lower(): v for k, v in response.getheaders()}

        # Validate declared Content-Length — fail closed on malformed value.
        cl_str = resp_headers.get("content-length")
        if cl_str is not None:
            try:
                cl = int(cl_str)
            except ValueError as exc:
                raise SecClientError(
                    "malformed Content-Length header; refusing before read"
                ) from exc
            if cl > size_cap:
                raise SecClientError(
                    f"declared Content-Length {cl} exceeds size cap {size_cap}"
                )

        # Read with size cap and per-chunk budget enforcement.
        chunks: list[bytes] = []
        total_read = 0
        while True:
            remaining = budget_end - clock()
            if remaining <= 0:
                raise SecClientError(
                    "total budget exceeded during read",
                    no_response_class="total_timeout",
                )
            if conn.sock is not None:
                conn.sock.settimeout(min(_READ_TIMEOUT, remaining))
            try:
                chunk = response.read(65536)
            except TimeoutError as exc:
                raise SecClientError(
                    "read timeout during body",
                    no_response_class="read_timeout",
                ) from exc
            if not chunk:
                break
            total_read += len(chunk)
            if total_read > size_cap:
                raise SecClientError(f"response body exceeded size cap {size_cap} during read")
            chunks.append(chunk)

        body = b"".join(chunks)
        return status, resp_headers, body

    finally:
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
        # Scheduled start time for attempt i (relative to schedule origin).
        scheduled_at = t_schedule_start + i * interval_seconds
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
        except SecBlockedError:
            # Blocked is a valid outcome; record it and continue.
            duration = _clock() - start_times[-1]
            record = AttemptRecord(
                request_class=_OBSERVATION_REQUEST_CLASS,
                gate_wait_seconds=0.0,
                duration_seconds=duration,
                retry_count=0,
                stop_condition="blocked",
                http_status_class="4xx",
                no_response_class=None,
                blocked=True,
            )
            stop = "blocked"
            any_blocked = True
        except SecClientError as exc:
            duration = _clock() - start_times[-1]
            # Use the typed no_response_class attribute rather than parsing
            # the exception message.
            nrc = exc.no_response_class or "other"
            record = AttemptRecord(
                request_class=_OBSERVATION_REQUEST_CLASS,
                gate_wait_seconds=0.0,
                duration_seconds=duration,
                retry_count=0,
                stop_condition=nrc,
                http_status_class=None,
                no_response_class=nrc,
                blocked=False,
            )
            stop = nrc

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
