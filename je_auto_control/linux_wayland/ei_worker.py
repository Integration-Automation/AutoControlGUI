"""Run a native EI session in a disposable helper; EOF ends its grant."""
from __future__ import annotations

import faulthandler
import socket
import sys
from typing import Any, Callable, Mapping

from je_auto_control.linux_wayland.ei_transport import (
    EiWorkerError, InputEvent, MAX_BATCH_EVENTS, _PeerClosed, _budget,
    open_worker_channel, read_message, write_message,
)
from je_auto_control.linux_wayland.libei import LibeiBackend, LibeiOutOfBounds, LibeiUnavailable
from je_auto_control.linux_wayland import oeffis
from je_auto_control.linux_wayland.permission import WaylandDependencyRequired, WaylandPermissionRequired


def _events(request: Mapping[str, Any]) -> list[InputEvent]:
    raw = request.get("events")
    if not isinstance(raw, list) or not 0 < len(raw) <= MAX_BATCH_EVENTS:
        raise EiWorkerError("invalid EI batch size")
    events = []
    for value in raw:
        if not isinstance(value, dict) or not isinstance(value.get("args"), list):
            raise EiWorkerError("invalid EI event")
        kind = value.get("kind")
        if not isinstance(kind, str):
            raise EiWorkerError("invalid EI event kind")
        event = InputEvent(kind, tuple(value["args"]))
        event.validate()
        events.append(event)
    return events


class WorkerSession:
    """Keep pressed-input ownership and release it only on the same native grant."""

    def __init__(self, backend_factory: Callable[..., LibeiBackend] = LibeiBackend) -> None:
        self._factory = backend_factory
        self.backend: LibeiBackend | None = None
        self.pressed: set[tuple[str, int]] = set()

    def handle(self, request: Mapping[str, Any]) -> dict[str, object]:
        """Apply a validated request or raise a typed refusal with no fallback."""
        operation = request.get("operation")
        if operation == "connect":
            return self._connect(request)
        if self.backend is None or not self.backend.is_connected:
            raise EiWorkerError("EI worker has no authorized session")
        if operation == "permission":
            self.backend.check_permission()
            return {"applied": 0}
        if operation == "send":
            events = _events(request)
            for event in events:
                getattr(self.backend, event.kind)(*event.args)
                self._track(event)
            return {"applied": len(events)}
        raise EiWorkerError("invalid EI worker operation")

    def _connect(self, request: Mapping[str, Any]) -> dict[str, object]:
        """Create native state only inside this process and bound its portal wait."""
        if self.backend is not None:
            raise EiWorkerError("EI worker already has a session")
        timeout = _budget(request.get("timeout_s", 38))
        self.backend = self._factory(portal_connect=lambda: oeffis.connect_eis_fd(timeout=timeout))
        if not self.backend.is_available:
            raise WaylandDependencyRequired("libei is missing; install libei or explicitly select CLI input")
        path = request.get("socket_path")
        if path is not None and (not isinstance(path, str) or not path or len(path) > 4096 or "\0" in path):
            raise EiWorkerError("invalid EI socket path")
        self.backend.connect(timeout=timeout, socket_path=path.encode("utf-8") if path else None)
        return {"applied": 0}

    def _track(self, event: InputEvent) -> None:
        if event.kind.startswith("press_"):
            self.pressed.add((event.kind.removeprefix("press_"), event.args[0]))
        elif event.kind.startswith("release_"):
            self.pressed.discard((event.kind.removeprefix("release_"), event.args[0]))

    def close(self) -> None:
        """Release held keys/buttons when authorized; always end the native grant."""
        backend, self.backend = self.backend, None
        if backend is None:
            return
        try:
            for kind, code in sorted(self.pressed):
                try:
                    getattr(backend, f"release_{kind}")(code)
                except (LibeiUnavailable, WaylandPermissionRequired, OSError):
                    break
        finally:
            self.pressed.clear()
            backend.disconnect()


def _error_reply(error: Exception) -> dict[str, object]:
    kind = "worker"
    if isinstance(error, WaylandDependencyRequired):
        kind = "dependency"
    elif isinstance(error, WaylandPermissionRequired):
        kind = "permission"
    elif isinstance(error, LibeiOutOfBounds):
        kind = "bounds"
    return {"error": kind, "reason": getattr(error, "reason", str(error))[:2048]}


def serve(channel: socket.socket, session: WorkerSession | None = None) -> None:
    """Consume private bounded requests until EOF, cancellation or first failure."""
    session = session or WorkerSession()
    try:
        while True:
            request = read_message(channel)
            request_id = request.get("request_id")
            if not isinstance(request_id, str) or not 0 < len(request_id) <= 64:
                raise EiWorkerError("invalid EI request identity")
            if request.get("operation") == "close":
                session.close()
                write_message(channel, {"request_id": request_id, "applied": 0})
                return
            try:
                reply = session.handle(request)
            except (LibeiUnavailable, WaylandPermissionRequired,
                    WaylandDependencyRequired, OSError, ValueError) as error:
                write_message(channel, {"request_id": request_id, **_error_reply(error)})
                return
            write_message(channel, {"request_id": request_id, **reply})
    except _PeerClosed:
        return
    finally:
        try:
            session.close()
        finally:
            channel.close()


def main() -> int:
    """Start the process-owned session; native crashes stay inside this process."""
    faulthandler.enable()
    if len(sys.argv) != 2:
        return 2
    try:
        serve(open_worker_channel(sys.argv[1]))
    except (LibeiUnavailable, OSError, ValueError):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
