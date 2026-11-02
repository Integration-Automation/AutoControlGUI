"""Cooperative stop for a running action list.

The executor had no way to end a run from outside: a script started from the
GUI, a server request or a scheduler ran until its last action. A run that
opts in -- :func:`stoppable_run`, ``execute_action_with_vars(..., run_id=...)``
or the ``AC_run_stoppable`` block -- carries a :class:`StopToken`:

* The executor checks it **before every action**, at every loop pass, and the
  waits of the block commands (``AC_sleep``, ``AC_wait_image``,
  ``AC_wait_pixel``, the ``AC_retry`` back-off) sleep on it, so they wake the
  moment a stop is requested. So do the polling waits outside the executor
  (``AC_wait_window``, ``AC_wait_text``, the smart waits, ``AC_expect_poll``
  and the rest): between two probes they sleep on :func:`pause`.
* A requested stop raises :class:`ExecutionStopped` on the run's own thread.
  It is never recorded-and-continued and ``AC_try`` / ``AC_retry`` do not
  catch it, but it is an ordinary exception: every ``finally`` on the way out
  runs, which is how ``type_keyboard`` / ``hotkey`` / ``AC_with_modifiers``
  let go of what they hold. An ``AC_try`` ``finally`` branch runs to its end
  first; a second stop request interrupts that as well.
* Keys and mouse buttons the run pressed with ``AC_press_keyboard_key`` /
  ``AC_press_mouse`` and has not released are released when the stopped run
  unwinds.
* The stop is sticky: an adapter that swallows the exception only delays it to
  the next checkpoint.

What is **not** interrupted: a command already inside the backend (one image
search, one OCR read, one HTTP request, a wrapper's own ``time.sleep``). The
run ends when that command returns.

Without a token nothing here does anything: ``executor.execute_action(...)``
called from plain Python behaves exactly as before.

A run is the thread that entered it. A thread started inside a run is not
part of it -- on every build, including a free-threaded one, where a new
thread inherits its creator's context variables -- unless it is handed the
token and binds it with :func:`bound_stop_token`, as ``AC_parallel`` does.
"""
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.thread_bound import ThreadBoundVar


class ExecutionStopped(AutoControlException):
    """The run was asked to stop; raised on the run's thread at its next checkpoint."""

    def __init__(self, run_id: str = "", reason: str = "") -> None:
        self.run_id = run_id
        self.reason = reason
        detail = f": {reason}" if reason else ""
        super().__init__(f"execution {run_id!r} stopped{detail}")


#: Commands that leave something held, and the commands that let go of it.
_HOLD_COMMANDS: Dict[str, Tuple[str, bool]] = {
    "AC_press_keyboard_key": ("key", True),
    "AC_release_keyboard_key": ("key", False),
    "AC_press_mouse": ("mouse", True),
    "AC_release_mouse": ("mouse", False),
}
_HOLD_ARGUMENT = {"key": "keycode", "mouse": "mouse_keycode"}


class StopToken:
    """What one run holds to learn that it should stop. Thread-safe."""

    def __init__(self, run_id: Optional[str] = None) -> None:
        self.run_id = str(run_id) if run_id else uuid.uuid4().hex[:12]
        self.reason = ""
        self.started_at = time.time()
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._requests = 0
        self._held: List[Tuple[str, Any]] = []

    @property
    def stopped(self) -> bool:
        """Whether a stop has been requested."""
        return self._event.is_set()

    @property
    def forced(self) -> bool:
        """Whether a stop was requested more than once (cleanup is interrupted too)."""
        with self._lock:
            return self._requests > 1

    def stop(self, reason: str = "") -> bool:
        """Request the stop; return whether this was the first request.

        Never blocks and never waits for the run: safe from a GUI thread.
        """
        with self._lock:
            self._requests += 1
            first = self._requests == 1
            if first:
                self.reason = str(reason)
        self._event.set()
        return first

    def raise_if_stopped(self) -> None:
        """Raise :class:`ExecutionStopped` once a stop was requested."""
        if self._event.is_set():
            raise ExecutionStopped(self.run_id, self.reason)

    def wait(self, seconds: float) -> bool:
        """Sleep up to ``seconds``, waking on a stop; return whether stopped."""
        return self._event.wait(max(0.0, seconds))

    def note_input(self, kind: str, code: Any, pressed: bool) -> None:
        """Remember (or forget) a key or mouse button this run holds down."""
        with self._lock:
            if pressed:
                self._held.append((kind, code))
            elif (kind, code) in self._held:
                self._held.remove((kind, code))

    def take_held(self) -> List[Tuple[str, Any]]:
        """What the run still holds, newest first; the list is emptied."""
        with self._lock:
            held, self._held = list(reversed(self._held)), []
        return held


# Thread-bound: where a new thread inherits its creator's context variables (a
# free-threaded build), a scheduler or observer thread first started inside a
# run would otherwise answer to that run's token for ever -- and a stop is
# sticky. A thread joins a run only through bound_stop_token().
_CURRENT: ThreadBoundVar[Optional[StopToken]] = ThreadBoundVar("je_auto_control_stop_token", None)
_SHIELDED: ThreadBoundVar[int] = ThreadBoundVar("je_auto_control_stop_shield", 0)
_REGISTRY_LOCK = threading.Lock()
_ACTIVE: Dict[str, StopToken] = {}


def current_stop_token() -> Optional[StopToken]:
    """The token of the stoppable run this thread is inside, else ``None``."""
    return _CURRENT.get()


def checkpoint() -> None:
    """Raise :class:`ExecutionStopped` if the current run was asked to stop.

    A no-op outside a stoppable run, and inside :func:`shielded` until the
    stop is requested a second time.
    """
    token = _CURRENT.get()
    if token is None or not token.stopped:
        return
    if _SHIELDED.get() and not token.forced:
        return
    raise ExecutionStopped(token.run_id, token.reason)


def pause(seconds: float, sleep: Optional[Callable[[float], Any]] = None) -> None:
    """Sleep ``seconds``; inside a stoppable run, wake and raise on a stop.

    Outside one this is exactly ``time.sleep(seconds)`` -- or ``sleep(seconds)``
    when the caller hands in the sleep it used before it became stop-aware,
    which keeps a module's own ``time.sleep`` the seam its tests replace.
    This is what every polling wait reachable from an ``AC_*`` command sleeps
    on between two probes, so a stop ends the wait instead of its timeout.
    """
    token = _CURRENT.get()
    if token is None or (_SHIELDED.get() and not token.forced):
        (sleep if sleep is not None else time.sleep)(seconds)
        return
    checkpoint()
    if token.wait(seconds):
        checkpoint()


@contextmanager
def shielded() -> Iterator[None]:
    """Let cleanup run although the run was stopped (an ``AC_try`` ``finally`` branch).

    A second stop request ends the shield, so cleanup that never returns
    cannot make a run unstoppable.
    """
    depth = _SHIELDED.set(_SHIELDED.get() + 1)
    try:
        yield
    finally:
        _SHIELDED.reset(depth)


@contextmanager
def bound_stop_token(token: Optional[StopToken]) -> Iterator[Optional[StopToken]]:
    """Make an existing token current on this thread (an ``AC_parallel`` branch)."""
    bound = _CURRENT.set(token)
    try:
        yield token
    finally:
        _CURRENT.reset(bound)


@contextmanager
def stoppable_run(run_id: Optional[str] = None,
                  token: Optional[StopToken] = None) -> Iterator[StopToken]:
    """Run the block as a stoppable run; yield its :class:`StopToken`.

    Everything the executor runs on this thread inside the block -- nested
    bodies, macros, ``AC_parallel`` branches -- stops when the token does.
    ``run_id`` names the run for :func:`stop_execution` (one is generated when
    omitted); pass ``token`` to use one created beforehand, e.g. by the thread
    that will request the stop. A block inside another stoppable run joins it
    unless it brings its own ``run_id`` or ``token``. When the run ends
    stopped, keys and buttons it still holds are released.
    """
    outer = _CURRENT.get()
    if outer is not None and run_id is None and token is None:
        yield outer
        return
    own = token if token is not None else StopToken(run_id)
    with _REGISTRY_LOCK:
        if own.run_id in _ACTIVE and _ACTIVE[own.run_id] is not own:
            raise AutoControlException(f"a run named {own.run_id!r} is already active")
        _ACTIVE[own.run_id] = own
    bound = _CURRENT.set(own)
    try:
        yield own
    finally:
        _CURRENT.reset(bound)
        with _REGISTRY_LOCK:
            _ACTIVE.pop(own.run_id, None)
        if own.stopped:
            release_held_inputs(own)


def stop_execution(run_id: Optional[str] = None, reason: str = "") -> int:
    """Ask a stoppable run to stop; return how many runs were asked.

    With ``run_id`` only that run; without, every active stoppable run except
    the caller's own (so a script can stop the others and carry on). Returns
    at once: the runs end at their next checkpoint, on their own threads.
    """
    with _REGISTRY_LOCK:
        if run_id is not None:
            targets = [_ACTIVE[run_id]] if run_id in _ACTIVE else []
        else:
            own = _CURRENT.get()
            targets = [token for token in _ACTIVE.values() if token is not own]
    for token in targets:
        token.stop(reason)
    if targets:
        autocontrol_logger.info("stop requested for run(s): %s",
                                ", ".join(token.run_id for token in targets))
    return len(targets)


def active_executions() -> List[Dict[str, Any]]:
    """The stoppable runs in progress: ``run_id``, ``started_at``, ``stopping``."""
    with _REGISTRY_LOCK:
        tokens = list(_ACTIVE.values())
    return [{"run_id": token.run_id, "started_at": token.started_at,
             "stopping": token.stopped} for token in tokens]


def note_command(name: str, arguments: Any) -> None:
    """Executor hook: track what a press / release command leaves held in this run."""
    hold = _HOLD_COMMANDS.get(name)
    if hold is None:
        return
    token = _CURRENT.get()
    if token is None:
        return
    kind, pressed = hold
    if isinstance(arguments, dict):
        code = arguments.get(_HOLD_ARGUMENT[kind])
    elif isinstance(arguments, (list, tuple)) and arguments:
        code = arguments[0]
    else:
        return
    try:
        token.note_input(kind, code, pressed)
    except TypeError:  # reason: an unhashable code cannot be compared; nothing to track
        return


def release_held_inputs(token: StopToken) -> int:
    """Release the keys and buttons ``token``'s run still holds; return how many.

    Never raises: this runs while a stop unwinds.
    """
    held = token.take_held()
    if not held:
        return 0
    from je_auto_control.wrapper.auto_control_keyboard import release_keyboard_key
    from je_auto_control.wrapper.auto_control_mouse import release_mouse
    releasers: Dict[str, Callable[[Any], Any]] = {"key": release_keyboard_key, "mouse": release_mouse}
    for kind, code in held:
        try:
            releasers[kind](code)
        except Exception as error:  # noqa: BLE001  # reason: logged; the other releases must still run
            autocontrol_logger.warning("could not release %s %r after a stop: %r", kind, code, error)
    return len(held)


__all__ = [
    "ExecutionStopped", "StopToken", "active_executions", "bound_stop_token",
    "checkpoint", "current_stop_token", "note_command", "pause",
    "release_held_inputs", "shielded", "stop_execution", "stoppable_run",
]
