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
    encode_ret_unlink, parse_op_header, peek_transfer_length,
)

_OP_HEADER_BYTES = 8  # version + command + status
_OP_IMPORT_BUSID_BYTES = 32
_URB_HEADER_BYTES = 20
_CMD_SUBMIT_BODY_BYTES = 28
_LISTEN_BACKLOG = 8
# Reject CMD_SUBMIT transfers advertising more than this so a hostile or
# corrupt client can't drive an unbounded allocation via _recv_exact.
# 16 MiB is generous for any real USB transfer.
_MAX_TRANSFER_BUFFER_BYTES = 16 * 1024 * 1024
# accept() 的輪詢間隔,用來定期檢查 _stop 旗標。
# How long accept() blocks before re-checking the _stop flag.
_ACCEPT_POLL_TIMEOUT_S = 0.5


def default_port() -> int:
    """Canonical USB/IP server port — 3240."""
    return 3240


class UsbIpServer:
    """Thread-per-connection USB/IP server bound to ``UrbBackend``."""

    def __init__(self, backend: UrbBackend, *,
                 host: str = "127.0.0.1",
                 port: int = 3240) -> None:
        # Least-privilege default (project policy): bind localhost. Exposing the
        # backing USB device to the LAN requires an explicit host="0.0.0.0".
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
        # 在發布 socket 前、於擁有者執行緒設定 timeout:交給 accept 執行緒
        # 設定會與 stop() 關閉 socket 競態,使 settimeout 拋出 WSAENOTSOCK。
        # Configure on the owning thread before publishing the socket. Leaving
        # it to the accept thread races a concurrent stop() closing the socket,
        # which makes settimeout raise WSAENOTSOCK (WinError 10038) outside any
        # handler (reproduced at 73/400 tight start/stop cycles).
        sock.settimeout(_ACCEPT_POLL_TIMEOUT_S)
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
        for worker in self._workers:
            worker.join(timeout=timeout)
        self._workers.clear()

    # --- internals ----------------------------------------------------

    def _accept_loop(self) -> None:
        # The timeout is set by start() on the owning thread before the socket
        # is published; touching it here would reintroduce the stop() race.
        listen = self._listen_sock
        if listen is None:
            return
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
            # Drop finished workers so the list doesn't grow without bound over
            # a long session with many short-lived connections (each dead Thread
            # object would otherwise be retained until stop()).
            self._workers[:] = [w for w in self._workers if w.is_alive()]
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
        _version, command, _status = parse_op_header(raw)
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
                # so just acknowledge with status 0. Reply with a proper
                # RET_UNLINK (0x4) — a RET_SUBMIT (0x3) would leave the
                # client's URB-cancel forever pending.
                seqnum = int.from_bytes(header[4:8], "big")
                ret = encode_ret_unlink(
                    seqnum=seqnum, devid=device.devnum,
                    direction=0, ep=0, status=0,
                )
                sock.sendall(ret)
            else:
                raise UsbIpError(
                    f"unexpected URB command 0x{command:08x}",
                )

    def _serve_cmd_submit(self, sock: socket.socket,
                          header: bytes) -> None:
        body = _recv_exact(sock, _CMD_SUBMIT_BODY_BYTES)
        # Two-phase: peek the length first (decode_cmd_submit would raise on
        # an OUT transfer whose buffer isn't present yet), read the buffer,
        # then decode the whole message.
        direction, tlen = peek_transfer_length(header, body)
        if tlen > _MAX_TRANSFER_BUFFER_BYTES:
            raise UsbIpError(
                f"CMD_SUBMIT transfer_buffer_length {tlen} exceeds "
                f"{_MAX_TRANSFER_BUFFER_BYTES}",
            )
        extra = b""
        if direction == 0 and tlen > 0:
            extra = _recv_exact(sock, tlen)
        submit = decode_cmd_submit(header + body + extra)
        response = self._backend.submit_urb(UrbRequest(
            seqnum=submit.seqnum, devid=submit.devid,
            direction=submit.direction, ep=submit.ep,
            setup=submit.setup,
            transfer_buffer=submit.transfer_buffer,
            transfer_buffer_length=submit.transfer_buffer_length,
        ))
        ret = encode_ret_submit(
            seqnum=submit.seqnum, devid=submit.devid,
            direction=submit.direction, ep=submit.ep,
            status=response.status,
            actual_length=response.actual_length,
            data=response.data,
            setup=submit.setup,
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
