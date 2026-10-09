"""Bounded queue and writer thread for a viewer's INPUT messages.

``RemoteDesktopViewer.send_input`` used to write to the socket on the caller's
thread. The caller is a GUI thread forwarding every mouse move, so a host that
stopped reading froze the viewer's window for as long as the write blocked.
:class:`InputSendQueue` takes the event and returns; one writer thread does the
blocking write.

Back-pressure, when the writer falls behind:

* **Pointer moves are droppable.** Once ``limit`` events are waiting, the
  oldest queued ``mouse_move`` gives way to the new event; a new move with no
  older move to replace is itself dropped. Only the newest position matters to
  the host, and :attr:`InputSendQueue.dropped_moves` counts what went.
* **Key, button, scroll and text events are never dropped.** They may wait
  beyond ``limit``. If ``limit * hard_factor`` of them pile up, or one write
  has been out longer than ``stall_timeout_s``, the connection is not carrying
  input any more: the queue fails, reports the error once and refuses further
  events -- delivering a key press minutes late would be worse than saying so.

Errors go to ``on_error`` (the viewer's existing error path), from the writer
thread or, for a stall noticed on :meth:`~InputSendQueue.put`, from the caller.
"""
import collections
import json
import socket
import struct
import sys
import threading
import time
from typing import Any, Callable, Deque, Mapping, Optional, Tuple

from je_auto_control.utils.logging.logging_instance import autocontrol_logger

#: Events whose queued copies may give way to a newer one. The name is read from
#: ``"action"`` (the TCP / WebSocket input message) or, failing that, ``"type"``.
DROPPABLE_TYPES = frozenset({"mouse_move"})

_NOT_CONNECTED_MESSAGE = "viewer is not connected"


def set_send_timeout(sock: socket.socket, seconds: float) -> bool:
    """Bound blocking sends on ``sock`` without touching its receive side; return whether it took.

    ``socket.settimeout`` covers both directions, and the viewer's receiver
    waits for frames without one. ``SO_SNDTIMEO`` is the send half alone: a
    write the peer does not drain fails with ``OSError`` after ``seconds``.
    """
    if sys.platform == "win32":
        value = struct.pack("L", max(1, int(seconds * 1000)))
    else:
        whole = int(seconds)
        value = struct.pack("ll", whole, int((seconds - whole) * 1_000_000))
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDTIMEO, value)
    except (OSError, AttributeError, ValueError) as error:
        autocontrol_logger.debug("remote_desktop viewer: no send timeout on this socket: %r", error)
        return False
    return True


class InputSendQueue:
    """Queues encoded INPUT payloads and writes them from one daemon thread."""

    def __init__(self, send: Callable[[bytes], None],   # noqa: PLR0913  # reason: keyword-only tuning of one queue
                 on_error: Callable[[Exception], None], *,
                 abort: Optional[Callable[[], None]] = None,
                 limit: int = 256, hard_factor: int = 4,
                 stall_timeout_s: float = 10.0, name: str = "rd-viewer-send") -> None:
        if limit < 1 or hard_factor < 1:
            raise ValueError("limit and hard_factor must be at least 1")
        self._send = send
        self._on_error = on_error
        self._abort = abort
        self._limit = int(limit)
        self._hard_limit = int(limit) * int(hard_factor)
        self._stall_timeout_s = float(stall_timeout_s)
        self._pending: Deque[Tuple[bool, bytes]] = collections.deque()
        self._cond = threading.Condition()
        self._closed = False
        self._failed = False
        self._write_started: Optional[float] = None
        self._dropped_moves = 0
        self._thread = threading.Thread(target=self._run, name=name, daemon=True)
        self._thread.start()

    @property
    def dropped_moves(self) -> int:
        """How many pointer moves gave way to newer events so far."""
        with self._cond:
            return self._dropped_moves

    @property
    def pending(self) -> int:
        """How many events wait for the writer."""
        with self._cond:
            return len(self._pending)

    @property
    def closed(self) -> bool:
        """Whether the queue stopped taking events (closed, or failed)."""
        with self._cond:
            return self._closed

    def put(self, action: Mapping[str, Any]) -> None:
        """Queue ``action`` for the writer and return at once; never blocks on the socket.

        Raises :class:`ConnectionError` once the queue is closed or has failed.
        """
        droppable = action.get("action", action.get("type")) in DROPPABLE_TYPES
        payload = json.dumps(dict(action), ensure_ascii=False).encode("utf-8")
        failure: Optional[Exception] = None
        with self._cond:
            if self._closed:
                raise ConnectionError(_NOT_CONNECTED_MESSAGE)
            failure = self._overdue_locked()
            full = failure is None and len(self._pending) >= self._limit
            if full and not self._drop_oldest_move_locked():
                if droppable:
                    self._dropped_moves += 1        # nothing older to give way: this move is the stale one
                    return
                if len(self._pending) >= self._hard_limit:
                    failure = ConnectionError(
                        f"remote input is not being delivered: {len(self._pending)} events waiting")
            if failure is None:
                self._pending.append((droppable, payload))
                self._cond.notify()
                return
            self._fail_locked()
        self._report(failure, abort=True)

    def close(self, timeout: float = 2.0) -> None:
        """Stop the writer and forget what is still queued; safe to call twice, and from the writer."""
        with self._cond:
            self._closed = True
            self._pending.clear()
            self._cond.notify_all()
        if self._thread is not threading.current_thread():
            self._thread.join(timeout=timeout)

    # internals ----------------------------------------------------------

    def _overdue_locked(self) -> Optional[Exception]:
        """The stall error if the write in flight has been out too long."""
        started = self._write_started
        if started is None or time.monotonic() - started <= self._stall_timeout_s:
            return None
        return TimeoutError(
            f"remote input write did not finish within {self._stall_timeout_s:g} s")

    def _drop_oldest_move_locked(self) -> bool:
        for index, (droppable, _payload) in enumerate(self._pending):
            if droppable:
                del self._pending[index]
                self._dropped_moves += 1
                return True
        return False

    def _fail_locked(self) -> None:
        self._closed = True
        self._failed = True
        self._pending.clear()
        self._cond.notify_all()

    def _report(self, error: Exception, *, abort: bool) -> None:
        """Tell the owner once; ``abort`` also unblocks a write stuck in the socket."""
        if abort and callable(self._abort):
            try:
                self._abort()
            except OSError as abort_error:
                autocontrol_logger.debug("remote_desktop viewer: abort after stall: %r", abort_error)
        try:
            self._on_error(error)
        except Exception:  # noqa: BLE001  # reason: callback isolation, the owner's handler must not kill the writer
            autocontrol_logger.exception("remote_desktop viewer input on_error callback raised")

    def _next(self) -> Optional[bytes]:
        with self._cond:
            while not self._pending and not self._closed:
                self._cond.wait()
            if self._closed:
                return None
            _droppable, payload = self._pending.popleft()
            self._write_started = time.monotonic()
            return payload

    def _run(self) -> None:
        while True:
            payload = self._next()
            if payload is None:
                return
            try:
                self._send(payload)
            except Exception as error:  # noqa: BLE001  # reason: reported through on_error; the writer ends here
                with self._cond:
                    already = self._closed       # closed or failed meanwhile: that side has reported
                    self._write_started = None
                    self._fail_locked()
                if not already:
                    self._report(error, abort=False)
                return
            with self._cond:
                self._write_started = None


__all__ = ["DROPPABLE_TYPES", "InputSendQueue", "set_send_timeout"]
