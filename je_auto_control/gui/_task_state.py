"""Qt-free immutable task payloads and cooperative cancellation/deadline checkpoints."""
from __future__ import annotations

from dataclasses import dataclass
import math
import threading
import time
from typing import Callable

from je_auto_control.utils.exception.exceptions import AutoControlException


class TaskControllerError(AutoControlException, ValueError):
    """Invalid task configuration or a task submitted outside its GUI owner thread."""


class TaskCancelled(AutoControlException):
    """A cooperative task reached cancellation or its configured deadline."""


@dataclass(frozen=True)
class TaskResult:
    """Completed value identified by the originating run, not the current panel selection."""

    run_id: str
    value: object


@dataclass(frozen=True)
class TaskError:
    """Structured failure state and recovery text for one run."""

    run_id: str
    state: str
    message: str
    recovery: str = ''


@dataclass(frozen=True)
class TaskProgress:
    """Bounded progress update for one run; it carries no Qt widget references."""

    run_id: str
    percent: int
    message: str = ''


class CancellationToken:
    """Pass an Event/deadline into bounded backends and check before and after each operation."""

    def __init__(self, run_id: str, timeout_s: float,
                 report: Callable[[TaskProgress], None]) -> None:
        if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)):
            raise TaskControllerError('task timeout must be a positive finite number')
        if not math.isfinite(timeout_s) or timeout_s <= 0:
            raise TaskControllerError('task timeout must be a positive finite number')
        self.run_id = run_id
        self.event = threading.Event()
        self.deadline = time.monotonic() + timeout_s
        self._report = report
        self._timed_out = False

    @property
    def timed_out(self) -> bool:
        """Whether cancellation was caused by the deadline."""
        return self._timed_out

    def cancel(self, *_args: object) -> None:
        """Signal cancellation without blocking Qt or touching backend/GUI objects."""
        self.event.set()

    def expire(self) -> None:
        """Signal the deadline while a backend is waiting on the cancellation Event."""
        self._timed_out = True
        self.event.set()

    def remaining_s(self) -> float:
        """Return a positive request timeout or raise at the cancellation boundary."""
        self.checkpoint()
        return max(.001, self.deadline - time.monotonic())

    def checkpoint(self) -> None:
        """Reject new work once cancelled; native resource cleanup belongs in the work's finally."""
        if time.monotonic() >= self.deadline and not self.event.is_set():
            self.expire()
        if self.event.is_set():
            raise TaskCancelled('task deadline expired' if self.timed_out else 'task cancelled')

    def wait(self, seconds: float) -> None:
        """Wake AC_sleep and polling promptly when a GUI task is cancelled."""
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError('sleep seconds must be a nonnegative finite number')
        self.event.wait(min(seconds, self.remaining_s()))
        self.checkpoint()

    def report(self, percent: int, message: str = '') -> None:
        """Queue a typed progress value; never call a widget from the worker."""
        self.checkpoint()
        if isinstance(percent, bool) or not isinstance(percent, int) or not 0 <= percent <= 100:
            raise TaskControllerError('task progress must be an integer from 0 through 100')
        if not isinstance(message, str):
            raise TaskControllerError('task progress message must be text')
        self._report(TaskProgress(self.run_id, percent, message))

    def retire(self) -> None:
        """Release the completed worker's signal reference without altering terminal outcome."""
        self._report = lambda _value: None


def task_error(run_id: str, failure: Exception) -> TaskError:
    """Map explicit exception types, without inferring native permissions from error strings."""
    if isinstance(failure, PermissionError):
        state = 'needs_permission'
    elif isinstance(failure, ImportError):
        state = 'needs_dependency'
    elif isinstance(failure, NotImplementedError):
        state = 'unsupported'
    else:
        state = 'error'
    return TaskError(run_id, state, str(failure))


__all__ = ['CancellationToken', 'TaskCancelled', 'TaskControllerError', 'TaskResult', 'TaskError', 'TaskProgress']
