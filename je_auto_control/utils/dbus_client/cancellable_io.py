"""Socket operations keep their total deadline while observing only the current task's cancellation."""
import contextlib
import select
import socket
import time

from je_auto_control.utils.exception.cancellation import (
    cancellation_checkpoint, cancellation_timeout, current_cancellation_token,
)


def _remaining(deadline: float) -> float:
    cancellation_checkpoint()
    remaining = deadline-time.monotonic()
    if remaining <= 0:
        raise socket.timeout('the session bus did not answer in time')
    return remaining


def receive(sock: socket.socket, count: int, timeout: float) -> bytes:
    """Read one chunk without discarding partial D-Bus frames across poll intervals."""
    if current_cancellation_token() is None:
        sock.settimeout(timeout)
        return sock.recv(count)
    deadline = time.monotonic()+max(0.0, timeout)
    while True:
        sock.settimeout(cancellation_timeout(_remaining(deadline)))
        try:
            return sock.recv(count)
        except socket.timeout:
            _remaining(deadline)


def send(sock: socket.socket, data: bytes) -> None:
    """Track partial writes explicitly so a poll timeout can never resend bytes."""
    if current_cancellation_token() is None:
        sock.sendall(data)
        return
    original_timeout = sock.gettimeout()
    deadline = time.monotonic()+(original_timeout if original_timeout is not None else 10.0)
    remaining = memoryview(data)
    try:
        while remaining:
            sock.settimeout(cancellation_timeout(_remaining(deadline)))
            try:
                written = sock.send(remaining)
            except socket.timeout:
                continue
            if not written:
                raise ConnectionError('the session bus closed during a write')
            remaining = remaining[written:]
    finally:
        with contextlib.suppress(OSError):
            sock.settimeout(original_timeout)


def connect(sock: socket.socket, address: str, timeout: float) -> None:
    """Keep initial connection waits cancellable without shortening the original deadline."""
    sock.settimeout(timeout)
    if current_cancellation_token() is None:
        sock.connect(address)
        return
    cancellation_checkpoint()
    deadline = time.monotonic()+max(0.0, timeout)
    sock.setblocking(False)
    try:
        try:
            sock.connect(address)
        except (BlockingIOError, InterruptedError):
            _await_connected(sock, deadline)
    finally:
        with contextlib.suppress(OSError):
            sock.settimeout(timeout)


def _await_connected(sock: socket.socket, deadline: float) -> None:
    while True:
        _, writable, exceptional = select.select([], [sock], [sock], cancellation_timeout(_remaining(deadline)))
        cancellation_checkpoint()
        if writable or exceptional:
            code = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
            if code:
                raise OSError(code, 'the session bus connection failed')
            return
