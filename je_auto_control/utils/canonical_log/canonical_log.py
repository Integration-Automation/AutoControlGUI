"""Canonical (wide-event) log lines and structured JSON log formatting.

``logging_instance`` emits a fixed pipe-delimited human string with no JSON
option and no trace/span fields, but OTel log-trace correlation needs
``trace_id`` / ``span_id`` on each record. This adds a Stripe-style canonical
log line (one wide field-bag emitted per run) and a JSON ``logging.Formatter``
that carries trace context.

Pure standard library (``json`` / ``logging``); imports no ``PySide6``. The
timer clock is injectable, so durations are deterministic in CI.
"""
import json
import logging
import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, Mapping, Optional

_STANDARD = frozenset(vars(logging.makeLogRecord({})))


class CanonicalLogLine:
    """A request-scoped accumulator emitting one wide log line."""

    def __init__(self, fields: Optional[Mapping[str, Any]] = None, *,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._fields: Dict[str, Any] = dict(fields or {})
        self._clock = clock

    def add(self, key: str, value: Any) -> "CanonicalLogLine":
        """Add or overwrite one field; returns self for chaining."""
        self._fields[str(key)] = value
        return self

    def update(self, mapping: Mapping[str, Any]) -> "CanonicalLogLine":
        """Merge a mapping of fields."""
        for key, value in mapping.items():
            self._fields[str(key)] = value
        return self

    @contextmanager
    def timer(self, name: str) -> Iterator[None]:
        """Time a block, recording ``{name}_ms`` on completion."""
        start = self._clock()
        try:
            yield
        finally:
            self._fields[f"{name}_ms"] = round((self._clock() - start) * 1000, 3)

    def to_dict(self) -> Dict[str, Any]:
        """Return the accumulated fields."""
        return dict(self._fields)

    def render(self) -> str:
        """Render the line as a single JSON object (sorted keys)."""
        return json.dumps(self._fields, sort_keys=True, default=str)

    def emit(self, sink: Callable[[Dict[str, Any]], Any]) -> "CanonicalLogLine":
        """Send the field dict to ``sink`` (e.g. a logger or a list append)."""
        sink(self.to_dict())
        return self


def bind_trace_context(line: CanonicalLogLine,
                       context: Any) -> CanonicalLogLine:
    """Attach ``trace_id`` / ``span_id`` from a SpanContext to ``line``."""
    return line.add("trace_id", context.trace_id).add("span_id",
                                                      context.span_id)


class JSONLogFormatter(logging.Formatter):
    """A ``logging.Formatter`` that emits one JSON object per record.

    Includes ``trace_id`` / ``span_id`` (and any non-standard ``extra=`` fields)
    when present, for OTel log-trace correlation.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {"level": record.levelname,
                                   "logger": record.name,
                                   "message": record.getMessage()}
        for key, value in vars(record).items():
            if key not in _STANDARD and not key.startswith("_"):
                payload[key] = value
        return json.dumps(payload, default=str)
