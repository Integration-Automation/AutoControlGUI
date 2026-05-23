"""Phase 3.3: TCP relay for WebRTC fallback / NAT-traversal failure.

When a viewer and host can't establish a direct peer-to-peer connection
(strict NAT, mobile carrier-grade NAT, hotel Wi-Fi), they can both
connect *outbound* to a relay that just pipes bytes between them.
This is the same mental model as a TURN server but TCP-only and
deliberately small — anything you can pump down a socket goes through.

Handshake (each connection sends this once, then raw bytes flow):

    byte[0]    = role (0x01 = host, 0x02 = viewer)
    byte[1:33] = session_id (32 ASCII chars, host and viewer agree
                 out-of-band — typically the host's 9-digit ID hex-padded)

The first connection for a session_id is parked until its partner
arrives; the second connection wires the two sockets together and
streams in both directions until either side closes.

Security note: the relay sees *encrypted* traffic only if the original
host has TLS configured. Operators who care should run the relay
behind TLS termination (nginx / Caddy) and pin certificates.
"""
from __future__ import annotations

import socket
import threading
from typing import Dict, Optional, Tuple

from je_auto_control.utils.logging.logging_instance import autocontrol_logger

_HANDSHAKE_BYTES = 33  # 1 role + 32 session_id
_ROLE_HOST = 0x01
_ROLE_VIEWER = 0x02
_BUFFER_SIZE = 64 * 1024
_HANDSHAKE_TIMEOUT_S = 30.0


class RelayError(RuntimeError):
    """Raised for handshake or pairing errors."""


def _read_exact(sock: socket.socket, length: int) -> bytes:
    """Block-read exactly ``length`` bytes or raise ``ConnectionError``."""
    buf = bytearray()
    while len(buf) < length:
        chunk = sock.recv(length - len(buf))
        if not chunk:
            raise ConnectionError("relay peer closed during handshake")
        buf.extend(chunk)
    return bytes(buf)


def _pipe(src: socket.socket, dst: socket.socket,
          stop_event: threading.Event) -> None:
    """Forward bytes from ``src`` to ``dst`` until either closes."""
    try:
        while not stop_event.is_set():
            data = src.recv(_BUFFER_SIZE)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        stop_event.set()


def _pair_and_pump(host_sock: socket.socket,
                   viewer_sock: socket.socket) -> None:
    """Bridge two sockets in both directions on dedicated threads."""
    stop = threading.Event()
    t1 = threading.Thread(
        target=_pipe, args=(host_sock, viewer_sock, stop),
        name="relay-h2v", daemon=True,
    )
    t2 = threading.Thread(
        target=_pipe, args=(viewer_sock, host_sock, stop),
        name="relay-v2h", daemon=True,
    )
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    for sock in (host_sock, viewer_sock):
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            sock.close()
        except OSError:
            pass


class RelayServer:
    """In-process TCP relay paired by 32-byte session ID."""

    def __init__(self, bind: str = "127.0.0.1", port: int = 0,
                 max_pending_sessions: int = 32) -> None:
        self._bind = bind
        self._requested_port = int(port)
        self._max_pending = int(max_pending_sessions)
        self._listen_sock: Optional[socket.socket] = None
        self._accept_thread: Optional[threading.Thread] = None
        self._shutdown = threading.Event()
        # session_id -> (role, socket) waiting for the partner.
        self._pending: Dict[bytes, Tuple[int, socket.socket]] = {}
        self._pending_lock = threading.Lock()
        self._port = 0

    @property
    def port(self) -> int:
        return self._port

    @property
    def is_running(self) -> bool:
        return self._listen_sock is not None and not self._shutdown.is_set()

    def start(self) -> None:
        if self.is_running:
            return
        self._shutdown.clear()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self._bind, self._requested_port))
        sock.listen(self._max_pending)
        self._port = sock.getsockname()[1]
        self._listen_sock = sock
        self._accept_thread = threading.Thread(
            target=self._accept_loop, name="relay-accept", daemon=True,
        )
        self._accept_thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        if self._listen_sock is None:
            return
        self._shutdown.set()
        try:
            self._listen_sock.close()
        except OSError:
            pass
        self._listen_sock = None
        with self._pending_lock:
            for _role, sock in self._pending.values():
                try:
                    sock.close()
                except OSError:
                    pass
            self._pending.clear()
        if self._accept_thread is not None:
            self._accept_thread.join(timeout=timeout)
            self._accept_thread = None

    def _accept_loop(self) -> None:
        listen = self._listen_sock
        if listen is None:
            return
        listen.settimeout(0.5)
        while not self._shutdown.is_set():
            try:
                client_sock, _address = listen.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            threading.Thread(
                target=self._handle_client, args=(client_sock,),
                name="relay-client", daemon=True,
            ).start()

    def _handle_client(self, client_sock: socket.socket) -> None:
        try:
            client_sock.settimeout(_HANDSHAKE_TIMEOUT_S)
            handshake = _read_exact(client_sock, _HANDSHAKE_BYTES)
            client_sock.settimeout(None)
        except OSError as error:
            # ConnectionError already inherits from OSError.
            autocontrol_logger.info("relay handshake failed: %r", error)
            try:
                client_sock.close()
            except OSError:
                pass
            return
        role = handshake[0]
        session_id = handshake[1:]
        if role not in (_ROLE_HOST, _ROLE_VIEWER):
            autocontrol_logger.info("relay bad role %#x", role)
            client_sock.close()
            return
        self._register_or_pair(role, session_id, client_sock)

    def _register_or_pair(self, role: int, session_id: bytes,
                          client_sock: socket.socket) -> None:
        with self._pending_lock:
            partner = self._pending.pop(session_id, None)
            if partner is None:
                if len(self._pending) >= self._max_pending:
                    autocontrol_logger.info(
                        "relay rejecting session: pending table full",
                    )
                    client_sock.close()
                    return
                self._pending[session_id] = (role, client_sock)
                return
        partner_role, partner_sock = partner
        if partner_role == role:
            autocontrol_logger.info(
                "relay role collision for session %r", session_id,
            )
            partner_sock.close()
            client_sock.close()
            return
        host_sock = client_sock if role == _ROLE_HOST else partner_sock
        viewer_sock = client_sock if role == _ROLE_VIEWER else partner_sock
        _pair_and_pump(host_sock, viewer_sock)


def encode_handshake(role: str, session_id: bytes) -> bytes:
    """Build the 33-byte handshake for ``role`` ("host" or "viewer")."""
    if role == "host":
        role_byte = _ROLE_HOST
    elif role == "viewer":
        role_byte = _ROLE_VIEWER
    else:
        raise RelayError(f"role must be 'host' or 'viewer', got {role!r}")
    if not isinstance(session_id, (bytes, bytearray)) \
            or len(session_id) != 32:
        raise RelayError("session_id must be exactly 32 bytes")
    return bytes([role_byte]) + bytes(session_id)


__all__ = ["RelayServer", "RelayError", "encode_handshake"]
