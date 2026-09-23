"""The canonicaliser: what a value means to the callee, not what it looks like.

`worker-runtime.md` r5 § 4, "Why a prefix predicate is not safe on an
interpreted argument", carries a paragraph beginning **"What the canonicalizer
must do"**. Every rule in `URL_RULES` and `FS_PATH_RULES` below implements one
clause of it and records that clause in `clause`, so the mapping is readable
rather than asserted.

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

**`fs-path` canonicalisation reads the host filesystem.** `resolve-symlinks`
calls `os.path.realpath`, which is a blocking syscall and makes the canonical
form depend on the machine. Nothing else here performs I/O.

**Two clauses normalise rather than refuse, and their omission fails closed.**
Case-folding a host and dropping a default port both admit strictly more, and
no predicate in r5's fragment ranges over a port at all, so removing either
can only shrink what the fragment admits. `tests/containment` proves that
direction for both rather than claiming a bypass neither has; the spec's
verification ledger records what that leaves open against AC-0216.
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
    "canonicalise_host",
    "canonicalise_url_path",
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


def _valid_port(port_text: str) -> bool:
    """Return whether `port_text` is a port exactly as the URL grammar has one.

    ASCII digits, and not `str.isdigit`. That predicate is true of 128
    characters `int()` refuses — U+00B2 SUPERSCRIPT TWO among them, which
    made this function's caller crash rather than refuse — and true of the
    Arabic-Indic digits, which `int()` accepts, so an authority RFC 3986 does
    not admit would have been rewritten into one that looks valid.
    """
    return port_text.isascii() and port_text.isdecimal() and 1 <= int(port_text) <= 65535


def _drop_root_label(host: str) -> str:
    """Return `host` without its DNS root label.

    `sec.gov.` and `sec.gov` are the same name to a resolver, and a check
    that treats them as two is a check with a spare spelling. The ceiling's
    host argument and the value's host both come through here, because a
    normalisation only one side runs is a differential rather than a
    canonical form.
    """
    return host[:-1] if host.endswith(".") else host


def _empty_label(host: str) -> bool:
    """Return whether `host` has a label with nothing in it."""
    return host == "" or any(label == "" for label in host.split("."))


def _canonical_labels(host: str) -> str:
    """Return the host as the encoder spells it, with its root label gone.

    **Label structure is decided on the encoder's output, not on its input.**
    IDNA reads four characters as a separator directly, and its own
    normalisation turns two more into one — NFKC maps U+2024 and U+FE52 to a
    full stop inside a label — so any list of separators kept here is a
    snapshot of one codec version rather than the rule. Encoding first and
    splitting afterwards makes the guard hold for whatever the encoder maps,
    which is the spelling the resolver will answer for.
    """
    encoded = _drop_root_label(_idna(host))
    if "%" in encoded:
        # The residual-separator refusal ranges over the path, and the host
        # reaches its canonical form by another route: the codec's NFKC pass
        # can turn a fullwidth sequence into a literal percent escape, so
        # a host written in fullwidth digits can canonicalise to `%00.example`.
        # A client that decodes the authority then resolves something this
        # check never compared, which is the differential the path's refusal
        # exists to prevent, on the component it does not reach.
        raise ContainmentUndecidable(
            f"host {host!r} encodes to {encoded!r}, which carries a percent "
            "escape; a client that decodes the authority resolves a different "
            "name than this check compared"
        )
    if _empty_label(encoded):
        raise ContainmentUndecidable(
            f"host {host!r} encodes to {encoded!r}, which has a label with "
            "nothing in it, so it names no single resolvable name"
        )
    return encoded


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

    `port_text` holds the port exactly as the authority spelled it, and
    `port` the number `drop-default-ports` made of it. The two are separate
    because validating a port is `refuse-invalid-port`'s judgment: a
    conversion anywhere else would have to repeat that check, and a rule
    whose work another step redoes cannot be shown to carry weight.
    """

    raw: str
    userinfo: str
    scheme: str
    host: str
    port_text: str
    port: int | None
    path: str
    query: str

    def canonical(self) -> CanonicalUrl:
        """Return the value the adapter receives, leaving the parse behind.

        The port comes from `drop-default-ports`, already a number or
        absent. Nothing is converted here, so no conversion can fail here.
        """
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

    `name` is the identity AC-0216's mutation evidence is indexed by.
    """

    name: str
    clause: str
    apply: Callable[[T], T]


def _refuse_control_characters(url: UrlUnderReview) -> UrlUnderReview:
    """Reject a URL carrying a character `urlsplit` strips and others do not.

    One of four guards that share r5's ambiguity clause. They are four rules
    and not one because AC-0216 indexes its evidence per rule, and a rule
    holding four guards can lose three of them with every case still green.
    """
    offending = _AMBIGUOUS_CHARACTERS & set(url.raw)
    if offending:
        raise ContainmentUndecidable(
            f"{url.raw!r} carries the control character {min(offending)!r}; parsers "
            "disagree on whether it terminates the URL, strips out, or stays"
        )
    return url


def _refuse_second_userinfo(url: UrlUnderReview) -> UrlUnderReview:
    """Reject an authority with more than one `@`, which parsers read differently."""
    if "@" in url.userinfo:
        raise ContainmentUndecidable(
            f"authority {url.userinfo + '@' + url.host!r} carries more than one '@'; "
            "parsers disagree on which side is the host, so the value has no "
            "single meaning"
        )
    return url


def _refuse_empty_label(url: UrlUnderReview) -> UrlUnderReview:
    """Reject a host with a label holding nothing, a missing host included.

    This reads the spelling the caller wrote, which is the half that does not
    depend on the IDNA codec. A character the encoder *turns into* a
    separator is caught in `idna-normalise-host`, against the encoded
    spelling, because only the encoder knows which characters those are.
    """
    if _empty_label(url.host):
        raise ContainmentUndecidable(
            f"host {url.host!r} has a label with nothing in it — a missing host, a "
            "leading separator or a doubled one — so it names no single resolvable "
            "name and no host predicate can decide it"
        )
    return url


def _refuse_invalid_port(url: UrlUnderReview) -> UrlUnderReview:
    """Reject an authority whose port is not a port.

    A reader that splits the authority on the first colon and a reader that
    parses it see different hosts, so the value names neither.
    """
    if url.port_text and not _valid_port(url.port_text):
        raise ContainmentUndecidable(
            f"{url.port_text!r} is not a port, so the authority of {url.raw!r} has no "
            "single reading: a reader that splits on the first colon sees "
            f"{url.host!r} and a reader that parses the authority sees neither"
        )
    return url


def _drop_default_port(url: UrlUnderReview) -> UrlUnderReview:
    """Drop a port the scheme already implies, so `:443` and nothing agree.

    Nothing in r5's `url` predicate row ranges over a port, so this rule
    changes the value handed on and never changes a decision. Its omission is
    therefore fail-closed, which the suite proves rather than assuming; what
    an omission does cost is the port itself, which then does not reach the
    canonical value at all.
    """
    if not _valid_port(url.port_text):
        # Not this rule's judgment to make: `refuse-invalid-port` owns it,
        # and a port it has not passed is one this rule declines to read.
        return url
    port = int(url.port_text)
    return replace(url, port=None if port == _DEFAULT_PORTS.get(url.scheme) else port)


def _idna(host: str) -> str:
    """Return `host` in punycode, refusing a host IDNA cannot represent."""
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError as error:
        raise ContainmentUndecidable(
            f"host {host!r} is not IDNA-encodable, so what the callee resolves is "
            f"undecided here: {error}"
        ) from error


def _idna_host(url: UrlUnderReview) -> UrlUnderReview:
    """Encode the host to punycode, refusing a host IDNA cannot represent.

    A host carrying a character IDNA prohibits — a bidirectional override, say
    — is one no two clients agree on. Refusing beats guessing, and guessing is
    what a host predicate over the raw string does.

    The encoder is also what settles where the labels are, because its own
    normalisation can turn a character into a separator. So the root label is
    dropped and an empty label refused **against the encoded spelling**, here
    rather than earlier. `refuse-ambiguous-parse` makes the same refusal
    against the spelling the caller wrote, which is the half that does not
    depend on this codec.
    """
    return replace(url, host=_canonical_labels(url.host))


def _lowercase_host_not_path(url: UrlUnderReview) -> UrlUnderReview:
    """Case-fold the host, and leave the path's case exactly as it arrived.

    The standard library's IDNA codec does not fold case, so this rule is the
    only thing that does. Both halves of the clause are permissive in the same
    direction — a folded host matches strictly more ceilings, and an unfolded
    path matches strictly fewer — so removing the rule can only shrink what
    the fragment admits. The suite proves that direction.
    """
    return replace(url, host=url.host.lower())


def _decode_once_then_refuse_residual(path: str) -> str:
    """Decode a path once, then refuse a separator still encoded afterwards."""
    decoded = unquote(path)
    residual = _ENCODED_SEPARATOR.search(decoded)
    if residual is not None:
        raise ContainmentUndecidable(
            f"path {path!r} still contains the encoded separator "
            f"{residual.group()!r} after decoding, so the callee will read a "
            "different path than this check does"
        )
    return decoded


def _percent_decode_then_refuse_residual(url: UrlUnderReview) -> UrlUnderReview:
    """Decode the path once, then refuse a separator still encoded afterwards.

    One round of decoding is all a canonical value may need. A value that
    still holds an encoded separator afterwards was double-encoded on purpose,
    and the callee that decodes again sees a path this check never looked at.
    """
    return replace(url, path=_decode_once_then_refuse_residual(url.path))


def _remove_url_dot_segments(url: UrlUnderReview) -> UrlUnderReview:
    """Apply RFC 3986 § 5.2.4 to the path, so `..` cannot leave a path root."""
    return replace(url, path=_remove_dot_segments(url.path))


def _resolve_fs_symlinks(path: str) -> str:
    """Resolve every symlink in the path, because a name-only pass admits a link.

    r5 states this for `fs-path` specifically: normalisation that only edits
    the name admits a link pointing outside the root, which is CWE-59.
    `realpath` removes dot segments on the way, so `fs-path` needs no separate
    lexical pass — one that ran after this would never change a value, and a
    rule that cannot change a value cannot be shown to carry weight.

    **This is the one step in the package that reads the host filesystem.**
    It is a blocking syscall with no bound, and it makes an `fs-path`'s
    canonical form depend on the machine the fragment runs on. Both are
    inherent to resolving a link rather than a choice made here, and both are
    recorded so a consumer sizing the tool-call path can see them. Whatever
    `realpath` refuses to answer for — a name with a NUL in it, a symlink
    loop, an unreadable parent — is refused in this package's vocabulary
    rather than as the operating system spelled it.
    """
    try:
        return os.path.realpath(path)
    except (OSError, RuntimeError, ValueError) as error:
        raise ContainmentUndecidable(
            f"the filesystem cannot resolve {path!r}, so where it points is "
            f"undecided here: {error}"
        ) from error


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
        name="refuse-control-characters",
        clause="reject an ambiguous parse rather than guessing",
        apply=_refuse_control_characters,
    ),
    CanonicalisationRule(
        name="refuse-second-userinfo",
        clause="reject an ambiguous parse rather than guessing",
        apply=_refuse_second_userinfo,
    ),
    CanonicalisationRule(
        name="refuse-empty-label",
        clause="reject an ambiguous parse rather than guessing",
        apply=_refuse_empty_label,
    ),
    CanonicalisationRule(
        name="refuse-invalid-port",
        clause="reject an ambiguous parse rather than guessing",
        apply=_refuse_invalid_port,
    ),
    CanonicalisationRule(
        name="drop-default-ports",
        clause="drop default ports",
        apply=_drop_default_port,
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

#: The `fs-path` rules. One rule, because `realpath` is both the symlink
#: resolution r5 names and a dot-segment removal, and a second lexical pass
#: after it would be inert.
FS_PATH_RULES: Final[tuple[CanonicalisationRule[str], ...]] = (
    CanonicalisationRule(
        name="resolve-symlinks",
        clause="For `fs-path`, normalization resolves symlinks",
        apply=_resolve_fs_symlinks,
    ),
)


def rule_names() -> tuple[str, ...]:
    """Return every rule name once, reading the tuples as they stand now."""
    seen: list[str] = [rule.name for rule in URL_RULES]
    seen += [rule.name for rule in FS_PATH_RULES if rule.name not in seen]
    return tuple(seen)


def canonicalise_host(host: str) -> str:
    """Return the canonical form of a host a ceiling names.

    A ceiling's host is compared against a canonical one, so it has to be
    canonical itself. Comparing a canonical value against a literal somebody
    typed is a string coincidence, not a containment check.
    """
    written = _drop_root_label(host)
    if _empty_label(written):
        raise ContainmentUndecidable(
            f"{host!r} has a label with nothing in it, so it names no domain and "
            "a predicate over it would range over every host or none"
        )
    return _canonical_labels(written).lower()


def canonicalise_url_path(path: str) -> str:
    """Return the canonical form of a URL path a ceiling names."""
    return _remove_dot_segments(_decode_once_then_refuse_residual(path))


def canonicalise_fs_root(root: str) -> str:
    """Return the canonical form of a `within(root)` argument."""
    return _run_fs_rules(root)


def _run_fs_rules(path: str) -> str:
    canonical = path
    for rule in FS_PATH_RULES:
        canonical = rule.apply(canonical)
    return canonical


def _split_authority(authority: str) -> tuple[str, str]:
    """Return `(host, port-as-written)` for an authority with no userinfo.

    The split is part of the parse, not of a clause: every host predicate
    needs a host, and a reader that never separates the port from the host
    compares the wrong string. `refuse-ambiguous-parse` is what judges a port
    that is not one.
    """
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
        return host, remainder[1:]
    host, separator, port_text = authority.partition(":")
    return host, port_text if separator else ""


def _canonicalise_url(value: object) -> CanonicalUrl:
    if not isinstance(value, str):
        raise ContainmentUndecidable(
            f"a {type(value).__name__} is not a URL, so no URL predicate can decide it"
        )
    try:
        parts = urlsplit(value)
    except ValueError as error:
        # `urlsplit` raises for an unclosed IPv6 literal and for an authority
        # carrying a character NFKC turns into a URL delimiter. Both are
        # values a model can choose, and both are refusals rather than
        # defects, so they leave here as one.
        raise ContainmentUndecidable(
            f"{value!r} does not parse as a URL, so what the callee would "
            f"resolve is undecided here: {error}"
        ) from error
    if not parts.scheme:
        raise ContainmentUndecidable(f"{value!r} declares no scheme, so it is not a URL")
    # The userinfo is split off before any rule runs: it is not a
    # canonicalisation clause but the parse itself, and it is the third row of
    # r5's unsafe-prefix table — `https://host@elsewhere/` reads as `host` to a
    # prefix check and resolves to `elsewhere`.
    userinfo, _, authority = parts.netloc.rpartition("@")
    host, port_text = _split_authority(authority)
    # The root label goes here for the spelling the caller wrote; the
    # encoded spelling is settled in `idna-normalise-host`, because the
    # encoder is what decides where a name's labels are.
    host = _drop_root_label(host)
    url = UrlUnderReview(
        raw=value,
        userinfo=userinfo,
        scheme=parts.scheme,
        host=host,
        port_text=port_text,
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
