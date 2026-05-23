"""Stdlib HTTP server that serves the Prometheus text format on ``/metrics``."""
from __future__ import annotations

import http.server
import threading
from typing import Optional

from je_auto_control.utils.observability.metrics import (
    MetricRegistry, default_registry,
)


_PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


def render_metrics_text(registry: Optional[MetricRegistry] = None) -> str:
    """Render the registry as Prometheus text — what scrapers want."""
    return (registry or default_registry()).render()


class _MetricsHandler(http.server.BaseHTTPRequestHandler):
    """One per-request handler. ``server._registry`` carries the source."""

    server_version = "AutoControlObservability/1.0"
    sys_version = ""

    def do_GET(self) -> None:  # noqa: N802 BaseHTTPRequestHandler protocol
        if self.path not in ("/", "/metrics"):
            self.send_error(404, "Not Found")
            return
        registry: MetricRegistry = getattr(
            self.server, "_registry", default_registry(),
        )
        body = render_metrics_text(registry).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", _PROMETHEUS_CONTENT_TYPE)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # Silence the default access log to keep the operator's stderr clean —
    # the scrape happens every 15 s and would otherwise drown real logs.
    def log_message(self, format: str, *args) -> None:  # noqa: A002, D401
        return


class PrometheusExporter:
    """Mini HTTP server (port-pickable) serving Prometheus ``/metrics``."""

    def __init__(self,
                 *, host: str = "127.0.0.1",
                 port: int = 9090,
                 registry: Optional[MetricRegistry] = None) -> None:
        self._host = host
        self._port = int(port)
        self._registry = registry or default_registry()
        self._server: Optional[http.server.ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def port(self) -> int:
        return self._port

    @property
    def is_running(self) -> bool:
        return self._server is not None

    def start(self) -> int:
        if self.is_running:
            return self._port
        server = http.server.ThreadingHTTPServer(
            (self._host, self._port), _MetricsHandler,
        )
        server._registry = self._registry  # type: ignore[attr-defined]
        self._port = server.server_address[1]
        self._server = server
        self._thread = threading.Thread(
            target=server.serve_forever, name="metrics-exporter",
            daemon=True,
        )
        self._thread.start()
        return self._port

    def stop(self) -> None:
        if not self.is_running:
            return
        try:
            self._server.shutdown()
        except (OSError, RuntimeError):
            pass
        try:
            self._server.server_close()
        except OSError:
            pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._server = None
        self._thread = None


_default_exporter: Optional[PrometheusExporter] = None
_default_lock = threading.Lock()


def default_exporter() -> PrometheusExporter:
    """Lazy process-wide exporter; starts on first ``.start()`` call."""
    global _default_exporter
    with _default_lock:
        if _default_exporter is None:
            _default_exporter = PrometheusExporter()
        return _default_exporter


__all__ = [
    "PrometheusExporter", "default_exporter", "render_metrics_text",
]
