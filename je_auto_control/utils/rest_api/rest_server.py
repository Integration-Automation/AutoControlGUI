"""Simple REST API server using stdlib ``http.server``.

Endpoints::

    GET  /health                  → {"status": "ok"}
    POST /execute   body=JSON     → {"result": <executor record>}
    GET  /jobs                    → list of scheduler jobs

The server defaults to ``127.0.0.1`` and the caller must opt into binding
to ``0.0.0.0`` — matching the policy in CLAUDE.md.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.run_history.history_store import default_history_store


class _JSONHandler(BaseHTTPRequestHandler):
    """Dispatch HTTP calls into executor / scheduler primitives."""

    server_version = "AutoControlREST/1.0"

    # Suppress default stderr access logs — route through the project logger.
    def log_message(self, fmt: str, *args: Any) -> None:
        autocontrol_logger.info("rest-api %s - %s",
                                self.address_string(), fmt % args)

    def do_GET(self) -> None:  # noqa: N802  # reason: stdlib API
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_json({"status": "ok"})
            return
        if parsed.path == "/jobs":
            self._send_json({"jobs": self._serialize_jobs()})
            return
        if parsed.path == "/history":
            self._send_json(
                {"runs": self._serialize_history(parsed.query)},
                default=str,
            )
            return
        autocontrol_logger.info("rest-api unknown GET path: %r", self.path)
        self._send_json({"error": "unknown path"}, status=404)

    def do_POST(self) -> None:  # noqa: N802  # reason: stdlib API
        if self.path != "/execute":
            autocontrol_logger.info("rest-api unknown POST path: %r", self.path)
            self._send_json({"error": "unknown path"}, status=404)
            return
        payload = self._read_json_body()
        if payload is None:
            return
        actions = payload.get("actions") if isinstance(payload, dict) else None
        if actions is None:
            self._send_json({"error": "missing 'actions' field"}, status=400)
            return
        try:
            from je_auto_control.utils.executor.action_executor import execute_action
            result = execute_action(actions)
        except (OSError, RuntimeError, ValueError, TypeError) as error:
            autocontrol_logger.error("rest-api execute_action failed: %r", error)
            self._send_json({"error": "execute_action failed"}, status=500)
            return
        self._send_json({"result": result}, default=str)

    # --- helpers -------------------------------------------------------------

    def _read_json_body(self) -> Optional[Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0 or length > 1_000_000:
            self._send_json({"error": "invalid Content-Length"}, status=400)
            return None
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError as error:
            autocontrol_logger.info("rest-api invalid JSON body: %r", error)
            self._send_json({"error": "invalid JSON"}, status=400)
            return None

    def _send_json(self, payload: Dict[str, Any], status: int = 200,
                   default=None) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=default).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    @staticmethod
    def _serialize_jobs() -> list:
        from je_auto_control.utils.scheduler.scheduler import default_scheduler
        return [
            {
                "job_id": job.job_id, "script_path": job.script_path,
                "interval_seconds": job.interval_seconds,
                "is_cron": job.is_cron, "repeat": job.repeat,
                "runs": job.runs, "enabled": job.enabled,
            }
            for job in default_scheduler.list_jobs()
        ]

    @staticmethod
    def _serialize_history(query: str) -> List[Dict[str, Any]]:
        params = parse_qs(query)
        try:
            limit = int(params.get("limit", ["100"])[0])
        except ValueError:
            limit = 100
        source_type = params.get("source_type", [None])[0] or None
        try:
            rows = default_history_store.list_runs(
                limit=limit, source_type=source_type,
            )
        except ValueError:
            return []
        return [
            {
                "id": r.id, "source_type": r.source_type,
                "source_id": r.source_id, "script_path": r.script_path,
                "started_at": r.started_at, "finished_at": r.finished_at,
                "status": r.status, "error_text": r.error_text,
                "duration_seconds": r.duration_seconds,
            }
            for r in rows
        ]


class RestApiServer:
    """Thin wrapper that owns the HTTP server + its background thread."""

    def __init__(self, host: str = "127.0.0.1", port: int = 9939) -> None:
        self._address: Tuple[str, int] = (host, port)
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def address(self) -> Tuple[str, int]:
        return self._address

    def start(self) -> None:
        if self._server is not None:
            return
        self._server = ThreadingHTTPServer(self._address, _JSONHandler)
        self._address = self._server.server_address[:2]
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True,
            name="AutoControlREST",
        )
        self._thread.start()
        autocontrol_logger.info("REST API listening on %s:%d", *self._address)

    def stop(self, timeout: float = 2.0) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        self._server = None
        self._thread = None


def start_rest_api_server(host: str = "127.0.0.1",
                          port: int = 9939) -> RestApiServer:
    """Start and return a ``RestApiServer``; convenience wrapper."""
    server = RestApiServer(host=host, port=port)
    server.start()
    return server
