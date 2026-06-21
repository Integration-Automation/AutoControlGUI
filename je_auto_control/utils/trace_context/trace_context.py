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
_TRACESTATE_KEY_RE = re.compile(r"^[a-z0-9][_0-9a-z\-*/]{0,255}$")
_FLAG_SAMPLED = 0x01

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
    """Create a child context: same trace, new span id, inherited state."""
    return SpanContext(parent.trace_id, new_span_id(rng), parent.trace_flags,
                       list(parent.tracestate))


def parse_tracestate(header: Optional[str]) -> List[Tuple[str, str]]:
    """Parse a ``tracestate`` header into an ordered list of (key, value)."""
    items: List[Tuple[str, str]] = []
    for member in (header or "").split(","):
        member = member.strip()
        if not member:
            continue
        key, sep, value = member.partition("=")
        if sep and _TRACESTATE_KEY_RE.match(key.strip()):
            items.append((key.strip(), value.strip()))
    return items[:32]


def format_tracestate(items: List[Tuple[str, str]]) -> str:
    """Serialise (key, value) pairs into a ``tracestate`` header value."""
    return ",".join(f"{key}={value}" for key, value in items[:32])


def parse_traceparent(header: str) -> SpanContext:
    """Parse a ``traceparent`` header into a :class:`SpanContext`."""
    parts = (header or "").strip().split("-")
    if len(parts) != 4:
        raise TraceContextError(f"traceparent must have 4 fields: {header!r}")
    version, trace_id, span_id, flags = parts
    _validate_traceparent_fields(version, trace_id, span_id, flags)
    return SpanContext(trace_id, span_id, int(flags, 16))


def _validate_traceparent_fields(version: str, trace_id: str, span_id: str,
                                 flags: str) -> None:
    if version != _VERSION:
        raise TraceContextError(f"unsupported traceparent version: {version!r}")
    if not _TRACE_ID_RE.match(trace_id) or trace_id == "0" * 32:
        raise TraceContextError(f"invalid trace id: {trace_id!r}")
    if not _SPAN_ID_RE.match(span_id) or span_id == "0" * 16:
        raise TraceContextError(f"invalid span id: {span_id!r}")
    if not _FLAGS_RE.match(flags):
        raise TraceContextError(f"invalid trace flags: {flags!r}")


def format_traceparent(ctx: SpanContext) -> str:
    """Serialise a :class:`SpanContext` into a ``traceparent`` header value."""
    return f"{_VERSION}-{ctx.trace_id}-{ctx.span_id}-{ctx.trace_flags:02x}"


def inject_context(headers: Optional[Dict[str, str]],
                   ctx: SpanContext) -> Dict[str, str]:
    """Return ``headers`` with ``traceparent`` (+ ``tracestate``) set."""
    out = dict(headers or {})
    out["traceparent"] = format_traceparent(ctx)
    if ctx.tracestate:
        out["tracestate"] = format_tracestate(ctx.tracestate)
    return out


def extract_context(headers: Optional[Dict[str, str]]) -> Optional[SpanContext]:
    """Extract a :class:`SpanContext` from request headers, or ``None``."""
    lookup = {str(key).lower(): value for key, value in (headers or {}).items()}
    raw = lookup.get("traceparent")
    if not raw:
        return None
    ctx = parse_traceparent(raw)
    state = parse_tracestate(lookup.get("tracestate"))
    return SpanContext(ctx.trace_id, ctx.span_id, ctx.trace_flags, state)
