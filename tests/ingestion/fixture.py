"""Fixture helpers for T1/T2 ingestion and diligence tests.

Exports:
    ``FILING_CONTENT_HASH`` — SHA-256 hex of the committed fixture HTML bytes.
    ``recorded_filing()``   — the fixture HTML bytes (used by T2's stub).
    ``make_http_response()`` — build raw HTTP/1.1 response bytes.
    ``FakeSocket``          — socket-like object serving raw HTTP bytes.
    ``make_seam()``         — build (resolve, open_socket, wrap) test callables.

The hash is a constant so a file-system change or accidental edit is caught
by ``test_fixture_hash_matches_file`` rather than silently producing wrong
evidence.  Both T2's stub and T1's storage tests rely on this module.
"""

from __future__ import annotations

import io
import socket as _socket
import ssl
from pathlib import Path
from typing import Any

#: SHA-256 hex of ``tests/fixtures/first_published_analysis.html``.
#: Pinned so that the T2 stub produces a deterministic artifact — the hash
#: feeds into ``build_published_analysis(filing_sha256=…)`` — and so that an
#: accidental edit to the fixture is caught by the assertion below.
FILING_CONTENT_HASH: str = "23e47d3359596a7f94aee998c15691f1d90eadb353dde55a74686cb71d2316f1"

_FIXTURE_PATH: Path = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "first_published_analysis.html"
)


def recorded_filing() -> bytes:
    """Return the fixture filing bytes.

    Reading the file each time (rather than storing a module-level constant)
    keeps the import lightweight and lets tests that mutate the file see their
    own version.  The hash constant stays pinned so the assertion catches
    post-mutation drift.
    """
    return _FIXTURE_PATH.read_bytes()


# ---------------------------------------------------------------------------
# SEC client test helpers
# ---------------------------------------------------------------------------

_HTTP_REASONS: dict[int, str] = {
    200: "OK",
    301: "Moved Permanently",
    302: "Found",
    303: "See Other",
    307: "Temporary Redirect",
    308: "Permanent Redirect",
    400: "Bad Request",
    403: "Forbidden",
    404: "Not Found",
    429: "Too Many Requests",
    500: "Internal Server Error",
    503: "Service Unavailable",
}


def make_http_response(
    status: int = 200,
    headers: dict[str, str] | None = None,
    body: bytes = b"",
    *,
    omit_content_length: bool = False,
) -> bytes:
    """Build raw HTTP/1.1 response bytes suitable for a FakeSocket.

    Parameters
    ----------
    status:
        HTTP status code.
    headers:
        Extra response headers. ``Content-Length`` is added automatically
        unless ``omit_content_length`` is True or the caller supplies it.
    body:
        Response body bytes.
    omit_content_length:
        When True, no ``Content-Length`` header is included (for testing
        chunked or unknown-length responses).
    """
    reason = _HTTP_REASONS.get(status, "Unknown")
    hdrs = dict(headers or {})
    if not omit_content_length and "content-length" not in {k.lower() for k in hdrs}:
        hdrs["Content-Length"] = str(len(body))
    lines = [f"HTTP/1.1 {status} {reason}"]
    for k, v in hdrs.items():
        lines.append(f"{k}: {v}")
    header_block = "\r\n".join(lines) + "\r\n\r\n"
    return header_block.encode() + body


class FakeSocket:
    """Minimal socket-like object that feeds raw HTTP response bytes to http.client.

    ``http.client.HTTPResponse`` calls ``sock.makefile("rb")`` and reads the
    full HTTP framing (status line, headers, body) from the returned file.
    ``FakeSocket.makefile`` returns a fresh ``BytesIO`` each call so the same
    ``FakeSocket`` instance can serve multiple connections in a test loop.

    ``sendall`` is a no-op by default; setting ``timeout_on_send=True`` makes
    it raise ``TimeoutError``, which exercises the read-timeout code path in
    ``_real_fetch`` (both send and response-read failures map to
    ``no_response_class="read_timeout"``).
    """

    def __init__(
        self,
        response: bytes = b"",
        *,
        timeout_on_send: bool = False,
    ) -> None:
        self._response = response
        self._timeout_on_send = timeout_on_send

    def makefile(self, mode: str, buffering: int = -1) -> io.BytesIO:
        """Return a fresh BytesIO so each connection sees the full response."""
        return io.BytesIO(self._response)

    def sendall(self, data: bytes) -> None:
        if self._timeout_on_send:
            raise TimeoutError("simulated send timeout")

    def settimeout(self, timeout: float | None) -> None:
        pass

    def close(self) -> None:
        pass


def make_seam(
    response: bytes = b"",
    *,
    resolved_addr: str = "8.8.8.8",
    resolved_addrs: list[str] | None = None,
    open_socket_error: BaseException | None = None,
    wrap_error: ssl.SSLError | None = None,
    timeout_on_send: bool = False,
    socket_opens: list[str] | None = None,
    wrap_calls: list[str | None] | None = None,
) -> tuple[Any, Any, Any]:
    """Build injectable (resolve, open_socket, wrap) callables for SEC client tests.

    Parameters
    ----------
    response:
        Raw HTTP response bytes to serve (use ``make_http_response`` to build).
    resolved_addr:
        The single IP address the fake resolver returns.  Ignored when
        ``resolved_addrs`` is provided.
    resolved_addrs:
        Ordered list of IP addresses the fake resolver returns.  Each address
        becomes one entry in the getaddrinfo result list.
    open_socket_error:
        When set, ``open_socket`` raises this exception instead of returning a
        ``FakeSocket``.  Use ``TimeoutError()`` to simulate a connect timeout.
    wrap_error:
        When set, ``wrap`` raises this ``ssl.SSLError`` to simulate TLS failure.
    timeout_on_send:
        When True, the fake socket's ``sendall`` raises ``TimeoutError``,
        exercising the read-timeout code path.
    socket_opens:
        When provided, each address passed to ``open_socket`` is appended here
        so callers can assert which addresses were connected to.
    wrap_calls:
        When provided, the ``server_hostname`` keyword arg passed to ``wrap``
        is appended here so callers can assert the TLS SNI hostname.
    """
    _addrs = resolved_addrs if resolved_addrs is not None else [resolved_addr]
    _fake = FakeSocket(response, timeout_on_send=timeout_on_send)
    _opens: list[str] = socket_opens if socket_opens is not None else []
    _wraps: list[str | None] = wrap_calls if wrap_calls is not None else []

    def resolve(host: str, port: int, **kwargs: Any) -> list[tuple[Any, ...]]:
        return [(_socket.AF_INET, _socket.SOCK_STREAM, 0, "", (addr, port)) for addr in _addrs]

    def open_socket(address: tuple[str, int], timeout: float | None = None) -> Any:
        if open_socket_error is not None:
            raise open_socket_error
        _opens.append(address[0])
        return _fake

    def wrap(sock: Any, server_hostname: str | None = None) -> Any:
        if wrap_error is not None:
            raise wrap_error
        _wraps.append(server_hostname)
        return sock

    return resolve, open_socket, wrap
