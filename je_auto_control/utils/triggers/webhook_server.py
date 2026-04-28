"""HTTP push trigger: fire a script when an external service POSTs to us.

Existing triggers poll the screen / file system; webhooks are different
because the firing event is *pushed* by another process. This module
runs a small :class:`http.server.ThreadingHTTPServer` and dispatches
requests to registered webhook entries.

Each registered webhook owns a path + optional method allowlist + an
optional bearer token. When a matching request arrives the server seeds
the executor's variable scope with::

    webhook.method   - request method (string)
    webhook.path     - request path (string)
    webhook.query    - decoded query string as ``dict[str, list[str]]``
    webhook.headers  - case-insensitive dict of header values
    webhook.body     - raw request body text (string)
    webhook.json     - parsed JSON body if Content-Type permits, else None

…and runs the configured action JSON file. Each fire is recorded in
``run_history`` under :data:`SOURCE_TRIGGER` so existing dashboards
surface webhook activity alongside other triggers.

Security defaults: bind 127.0.0.1; bodies are size-limited; token
comparison is constant-time. Script paths are resolved once on
registration and frozen — clients cannot influence which file runs.
"""
import hmac
import json
import threading
import uuid
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from je_auto_control.utils.json.json_file import read_action_json
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.run_history.artifact_manager import (
    capture_error_snapshot,
)
from je_auto_control.utils.run_history.history_store import (
    SOURCE_TRIGGER, STATUS_ERROR, STATUS_OK, default_history_store,
)


_DEFAULT_BIND = "127.0.0.1"
_MAX_BODY_BYTES = 1 << 20  # 1 MiB cap


@dataclass
class WebhookTrigger:
    """One registered webhook → script binding."""
    webhook_id: str
    path: str
    script_path: str
    methods: Tuple[str, ...] = ("POST",)
    token: Optional[str] = None
    enabled: bool = True
    fired: int = 0
    last_status: int = 0


def _normalize_methods(methods: Optional[List[str]]) -> Tuple[str, ...]:
    if not methods:
        return ("POST",)
    seen: List[str] = []
    for raw in methods:
        method = str(raw).upper().strip()
        if method and method not in seen:
            seen.append(method)
    return tuple(seen) or ("POST",)


def _normalize_path(path: str) -> str:
    cleaned = path.strip()
    if not cleaned:
        raise ValueError("webhook path must not be empty")
    if not cleaned.startswith("/"):
        cleaned = "/" + cleaned
    return cleaned


def _maybe_parse_json(content_type: str, body: str) -> Optional[Any]:
    if not body:
        return None
    if "json" not in (content_type or "").lower():
        return None
    try:
        return json.loads(body)
    except ValueError:
        return None


class _WebhookHandler(BaseHTTPRequestHandler):
    """HTTP handler dispatched by :class:`WebhookTriggerServer`."""

    server_version = "AutoControlWebhook/1.0"

    # Signature must mirror BaseHTTPRequestHandler.log_message exactly,
    # including the parameter name 'format' — pylint W0221 trips on
    # rename or annotation drift; the shadow of the stdlib 'format' is
    # the parent class's choice, not ours.
    # pylint: disable=redefined-builtin
    def log_message(self, format, *args):  # noqa: A002
        autocontrol_logger.debug("webhook %s", format % args)
    # pylint: enable=redefined-builtin

    def _read_body(self) -> str:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return ""
        if length > _MAX_BODY_BYTES:
            self.send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                            "body too large")
            return ""
        raw = self.rfile.read(length)
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("latin-1", errors="replace")

    def _collect_headers(self) -> Dict[str, str]:
        return {key.lower(): value for key, value in self.headers.items()}

    def _send_json(self, status: HTTPStatus, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _dispatch(self, method: str) -> None:
        registry: WebhookTriggerServer = self.server.webhook_owner  # type: ignore[attr-defined]
        parsed = urlparse(self.path)
        trigger = registry.match(parsed.path, method)
        if trigger is None:
            self.send_error(HTTPStatus.NOT_FOUND, "no webhook bound")
            return
        if not registry.authorize(trigger, self.headers.get("Authorization")):
            self.send_error(HTTPStatus.UNAUTHORIZED, "bad token")
            return
        body = self._read_body()
        if body == "" and int(self.headers.get("Content-Length") or 0) > 0:
            return  # _read_body already wrote an error response
        payload = {
            "webhook.method": method,
            "webhook.path": parsed.path,
            "webhook.query": parse_qs(parsed.query, keep_blank_values=True),
            "webhook.headers": self._collect_headers(),
            "webhook.body": body,
            "webhook.json": _maybe_parse_json(
                self.headers.get("Content-Type", ""), body,
            ),
        }
        run_id = registry.fire(trigger, payload)
        self._send_json(HTTPStatus.OK, {"run_id": run_id, "fired": True})

    def do_GET(self) -> None:  # noqa: N802 - http.server contract
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._dispatch("PUT")

    def do_DELETE(self) -> None:  # noqa: N802
        self._dispatch("DELETE")


class WebhookTriggerServer:
    """Push-based trigger: external HTTP requests fire the registered script."""

    def __init__(self,
                 executor: Optional[Callable[[list, Dict[str, Any]], Any]] = None,
                 ) -> None:
        self._lock = threading.RLock()
        # Serialise firings so concurrent webhook hits do not race on the
        # global executor's shared variable scope.
        self._fire_lock = threading.Lock()
        self._triggers: Dict[str, WebhookTrigger] = {}
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._bound: Optional[Tuple[str, int]] = None
        if executor is None:
            self._executor = self._default_executor
        else:
            self._executor = executor

    @property
    def is_running(self) -> bool:
        return self._server is not None

    @property
    def bound_address(self) -> Optional[Tuple[str, int]]:
        """Return ``(host, port)`` once the server is listening."""
        return self._bound

    def add(self,
            path: str,
            script_path: str,
            methods: Optional[List[str]] = None,
            token: Optional[str] = None,
            ) -> WebhookTrigger:
        """Register a new webhook → script binding."""
        normalized_path = _normalize_path(path)
        if not script_path:
            raise ValueError("script_path is required")
        trigger = WebhookTrigger(
            webhook_id=uuid.uuid4().hex[:8],
            path=normalized_path,
            script_path=str(script_path),
            methods=_normalize_methods(methods),
            token=token if token is not None else None,
        )
        with self._lock:
            for existing in self._triggers.values():
                if existing.path == normalized_path \
                        and set(existing.methods) & set(trigger.methods):
                    raise ValueError(
                        f"webhook conflict: {normalized_path} already bound "
                        f"to id {existing.webhook_id}"
                    )
            self._triggers[trigger.webhook_id] = trigger
        return trigger

    def remove(self, webhook_id: str) -> bool:
        with self._lock:
            return self._triggers.pop(webhook_id, None) is not None

    def set_enabled(self, webhook_id: str, enabled: bool) -> bool:
        with self._lock:
            trigger = self._triggers.get(webhook_id)
            if trigger is None:
                return False
            trigger.enabled = bool(enabled)
            return True

    def list_webhooks(self) -> List[WebhookTrigger]:
        with self._lock:
            return list(self._triggers.values())

    def match(self, path: str, method: str) -> Optional[WebhookTrigger]:
        with self._lock:
            for trigger in self._triggers.values():
                if not trigger.enabled:
                    continue
                if trigger.path == path and method in trigger.methods:
                    return trigger
            return None

    def authorize(self, trigger: WebhookTrigger,
                  auth_header: Optional[str]) -> bool:
        if not trigger.token:
            return True
        if not auth_header:
            return False
        expected = f"Bearer {trigger.token}".encode("utf-8")
        return hmac.compare_digest(auth_header.encode("utf-8"), expected)

    def fire(self, trigger: WebhookTrigger,
             payload: Dict[str, Any]) -> Optional[int]:
        """Run the trigger's script with ``payload`` seeded into variables."""
        with self._fire_lock:
            run_id = default_history_store.start_run(
                SOURCE_TRIGGER, f"webhook:{trigger.webhook_id}",
                trigger.script_path,
            )
            status = STATUS_OK
            error_text: Optional[str] = None
            try:
                actions = read_action_json(trigger.script_path)
                self._executor(actions, payload)
            except (OSError, ValueError, RuntimeError) as error:
                status = STATUS_ERROR
                error_text = repr(error)
                autocontrol_logger.error("webhook %s failed: %r",
                                         trigger.webhook_id, error)
            finally:
                artifact = (capture_error_snapshot(run_id)
                            if status == STATUS_ERROR else None)
                default_history_store.finish_run(
                    run_id, status, error_text, artifact_path=artifact,
                )
            with self._lock:
                live = self._triggers.get(trigger.webhook_id)
                if live is not None:
                    live.fired += 1
                    live.last_status = 200 if status == STATUS_OK else 500
            return run_id

    def start(self, host: str = _DEFAULT_BIND, port: int = 0) -> Tuple[str, int]:
        """Start the HTTP server; idempotent if already running."""
        with self._lock:
            if self._server is not None and self._bound is not None:
                return self._bound
            server = ThreadingHTTPServer((host, int(port)), _WebhookHandler)
            server.webhook_owner = self  # type: ignore[attr-defined]
            self._server = server
            actual_host, actual_port = server.server_address[:2]
            self._bound = (str(actual_host), int(actual_port))
            self._thread = threading.Thread(
                target=server.serve_forever,
                name="AutoControlWebhook",
                kwargs={"poll_interval": 0.2},
                daemon=True,
            )
            self._thread.start()
            return self._bound

    def stop(self, timeout: float = 2.0) -> None:
        with self._lock:
            server = self._server
            thread = self._thread
            self._server = None
            self._thread = None
            self._bound = None
        if server is not None:
            try:
                server.shutdown()
                server.server_close()
            except OSError as error:
                autocontrol_logger.warning("webhook stop error: %r", error)
        if thread is not None:
            thread.join(timeout=timeout)

    @staticmethod
    def _default_executor(actions: list, variables: Dict[str, Any]) -> Any:
        """Default: thread-safe global executor with ``variables`` seeded."""
        from je_auto_control.utils.executor.action_executor import (
            execute_action_with_vars,
        )
        return execute_action_with_vars(actions, variables)


default_webhook_server = WebhookTriggerServer()
