"""Run the libei session in a helper process, behind an opt-in switch.

**Why this exists.** ``ei_unref`` segfaults on libei 1.3.901 when a context's
backend opened and its handshake never progressed. ``LibeiBackend._teardown``
answers that by abandoning the context — a deliberate leak of one context and
one descriptor per process — because the alternative is a crash inside a
program that is driving someone's desktop. That in-process path is still the
default, and nothing here changes it.

A helper process is the other answer. The session lives in a child; when the
child exits, the operating system reclaims the context and the descriptor
whatever state libei left them in, and if libei does crash on some teardown
this project has not measured, it takes down a process that holds nothing
else. The parent keeps a pipe and a typed error.

**Why it is off by default.** Whether a *legitimate* cleanup still crashes on
a given libei can only be established on Linux, by the ``eis-verification``
job. Until that says the helper is needed, routing every keystroke through a
second process is cost without a measured benefit: a pipe round trip per
emission, a child to supervise, and a second way to fail. So
``JE_AUTOCONTROL_WAYLAND_EI_WORKER=1`` turns it on, and ``docker/eis_verify.py``
measures what it costs and what it reclaims.

**What the helper promises.**

* Requests carry an id, and a late answer to a request the caller gave up on
  is recognised and dropped, never mistaken for the next one's.
* A batch is bounded (:data:`ei_transport.MAX_BATCH`) and validated whole
  before any of it is applied.
* A caller's deadline or cancellation reaches the child, which stops between
  events and lets go of anything that batch had pressed.
* When the parent goes away — a clean close, or its pipe simply ending — the
  child releases every key and button still down before it exits.
* When the *child* dies without warning, the parent reports which keys were
  down in :class:`EiWorkerDied`. The compositor is expected to release them
  as it removes the dead client's devices; that is the EI protocol's job and
  is measured in CI rather than assumed here.

This module is the helper: run as
``python -m je_auto_control.linux_wayland.ei_worker`` it serves one session
and exits. The parent's half — starting it, sending to it, reclaiming it — is
:mod:`ei_client`, and what the two agree on is :mod:`ei_transport`.
"""
from __future__ import annotations

import os
import queue
import sys
import threading
from typing import Any, BinaryIO, Callable, Dict, Iterable, Optional, Set

from je_auto_control.linux_wayland.ei_transport import (
    ABS_X, ABS_Y, BUTTON_CODES, REL_HWHEEL, REL_WHEEL, EiProtocolError, Held,
    decode_batch, read_frame, write_frame,
)
from je_auto_control.linux_wayland.input_events import (
    EV_ABS, EV_KEY, EV_REL, EV_SYN, InputEvent,
)
from je_auto_control.linux_wayland.libei import (
    HANDSHAKE_TIMEOUT, LibeiBackend, LibeiConsentNotGranted,
    LibeiSessionRevoked, LibeiUnavailable,
)

_EOF = object()


class _Applier:
    """Turn evdev-shaped events into calls on a libei backend.

    Absolute motion and wheel deltas are gathered until ``EV_SYN`` (or the
    end of the batch), because that is how evdev spells "one pointer move":
    an X event, a Y event, then a sync.
    """

    def __init__(self, backend: Any) -> None:
        self._backend = backend
        self.held: Set[Held] = set()
        self._point: Dict[int, int] = {}
        self._wheel: Dict[int, int] = {}

    def apply(self, event: InputEvent) -> None:
        """Apply one event; libei's own refusals propagate."""
        if event.type == EV_KEY:
            self._key(event.code, event.value)
        elif event.type == EV_ABS:
            self._point[event.code] = event.value
        elif event.type == EV_REL:
            self._wheel[event.code] = (self._wheel.get(event.code, 0)
                                       + event.value)
        elif event.type == EV_SYN:
            self.flush()

    def _key(self, code: int, value: int) -> None:
        if value not in (0, 1):
            return  # 2 is the kernel's auto-repeat; libei has no such event
        kind = "button" if code in BUTTON_CODES else "key"
        if kind == "button":
            send = (self._backend.press_button if value
                    else self._backend.release_button)
        else:
            send = (self._backend.press_key if value
                    else self._backend.release_key)
        send(code)
        if value:
            self.held.add((kind, code))
        else:
            self.held.discard((kind, code))

    def flush(self) -> None:
        """Send whatever motion and scroll has been gathered."""
        point, self._point = self._point, {}
        wheel, self._wheel = self._wheel, {}
        if ABS_X in point and ABS_Y in point:
            self._backend.set_position(point[ABS_X], point[ABS_Y])
        horizontal = wheel.get(REL_HWHEEL, 0)
        vertical = wheel.get(REL_WHEEL, 0)
        if horizontal or vertical:
            # The kernel counts REL_WHEEL up as positive; libei counts down.
            self._backend.scroll(horizontal, -vertical)

    def discard_pending(self) -> None:
        """Forget gathered motion — a cancelled batch must not move later."""
        self._point, self._wheel = {}, {}

    def release(self, held: Iterable[Held]) -> None:
        """Let go of ``held``; a refusal for one must not strand the rest."""
        for kind, code in sorted(held):
            send = (self._backend.release_button if kind == "button"
                    else self._backend.release_key)
            try:
                send(code)
            except LibeiUnavailable:
                pass
            self.held.discard((kind, code))


class _Server:
    """The child's side of the conversation."""

    def __init__(self, reader: BinaryIO, writer: BinaryIO,
                 backend_factory: Callable[[], Any]) -> None:
        self._reader = reader
        self._writer = writer
        self._factory = backend_factory
        self._inbox: "queue.Queue[Any]" = queue.Queue()
        self._cancelled: Set[int] = set()
        self._lock = threading.Lock()
        self._applier: Optional[_Applier] = None
        self._backend: Any = None

    def run(self) -> int:
        """Serve until the parent closes or goes away; return an exit code."""
        threading.Thread(target=self._pump, name="ei-worker-reader",
                         daemon=True).start()
        try:
            if not self._start(self._inbox.get()):
                return 1
            self._serve()
            return 0
        finally:
            self._shutdown()

    def _pump(self) -> None:
        """Read frames off the pipe; cancellations jump the queue."""
        while True:
            try:
                frame = read_frame(self._reader)
            except (EiProtocolError, OSError, ValueError):
                frame = None
            if frame is None:
                self._inbox.put(_EOF)
                return
            if frame.get("op") == "cancel":
                with self._lock:
                    self._cancelled.add(int(frame.get("id", -1)))
                continue
            self._inbox.put(frame)

    def _start(self, frame: Any) -> bool:
        if frame is _EOF or frame.get("op") != "start":
            return False
        try:
            self._backend = self._connect(frame)
        except LibeiConsentNotGranted as error:
            self._reply({"op": "failed", "code": "consent",
                         "message": str(error), "outcome": error.outcome,
                         "declined": error.declined})
            return False
        except (LibeiUnavailable, OSError, ValueError) as error:
            self._reply({"op": "failed", "code": "unavailable",
                         "message": str(error)})
            return False
        if self._backend is None:
            self._reply({"op": "failed", "code": "missing_dependency",
                         "dependency": "libei",
                         "message": "libei.so.* not found on the loader path"})
            return False
        self._applier = _Applier(self._backend)
        self._reply({"op": "ready"})
        return True

    def _connect(self, frame: Dict[str, Any]) -> Any:
        """A connected backend, or None when libei is not installed."""
        backend = self._factory()
        if not backend.is_available:
            return None
        socket_path = frame.get("socket")
        backend.connect(
            timeout=float(frame.get("timeout") or HANDSHAKE_TIMEOUT),
            socket_path=socket_path.encode("utf-8") if socket_path else None)
        return backend

    def _serve(self) -> None:
        while True:
            frame = self._inbox.get()
            if frame is _EOF or frame.get("op") == "close":
                return
            if frame.get("op") == "batch":
                self._reply(self._batch(self._applier, frame))

    def _is_cancelled(self, request_id: int) -> bool:
        with self._lock:
            return request_id in self._cancelled

    def _batch(self, applier: Any, frame: Dict[str, Any]) -> Dict[str, Any]:
        """Apply one batch and describe how it went."""
        request_id = int(frame.get("id", -1))
        answer: Dict[str, Any] = {"op": "ack", "id": request_id, "applied": 0}
        before = set(applier.held)
        try:
            for event in decode_batch(frame.get("events")):
                if self._is_cancelled(request_id):
                    applier.discard_pending()
                    applier.release(applier.held - before)
                    answer["cancelled"] = True
                    break
                applier.apply(event)
                answer["applied"] += 1
            else:
                applier.flush()
        except LibeiSessionRevoked as error:
            answer.update(op="error", message=str(error), revoked=True)
        except LibeiUnavailable as error:
            applier.discard_pending()
            answer.update(op="error", message=str(error), revoked=False)
        answer["held"] = sorted([kind, code] for kind, code in applier.held)
        return answer

    def _reply(self, message: Dict[str, Any]) -> None:
        try:
            write_frame(self._writer, message)
        except (OSError, ValueError):
            pass  # the parent is gone; the main loop sees EOF and unwinds

    def _shutdown(self) -> None:
        """Release what is held, then let the session go."""
        if self._applier is not None:
            self._applier.release(set(self._applier.held))
        if self._backend is not None:
            # State-aware: a completed session is unreffed, a half-open one
            # is abandoned — and here "abandoned" means "reclaimed at exit".
            self._backend.disconnect()


def serve(reader: BinaryIO, writer: BinaryIO,
          backend_factory: Optional[Callable[[], Any]] = None) -> int:
    """Run the child's loop over two binary streams; return its exit code."""
    return _Server(reader, writer, backend_factory or LibeiBackend).run()


def main() -> int:
    """Entry point of the helper process."""
    # Keep the frame stream private: anything else that writes to stdout —
    # a library's diagnostics, a stray log handler — goes to stderr instead
    # of into the middle of a frame.
    frames = os.fdopen(os.dup(sys.stdout.fileno()), "wb", buffering=0)
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    sys.stdout = sys.stderr
    # Unbuffered, and not ``sys.stdin.buffer``: the reader thread spends its
    # life blocked in a read, and a buffered reader holds a lock while it
    # does — which the interpreter then cannot take at shutdown.
    requests = os.fdopen(os.dup(sys.stdin.fileno()), "rb", buffering=0)
    return serve(requests, frames)


def run_as_helper() -> None:
    """Serve, then leave without unwinding the interpreter. Never returns.

    The reader thread is still blocked on the pipe when the loop ends, and
    libei may hold a context that must not be released (the half-open state
    this helper exists for). Both are the operating system's to reclaim, so
    the process ends with ``os._exit`` once the log handlers are flushed —
    measured, not stylistic: with an ordinary exit the interpreter aborted in
    finalisation on the blocked reader, turning a clean answer into a crash.
    """
    import faulthandler
    import logging
    import signal

    # A crash in here is a native one. Without this it is a bare exit status
    # in the parent; with it, stderr carries the Python stack that led there.
    faulthandler.enable()

    def _unwind(_signum: int, _frame: Any) -> None:
        # Raised in the main thread, so the serve loop's ``finally`` runs and
        # held keys are released before a polite termination takes effect.
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _unwind)
    try:
        code = main()
    except SystemExit as stop:
        code = stop.code if isinstance(stop.code, int) else 0
    logging.shutdown()
    sys.stderr.flush()
    os._exit(code)


__all__ = ["main", "run_as_helper", "serve"]


if __name__ == "__main__":
    run_as_helper()
