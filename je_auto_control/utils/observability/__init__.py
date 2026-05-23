"""Phase 10.1: Prometheus-format metrics + OpenTelemetry-compatible traces.

A production deployment needs to answer "is this thing healthy?" and
"where did that 30-second click hang?" without anyone diffing log
files. This package answers both:

* :mod:`metrics` — process-wide Counter / Gauge / Histogram registry
  rendered as Prometheus text on demand. No hard dependency on
  ``prometheus_client``; when the package is installed it is honored,
  otherwise the bundled stdlib implementation is what gets exported.

* :mod:`tracing` — minimal OpenTelemetry-compatible tracer wrapper.
  When the ``opentelemetry-api`` package is importable, spans go
  through it (and downstream OTLP / Jaeger / Datadog exporters);
  otherwise a no-op tracer keeps every call site cost-free.

* :mod:`exporter` — tiny stdlib HTTP server that serves the
  Prometheus ``/metrics`` endpoint on a configurable port. Drop it
  next to the REST API and Grafana scrape works out of the box.

Hot-path instrumentation (e.g. ``record_action``) is wired into the
executor + agent loop so users get a real Prometheus dashboard
without instrumenting individual scripts.
"""
from je_auto_control.utils.observability.exporter import (
    PrometheusExporter, default_exporter, render_metrics_text,
)
from je_auto_control.utils.observability.metrics import (
    Counter, Gauge, Histogram, MetricRegistry, default_registry,
)
from je_auto_control.utils.observability.tracing import (
    NoOpSpan, NoOpTracer, Span, Tracer, default_tracer, traced,
)

__all__ = [
    "Counter", "Gauge", "Histogram", "MetricRegistry", "default_registry",
    "NoOpSpan", "NoOpTracer", "Span", "Tracer", "default_tracer", "traced",
    "PrometheusExporter", "default_exporter", "render_metrics_text",
]
