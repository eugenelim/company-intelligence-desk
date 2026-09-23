"""The canonicaliser: what a value means to the callee, not what it looks like.

`worker-runtime.md` r5 § 4, "Why a prefix predicate is not safe on an
interpreted argument", carries a paragraph beginning **"What the canonicalizer
must do"**. Every rule in `URL_RULES` and `FS_PATH_RULES` below implements one
clause of it, and each rule records the clause it implements in `clause` so
the mapping is readable rather than asserted. AC-0216 holds an input per rule
that this canonicaliser refuses and that is admitted once that rule is gone.

**The rules are an ordered tuple and nothing here can switch one off.** The
spec's first `Never do` refuses a disable switch inside a shipped security
control, so the mutation evidence AC-0216 wants is produced by patching these
module-level tuples in the test process. Reading the tuple through the module
global at call time is what makes that patch take effect; it is not a
parameter, and no caller can pass a different rule set.

**Order is load-bearing and is pinned by a case, not by this comment.**
`percent-decode-then-refuse-residual` must run before `remove-dot-segments`:
with the two transposed, `%2e%2e` survives dot-segment removal as text and
then decodes into a traversal that nothing re-checks. A probe confirmed this
on 2026-09-18. AC-0216 disables one rule at a time and cannot see a
transposition that keeps every rule, so `tests/containment` carries a separate
pinned case that reds when the two are swapped.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Final
from urllib.parse import unquote, urlsplit

from ced.domain.containment.domain_types import DomainType
from ced.domain.containment.errors import ContainmentUndecidable

__all__ = [
    "FS_PATH_RULES",
    "URL_RULES",
    "CanonicalUrl",
    "CanonicalisationRule",
    "UrlUnderReview",
    "canonicalise",
    "canonicalise_fs_root",
    "rule_names",
]

#: Ports a scheme carries implicitly, so a value naming one means the same
#: thing as a value that omits it.
_DEFAULT_PORTS: Final[dict[str, int]] = {"http": 80, "https": 443}

#: An encoded path separator or an encoded percent sign, which is what a
#: still-encoded separator looks like after one decoding round.
_ENCODED_SEPARATOR: Final[re.Pattern[str]] = re.compile(r"%(?:2[eEfF]|5[cC]|25)")

#: Characters that make a URL mean different things to different parsers.
#: `urlsplit` silently strips tab, newline and carriage return, so a value
#: carrying one has already diverged from what a stricter client would see.
_AMBIGUOUS_CHARACTERS: Final[frozenset[str]] = frozenset(
    {chr(code) for code in range(0x21)} | {chr(0x7F)}
)


@dataclass(frozen=True)
class CanonicalUrl:
    """A URL reduced to the components a predicate may range over.

    This is the value handed on, so it carries no userinfo: credentials in an
    authority are not part of what the callee resolves, and passing them
    through would hand an adapter something the check never ranged over.
    """

    scheme: str
    host: str
    port: int | None
    path: str
    query: str

    def __str__(self) -> str:
        """Render the canonical value an adapter receives."""
        authority = self.host if self.port is None else f"{self.host}:{self.port}"
        query = f"?{self.query}" if self.query else ""
        return f"{self.scheme}://{authority}{self.path}{query}"


@dataclass(frozen=True)
class UrlUnderReview:
    """A URL part-way through canonicalisation, with what the parse left over.

    `raw` and `userinfo` are not part of the canonical value and never reach
    an adapter. They are here because two clauses judge the *parse* rather
    than the components: a control character is invisible once `urlsplit` has
    stripped it, and a second `@` is invisible once the userinfo is split off.
    """

    raw: str
    userinfo: str
    authority: str
    scheme: str
    host: str
    port: int | None
    path: str
    query: str

    def canonical(self) -> CanonicalUrl:
        """Return the value the adapter receives, leaving the parse behind."""
        return CanonicalUrl(
            scheme=self.scheme,
            host=self.host,
            port=self.port,
            path=self.path,
            query=self.query,
        )


@dataclass(frozen=True)
class CanonicalisationRule[T]:
    """One clause of r5's "What the canonicalizer must do", as a step.

    `name` is the identity AC-0216's mutation evidence is indexed by; a rule
    that applies to more than one domain type appears in both tuples under the
    same name, because it is one rule with two applications.
    """

    name: str
    clause: str
    apply: Callable[[T], T]


def _refuse_ambiguous_url(url: UrlUnderReview) -> UrlUnderReview:
    """Reject a URL that more than one parser would read differently.

    Three shapes reach it: a control character, which `urlsplit` strips and a
    stricter client does not; a second `@`, where parsers disagree about which
    side is the host; and a missing host, which no host predicate can decide.
    """
    offending = _AMBIGUOUS_CHARACTERS & set(url.raw)
    if offending:
        raise ContainmentUndecidable(
            f"{url.raw!r} carries the control character {min(offending)!r}; parsers "
            "disagree on whether it terminates the URL, strips out, or stays"
        )
    if "@" in url.userinfo:
        raise ContainmentUndecidable(
            f"authority {url.userinfo + '@' + url.host!r} carries more than one '@'; "
            "parsers disagree on which side is the host, so the value has no "
            "single meaning"
        )
    if not url.host:
        raise ContainmentUndecidable(
            "the URL names no host, so no host predicate can decide it"
        )
    return url


def _normalise_port(url: UrlUnderReview) -> UrlUnderReview:
    """Split a validated port off the authority, dropping a scheme's default.

    **Dropping a default port means parsing the port first**, and parsing it
    is where the weight sits. Without this rule the host stays whatever comes
    before the first colon, so `www.example.com:443.attacker.example` reads as
    `www.example.com` to every host predicate while the authority is something
    else entirely. That naive split is exactly what `host` holds until this
    rule replaces it.
    """
    authority = url.authority
    if authority.startswith("["):
        closing = authority.find("]")
        if closing == -1:
            raise ContainmentUndecidable(
                f"authority {authority!r} opens an IPv6 literal it never closes"
            )
        host, remainder = authority[: closing + 1], authority[closing + 1 :]
        if remainder and not remainder.startswith(":"):
            raise ContainmentUndecidable(
                f"authority {authority!r} has trailing text after the IPv6 literal"
            )
        port_text = remainder[1:]
    else:
        host, separator, port_text = authority.partition(":")
        port_text = port_text if separator else ""
    if not port_text:
        return replace(url, host=host, port=None)
    if not port_text.isdigit() or not 1 <= int(port_text) <= 65535:
        raise ContainmentUndecidable(
            f"{port_text!r} is not a port, so authority {authority!r} has no single reading"
        )
    port = int(port_text)
    return replace(
        url, host=host, port=None if port == _DEFAULT_PORTS.get(url.scheme) else port
    )


def _idna_host(url: UrlUnderReview) -> UrlUnderReview:
    """Encode the host to punycode, refusing a host IDNA cannot represent.

    A host carrying a character IDNA prohibits — a bidirectional override, say
    — is one no two clients agree on. Refusing beats guessing, and guessing is
    what a host predicate over the raw string does.
    """
    try:
        encoded = url.host.encode("idna").decode("ascii")
    except UnicodeError as error:
        raise ContainmentUndecidable(
            f"host {url.host!r} is not IDNA-encodable, so what the callee resolves "
            f"is undecided here: {error}"
        ) from error
    return replace(url, host=encoded)


def _lowercase_host_not_path(url: UrlUnderReview) -> UrlUnderReview:
    """Case-fold the host, and leave the path's case exactly as it arrived.

    The second half is the half with a bypass behind it. A path is
    case-sensitive to most callees, so folding it makes `/Evidence/` and
    `/evidence/` the same value to the check and two different resources to
    the thing that fetches them.
    """
    return replace(url, scheme=url.scheme.lower(), host=url.host.lower())


def _percent_decode_then_refuse_residual(url: UrlUnderReview) -> UrlUnderReview:
    """Decode the path once, then refuse a separator still encoded afterwards.

    One round of decoding is all a canonical value may need. A value that
    still holds an encoded separator after it was double-encoded on purpose,
    and the callee that decodes again sees a path this check never looked at.
    """
    decoded = unquote(url.path)
    residual = _ENCODED_SEPARATOR.search(decoded)
    if residual is not None:
        raise ContainmentUndecidable(
            f"path {url.path!r} still contains the encoded separator "
            f"{residual.group()!r} after decoding, so the callee will read a "
            "different path than this check does"
        )
    return replace(url, path=decoded)


def _remove_url_dot_segments(url: UrlUnderReview) -> UrlUnderReview:
    """Apply RFC 3986 § 5.2.4 to the path, so `..` cannot leave a path root."""
    return replace(url, path=_remove_dot_segments(url.path))


def _resolve_fs_symlinks(path: str) -> str:
    """Resolve every symlink in the path, because a name-only pass admits a link.

    r5 states this for `fs-path` specifically: normalisation that only edits
    the name admits a link pointing outside the root, which is CWE-59.
    """
    return os.path.realpath(path)


def _remove_fs_dot_segments(path: str) -> str:
    """Remove `.` and `..` lexically, so a non-existent path still normalises."""
    return os.path.normpath(path)


def _remove_dot_segments(path: str) -> str:
    """Return `path` with dot segments removed, per RFC 3986 § 5.2.4."""
    output: list[str] = []
    for segment in path.split("/"):
        if segment == ".":
            continue
        if segment == "..":
            if output[1:]:
                output.pop()
            continue
        output.append(segment)
    resolved = "/".join(output)
    if path.endswith(("/.", "/..")) and not resolved.endswith("/"):
        resolved += "/"
    return resolved


#: The URL canonicalisation rules, in the order they run. Transposing
#: `percent-decode-then-refuse-residual` and `remove-dot-segments` admits an
#: encoded traversal; a pinned case in `tests/containment` reds when they swap.
URL_RULES: Final[tuple[CanonicalisationRule[UrlUnderReview], ...]] = (
    CanonicalisationRule(
        name="refuse-ambiguous-parse",
        clause="reject an ambiguous parse rather than guessing",
        apply=_refuse_ambiguous_url,
    ),
    CanonicalisationRule(
        name="drop-default-ports",
        clause="drop default ports",
        apply=_normalise_port,
    ),
    CanonicalisationRule(
        name="idna-normalise-host",
        clause="IDNA-normalize the host to punycode",
        apply=_idna_host,
    ),
    CanonicalisationRule(
        name="lowercase-host-not-path",
        clause="lowercase the host and not the path",
        apply=_lowercase_host_not_path,
    ),
    CanonicalisationRule(
        name="percent-decode-then-refuse-residual",
        clause=(
            "percent-decode before dot-segment removal and refuse a value that "
            "still contains an encoded separator afterwards"
        ),
        apply=_percent_decode_then_refuse_residual,
    ),
    CanonicalisationRule(
        name="remove-dot-segments",
        clause=(
            "percent-decode before dot-segment removal and refuse a value that "
            "still contains an encoded separator afterwards"
        ),
        apply=_remove_url_dot_segments,
    ),
)

#: The `fs-path` rules, in the order they run. Symlink resolution comes first
#: because removing `..` lexically before following a link is the bug the
#: clause exists to prevent, not a cheaper way to reach the same answer.
FS_PATH_RULES: Final[tuple[CanonicalisationRule[str], ...]] = (
    CanonicalisationRule(
        name="resolve-symlinks",
        clause="For `fs-path`, normalization resolves symlinks",
        apply=_resolve_fs_symlinks,
    ),
    CanonicalisationRule(
        name="remove-dot-segments",
        clause=(
            "percent-decode before dot-segment removal and refuse a value that "
            "still contains an encoded separator afterwards"
        ),
        apply=_remove_fs_dot_segments,
    ),
)


def rule_names() -> tuple[str, ...]:
    """Return every rule name once, reading the tuples as they stand now."""
    seen: list[str] = [rule.name for rule in URL_RULES]
    seen += [rule.name for rule in FS_PATH_RULES if rule.name not in seen]
    return tuple(seen)


def canonicalise_fs_root(root: str) -> str:
    """Return the canonical form of a `within(root)` argument.

    The root a ceiling names goes through the same rules as the value it is
    compared against. A root left uncanonicalised makes the comparison a
    string coincidence.
    """
    return _run_fs_rules(root)


def _run_fs_rules(path: str) -> str:
    canonical = path
    for rule in FS_PATH_RULES:
        canonical = rule.apply(canonical)
    return canonical


def _canonicalise_url(value: object) -> CanonicalUrl:
    if not isinstance(value, str):
        raise ContainmentUndecidable(
            f"a {type(value).__name__} is not a URL, so no URL predicate can decide it"
        )
    parts = urlsplit(value)
    if not parts.scheme:
        raise ContainmentUndecidable(f"{value!r} declares no scheme, so it is not a URL")
    # The userinfo is split off before any rule runs: it is not a
    # canonicalisation clause but the parse itself, and it is the third row of
    # r5's unsafe-prefix table — `https://host@elsewhere/` reads as `host` to a
    # prefix check and resolves to `elsewhere`.
    userinfo, _, authority = parts.netloc.rpartition("@")
    url = UrlUnderReview(
        raw=value,
        userinfo=userinfo,
        authority=authority,
        scheme=parts.scheme,
        # The naive reading, held only until `drop-default-ports` replaces it
        # with the parsed one. See that rule for why the two differ.
        host=authority.partition(":")[0],
        port=None,
        path=parts.path or "/",
        query=parts.query,
    )
    for rule in URL_RULES:
        url = rule.apply(url)
    return url.canonical()


def canonicalise(domain_type: DomainType, value: object) -> object:
    """Return the canonical form of `value` for `domain_type`.

    Raises `ContainmentUndecidable` where the value has no single reading. The
    caller passes the returned value on: canonicalising for the check and
    handing the adapter the original string rebuilds the differential inside
    our own process, which is r5's third rule.
    """
    match domain_type:
        case DomainType.URL:
            return _canonicalise_url(value)
        case DomainType.FS_PATH:
            if not isinstance(value, str):
                raise ContainmentUndecidable(
                    f"a {type(value).__name__} is not a filesystem path"
                )
            return _run_fs_rules(value)
        case _:
            return value
