"""Keep cancelled socket descriptors alive until their last I/O operation exits."""
from contextlib import contextmanager, suppress
import errno
import socket
from threading import Lock
from typing import Iterator, Optional


class SocketOwner:
    """Own one connection and defer its close while cancellation wakes borrowers."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._current: Optional[socket.socket] = None
        self._retired: Optional[socket.socket] = None
        self._borrowers = 0

    @property
    def connection(self) -> Optional[socket.socket]:
        """Return the currently available connection, without borrowing it."""
        with self._lock:
            return self._current

    def adopt(self, connection: socket.socket) -> None:
        """Accept a new connection only after the previous owner is fully drained."""
        with self._lock:
            if self._current is not None or self._retired is not None:
                with suppress(OSError):
                    connection.close()
                raise OSError(errno.EBUSY, 'the previous session bus connection has not drained')
            self._current = connection

    @contextmanager
    def borrow(self) -> Iterator[socket.socket]:
        """Protect the descriptor during I/O and reject completion after cancellation."""
        with self._lock:
            connection = self._current
            if connection is None:
                raise OSError(errno.ENOTCONN, 'the session bus connection is closed')
            self._borrowers += 1
        try:
            yield connection
            with self._lock:
                if self._current is not connection:
                    raise OSError(errno.ENOTCONN, 'the session bus connection was cancelled')
        finally:
            with self._lock:
                self._borrowers -= 1
                if self._borrowers == 0 and self._retired is not None:
                    with suppress(OSError):
                        self._retired.close()
                    self._retired = None

    def close(self) -> None:
        """Detach and wake the connection; the last borrower closes its descriptor."""
        with self._lock:
            connection, self._current = self._current, None
            if connection is None:
                return
            with suppress(OSError):
                connection.shutdown(socket.SHUT_RDWR)
            if self._borrowers:
                self._retired = connection
            else:
                with suppress(OSError):
                    connection.close()
