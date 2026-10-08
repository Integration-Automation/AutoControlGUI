"""The parent's side of the libei helper process.

:mod:`ei_worker` is the helper; this is what talks to it. Kept apart because
they run in different processes and fail in different ways: nothing in here
loads libei, and nothing in there supervises a process.

:class:`EiWorkerClient` owns one helper — starts it, sends it bounded batches
with a deadline, tells it to stop when the caller gives up, and reclaims its
pipes when it ends, however it ends. :class:`WorkerBackend` wraps a client in
the emission surface ``keyboard`` and ``mouse`` already call on
``LibeiBackend``, so :mod:`_select_input` can hand out either.

Reached only when ``JE_AUTOCONTROL_WAYLAND_EI_WORKER=1``; see :mod:`ei_worker`
for why the helper exists and why it is off by default.
"""
from __future__ import annotations

import atexit
import queue
import subprocess  # nosec B404  # reason: argv list of this interpreter, no shell
import sys
import threading
import time
from typing import Any, BinaryIO, Callable, Dict, List, Optional, Sequence, Set, Tuple

from je_auto_control.linux_wayland.ei_transport import (
    ABS_X, ABS_Y, BUTTON_CODES, REL_HWHEEL, REL_WHEEL, EiDependencyMissing,
    EiEmitRefused, EiProtocolError, EiWorkerCancelled, EiWorkerDied,
    EiWorkerError, EiWorkerTimeout, Held, InputAck, encode_batch, read_frame,
    write_frame,
)
from je_auto_control.linux_wayland.input_events import (
    EV_ABS, EV_KEY, EV_REL, EV_SYN, InputEvent,
)
from je_auto_control.linux_wayland.libei import (
    HANDSHAKE_TIMEOUT, LibeiConsentNotGranted, LibeiSessionRevoked,
    LibeiUnavailable,
)

#: How long the helper may take to import, ask the portal, and handshake.
#: The consent dialog is a human in the loop, so this is human-scale.
START_TIMEOUT = 90.0
#: Default deadline for one emission.
EMIT_TIMEOUT = 2.0
_CLOSE_TIMEOUT = 3.0
_CANCEL_GRACE = 1.0
_POLL = 0.05

_EOF = object()


_ACTIVE: Set["EiWorkerClient"] = set()
_ACTIVE_LOCK = threading.Lock()


def active_worker_count() -> int:
    """How many helper processes this process has started and not reaped."""
    with _ACTIVE_LOCK:
        return len(_ACTIVE)


def _spawn_worker() -> Any:
    """Start the helper with this interpreter; stderr is left inherited."""
    argv = [sys.executable, "-m", "je_auto_control.linux_wayland.ei_worker"]
    return subprocess.Popen(  # nosec B603  # nosemgrep  # reason: fixed argv
        argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE)


class EiWorkerClient:
    """The parent's handle on one helper process.

    :param spawn: returns a process-like object with binary ``stdin`` /
        ``stdout``, ``poll``, ``wait``, ``terminate`` and ``kill``. Tests pass
        a fake; the default starts ``python -m …ei_worker``.
    :param socket_path: connect to this EIS socket instead of asking the
        portal — what the verification images use.
    :param on_orphaned_keys: called with the evdev codes that were down when
        the helper died unexpectedly.
    """

    def __init__(self, *, spawn: Optional[Callable[[], Any]] = None,
                 socket_path: Optional[str] = None,
                 handshake_timeout_s: float = HANDSHAKE_TIMEOUT,
                 start_timeout_s: float = START_TIMEOUT,
                 on_orphaned_keys: Optional[Callable[[List[int]], None]] = None,
                 ) -> None:
        self._spawn = spawn or _spawn_worker
        self._socket_path = socket_path
        self._handshake_timeout_s = handshake_timeout_s
        self._start_timeout_s = start_timeout_s
        self._on_orphaned_keys = on_orphaned_keys
        self._process: Any = None
        self._reader: Optional[threading.Thread] = None
        self._inbox: "queue.Queue[Any]" = queue.Queue()
        self._lock = threading.Lock()
        self._next_id = 0
        self._pressed: Set[Held] = set()
        self._dead = True
        self._closing = False
        self._last_returncode: Optional[int] = None

    @property
    def is_alive(self) -> bool:
        """Whether the helper is running and has completed its handshake."""
        return not self._dead

    @property
    def returncode(self) -> Optional[int]:
        """The helper's exit status once it has ended, else None.

        Negative on POSIX when a signal ended it — the number a
        verification reads to tell a clean exit from a crash.
        """
        return self._returncode()

    @property
    def pressed(self) -> Tuple[int, ...]:
        """The evdev codes the helper is believed to be holding down."""
        return tuple(sorted(code for _kind, code in self._pressed))

    def start(self) -> None:
        """Start the helper and wait for its session to come up.

        :raises EiDependencyMissing: libei is not installed where it runs.
        :raises LibeiConsentNotGranted: the portal did not grant a session.
        :raises EiWorkerError: it could not be started or did not come up.
        """
        with self._lock:
            if not self._dead:
                return
            self._closing = False
            try:
                self._process = self._spawn()
            except OSError as error:
                raise EiWorkerError(
                    f"the libei helper could not be started: {error}",
                ) from error
            with _ACTIVE_LOCK:
                _ACTIVE.add(self)
            self._inbox = queue.Queue()
            self._reader = threading.Thread(
                target=self._pump, args=(self._process.stdout, self._inbox),
                name="ei-worker-client", daemon=True)
            self._reader.start()
            try:
                self._handshake()
            except BaseException:
                self._reap()
                raise
            self._dead = False

    def send(self, batch: Sequence[InputEvent], *, timeout_s: float,
             cancel: Optional[threading.Event] = None) -> InputAck:
        """Apply ``batch`` in the helper and wait for its acknowledgement.

        :param timeout_s: seconds to wait; on expiry the helper is told to
            stop and :class:`EiWorkerTimeout` is raised.
        :param cancel: set it from another thread to abandon the request.
        :raises EiProtocolError: the batch is empty or over the limit.
        :raises EiEmitRefused: libei refused it; nothing further was sent.
        :raises LibeiSessionRevoked: the compositor ended the session.
        :raises EiWorkerDied: the helper is gone.
        """
        events = encode_batch(batch)
        with self._lock:
            if self._dead:
                raise EiWorkerDied(
                    "the libei helper is not running; call "
                    "reset_input_authorisation() to start a new one",
                    self._returncode())
            self._next_id += 1
            request_id = self._next_id
            started = time.monotonic()
            self._write({"op": "batch", "id": request_id, "events": events})
            answer = self._await(request_id, timeout_s, cancel, events)
            self._pressed = {(str(kind), int(code))
                             for kind, code in answer.get("held", ())}
            return self._settle(answer, request_id,
                                time.monotonic() - started)

    def close(self) -> None:
        """Ask the helper to exit, wait for it, and reclaim its pipes.

        The helper releases anything it holds down on the way out. Safe to
        call twice and from any thread.
        """
        self._closing = True
        with self._lock:
            if self._process is None:
                return
            try:
                write_frame(self._process.stdin, {"op": "close"})
            except (OSError, ValueError, EiProtocolError):
                pass
            self._reap()
            self._pressed = set()

    # --- plumbing ----------------------------------------------------------

    @staticmethod
    def _pump(stream: BinaryIO, inbox: "queue.Queue[Any]") -> None:
        """Move frames from the helper's stdout into the inbox until EOF."""
        while True:
            try:
                frame = read_frame(stream)
            except (EiProtocolError, OSError, ValueError):
                frame = None
            if frame is None:
                inbox.put(_EOF)
                return
            inbox.put(frame)

    def _handshake(self) -> None:
        write_frame(self._process.stdin, {
            "op": "start", "socket": self._socket_path,
            "timeout": self._handshake_timeout_s})
        deadline = time.monotonic() + self._start_timeout_s
        while True:
            remaining = deadline - time.monotonic()
            if self._closing:
                raise EiWorkerError("the libei helper was closed while starting")
            if remaining <= 0:
                raise LibeiConsentNotGranted(
                    "the libei helper did not come up within "
                    f"{self._start_timeout_s:g}s (a consent dialog may be "
                    "waiting)", "timeout", False)
            try:
                frame = self._inbox.get(timeout=min(remaining, _POLL))
            except queue.Empty:
                continue
            if frame is _EOF:
                raise EiWorkerError(
                    "the libei helper exited before its session came up "
                    f"(exit status {self._returncode()})")
            if frame.get("op") == "ready":
                return
            if frame.get("op") == "failed":
                raise _start_failure(frame)

    def _write(self, message: Dict[str, Any]) -> None:
        try:
            write_frame(self._process.stdin, message)
        except (OSError, ValueError) as error:
            raise self._died() from error

    def _await(self, request_id: int, timeout_s: float,
               cancel: Optional[threading.Event],
               events: List[List[int]]) -> Dict[str, Any]:
        """Wait for the answer to ``request_id``, dropping any older one."""
        deadline = time.monotonic() + max(0.0, timeout_s)
        while True:
            if self._closing:
                raise EiWorkerCancelled("the libei helper is being closed")
            if cancel is not None and cancel.is_set():
                raise self._abandon(request_id, events, cancelled=True)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise self._abandon(request_id, events, cancelled=False)
            frame = self._next_frame(min(remaining, _POLL))
            if frame is not None and frame.get("id") == request_id:
                return frame

    def _next_frame(self, timeout: float) -> Optional[Dict[str, Any]]:
        try:
            frame = self._inbox.get(timeout=timeout)
        except queue.Empty:
            return None
        if frame is _EOF:
            raise self._died()
        return frame

    def _abandon(self, request_id: int, events: List[List[int]],
                 cancelled: bool) -> Exception:
        """Tell the helper to stop this request; build what to raise."""
        self._write({"op": "cancel", "id": request_id})
        applied = None
        deadline = time.monotonic() + _CANCEL_GRACE
        while time.monotonic() < deadline:
            frame = self._next_frame(_POLL)
            if frame is not None and frame.get("id") == request_id:
                applied = int(frame.get("applied", 0))
                self._pressed = {(str(kind), int(code))
                                 for kind, code in frame.get("held", ())}
                break
        else:
            # No answer: assume the worst about what is down, until a later
            # acknowledgement says otherwise.
            self._pressed |= _presses(events)
        if cancelled:
            return EiWorkerCancelled(
                f"request {request_id} was cancelled", applied)
        return EiWorkerTimeout(
            f"the libei helper did not acknowledge request {request_id} in "
            "time; it was told to stop")

    def _settle(self, answer: Dict[str, Any], request_id: int,
                elapsed: float) -> InputAck:
        """Turn the helper's answer into an ack or the error it describes."""
        if answer.get("op") == "error":
            message = str(answer.get("message", "libei refused the request"))
            if answer.get("revoked"):
                raise LibeiSessionRevoked(message)
            raise EiEmitRefused(message)
        return InputAck(request_id, int(answer.get("applied", 0)), elapsed,
                        bool(answer.get("cancelled", False)))

    def _died(self) -> EiWorkerDied:
        """Record the helper's death and describe it."""
        orphaned = list(self.pressed)
        self._pressed = set()
        self._reap()
        if orphaned and self._on_orphaned_keys is not None:
            self._on_orphaned_keys(orphaned)
        return EiWorkerDied(
            f"the libei helper exited unexpectedly (exit status "
            f"{self._returncode()})"
            + (f" with keys {orphaned} down" if orphaned else ""),
            self._returncode(), orphaned)

    def _returncode(self) -> Optional[int]:
        process = self._process
        if process is None:
            return self._last_returncode
        return process.poll()

    def _reap(self) -> None:
        """Stop the process if it is still there and close both pipes."""
        process, self._process = self._process, None
        self._dead = True
        if process is None:
            return
        _close_quietly(process.stdin)
        self._last_returncode = _stop_process(process)
        reader, self._reader = self._reader, None
        if reader is not None and reader is not threading.current_thread():
            reader.join(timeout=_CLOSE_TIMEOUT)
        _close_quietly(process.stdout)
        with _ACTIVE_LOCK:
            _ACTIVE.discard(self)


def _presses(events: Sequence[Sequence[int]]) -> Set[Held]:
    """The keys and buttons a batch would leave down if all of it ran."""
    down: Set[Held] = set()
    for kind, code, value in events:
        if kind != EV_KEY:
            continue
        key = ("button" if code in BUTTON_CODES else "key", code)
        if value == 1:
            down.add(key)
        elif value == 0:
            down.discard(key)
    return down


def _start_failure(frame: Dict[str, Any]) -> Exception:
    """The typed error a ``failed`` frame stands for."""
    message = str(frame.get("message", "the libei helper could not start"))
    code = frame.get("code")
    if code == "missing_dependency":
        return EiDependencyMissing(str(frame.get("dependency", "libei")),
                                   message)
    if code == "consent":
        return LibeiConsentNotGranted(
            message, str(frame.get("outcome", "")),
            bool(frame.get("declined", False)))
    return EiWorkerError(message)


def _close_quietly(stream: Any) -> None:
    try:
        if stream is not None:
            stream.close()
    except (OSError, ValueError):
        pass


def _stop_process(process: Any) -> Optional[int]:
    """Wait for a process that was asked to exit; escalate if it will not."""
    for stop in (None, process.terminate, process.kill):
        if stop is not None:
            try:
                stop()
            except OSError:
                pass
        try:
            return process.wait(timeout=_CLOSE_TIMEOUT)
        except subprocess.TimeoutExpired:
            continue
    return process.poll()


class WorkerBackend:
    """The emission surface of :class:`LibeiBackend`, served by a helper.

    ``keyboard`` and ``mouse`` call the same methods on either, so which one
    they hold is decided in :mod:`_select_input` and nowhere else.
    """

    def __init__(self, client: EiWorkerClient,
                 timeout_s: float = EMIT_TIMEOUT) -> None:
        self._client = client
        self._timeout_s = timeout_s

    @property
    def is_available(self) -> bool:
        """Always true: a backend only exists once its helper came up."""
        return True

    @property
    def is_connected(self) -> bool:
        """Whether the helper is still running."""
        return self._client.is_alive

    def _send(self, *events: InputEvent) -> InputAck:
        return self._client.send(events, timeout_s=self._timeout_s)

    def press_key(self, keycode: int) -> None:
        """Send a keydown for one evdev key code."""
        self._send(InputEvent(EV_KEY, int(keycode), 1))

    def release_key(self, keycode: int) -> None:
        """Send a keyup for one evdev key code."""
        self._send(InputEvent(EV_KEY, int(keycode), 0))

    def press_button(self, button_code: int) -> None:
        """Press one BTN_* code (272 is BTN_LEFT)."""
        self._send(InputEvent(EV_KEY, int(button_code), 1))

    def release_button(self, button_code: int) -> None:
        """Release one BTN_* code."""
        self._send(InputEvent(EV_KEY, int(button_code), 0))

    def click_button(self, button_code: int) -> None:
        """Press then release one BTN_* code, as one request."""
        self._send(InputEvent(EV_KEY, int(button_code), 1),
                   InputEvent(EV_KEY, int(button_code), 0))

    def set_position(self, x: int, y: int) -> None:
        """Move the pointer to an absolute screen position."""
        self._send(InputEvent(EV_ABS, ABS_X, int(x)),
                   InputEvent(EV_ABS, ABS_Y, int(y)),
                   InputEvent(EV_SYN, 0, 0))

    def scroll(self, dx: int, dy: int) -> None:
        """Scroll by whole wheel clicks, in libei's frame (positive y down)."""
        self._send(InputEvent(EV_REL, REL_HWHEEL, int(dx)),
                   InputEvent(EV_REL, REL_WHEEL, -int(dy)),
                   InputEvent(EV_SYN, 0, 0))

    def disconnect(self) -> None:
        """Close the helper, which ends the session."""
        self._client.close()


_DEFAULT_BACKEND: Optional[WorkerBackend] = None
_PROBE_FAILED = False
_PROBE_ERROR: Optional[BaseException] = None
_DEFAULT_LOCK = threading.Lock()


def connected_backend() -> Optional[WorkerBackend]:
    """A backend served by a running helper, or None — probing at most once.

    The counterpart of :func:`libei.connected_backend`, with the same
    contract: None means "use the ydotool CLI", and the reason is kept for
    :func:`last_probe_error`.
    """
    global _DEFAULT_BACKEND, _PROBE_FAILED, _PROBE_ERROR
    with _DEFAULT_LOCK:
        if _DEFAULT_BACKEND is not None:
            return _DEFAULT_BACKEND
        if _PROBE_FAILED:
            return None
        client = EiWorkerClient()
        try:
            client.start()
        except (LibeiUnavailable, OSError, ValueError) as error:
            _PROBE_FAILED = True
            _PROBE_ERROR = error
            return None
        _DEFAULT_BACKEND = WorkerBackend(client)
        return _DEFAULT_BACKEND


def last_probe_error() -> Optional[BaseException]:
    """Why the helper did not come up, if it did not."""
    with _DEFAULT_LOCK:
        return _PROBE_ERROR


def reset_default_backend() -> None:
    """Close the cached helper, if any, so the next probe starts fresh."""
    global _DEFAULT_BACKEND, _PROBE_FAILED, _PROBE_ERROR
    with _DEFAULT_LOCK:
        backend, _DEFAULT_BACKEND = _DEFAULT_BACKEND, None
        _PROBE_FAILED = False
        _PROBE_ERROR = None
    if backend is not None:
        backend.disconnect()


def _close_all_at_exit() -> None:
    """Do not leave a helper behind when the interpreter exits."""
    with _ACTIVE_LOCK:
        clients = list(_ACTIVE)
    for client in clients:
        client.close()


atexit.register(_close_all_at_exit)


__all__ = [
    "EMIT_TIMEOUT", "EiWorkerClient", "START_TIMEOUT", "WorkerBackend",
    "active_worker_count", "connected_backend", "last_probe_error",
    "reset_default_backend",
]
