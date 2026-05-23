"""Phase 10.1: Prometheus metrics + OpenTelemetry tracing tests."""
import socket
import urllib.error
import urllib.request

import pytest

from je_auto_control.utils.observability import (
    Counter, Gauge, Histogram, MetricRegistry, NoOpTracer,
    PrometheusExporter, Tracer, render_metrics_text, traced,
)


@pytest.fixture
def registry():
    return MetricRegistry()


# --- Counter --------------------------------------------------------

def test_counter_starts_at_zero_and_increments():
    counter = Counter("test_counter", "doc")
    assert counter.value() == pytest.approx(0.0)
    counter.inc()
    counter.inc(3)
    assert counter.value() == pytest.approx(4.0)


def test_counter_rejects_negative_increment():
    counter = Counter("test_counter", "doc")
    with pytest.raises(ValueError, match="non-negative"):
        counter.inc(-1)


def test_counter_with_labels_keeps_series_separate():
    counter = Counter("hits", "doc", label_names=("method",))
    counter.inc(labels={"method": "GET"})
    counter.inc(labels={"method": "GET"})
    counter.inc(labels={"method": "POST"})
    assert counter.value(labels={"method": "GET"}) == 2
    assert counter.value(labels={"method": "POST"}) == 1


def test_counter_rejects_unknown_labels():
    counter = Counter("hits", "doc", label_names=("method",))
    with pytest.raises(ValueError, match="unknown labels"):
        counter.inc(labels={"method": "GET", "extra": "x"})


def test_counter_requires_labels_when_declared():
    counter = Counter("hits", "doc", label_names=("method",))
    with pytest.raises(ValueError, match="expects labels"):
        counter.inc()


@pytest.mark.parametrize("bad_name", [
    "", "1bad", "bad-name", "with space", "back\\slash",
])
def test_counter_validates_name(bad_name):
    with pytest.raises(ValueError):
        Counter(bad_name, "doc")


def test_counter_render_emits_help_and_type():
    counter = Counter("hits", "the docstring")
    counter.inc(2)
    text = counter.render()
    assert "# HELP hits the docstring" in text
    assert "# TYPE hits counter" in text
    assert "hits 2" in text


# --- Gauge ----------------------------------------------------------

def test_gauge_set_inc_dec_round_trip():
    gauge = Gauge("mem", "doc")
    gauge.set(42)
    gauge.inc(3.5)
    gauge.dec(1.5)
    assert gauge.value() == pytest.approx(44.0)


def test_gauge_render_includes_value():
    gauge = Gauge("active", "doc")
    gauge.set(7)
    assert "active 7" in gauge.render()


# --- Histogram ------------------------------------------------------

def test_histogram_observe_increments_appropriate_buckets():
    histogram = Histogram(
        "latency_seconds", "doc",
        buckets=(0.1, 1.0, 10.0),
    )
    histogram.observe(0.05)  # → bucket 0.1
    histogram.observe(0.5)   # → buckets 1.0, 10.0
    histogram.observe(5.0)   # → bucket 10.0
    snap = histogram.snapshot()
    assert snap["count"] == 3
    assert snap["sum"] == pytest.approx(5.55)
    bucket_counts = dict(snap["buckets"])
    assert bucket_counts[0.1] == 1
    assert bucket_counts[1.0] == 2
    assert bucket_counts[10.0] == 3


def test_histogram_render_includes_inf_bucket_and_sum():
    histogram = Histogram("latency", "doc", buckets=(0.1, 1.0))
    histogram.observe(0.05)
    histogram.observe(2.0)
    text = histogram.render()
    assert 'latency_bucket{le="0.1"} 1' in text
    assert 'latency_bucket{le="1"} 1' in text or 'latency_bucket{le="1.0"} 1' in text
    assert 'latency_bucket{le="+Inf"} 2' in text
    assert "latency_count 2" in text


def test_histogram_requires_increasing_buckets():
    with pytest.raises(ValueError, match="strictly increasing"):
        Histogram("x", "doc", buckets=(1.0, 0.5))


# --- MetricRegistry -------------------------------------------------

def test_registry_register_returns_existing_on_collision(registry):
    counter_a = registry.register(Counter("hits", "doc"))
    counter_b = registry.register(Counter("hits", "different doc"))
    assert counter_a is counter_b


def test_registry_rejects_kind_mismatch(registry):
    registry.register(Counter("hits", "doc"))
    with pytest.raises(ValueError, match="already registered"):
        registry.register(Gauge("hits", "doc"))


def test_registry_render_concatenates_metrics(registry):
    registry.register(Counter("a", "doc")).inc(1)
    registry.register(Gauge("b", "doc")).set(2)
    text = registry.render()
    assert "TYPE a counter" in text
    assert "TYPE b gauge" in text


# --- Tracer ---------------------------------------------------------

def test_noop_tracer_yields_a_span_and_ends_it():
    tracer = Tracer(force_noop=True)
    with tracer.start_as_current_span("work") as span:
        span.set_attribute("k", "v")
        assert span.name == "work"
    assert span.end_ns is not None
    assert span.duration_ns >= 0


def test_noop_tracer_records_exceptions():
    tracer = Tracer(force_noop=True)
    with pytest.raises(RuntimeError):
        with tracer.start_as_current_span("boom") as span:
            raise RuntimeError("nope")
    assert span.attributes["exception.type"] == "RuntimeError"
    assert "nope" in span.attributes["exception.message"]


def test_traced_decorator_wraps_callable_in_span():
    tracer = Tracer(force_noop=True)
    @traced("my_op", tracer=tracer)
    def add(a, b):
        return a + b
    assert add(2, 3) == 5


def test_default_tracer_picks_noop_when_otel_missing():
    tracer = Tracer(force_noop=True)
    assert tracer.backend_name == "noop"
    assert isinstance(tracer._resolve_inner(), NoOpTracer)


# --- Prometheus exporter -------------------------------------------

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_render_metrics_text_uses_default_registry():
    # Default registry may be populated by other tests; either way the
    # output is a string. Best to register a marker metric and look for it.
    from je_auto_control.utils.observability import default_registry
    default_registry().register(Counter("marker_metric", "doc")).inc(1)
    text = render_metrics_text()
    assert "marker_metric 1" in text
    # Clean up.
    default_registry().unregister("marker_metric")


def test_exporter_serves_metrics_endpoint():
    registry = MetricRegistry()
    registry.register(Counter("served", "doc")).inc(7)
    exporter = PrometheusExporter(
        host="127.0.0.1", port=_free_port(), registry=registry,
    )
    exporter.start()
    try:
        url = f"http://127.0.0.1:{exporter.port}/metrics"
        with urllib.request.urlopen(url, timeout=2.0) as resp:
            body = resp.read().decode("utf-8")
            content_type = resp.headers.get("Content-Type", "")
        assert "served 7" in body
        assert content_type.startswith("text/plain")
    finally:
        exporter.stop()


def test_exporter_returns_404_on_unrelated_path():
    exporter = PrometheusExporter(host="127.0.0.1", port=_free_port())
    exporter.start()
    try:
        url = f"http://127.0.0.1:{exporter.port}/admin"
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(url, timeout=2.0)
        assert exc.value.code == 404
    finally:
        exporter.stop()


def test_exporter_start_stop_idempotent():
    exporter = PrometheusExporter(host="127.0.0.1", port=_free_port())
    exporter.start()
    exporter.start()  # no-op
    exporter.stop()
    exporter.stop()  # no-op
    assert exporter.is_running is False


# --- Executor metric integration ----------------------------------

def test_executor_increments_action_counter_on_success():
    from je_auto_control.utils.observability import default_registry
    from je_auto_control.utils.executor import action_executor as exec_mod
    # Force re-registration so we can count from a known baseline.
    exec_mod._EXECUTOR_METRIC_CACHE.clear()
    default_registry().unregister("autocontrol_action_calls_total")
    default_registry().unregister("autocontrol_action_duration_seconds")
    exec_mod._observe_executor_metrics(
        "AC_screenshot", started_at=0.0, error=None,
    )
    exec_mod._observe_executor_metrics(
        "AC_screenshot", started_at=0.0, error=RuntimeError("boom"),
    )
    counter = default_registry().get("autocontrol_action_calls_total")
    assert counter is not None
    assert counter.value(
        labels={"action": "AC_screenshot", "outcome": "ok"},
    ) == 1
    assert counter.value(
        labels={"action": "AC_screenshot", "outcome": "error"},
    ) == 1
