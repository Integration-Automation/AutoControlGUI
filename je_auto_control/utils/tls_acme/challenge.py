"""HTTP-01 challenge server + certbot subprocess wrapper."""
from __future__ import annotations

import http.server
import shutil
import subprocess  # nosec B404  # reason: needed to drive certbot
import threading
from pathlib import Path
from typing import Dict, List, Optional


class _ChallengeHandler(http.server.BaseHTTPRequestHandler):
    """Serve ``/.well-known/acme-challenge/<token>`` responses from memory."""

    server_version = "AutoControlACME/1.0"
    sys_version = ""

    # ``tokens`` is injected by HttpChallengeServer via the server attr.
    def do_GET(self) -> None:  # noqa: N802 BaseHTTPRequestHandler protocol
        tokens: Dict[str, str] = getattr(
            self.server, "_acme_tokens", {},
        )
        prefix = "/.well-known/acme-challenge/"
        if not self.path.startswith(prefix):
            self.send_error(404, "Not Found")
            return
        token = self.path[len(prefix):]
        body = tokens.get(token)
        if body is None:
            self.send_error(404, "Unknown ACME token")
            return
        encoded = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    # Silence the default stderr access log; this server is short-lived
    # and noisy logging on every challenge poll just confuses the user.
    def log_message(self, format: str, *args) -> None:  # noqa: A002, D401
        return


class HttpChallengeServer:
    """Tiny HTTP server for the ACME HTTP-01 challenge.

    Listens on the configured port (80 in production, anything in
    tests) and answers GET ``/.well-known/acme-challenge/<token>``
    with the matching key authorization. Start, hand to the ACME
    flow, stop.
    """

    def __init__(self, *, host: str = "0.0.0.0",  # noqa: S104  # nosec B104  # NOSONAR python:S5332  # reason: server must be reachable by Let's Encrypt's HTTP-01 validator from the public internet
                 port: int = 80) -> None:
        self._host = host
        self._port = int(port)
        self._tokens: Dict[str, str] = {}
        self._server: Optional[http.server.ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def port(self) -> int:
        return self._port

    @property
    def is_running(self) -> bool:
        return self._server is not None

    def set_token(self, token: str, key_authorization: str) -> None:
        """Register one challenge token → key_authorization mapping."""
        if not token or not key_authorization:
            raise ValueError("token and key_authorization are required")
        self._tokens[token] = key_authorization

    def clear_tokens(self) -> None:
        self._tokens.clear()

    def start(self) -> int:
        """Bind + spawn the handler thread. Returns the bound port."""
        if self.is_running:
            return self._port
        server = http.server.ThreadingHTTPServer(
            (self._host, self._port), _ChallengeHandler,
        )
        # Stash tokens on the server so each request handler can read them.
        server._acme_tokens = self._tokens  # type: ignore[attr-defined]
        self._port = server.server_address[1]
        self._server = server
        self._thread = threading.Thread(
            target=server.serve_forever, name="acme-http01", daemon=True,
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


def run_certbot(domain: str, *,
                email: str,
                webroot: str,
                staging: bool = False,
                extra_args: Optional[List[str]] = None,
                timeout: float = 300.0) -> Path:
    """Invoke ``certbot`` to acquire / renew a cert via HTTP-01.

    Returns the path to the issued ``fullchain.pem``. The caller is
    expected to have a HTTP-01-reachable webroot already wired up
    (e.g. by pointing certbot at the same directory the
    :class:`HttpChallengeServer` serves from).

    Raises :class:`FileNotFoundError` when certbot isn't on PATH and
    :class:`subprocess.CalledProcessError` on certbot exit != 0.
    """
    certbot = shutil.which("certbot")
    if certbot is None:
        raise FileNotFoundError(
            "certbot not found on PATH — pip install certbot or use a "
            "system package",
        )
    args = [
        certbot, "certonly", "--non-interactive",
        "--agree-tos", "--email", email,
        "--webroot", "-w", webroot,
        "-d", domain,
    ]
    if staging:
        args.append("--staging")
    if extra_args:
        args.extend(extra_args)
    subprocess.run(  # nosec B603  # reason: argv list, no shell, binary path resolved by shutil.which
        args, check=True, timeout=timeout, capture_output=True,
    )
    return Path("/etc/letsencrypt/live") / domain / "fullchain.pem"


__all__ = ["HttpChallengeServer", "run_certbot"]
