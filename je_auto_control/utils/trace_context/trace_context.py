"""W3C Trace Context (traceparent / tracestate) propagation.

The existing ``observability`` tracer and ``agent_trace`` spans carry no IDs and
cannot be correlated across an HTTP boundary. This module implements the W3C
Trace Context standard so a run can generate, parse, and propagate
``traceparent`` / ``tracestate`` headers — the keystone that lets spans, logs,
and downstream services share one trace.

Pure standard library (``os`` / ``re``); imports no ``PySide6``. ID generation
accepts an injectable RNG so trace/span IDs are deterministic under test.
"""
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from je_auto_control.utils.exception.exceptions import AutoControlException

_VERSION = "00"
_TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_SPAN_ID_RE = re.compile(r"^[0-9a-f]{16}$")
_FLAGS_RE = re.compile(r"^[0-9a-f]{2}$")
_VERSION_RE = re.compile(r"^[0-9a-f]{2}$")
# A simple key, or a multi-tenant ``tenant@system`` key (W3C Trace Context).
_TRACESTATE_KEY_RE = re.compile(
    r"^(?:[a-z0-9][_0-9a-z\-*/]{0,240}@[a-z][_0-9a-z\-*/]{0,13}|[a-z][_0-9a-z\-*/]{0,255})$")
# value = 0*255(chr) nblk-chr; chr = %x20 / nblk-chr; nblk-chr = printable ASCII but "," and "=".
_TRACESTATE_VALUE_RE = re.compile(r"[\x20-\x2b\x2d-\x3c\x3e-\x7e]{0,255}[\x21-\x2b\x2d-\x3c\x3e-\x7e]")
_MAX_MEMBERS = 32
_OWS = " \t"
_FLAG_SAMPLED = 0x01
_KNOWN_FLAGS = 0x03             # sampled, and Level 2's random-trace-id bit

RandBytes = Callable[[int], bytes]


class TraceContextError(AutoControlException):
    """A traceparent / tracestate header was malformed."""


@dataclass(frozen=True)
class SpanContext:
    """An immutable W3C trace context identifying one span within a trace."""

    trace_id: str
    span_id: str
    trace_flags: int = _FLAG_SAMPLED
    tracestate: List[Tuple[str, str]] = field(default_factory=list)

    @property
    def sampled(self) -> bool:
        """Whether the sampled flag bit is set."""
        return bool(self.trace_flags & _FLAG_SAMPLED)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-friendly view of the context."""
        return {"trace_id": self.trace_id, "span_id": self.span_id,
                "trace_flags": self.trace_flags, "sampled": self.sampled,
                "tracestate": [list(item) for item in self.tracestate]}


def _rand_hex(n_bytes: int, rng: Optional[RandBytes]) -> str:
    raw = (rng(n_bytes) if rng is not None else os.urandom(n_bytes))
    value = raw[:n_bytes].rjust(n_bytes, b"\x00")
    if not any(value):                       # all-zero IDs are invalid
        value = (b"\x00" * (n_bytes - 1)) + b"\x01"
    return value.hex()


def new_trace_id(rng: Optional[RandBytes] = None) -> str:
    """Return a random 16-byte (32 hex) trace id."""
    return _rand_hex(16, rng)


def new_span_id(rng: Optional[RandBytes] = None) -> str:
    """Return a random 8-byte (16 hex) span id."""
    return _rand_hex(8, rng)


def new_root_context(rng: Optional[RandBytes] = None, *,
                     sampled: bool = True) -> SpanContext:
    """Create a fresh root span context with new trace and span IDs."""
    return SpanContext(new_trace_id(rng), new_span_id(rng),
                       _FLAG_SAMPLED if sampled else 0)


def child_context(parent: SpanContext,
                  rng: Optional[RandBytes] = None) -> SpanContext:
    """Create a child context: same trace, new span id, inherited state.

    Flag bits this implementation does not know are cleared, as W3C Trace
    Context 3.2.2.5 requires of a vendor that propagates them (``ff`` was
    passed on unchanged).
    """
    return SpanContext(parent.trace_id, new_span_id(rng), parent.trace_flags & _KNOWN_FLAGS,
                       list(parent.tracestate))


def _valid_member(key: str, value: str) -> bool:
    return bool(_TRACESTATE_KEY_RE.fullmatch(key) and _TRACESTATE_VALUE_RE.fullmatch(value))


def parse_tracestate(header: Optional[str]) -> List[Tuple[str, str]]:
    """Parse a ``tracestate`` header into an ordered list of (key, value).

    Only optional whitespace around the commas is trimmed: a value may begin
    with spaces (W3C Trace Context 3.3.1.3.2), which used to be stripped. A
    member whose value breaks the grammar -- empty, ``=`` or ``,`` inside, over
    256 characters, a control character such as the CR LF that used to be
    written back out -- is discarded. Parsing stops after 32 members, and a
    duplicated key makes the whole header invalid.
    """
    items: List[Tuple[str, str]] = []
    seen = set()
    for member in (header or "").split(","):
        member = member.strip(_OWS)
        if not member:
            continue
        key, sep, value = member.partition("=")
        if not sep or not _valid_member(key, value):
            continue
        if key in seen:
            return []
        seen.add(key)
        items.append((key, value))
        if len(items) == _MAX_MEMBERS:
            break               # 3.3.1.1: at most 32; a set and this stop keep the work linear
    return items


def format_tracestate(items: List[Tuple[str, str]]) -> str:
    """Serialise (key, value) pairs into a ``tracestate`` header value.

    A pair that breaks the key or value grammar raises
    :class:`TraceContextError` rather than reaching an outgoing header.
    """
    members = list(items)[:_MAX_MEMBERS]
    for key, value in members:
        if not (isinstance(key, str) and isinstance(value, str) and _valid_member(key, value)):
            raise TraceContextError(f"invalid tracestate member: {key!r}={value!r}")
    return ",".join(f"{key}={value}" for key, value in members)


def parse_traceparent(header: str) -> SpanContext:
    """Parse a ``traceparent`` header into a :class:`SpanContext`.

    A version above ``00`` is read as ``00`` and any fields after the flags
    are ignored (W3C Trace Context 4.3), so a newer caller's trace continues
    instead of a new one starting; ``ff`` is invalid.
    """
    parts = (header or "").strip(_OWS).split("-")          # only HTTP OWS, not a line break or NBSP
    version = parts[0]
    if not _VERSION_RE.fullmatch(version) or version == "ff":
        raise TraceContextError(f"invalid traceparent version: {version!r}")
    if len(parts) < 4 or (version == _VERSION and len(parts) != 4):
        raise TraceContextError(f"traceparent must have 4 fields: {header!r}")
    trace_id, span_id, flags = parts[1:4]
    _validate_traceparent_fields(trace_id, span_id, flags)
    return SpanContext(trace_id, span_id, int(flags, 16))


def _validate_traceparent_fields(trace_id: str, span_id: str, flags: str) -> None:
    # fullmatch: "$" also matches before a trailing newline, so an id ending
    # in "\n" passed and was written back into an outgoing header.
    if not _TRACE_ID_RE.fullmatch(trace_id) or trace_id == "0" * 32:
        raise TraceContextError(f"invalid trace id: {trace_id!r}")
    if not _SPAN_ID_RE.fullmatch(span_id) or span_id == "0" * 16:
        raise TraceContextError(f"invalid span id: {span_id!r}")
    if not _FLAGS_RE.fullmatch(flags):
        raise TraceContextError(f"invalid trace flags: {flags!r}")


def format_traceparent(ctx: SpanContext) -> str:
    """Serialise a :class:`SpanContext` into a ``traceparent`` header value.

    The fields are validated first: a hand-built context wrote a CR LF in its
    trace id, or flags of 256 as ``-100``, straight into the header.
    """
    flags = ctx.trace_flags
    if isinstance(flags, bool) or not isinstance(flags, int) or not 0 <= flags <= 0xFF:
        raise TraceContextError(f"invalid trace flags: {flags!r}")
    _validate_traceparent_fields(str(ctx.trace_id), str(ctx.span_id), f"{flags:02x}")
    return f"{_VERSION}-{ctx.trace_id}-{ctx.span_id}-{flags:02x}"


def inject_context(headers: Optional[Dict[str, str]],
                   ctx: SpanContext) -> Dict[str, str]:
    """Return ``headers`` with ``traceparent`` (+ ``tracestate``) set."""
    out = dict(headers or {})
    out["traceparent"] = format_traceparent(ctx)
    if ctx.tracestate:
        out["tracestate"] = format_tracestate(ctx.tracestate)
    return out


def extract_context(headers: Optional[Dict[str, str]]) -> Optional[SpanContext]:
    """Extract a :class:`SpanContext` from request headers, or ``None``.

    An invalid ``traceparent`` is ``None`` too -- W3C Trace Context says to
    ignore it and start a new trace; it used to raise out of the handler.
    """
    lookup = {str(key).lower(): value for key, value in (headers or {}).items()}
    raw = lookup.get("traceparent")
    if not raw:
        return None
    try:
        ctx = parse_traceparent(raw)
    except TraceContextError:
        return None
    state = parse_tracestate(lookup.get("tracestate"))
    return SpanContext(ctx.trace_id, ctx.span_id, ctx.trace_flags, state)
