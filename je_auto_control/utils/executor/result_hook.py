"""An opt-in hook that is told the result of every command one run executes.

A block command (``AC_loop``, ``AC_try``, ``AC_if_*``...) records its own
summary, so the result of a command in its body is in no execution record.
Whoever needs those results -- the Script Builder, to show a token issued
inside a loop once -- registers a callback for the run::

    with observe_results(callback):
        executor.execute_action(actions)

or ``execute_action(actions, result_callback=callback)``. The callback is
called after each command that returned, nested ones included, with
``(command, arguments, result, path)``:

* ``arguments`` is the action's second element as written (``None`` when it
  has none): placeholders such as ``${secrets.db}`` are not expanded.
* ``result`` is the object the command returned -- the same object the record
  holds, so the callback must not change it.
* ``path`` says where the step is: one :class:`StepPosition` per enclosing
  action list, outermost first.

A command that failed has no result and is not reported; neither is a
``dry_run``. The hook belongs to the thread that registered it and ends with
the ``with`` block: a thread started during the run (``AC_parallel``, a
scheduler) does not inherit it, and its commands are not reported. Nothing
about the run changes: what it returns, records and logs is the same with and
without a hook, and a callback that raises is logged by its exception type and
otherwise ignored. With no hook registered the executor pays one lookup per
action list and one per command.

``step_callback`` is a different contract and stays as it is: it is called
*before* each action of the list it was passed with, with that action alone,
and is not handed down to nested bodies -- its callers count top-level steps.
"""
from contextlib import contextmanager
from typing import Any, Callable, Iterator, List, NamedTuple, Optional, Tuple

from je_auto_control.utils.exception.exceptions import AutoControlActionException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.thread_bound import ThreadBoundVar


class StepPosition(NamedTuple):
    """Where a step is inside one action list.

    ``run`` counts the action lists the enclosing step has started so far (the
    iteration of a loop, the attempt of a retry; 1 for a body that runs once),
    ``position`` is the 1-based index of the step in its list and ``command``
    its name.
    """
    run: int
    position: int
    command: str


StepPath = Tuple[StepPosition, ...]
ResultHook = Callable[[str, Any, Any, StepPath], None]


class _Frame:
    """The action list being run: which of its steps is running, and how many lists that step started."""

    __slots__ = ("run", "position", "command", "started")

    def __init__(self, run: int) -> None:
        self.run = run
        self.position = 0
        self.command = ""
        self.started = 0

    def advance(self, position: int, action: Any) -> None:
        """Note that step ``position`` of this list is about to run."""
        self.position = position
        self.command = _command_of(action)
        self.started = 0


class _Observation:
    """One registered callback and the stack of action lists running under it."""

    __slots__ = ("callback", "frames", "started")

    def __init__(self, callback: ResultHook) -> None:
        self.callback = callback
        self.frames: List[_Frame] = []
        self.started = 0


_ACTIVE: "ThreadBoundVar[Optional[_Observation]]" = ThreadBoundVar("autocontrol_result_hook", None)


def _command_of(action: Any) -> str:
    if isinstance(action, list) and action and isinstance(action[0], str):
        return action[0]
    return "<invalid>"


@contextmanager
def observe_results(callback: ResultHook) -> Iterator[None]:
    """Report every command result of the runs inside the block to ``callback``.

    For the calling thread only, and only until the block ends. Raises
    ``AutoControlActionException`` when ``callback`` cannot be called.
    """
    if not callable(callback):
        raise AutoControlActionException("result_callback must be callable")
    token = _ACTIVE.set(_Observation(callback))
    try:
        yield
    finally:
        _ACTIVE.reset(token)


def enter_list() -> Optional[_Frame]:
    """Executor: an action list starts; ``None`` when no hook is registered."""
    observation = _ACTIVE.get()
    if observation is None:
        return None
    parent = observation.frames[-1] if observation.frames else observation
    parent.started += 1
    frame = _Frame(parent.started)
    observation.frames.append(frame)
    return frame


def leave_list(frame: Optional[_Frame]) -> None:
    """Executor: the action list of ``frame`` ended, however it ended."""
    if frame is None:
        return
    observation = _ACTIVE.get()
    if observation is not None and frame in observation.frames:
        del observation.frames[observation.frames.index(frame):]


def report_result(action: Any, result: Any) -> None:
    """Executor: ``action`` returned ``result``; tell the hook, if there is one."""
    observation = _ACTIVE.get()
    if observation is None or not observation.frames:
        return
    path = tuple(StepPosition(frame.run, frame.position, frame.command)
                 for frame in observation.frames)
    arguments = action[1] if isinstance(action, list) and len(action) > 1 else None
    try:
        observation.callback(_command_of(action), arguments, result, path)
    except Exception as error:  # noqa: BLE001  # reason: an observer must not fail the run it watches
        # The type only: the message could quote the result it was handed.
        autocontrol_logger.warning("result hook raised %s; ignored", type(error).__name__)


__all__ = ["ResultHook", "StepPath", "StepPosition", "observe_results"]
