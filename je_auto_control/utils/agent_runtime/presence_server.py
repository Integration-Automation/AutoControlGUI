"""One owned presence source with bounded authenticated connections and connection-only token cleanup."""
from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass, field
import queue
import threading
import time
from typing import Any, Callable

from je_auto_control.utils.agent_runtime.errors import AgentControlBusy, AgentTaskError
from je_auto_control.utils.agent_runtime.presence_frames import decode_frame, encode_frame, identifier
from je_auto_control.utils.agent_runtime.presence_handshake import server_handshake
from je_auto_control.utils.agent_runtime.presence_pipe_windows import WindowsPresencePipe
from je_auto_control.utils.agent_runtime.presence_protocol import PresenceProtocol
from je_auto_control.utils.agent_runtime.presence_security_windows import WindowsPresenceSecurity
from je_auto_control.utils.agent_runtime.presence_windows import WindowsPresenceSource


@dataclass
class _Lifecycle:
    source: Any = None
    listener: Any = None
    acceptor: threading.Thread | None = None
    clients: dict[Any, threading.Thread] = field(default_factory=dict)
    stop: threading.Event = field(default_factory=threading.Event)
    slots: queue.Queue[None] = field(default_factory=lambda: queue.Queue(maxsize=16))
    failures: list[str] = field(default_factory=list)


class PresenceServer:
    """Reserve one session endpoint before starting observation; borrowers never own this server."""

    def __init__(self, source_factory: Callable[[], Any] = WindowsPresenceSource, *,
                 pipe: Any = None, security: Any = None) -> None:
        self._factory = source_factory
        self._pipe = pipe if pipe is not None else WindowsPresencePipe()
        self._security = security if security is not None else WindowsPresenceSecurity()
        self._life = _Lifecycle()
        self._mutex = threading.RLock()
        self._attempted = False

    def start(self) -> dict:
        """Start once, only after first-instance ownership; an occupied endpoint never starts a source."""
        with self._mutex:
            if self._attempted or self._life.stop.is_set():
                raise AgentTaskError('physical presence server cannot restart')
            self._attempted = True
        try:
            self._life.listener = self._pipe.listen()
        except AgentControlBusy:
            return {'ready': False, 'occupied': True}
        try:
            self._life.source = self._factory()
            self._life.source.start()
            generation = identifier(self._life.source.status()['generation'])
            if self._life.stop.is_set():
                raise AgentTaskError('physical presence server stopped during startup')
            self._life.acceptor = threading.Thread(target=self._accept, name='PresenceAccept', daemon=True)
            self._life.acceptor.start()
            return {'ready': True, 'generation': generation}
        except BaseException:
            self.close()
            raise

    def status(self) -> dict:
        """Read coarse process-local diagnostics without starting native resources or granting a lease."""
        with self._mutex:
            thread = self._life.acceptor
            return {'running': thread is not None and thread.is_alive() and not self._life.stop.is_set(),
                    'clients': len(self._life.clients), 'failed': bool(self._life.failures)}

    def _failure(self, error: BaseException) -> None:
        with self._mutex:
            self._life.failures.append(type(error).__name__)
            self._life.stop.set()
        if self._life.source is not None:
            try:
                self._life.source.close()
            except (OSError, RuntimeError, ValueError, AgentTaskError) as cleanup:
                with self._mutex:
                    self._life.failures.append(type(cleanup).__name__)

    def _accept(self) -> None:
        try:
            while not self._life.stop.is_set():
                try:
                    self._life.slots.put(None, timeout=0.05)
                except queue.Full:
                    continue
                self._accept_one()
        except (OSError, EOFError, RuntimeError, ValueError, AgentTaskError) as error:
            if not self._life.stop.is_set():
                self._failure(error)

    def _accept_one(self) -> None:
        connection = None
        transferred = False
        try:
            connection = self._life.listener.accept()
            if self._life.stop.is_set():
                connection.close()
                return
            thread = threading.Thread(target=self._client, args=(connection,), name='PresenceClient', daemon=True)
            with self._mutex:
                self._life.clients[connection] = thread
            thread.start()
            transferred = True
        finally:
            if not transferred:
                try:
                    if connection is not None:
                        connection.close()
                    with self._mutex:
                        self._life.clients.pop(connection, None)
                finally:
                    self._life.slots.get_nowait()

    def _client(self, connection: Any) -> None:
        protocol, peer = None, None
        try:
            protocol = PresenceProtocol(self._life.source)
            peer = server_handshake(connection, self._security, protocol.generation)
            self._exchange(connection, protocol, peer)
        except (OSError, EOFError, ValueError, AgentTaskError):
            pass  # reason: malformed/disconnected clients retire their own tokens, not the shared source
        finally:
            self._retire_client(connection, protocol, peer)

    def _exchange(self, connection: Any, protocol: PresenceProtocol, peer: Any) -> None:
        while not self._life.stop.is_set():
            value = decode_frame(connection.recv_bytes(4096))
            if not peer.alive():
                raise AgentTaskError('physical presence client process has exited')
            reply = protocol.request(value)
            if not peer.alive():
                raise AgentTaskError('physical presence client process exited before its reply')
            connection.send_bytes(encode_frame(reply))

    def _retire_client(self, connection: Any, protocol: Any, peer: Any) -> None:
        try:
            with ExitStack() as cleanup:
                cleanup.callback(connection.close)
                if peer is not None:
                    cleanup.callback(peer.close)
                if protocol is not None:
                    cleanup.callback(protocol.close)
        except (OSError, RuntimeError, ValueError, AgentTaskError) as error:
            self._failure(error)
        finally:
            with self._mutex:
                self._life.clients.pop(connection, None)
            self._life.slots.get_nowait()

    def close(self) -> None:
        """Fence the source, close owned connections/listener and bound local thread retirement."""
        self._life.stop.set()
        with self._mutex:
            clients = dict(self._life.clients)
        resources = [self._life.source, *clients, self._life.listener]
        errors = []
        for resource in resources:
            try:
                if resource is not None:
                    resource.close()
            except (OSError, RuntimeError, ValueError, AgentTaskError) as error:
                errors.append(type(error).__name__)
        self._join([self._life.acceptor, *clients.values()])
        if errors or self._life.failures:
            raise AgentTaskError('physical presence server resources have not retired')

    def _join(self, threads: list[threading.Thread | None]) -> None:
        deadline = time.monotonic() + 1
        for thread in threads:
            if thread is not None and thread is not threading.current_thread() and thread.ident is not None:
                thread.join(timeout=max(0, deadline - time.monotonic()))
                if thread.is_alive():
                    raise AgentTaskError('physical presence server thread has not retired')
