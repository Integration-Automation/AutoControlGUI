"""USB/IP host-side TCP server."""
from __future__ import annotations

import socket
import threading
from typing import Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.usbip.backend import (
    UrbBackend, UrbRequest,
)
from je_auto_control.utils.usbip.protocol import (
    OP_REQ_DEVLIST, OP_REQ_IMPORT, USBIP_CMD_SUBMIT, USBIP_CMD_UNLINK,
    UsbIpError, decode_cmd_submit, decode_op_request,
    encode_op_rep_devlist, encode_op_rep_import, encode_ret_submit,
    parse_op_header,
)

_OP_HEADER_BYTES = 8  # version + command + status
_OP_IMPORT_BUSID_BYTES = 32
_URB_HEADER_BYTES = 20
_CMD_SUBMIT_BODY_BYTES = 28
_LISTEN_BACKLOG = 8


def default_port() -> int:
    """Canonical USB/IP server port — 3240."""
    return 3240


class UsbIpServer:
    """Thread-per-connection USB/IP server bound to ``UrbBackend``."""

    def __init__(self, backend: UrbBackend, *,
                 host: str = "0.0.0.0",  # noqa: S104  # nosec B104  # NOSONAR python:S5332  # reason: USB/IP clients connect from other machines on the LAN
                 port: int = 3240) -> None:
        self._backend = backend
        self._host = host
        self._port = int(port)
        self._listen_sock: Optional[socket.socket] = None
        self._accept_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._workers: list = []

    @property
    def port(self) -> int:
        return self._port

    @property
    def is_running(self) -> bool:
        return self._listen_sock is not None

    def start(self) -> int:
        if self.is_running:
            return self._port
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self._host, self._port))
        sock.listen(_LISTEN_BACKLOG)
        self._port = sock.getsockname()[1]
        self._listen_sock = sock
        self._stop.clear()
        self._accept_thread = threading.Thread(
            target=self._accept_loop, name="usbip-accept", daemon=True,
        )
        self._accept_thread.start()
        return self._port

    def stop(self, *, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._listen_sock is not None:
            try:
                self._listen_sock.close()
            except OSError:
                pass
            self._listen_sock = None
        if self._accept_thread is not None:
            self._accept_thread.join(timeout=timeout)
            self._accept_thread = None
        for worker in list(self._workers):
            worker.join(timeout=timeout)
        self._workers.clear()

    # --- internals ----------------------------------------------------

    def _accept_loop(self) -> None:
        listen = self._listen_sock
        if listen is None:
            return
        listen.settimeout(0.5)
        while not self._stop.is_set():
            try:
                client_sock, _address = listen.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            worker = threading.Thread(
                target=self._handle_client, args=(client_sock,),
                name="usbip-client", daemon=True,
            )
            self._workers.append(worker)
            worker.start()

    def _handle_client(self, client_sock: socket.socket) -> None:
        try:
            client_sock.settimeout(30.0)
            self._serve(client_sock)
        except (OSError, UsbIpError) as error:
            autocontrol_logger.info("usbip client error: %r", error)
        finally:
            try:
                client_sock.close()
            except OSError:
                pass

    def _serve(self, sock: socket.socket) -> None:
        """One OP request, then optionally a stream of URB commands."""
        raw = _recv_exact(sock, _OP_HEADER_BYTES)
        version, command, _status = parse_op_header(raw)
        if command == OP_REQ_DEVLIST:
            self._serve_devlist(sock)
            return
        if command == OP_REQ_IMPORT:
            busid_bytes = _recv_exact(sock, _OP_IMPORT_BUSID_BYTES)
            request = decode_op_request(raw + busid_bytes)
            self._serve_import(sock, request.busid or "")
            return
        raise UsbIpError(f"unknown OP command 0x{command:04x}")

    def _serve_devlist(self, sock: socket.socket) -> None:
        devices = self._backend.list_devices()
        sock.sendall(encode_op_rep_devlist(devices))

    def _serve_import(self, sock: socket.socket, busid: str) -> None:
        device = self._backend.find_by_busid(busid)
        sock.sendall(encode_op_rep_import(device))
        if device is None:
            return
        # After a successful import the client switches to URB-mode.
        # Loop reading USBIP_CMD_* until the client hangs up.
        while not self._stop.is_set():
            try:
                header = _recv_exact(sock, _URB_HEADER_BYTES)
            except OSError:
                return
            command = int.from_bytes(header[:4], "big")
            if command == USBIP_CMD_SUBMIT:
                self._serve_cmd_submit(sock, header)
            elif command == USBIP_CMD_UNLINK:
                _ = _recv_exact(sock, _CMD_SUBMIT_BODY_BYTES)
                # Unlink: we don't track in-flight URBs in the scaffold,
                # so just acknowledge with status 0.
                seqnum = int.from_bytes(header[4:8], "big")
                ret = encode_ret_submit(
                    seqnum=seqnum, devid=device.devnum,
                    direction=0, ep=0, status=0, actual_length=0,
                )
                sock.sendall(ret)
            else:
                raise UsbIpError(
                    f"unexpected URB command 0x{command:08x}",
                )

    def _serve_cmd_submit(self, sock: socket.socket,
                          header: bytes) -> None:
        body = _recv_exact(sock, _CMD_SUBMIT_BODY_BYTES)
        # Decode the header+body so we know how big the OUT buffer is.
        partial = decode_cmd_submit(header + body)
        if partial.direction == 0 and partial.transfer_buffer_length > 0:
            extra = _recv_exact(sock, partial.transfer_buffer_length)
            partial = decode_cmd_submit(header + body + extra)
        response = self._backend.submit_urb(UrbRequest(
            seqnum=partial.seqnum, devid=partial.devid,
            direction=partial.direction, ep=partial.ep,
            setup=partial.setup,
            transfer_buffer=partial.transfer_buffer,
            transfer_buffer_length=partial.transfer_buffer_length,
        ))
        ret = encode_ret_submit(
            seqnum=partial.seqnum, devid=partial.devid,
            direction=partial.direction, ep=partial.ep,
            status=response.status,
            actual_length=response.actual_length,
            data=response.data,
            setup=partial.setup,
        )
        sock.sendall(ret)


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    """Block until ``n`` bytes are received or the peer hangs up."""
    chunks: list = []
    remaining = n
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise OSError("usbip peer closed connection")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


__all__ = ["UsbIpServer", "default_port"]
