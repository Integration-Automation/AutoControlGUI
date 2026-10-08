"""The executor's hook into the action journal, and the switch that turns it on.

Journalling is opt-in. With no journal started, :func:`step` returns one
shared no-op object -- a global read and a function call per action, nothing
allocated -- so dispatch costs what it did before this module existed.

Once :func:`start_action_journal` has run, every action the executor runs --
from the GUI, the CLI, the REST, socket and MCP servers alike, because they
all end in ``Executor._run_one_action`` -- is written when it starts and again
when it ends. The parent of a nested action is whatever action is running on
the same thread; an ``AC_parallel`` branch runs on a new thread, so the block
hands its own step over with :func:`branch_scope`. A runner that submits work
to a thread pool (the DAG runner, the device matrix) wraps what it submits in
:func:`carry_step` for the same reason.

Pure standard library; imports no ``PySide6``.
"""
import dataclasses
import itertools
import threading
import time
import uuid
from pathlib import Path
from types import TracebackType
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, TypeVar, Union

from je_auto_control.utils.action_journal.events import (
    STATUS_ERROR, STATUS_INCOMPLETE, STATUS_OK, ActionEvent,
)
from je_auto_control.utils.action_journal.sanitize import (
    artifacts_of_step, describe_outcome, sanitise_params,
)
from je_auto_control.utils.action_journal.store import ActionJournal
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger

_MAX_ERROR_CHARS = 1000


class ActionJournalError(AutoControlException, RuntimeError):
    """A journal was started while another one was still running."""


class _Session:
    """One started journal: where it writes and the ids it hands out."""

    def __init__(self, journal: ActionJournal, run_id: str,
                 session: Optional[str]) -> None:
        self.journal = journal
        self.run_id = run_id
        self.label = session
        self.token = uuid.uuid4().hex[:8]
        self.started = 0
        self.error: Optional[str] = None
        self._counter = itertools.count(1)
        self._lock = threading.Lock()

    def start_event(self, event: ActionEvent) -> ActionEvent:
        """Number ``event`` and write its start line, in one critical section.

        Numbering and writing together is what makes file order the order
        the actions started in, across threads.
        """
        with self._lock:
            sequence = next(self._counter)
            numbered = dataclasses.replace(
                event, sequence=sequence, step_id=f"{self.token}-{sequence}")
            self.journal.append(numbered)
            self.started = sequence
        return numbered

    def status(self) -> Dict[str, Any]:
        """The session as a JSON-ready dict."""
        return {"path": str(self.journal.path), "run_id": self.run_id,
                "session": self.label, "events": self.started, "error": self.error}


#: The started journal, or ``None``. Read without a lock on every action.
_ACTIVE: Optional[_Session] = None
#: The session most recently stopped (or failed), for the status report.
_LAST: Optional[_Session] = None
_SWITCH = threading.Lock()
#: Per thread: ``stack`` of running step ids, plus what a branch inherited.
_LOCAL = threading.local()


class _NullStep:
    """What :func:`step` returns while no journal is started; does nothing."""

    __slots__ = ()

    def __enter__(self) -> "_NullStep":
        return self

    def __exit__(self, *_exc: Any) -> None:
        """Let any exception through."""

    def outcome(self, _value: Any) -> None:
        """Ignore the action's return value."""


_NULL = _NullStep()


def _stack() -> List[str]:
    stack = getattr(_LOCAL, "stack", None)
    if stack is None:
        stack = _LOCAL.stack = []
    return stack


def _open_steps() -> List["_Step"]:
    running = getattr(_LOCAL, "steps", None)
    if running is None:
        running = _LOCAL.steps = []
    return running


def _error_text(error: BaseException) -> str:
    # The same masking log lines get: an error message can quote an argument.
    from je_auto_control.utils.config_redaction.config_redaction import (
        redact_secret_text,
    )
    return redact_secret_text(repr(error)[:_MAX_ERROR_CHARS])


def _control_signals() -> Tuple[type, ...]:
    from je_auto_control.utils.executor.flow_control import LoopBreak, LoopContinue
    return LoopBreak, LoopContinue


class _Step:
    """One running action: writes its start on entry and its end on exit."""

    __slots__ = ("_session", "_action", "_event", "_outcome", "_result", "artifacts")

    def __init__(self, session: _Session, action: Any) -> None:
        self._session = session
        self._action = action
        self._event: Optional[ActionEvent] = None
        self._outcome: Optional[Dict[str, Any]] = None
        self._result: Any = None
        #: What :func:`note_artifact` attached while this step was running.
        self.artifacts: List[Dict[str, str]] = []

    def __enter__(self) -> "_Step":
        session, action = self._session, self._action
        command = action[0] if action and isinstance(action[0], str) else "<invalid>"
        params, unreplayable = sanitise_params(
            command, action[1] if len(action) > 1 else None)
        stack = _stack()
        event = ActionEvent(
            run_id=session.run_id, step_id="", sequence=0, command=command,
            parent_id=stack[-1] if stack else getattr(_LOCAL, "parent", None),
            params=params, unreplayable=unreplayable, started_at=time.time(),
            branch=getattr(_LOCAL, "branch", None), thread=threading.get_ident(),
            session=session.label)
        try:
            self._event = session.start_event(event)
        except OSError as error:
            _fail(session, error)
            return self
        stack.append(self._event.step_id)
        _open_steps().append(self)
        return self

    def outcome(self, value: Any) -> None:
        """Note what the action returned (by type and size only)."""
        self._outcome = describe_outcome(value)
        self._result = value

    def __exit__(self, exc_type: Optional[Type[BaseException]],
                 exc: Optional[BaseException], _tb: Optional[TracebackType]) -> None:
        event = self._event
        if event is None:
            return
        stack = _stack()
        if stack and stack[-1] == event.step_id:
            stack.pop()
        running = _open_steps()
        if running and running[-1] is self:
            running.pop()
        ended = self._ended(event, exc)
        _LOCAL.last = (self._session, ended)
        try:
            self._session.journal.append_end(ended)
        except OSError as error:
            _fail(self._session, error)

    def _ended(self, event: ActionEvent, exc: Optional[BaseException]) -> ActionEvent:
        """``event`` with the status its exit earned."""
        status, error, outcome = STATUS_OK, None, self._outcome
        if exc is not None and isinstance(exc, _control_signals()):
            # AC_break / AC_continue unwinding through a block is the block
            # doing its job, not a failure.
            outcome = {"type": "signal", "signal": type(exc).__name__}
        elif isinstance(exc, Exception):
            status, error = STATUS_ERROR, _error_text(exc)
        elif exc is not None:
            # KeyboardInterrupt / SystemExit: the action never finished.
            status, error = STATUS_INCOMPLETE, _error_text(exc)
        params = self._action[1] if len(self._action) > 1 else None
        found = self.artifacts + [
            item for item in artifacts_of_step(params, self._result, event.started_at)
            if item not in self.artifacts]
        return dataclasses.replace(
            event, status=status, error=error, outcome=outcome,
            finished_at=time.time(), artifacts=tuple(found))


def _fail(session: _Session, error: OSError) -> None:
    """Stop journalling after a write failed; the automation itself goes on."""
    global _ACTIVE, _LAST
    session.error = repr(error)
    autocontrol_logger.error(
        "action journal %s stopped: %r", session.journal.path, error)
    with _SWITCH:
        if _ACTIVE is session:
            _ACTIVE, _LAST = None, session


def step(action: Any) -> Union[_Step, _NullStep]:
    """A context manager recording ``action``; a shared no-op when journalling is off."""
    session = _ACTIVE
    if session is None:
        return _NULL
    return _Step(session, action)


def current_step() -> Optional[str]:
    """The id of the step running on this thread, when a journal is started."""
    if _ACTIVE is None:
        return None
    stack = getattr(_LOCAL, "stack", None)
    return stack[-1] if stack else getattr(_LOCAL, "parent", None)


def note_artifact(kind: str, *, path: Optional[str] = None,
                  ident: Optional[str] = None) -> bool:
    """Attach something a step produced to that step's journal record.

    ``kind`` says what it is (``"screenshot"``, ``"report"``, ``"trace"``...);
    give the file's ``path`` or an ``ident`` such as a trace id. It goes to the
    step running on this thread. With none running -- a failure screenshot is
    taken once the run has already failed -- it goes to the step that most
    recently ended on this thread, as a second ``end`` line. Returns whether
    anything was recorded; with no journal started this does nothing.
    """
    session = _ACTIVE
    if session is None or (path is None and ident is None):
        return False
    entry: Dict[str, str] = {"kind": str(kind)}
    if path is not None:
        entry["path"] = str(path)
    if ident is not None:
        entry["id"] = str(ident)
    running = getattr(_LOCAL, "steps", None)
    if running:
        if entry not in running[-1].artifacts:
            running[-1].artifacts.append(entry)
        return True
    return _note_after_end(session, entry)


def _note_after_end(session: _Session, entry: Dict[str, str]) -> bool:
    """Rewrite the end of this thread's last step with ``entry`` added."""
    last_session, last = getattr(_LOCAL, "last", None) or (None, None)
    if last is None or last_session is not session:
        return False
    if entry in last.artifacts:
        return True
    updated = dataclasses.replace(last, artifacts=last.artifacts + (entry,))
    try:
        session.journal.append_end(updated)
    except OSError as error:
        _fail(session, error)
        return False
    _LOCAL.last = (session, updated)
    return True


class _BranchScope:
    """Binds the parent step and branch index of a worker thread for a block."""

    __slots__ = ("_parent", "_index", "_before")

    def __init__(self, parent: Optional[str], index: Optional[int] = None) -> None:
        self._parent = parent
        self._index = index
        self._before: Tuple[Optional[str], Optional[int]] = (None, None)

    def __enter__(self) -> "_BranchScope":
        # Restored on exit: a pool thread is reused, and a scope may be
        # entered on a thread that is itself a branch.
        self._before = (getattr(_LOCAL, "parent", None), getattr(_LOCAL, "branch", None))
        _LOCAL.parent = self._parent
        _LOCAL.branch = self._index
        return self

    def __exit__(self, *_exc: Any) -> None:
        _LOCAL.parent, _LOCAL.branch = self._before


def branch_scope(parent: Optional[str], index: Optional[int] = None) -> _BranchScope:
    """Make ``parent`` the parent of what this (new) thread runs, as branch ``index``."""
    return _BranchScope(parent, index)


_Work = TypeVar("_Work", bound=Callable[..., Any])


def carry_step(work: _Work, index: Optional[int] = None) -> _Work:
    """``work`` bound to the step running here, for a call on another thread.

    Call this on the thread that hands the work over (it reads that thread's
    running step); what ``work`` runs on the pool thread is then recorded as
    that step's child, branch ``index``. With no journal started, ``work`` is
    returned untouched.
    """
    if _ACTIVE is None:
        return work
    parent = current_step()

    def carried(*args: Any, **kwargs: Any) -> Any:
        with branch_scope(parent, index):
            return work(*args, **kwargs)
    return carried  # type: ignore[return-value]  # reason: same call signature as work


def start_action_journal(path: Union[str, Path, None] = None, *,
                         run_id: Optional[str] = None,
                         session: Optional[str] = None) -> Dict[str, Any]:
    """Start writing every executed action to the journal at ``path``.

    ``path`` defaults to ``~/.je_auto_control/action_journal.jsonl``; the file
    is appended to, never truncated. Everything recorded until
    :func:`stop_action_journal` belongs to ``run_id`` (a fresh one when not
    given). ``session`` is a free label -- a device or session name -- stored
    on each event. Raises :class:`ActionJournalError` if one is already started.
    """
    global _ACTIVE
    journal = ActionJournal(Path(path).resolve() if path is not None else None)
    journal.path.parent.mkdir(parents=True, exist_ok=True)
    started = _Session(journal, str(run_id) if run_id else uuid.uuid4().hex, session)
    with _SWITCH:
        if _ACTIVE is not None:
            raise ActionJournalError(
                f"an action journal is already started ({_ACTIVE.journal.path})")
        _ACTIVE = started
    return started.status()


def stop_action_journal() -> Dict[str, Any]:
    """Stop journalling; return the stopped session (path, run id, event count).

    Actions still running finish their records. Stopping when nothing is
    started is not an error: the result says ``"active": False``.
    """
    global _ACTIVE, _LAST
    with _SWITCH:
        stopped, _ACTIVE = _ACTIVE, None
        _LAST = stopped or _LAST
    if stopped is None:
        return {"active": False}
    return {"active": False, **stopped.status()}


def action_journal_status() -> Dict[str, Any]:
    """Whether a journal is started, and where it writes."""
    session, last = _ACTIVE, _LAST
    if session is not None:
        return {"active": True, **session.status()}
    return {"active": False, **({"last": last.status()} if last is not None else {})}
