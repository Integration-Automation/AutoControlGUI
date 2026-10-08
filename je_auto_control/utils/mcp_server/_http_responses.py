"""Request-body and response plumbing of the MCP HTTP handler.

Split out of :mod:`.http_transport`: reading a bounded body, writing a JSON
answer with its headers, draining an unread body before a 4xx (so Windows
does not turn the close into a reset), and opening an SSE response. None of
it knows about sessions, authorisation or the dispatcher.
"""
import threading
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

from je_auto_control.utils.http_headers import parse_content_length, wire_json_text
from je_auto_control.utils.logging.logging_instance import autocontrol_logger

MAX_BODY = 1_000_000
SSE_MEDIA_TYPE = "text/event-stream"
# Cap drain reads so a hostile Content-Length can't make us spin forever.
_DRAIN_CHUNK = 64 * 1024
_DRAIN_CAP_MULTIPLE = 4


class HttpResponseMixin:
    """Body reading and response writing for a ``BaseHTTPRequestHandler``."""

    # Set once this request's body has been read off the socket, so a later
    # error response knows there is nothing left to drain.
    _body_consumed = False

    if TYPE_CHECKING:
        headers: Any
        rfile: Any
        wfile: Any
        close_connection: bool

        def send_response(self, code: int, message: Optional[str] = None) -> None:
            """Provided by ``BaseHTTPRequestHandler``."""

        def send_header(self, keyword: str, value: str) -> None:
            """Provided by ``BaseHTTPRequestHandler``."""

        def end_headers(self) -> None:
            """Provided by ``BaseHTTPRequestHandler``."""

    def _client_accepts_sse(self) -> bool:
        accept = self.headers.get("Accept", "")
        return SSE_MEDIA_TYPE in accept

    def _open_event_stream(self, send_lock: threading.Lock) -> Callable[[str], None]:
        """Send the headers of an SSE response; return a writer of its events."""
        self.close_connection = True
        with send_lock:
            self.send_response(200)
            self.send_header("Content-Type", f"{SSE_MEDIA_TYPE}; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            self.wfile.flush()

        def emit(payload: str) -> None:
            with send_lock:
                self.wfile.write(b"data: ")
                self.wfile.write(payload.encode("utf-8"))
                self.wfile.write(b"\n\n")
                self.wfile.flush()
        return emit

    def _read_body(self) -> Optional[str]:
        length = parse_content_length(self.headers)
        if length <= 0 or length > MAX_BODY:
            self._send_json({"error": "invalid Content-Length"}, status=400)
            return None
        raw = self.rfile.read(length)
        # From here the body is gone from the socket. Any 4xx we send later
        # must not try to drain it again: there is nothing left to read, so
        # the drain would block on the next request's bytes until the socket
        # timeout and pin this worker for thirty seconds.
        self._body_consumed = True
        try:
            return raw.decode("utf-8").strip()
        except UnicodeDecodeError:
            self._send_json({"error": "body must be UTF-8"}, status=400)
            return None

    def _send_json(self, payload: Any, status: int = 200,
                   extra_headers: Optional[Dict[str, str]] = None) -> None:
        body = wire_json_text(payload).encode("utf-8")
        self._write_headers(status, body, extra_headers)
        self.wfile.write(body)
        if status >= 400:
            # Drain any unread request body before the socket closes.
            # Without this, Windows TCP turns "close with unread bytes"
            # into RST and the client surfaces WinError 10053 before it
            # can read the 4xx response.
            self._drain_body()

    def _drain_body(self) -> None:
        if self._body_consumed:
            return
        declared = parse_content_length(self.headers)
        if declared <= 0:
            return
        cap = min(declared, MAX_BODY * _DRAIN_CAP_MULTIPLE)
        remaining = cap
        try:
            while remaining > 0:
                chunk = self.rfile.read(min(remaining, _DRAIN_CHUNK))
                if not chunk:
                    break
                remaining -= len(chunk)
        except OSError as error:
            # Draining is a courtesy to the client's read of our 4xx. If the
            # peer has already gone, there is nothing left to be courteous
            # about — and letting this escape logs a whole traceback for it.
            autocontrol_logger.debug("MCP drain aborted: %r", error)

    def _send_raw_json(self, raw_json: str,
                       extra_headers: Optional[Dict[str, str]] = None,
                       status: int = 200) -> None:
        body = raw_json.encode("utf-8")
        self._write_headers(status, body, extra_headers)
        self.wfile.write(body)

    def _send_blank(self, status: int) -> None:
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _write_headers(self, status: int, body: bytes,
                       extra_headers: Optional[Dict[str, str]] = None,
                       ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()


__all__ = ["HttpResponseMixin", "MAX_BODY", "SSE_MEDIA_TYPE"]
