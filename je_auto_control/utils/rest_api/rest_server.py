"""HTTP front-end for the AutoControl headless API.

Routes requests to handler functions in :mod:`rest_handlers`, applies the
bearer-token + per-IP rate-limit gate from :mod:`rest_auth`, and writes
each authenticated request to the audit log so misuse is traceable.

Defaults to ``127.0.0.1`` per the security policy in CLAUDE.md; binding
to ``0.0.0.0`` requires an explicit caller decision.
"""
from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.parse import urlparse

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.rest_api.rest_auth import RestAuthGate, generate_token
from je_auto_control.utils.rest_api.rest_handlers import (
    HandlerResult, RouteContext,
    handle_audit_list, handle_audit_verify,
    handle_commands, handle_config_export, handle_config_import,
    handle_diagnose, handle_execute, handle_execute_file,
    handle_health, handle_history, handle_inspector_recent,
    handle_inspector_summary, handle_jobs, handle_mouse_position,
    handle_openapi, handle_remote_sessions, handle_screen_size,
    handle_screenshot, handle_usb_devices, handle_usb_events, handle_windows,
)
from je_auto_control.utils.rest_api.rest_metrics import RestMetrics


HandlerFn = Callable[[RouteContext], HandlerResult]

_GET_ROUTES: Dict[str, HandlerFn] = {
    "/health": handle_health,
    "/jobs": handle_jobs,
    "/history": handle_history,
    "/screenshot": handle_screenshot,
    "/mouse_position": handle_mouse_position,
    "/screen_size": handle_screen_size,
    "/windows": handle_windows,
    "/sessions": handle_remote_sessions,
    "/commands": handle_commands,
    "/audit/list": handle_audit_list,
    "/audit/verify": handle_audit_verify,
    "/inspector/recent": handle_inspector_recent,
    "/inspector/summary": handle_inspector_summary,
    "/usb/devices": handle_usb_devices,
    "/usb/events": handle_usb_events,
    "/diagnose": handle_diagnose,
    "/openapi.json": handle_openapi,
}

_POST_ROUTES: Dict[str, HandlerFn] = {
    "/execute": handle_execute,
    "/execute_file": handle_execute_file,
    "/config/export": handle_config_export,
    "/config/import": handle_config_import,
}

# /health is intentionally unauthenticated so probes / load balancers
# can liveness-check without holding the bearer token.
_PUBLIC_PATHS = frozenset({"/health"})

_MAX_BODY_BYTES = 1_000_000


class _RestRequestHandler(BaseHTTPRequestHandler):
    """Stdlib request handler — delegates to gate + route table."""

    server_version = "AutoControlREST/2.0"

    def log_message(self, format, *args) -> None:  # noqa: A002  # pylint: disable=redefined-builtin  # reason: stdlib BaseHTTPRequestHandler override
        autocontrol_logger.info("rest-api %s - %s",
                                self.address_string(), format % args)

    def do_GET(self) -> None:  # noqa: N802  # reason: stdlib API
        parsed = urlparse(self.path)
        if parsed.path == "/metrics":
            self._serve_metrics()
            return
        if parsed.path == "/dashboard" or parsed.path.startswith("/dashboard/"):
            self._serve_dashboard(parsed.path)
            return
        if parsed.path == "/docs":
            self._serve_dashboard("/dashboard/swagger.html")
            return
        self._dispatch("GET", _GET_ROUTES, body=None)

    def _serve_dashboard(self, path: str) -> None:
        if path == "/dashboard":
            asset = "index.html"
        else:
            asset = path[len("/dashboard/"):]
        body, content_type, status = _load_dashboard_asset(asset)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        # Static assets — safe to cache briefly inside the same session.
        self.send_header("Cache-Control", "private, max-age=60")
        self.end_headers()
        self.wfile.write(body)
        self._metrics().record_request("GET", "/dashboard", status)

    def _serve_metrics(self) -> None:
        client_ip = self.client_address[0] if self.client_address else "?"
        verdict = self._gate().check(
            client_ip=client_ip,
            header_value=self.headers.get("Authorization"),
        )
        if verdict != "ok":
            if verdict == "unauthorized":
                self._metrics().record_failed_auth()
            self._reject(verdict)
            self._metrics().record_request(
                "GET", "/metrics", _verdict_to_status(verdict),
            )
            return
        body = self._metrics().render(
            audit_row_count=_count_audit_rows(getattr(self.server, "audit_log", None)),
            active_sessions=_count_active_sessions(),
            scheduler_jobs=_count_scheduler_jobs(),
        ).encode("utf-8")
        self.send_response(200)
        self.send_header(
            "Content-Type", "text/plain; version=0.0.4; charset=utf-8",
        )
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self._metrics().record_request("GET", "/metrics", 200)

    def do_POST(self) -> None:  # noqa: N802  # reason: stdlib API
        body = self._read_json_body()
        if body is _BODY_ERROR_SENT:
            return
        self._dispatch("POST", _POST_ROUTES, body=body)

    def _dispatch(self, method: str, routes: Dict[str, HandlerFn],
                  body: Any) -> None:
        parsed = urlparse(self.path)
        handler = routes.get(parsed.path)
        if handler is None:
            self._send_json({"error": "unknown path"}, status=404)
            return
        client_ip = self.client_address[0] if self.client_address else "?"
        if parsed.path not in _PUBLIC_PATHS:
            verdict = self._gate().check(
                client_ip=client_ip,
                header_value=self.headers.get("Authorization"),
            )
            if verdict != "ok":
                if verdict == "unauthorized":
                    self._metrics().record_failed_auth()
                self._reject(verdict)
                self._audit(method, parsed.path, client_ip, verdict)
                self._metrics().record_request(
                    method, parsed.path, _verdict_to_status(verdict),
                )
                return
        ctx = RouteContext(query=parsed.query, body=body, client_ip=client_ip)
        try:
            status, payload = handler(ctx)
        except (OSError, RuntimeError, ValueError, TypeError,
                AutoControlException) as error:
            autocontrol_logger.error(
                "rest-api %s %s handler raised: %r", method, parsed.path, error,
            )
            self._send_json({"error": "handler crashed"}, status=500)
            self._audit(method, parsed.path, client_ip, "error")
            self._metrics().record_request(method, parsed.path, 500)
            return
        self._send_json(payload, status=status, default=str)
        if parsed.path not in _PUBLIC_PATHS:
            self._audit(method, parsed.path, client_ip, f"ok:{status}")
        self._metrics().record_request(method, parsed.path, status)

    def _gate(self) -> RestAuthGate:
        return self.server.auth_gate  # type: ignore[attr-defined]

    def _metrics(self) -> RestMetrics:
        return self.server.metrics  # type: ignore[attr-defined]

    def _audit(self, method: str, path: str, client_ip: str,
               outcome: str) -> None:
        audit = getattr(self.server, "audit_log", None)
        if audit is None:
            return
        try:
            audit.log(
                "rest_api", host_id=client_ip,
                detail=f"{method} {path} -> {outcome}",
            )
        except (OSError, RuntimeError) as error:
            autocontrol_logger.warning("rest-api audit write failed: %r", error)

    def _reject(self, verdict: str) -> None:
        if verdict == "rate_limited":
            self._send_json({"error": "rate limited"}, status=429)
        elif verdict == "locked_out":
            self._send_json({"error": "too many failed auth attempts"},
                            status=429)
        else:
            self._send_json({"error": "unauthorized"}, status=401)

    def _read_json_body(self) -> Any:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0 or length > _MAX_BODY_BYTES:
            self._send_json({"error": "invalid Content-Length"}, status=400)
            return _BODY_ERROR_SENT
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError:
            self._send_json({"error": "invalid JSON"}, status=400)
            return _BODY_ERROR_SENT

    def _send_json(self, payload: Dict[str, Any], status: int = 200,
                   default=None) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=default).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


_BODY_ERROR_SENT = object()


def _verdict_to_status(verdict: str) -> int:
    if verdict in ("rate_limited", "locked_out"):
        return 429
    return 401


def _count_audit_rows(audit: Any) -> int:
    if audit is None:
        return 0
    try:
        rows = audit.query(limit=1_000_000)
    except (OSError, RuntimeError):
        return 0
    return len(rows)


def _count_active_sessions() -> int:
    try:
        from je_auto_control.utils.remote_desktop.registry import registry
        host = registry.host_status()
        viewer = registry.viewer_status()
    except (OSError, RuntimeError, ImportError, AttributeError):
        return 0
    return int(bool(host.get("running"))) + int(bool(viewer.get("connected")))


def _count_scheduler_jobs() -> int:
    try:
        from je_auto_control.utils.scheduler.scheduler import default_scheduler
        return len(default_scheduler.list_jobs())
    except (OSError, RuntimeError, ImportError, AttributeError):
        return 0


_DASHBOARD_DIR = Path(__file__).resolve().parent / "dashboard"
_DASHBOARD_MIME: Dict[str, str] = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
}
# Conservative whitelist — alphanumerics, dot, dash, underscore. No path
# separators, no parent traversal, no leading dots.
_DASHBOARD_ASSET_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]*$")


def _load_dashboard_asset(asset: str) -> Tuple[bytes, str, int]:
    if not _DASHBOARD_ASSET_RE.match(asset):
        return b"not found", "text/plain; charset=utf-8", 404
    target = (_DASHBOARD_DIR / asset).resolve()
    try:
        target.relative_to(_DASHBOARD_DIR)
    except ValueError:
        return b"not found", "text/plain; charset=utf-8", 404
    if not target.is_file():
        return b"not found", "text/plain; charset=utf-8", 404
    suffix = target.suffix.lower()
    mime = _DASHBOARD_MIME.get(suffix, "application/octet-stream")
    try:
        body = target.read_bytes()
    except OSError as error:
        autocontrol_logger.warning("dashboard asset read %s: %r", asset, error)
        return b"read error", "text/plain; charset=utf-8", 500
    return body, mime, 200


class RestApiServer:
    """Owns the HTTP server thread, the auth gate, and the audit handle."""

    def __init__(self, host: str = "127.0.0.1", port: int = 9939,
                 *, token: Optional[str] = None,
                 enable_audit: bool = True) -> None:
        self._address: Tuple[str, int] = (host, port)
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._token = token if token else generate_token()
        self._auth = RestAuthGate(expected_token=self._token)
        self._audit_log = self._open_audit_log() if enable_audit else None
        self._metrics = RestMetrics()

    @staticmethod
    def _open_audit_log() -> Any:
        try:
            from je_auto_control.utils.remote_desktop.audit_log import (
                default_audit_log,
            )
            return default_audit_log()
        except (OSError, RuntimeError, ImportError) as error:
            autocontrol_logger.warning("rest-api audit unavailable: %r", error)
            return None

    @property
    def address(self) -> Tuple[str, int]:
        return self._address

    @property
    def token(self) -> str:
        return self._token

    @property
    def is_running(self) -> bool:
        return self._server is not None

    @property
    def base_url(self) -> str:
        host, port = self._address
        return f"http://{host}:{port}"

    def start(self) -> None:
        if self._server is not None:
            return
        server = ThreadingHTTPServer(self._address, _RestRequestHandler)
        server.auth_gate = self._auth  # type: ignore[attr-defined]
        server.audit_log = self._audit_log  # type: ignore[attr-defined]
        server.metrics = self._metrics  # type: ignore[attr-defined]
        self._address = server.server_address[:2]
        self._server = server
        self._thread = threading.Thread(
            target=server.serve_forever, daemon=True, name="AutoControlREST",
        )
        self._thread.start()
        autocontrol_logger.info(
            "REST API listening on %s:%d (audit=%s)",
            self._address[0], self._address[1],
            "on" if self._audit_log is not None else "off",
        )

    def stop(self, timeout: float = 2.0) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        self._server = None
        self._thread = None
        autocontrol_logger.info("REST API stopped")


def start_rest_api_server(host: str = "127.0.0.1", port: int = 9939,
                          *, token: Optional[str] = None,
                          enable_audit: bool = True) -> RestApiServer:
    """Construct, start, and return a ``RestApiServer``."""
    server = RestApiServer(
        host=host, port=port, token=token, enable_audit=enable_audit,
    )
    server.start()
    return server


__all__ = ["RestApiServer", "start_rest_api_server"]
