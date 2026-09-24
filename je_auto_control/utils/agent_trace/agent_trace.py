"""Record agent/LLM activity as OpenTelemetry GenAI-convention spans.

When automation drives an LLM agent, you want the same observability an
OpenTelemetry backend gives a service: per-operation spans carrying token usage,
model, and status. ``AgentTrace`` records spans whose attributes follow the
OTel **GenAI semantic conventions** (``gen_ai.operation.name``,
``gen_ai.system``, ``gen_ai.request.model``, ``gen_ai.usage.input_tokens`` /
``output_tokens``, ``gen_ai.tool.name``) and the convention span name
``"{operation} {model}"`` — :meth:`AgentTrace.to_otel` emits OTLP/JSON span
objects (ids, nanosecond times, typed attributes), while :meth:`summary` rolls up
cost/latency for a run.

It pairs with trajectory evaluation: record the run here, score it there. Pure
standard library (no ``opentelemetry`` dependency); the clock is injectable so
durations are deterministically testable. Imports no ``PySide6``.
"""
import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, List, Optional

from je_auto_control.utils.otlp_export.otlp_export import attributes_to_otlp
from je_auto_control.utils.trace_context.trace_context import new_span_id, new_trace_id

STATUS_OK = "ok"
STATUS_ERROR = "error"
# OTLP enum values (OTLP/JSON encodes enums as integers).
_SPAN_KIND_CLIENT = 3
_STATUS_CODE_OK, _STATUS_CODE_ERROR = 1, 2



def _genai_attributes(operation: str, model: Optional[str],
                      system: Optional[str], input_tokens: Optional[int],
                      output_tokens: Optional[int], tool_name: Optional[str],
                      extra: Dict[str, Any]) -> Dict[str, Any]:
    attributes: Dict[str, Any] = {"gen_ai.operation.name": operation}
    if system is not None:
        # gen_ai.provider.name is the current convention; gen_ai.system is kept
        # for backends that still read the older name.
        attributes["gen_ai.provider.name"] = system
        attributes["gen_ai.system"] = system
    if model is not None:
        attributes["gen_ai.request.model"] = model
    if input_tokens is not None:
        attributes["gen_ai.usage.input_tokens"] = int(input_tokens)
    if output_tokens is not None:
        attributes["gen_ai.usage.output_tokens"] = int(output_tokens)
    if tool_name is not None:
        attributes["gen_ai.tool.name"] = tool_name
    attributes.update(extra)
    return attributes


_RECORD_ARGUMENTS = frozenset({"model", "system", "input_tokens", "output_tokens", "tool_name"})

class AgentTrace:
    """Collects GenAI-convention spans for one agent run."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        """``clock`` returns a monotonic time; injectable for tests."""
        self._clock = clock
        self._spans: List[Dict[str, Any]] = []
        self._trace_id = new_trace_id()

    def record(self, operation: str, *, model: Optional[str] = None,
               system: Optional[str] = None,
               input_tokens: Optional[int] = None,
               output_tokens: Optional[int] = None,
               tool_name: Optional[str] = None, duration_s: float = 0.0,
               status: str = STATUS_OK,
               attributes: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Record a completed span and return it."""
        attrs = _genai_attributes(operation, model, system, input_tokens,
                                  output_tokens, tool_name, attributes or {})
        name = f"{operation} {model}" if model else operation
        end_ns = time.time_ns()
        span = {"name": name, "attributes": attrs,
                "duration_s": float(duration_s), "status": status,
                "span_id": new_span_id(), "end_ns": end_ns,
                "start_ns": end_ns - int(float(duration_s) * 1e9)}
        self._spans.append(span)
        return span

    @contextmanager
    def operation(self, operation: str, **kwargs: Any
                  ) -> Iterator[Dict[str, Any]]:
        """Time a block as a span; yields a mutable ``fields`` dict.

        Set token counts etc. on the yielded dict (e.g.
        ``fields['output_tokens'] = 42``); a raised exception marks the span
        ``error`` and re-raises.
        """
        fields: Dict[str, Any] = {}
        start = self._clock()
        try:
            yield fields
        except Exception:
            self._record_block(operation, start, STATUS_ERROR, kwargs, fields)
            raise
        self._record_block(operation, start, STATUS_OK, kwargs, fields)

    def _record_block(self, operation: str, start: float, status: str,
                      kwargs: Dict[str, Any], fields: Dict[str, Any]) -> None:
        """Record an :meth:`operation` span; ``fields`` win and extras become attributes.

        ``**kwargs, **fields`` raised TypeError when a field repeated an
        argument (``model``) or was not one (``cost_usd``) -- after the work
        was done, and on the error path in place of the caller's exception.
        """
        merged = {**kwargs, **fields}
        attributes = dict(merged.pop("attributes", None) or {})
        for key in [key for key in merged if key not in _RECORD_ARGUMENTS]:
            attributes[key] = merged.pop(key)
        self.record(operation, duration_s=self._clock() - start, status=status,
                    attributes=attributes or None, **merged)

    def spans(self) -> List[Dict[str, Any]]:
        """Return a copy of the recorded spans."""
        return [dict(span) for span in self._spans]

    def summary(self) -> Dict[str, Any]:
        """Roll up span count, errors, token usage, and total duration."""
        def _tokens(key: str) -> int:
            return sum(int(s["attributes"].get(key, 0)) for s in self._spans)
        return {
            "span_count": len(self._spans),
            "error_count": sum(1 for s in self._spans
                               if s["status"] == STATUS_ERROR),
            "input_tokens": _tokens("gen_ai.usage.input_tokens"),
            "output_tokens": _tokens("gen_ai.usage.output_tokens"),
            "duration_s": sum(s["duration_s"] for s in self._spans),
        }

    def to_otel(self) -> List[Dict[str, Any]]:
        """Export the spans as OTLP/JSON span objects.

        Every span shares this run's ``traceId`` and has its own ``spanId``;
        times are wall-clock nanoseconds (strings, as OTLP/JSON encodes
        64-bit integers), ``kind`` and ``status.code`` are the OTLP enum
        integers, and attributes are typed ``{key, value}`` pairs.
        """
        return [{
            "traceId": self._trace_id, "spanId": s["span_id"],
            "name": s["name"], "kind": _SPAN_KIND_CLIENT,
            "startTimeUnixNano": str(s["start_ns"]),
            "endTimeUnixNano": str(s["end_ns"]),
            "attributes": attributes_to_otlp(s["attributes"]),
            "status": {"code": _STATUS_CODE_ERROR if s["status"] == STATUS_ERROR
                       else _STATUS_CODE_OK},
        } for s in self._spans]

    def reset(self) -> None:
        """Drop all recorded spans and start a new trace id for the next run.

        Keeping the id made an OTLP backend merge the next run into this one.
        """
        self._spans.clear()
        self._trace_id = new_trace_id()


default_trace = AgentTrace()


def reset_trace() -> None:
    """Clear the module-level :data:`default_trace`."""
    default_trace.reset()
