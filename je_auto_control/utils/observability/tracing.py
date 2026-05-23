"""OpenTelemetry-compatible tracer wrapper with a no-op fallback."""
from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Iterator, Optional


class NoOpSpan:
    """The shape we hand back when no real tracer is configured."""

    __slots__ = ("name", "attributes", "start_ns", "end_ns")

    def __init__(self, name: str) -> None:
        self.name = name
        self.attributes: dict = {}
        self.start_ns = time.monotonic_ns()
        self.end_ns: Optional[int] = None

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def record_exception(self, exception: BaseException) -> None:
        self.attributes["exception.type"] = type(exception).__name__
        self.attributes["exception.message"] = str(exception)

    def end(self) -> None:
        if self.end_ns is None:
            self.end_ns = time.monotonic_ns()

    @property
    def duration_ns(self) -> int:
        if self.end_ns is None:
            return 0
        return self.end_ns - self.start_ns


# Alias so callers can type-hint ``Span``; the OTel-backed tracer returns
# whatever ``otel.trace.Span`` is, but it ducktypes the same interface.
Span = NoOpSpan


class NoOpTracer:
    """Tracer that creates :class:`NoOpSpan` objects. Always available."""

    name = "noop"

    @contextmanager
    def start_as_current_span(self,
                              name: str,
                              attributes: Optional[dict] = None,
                              ) -> Iterator[Span]:
        span = NoOpSpan(name)
        if attributes:
            for k, v in attributes.items():
                span.set_attribute(k, v)
        try:
            yield span
        except BaseException as exc:
            span.record_exception(exc)
            raise
        finally:
            span.end()


class _OtelTracerAdapter:
    """Thin wrapper around ``opentelemetry.trace.Tracer`` for our protocol."""

    name = "opentelemetry"

    def __init__(self, otel_tracer: Any) -> None:
        self._tracer = otel_tracer

    @contextmanager
    def start_as_current_span(self,
                              name: str,
                              attributes: Optional[dict] = None,
                              ) -> Iterator[Any]:
        with self._tracer.start_as_current_span(
                name, attributes=attributes or None,
        ) as span:
            yield span


def _try_otel_tracer(name: str) -> Optional[_OtelTracerAdapter]:
    """Return a real OpenTelemetry tracer when the SDK is importable."""
    try:
        from opentelemetry import trace
    except ImportError:
        return None
    return _OtelTracerAdapter(trace.get_tracer(name))


class Tracer:
    """Polymorphic tracer — real OTel or no-op, decided at first use."""

    def __init__(self, name: str = "je_auto_control",
                 *, force_noop: bool = False) -> None:
        self._name = name
        self._force_noop = force_noop
        self._inner: Optional[Any] = None
        self._lock = threading.Lock()

    @property
    def backend_name(self) -> str:
        return self._resolve_inner().name

    @contextmanager
    def start_as_current_span(self, name: str,
                              attributes: Optional[dict] = None,
                              ) -> Iterator[Any]:
        inner = self._resolve_inner()
        with inner.start_as_current_span(name, attributes) as span:
            yield span

    def _resolve_inner(self) -> Any:
        with self._lock:
            if self._inner is not None:
                return self._inner
            if not self._force_noop:
                otel = _try_otel_tracer(self._name)
                if otel is not None:
                    self._inner = otel
                    return otel
            self._inner = NoOpTracer()
            return self._inner


_default_tracer: Optional[Tracer] = None
_default_lock = threading.Lock()


def default_tracer() -> Tracer:
    """Lazy process-wide tracer."""
    global _default_tracer
    with _default_lock:
        if _default_tracer is None:
            _default_tracer = Tracer()
        return _default_tracer


def traced(span_name: Optional[str] = None,
           *, tracer: Optional[Tracer] = None,
           record_args: bool = False) -> Callable[..., Callable[..., Any]]:
    """Decorator: wrap a callable in a span. ``span_name`` defaults to ``f.__qualname__``."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        name = span_name or getattr(fn, "__qualname__", fn.__name__)

        @wraps(fn)
        def wrapper(*args, **kwargs):
            real_tracer = tracer or default_tracer()
            attrs = None
            if record_args:
                attrs = {
                    f"arg.{i}": repr(a)[:120] for i, a in enumerate(args)
                }
                attrs.update({
                    f"kwarg.{k}": repr(v)[:120] for k, v in kwargs.items()
                })
            with real_tracer.start_as_current_span(name, attrs):
                return fn(*args, **kwargs)

        return wrapper

    return decorator


__all__ = [
    "NoOpSpan", "NoOpTracer", "Span", "Tracer", "default_tracer", "traced",
]
