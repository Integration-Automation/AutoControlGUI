"""Process-global singleton holding the running REST server (if any).

JSON action scripts call ``AC_rest_api_start`` and ``AC_rest_api_stop``
without juggling handles, so the executor adapters need a stable place to
look up the active server. Mirrors the ``remote_desktop.registry`` shape.
"""
from __future__ import annotations

import threading
from typing import Any, Dict, Optional

from je_auto_control.utils.rest_api.rest_server import RestApiServer


class _RestApiRegistry:
    """One running REST server per process (or none)."""

    def __init__(self) -> None:
        self._server: Optional[RestApiServer] = None
        self._lock = threading.Lock()

    @property
    def server(self) -> Optional[RestApiServer]:
        with self._lock:
            return self._server

    def start(self, host: str = "127.0.0.1", port: int = 9939,
              *, token: Optional[str] = None,
              enable_audit: bool = True) -> Dict[str, Any]:
        """Stop any existing server, then start a fresh one with the config.

        The whole start lifecycle (stop existing → construct → bind →
        track) runs under ``_lock`` so two concurrent ``start()`` calls
        cannot leak servers or race on port binding.
        """
        with self._lock:
            previous = self._server
            self._server = None
            if previous is not None:
                previous.stop(timeout=2.0)
            server = RestApiServer(
                host=host, port=int(port), token=token,
                enable_audit=enable_audit,
            )
            server.start()
            self._server = server
        return self.status()

    def stop(self, timeout: float = 2.0) -> Dict[str, Any]:
        with self._lock:
            server = self._server
            self._server = None
        if server is not None:
            server.stop(timeout=timeout)
        return self.status()

    def status(self) -> Dict[str, Any]:
        with self._lock:
            server = self._server
        if server is None:
            return {
                "running": False, "host": None, "port": 0,
                "token": None, "url": None,  # nosec B105  # reason: dict key, value None means server stopped
            }
        host, port = server.address
        return {
            "running": server.is_running, "host": host, "port": int(port),
            "token": server.token, "url": server.base_url,
        }


rest_api_registry = _RestApiRegistry()


__all__ = ["rest_api_registry"]
