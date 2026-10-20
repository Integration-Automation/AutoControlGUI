"""Cooperative task cancellation and inert progress data without Qt dependencies."""
from concurrent.futures import CancelledError
from dataclasses import dataclass
import math
from threading import Event, TIMEOUT_MAX
from typing import Callable, Optional


@dataclass(frozen=True)
class TaskProgress:
    """One task's immutable progress observation, independent of any widget."""

    task_id: int
    completed: int
    total: Optional[int] = None
    detail: str = ''


class CancellationToken:
    """Thread-safe cooperative cancellation; work owns and releases its own resources."""

    def __init__(self, task_id: int, notify: Optional[Callable[[TaskProgress], None]] = None) -> None:
        self._task_id = task_id
        self._notify = notify
        self._stop = Event()

    @property
    def is_cancelled(self) -> bool:
        """Whether cancellation has been requested."""
        return self._stop.is_set()

    def cancel(self) -> None:
        """Request stop without closing another thread's resources or waiting."""
        self._stop.set()

    def checkpoint(self) -> None:
        """Raise cooperative cancellation at a safe resource-ownership boundary."""
        if self.is_cancelled:
            raise CancelledError()

    def wait(self, timeout_s: float) -> bool:
        """Wait at most a finite nonnegative interval; return whether stop was requested."""
        if not math.isfinite(timeout_s) or timeout_s < 0 or timeout_s > TIMEOUT_MAX:
            raise ValueError('cancellation wait needs a finite nonnegative timeout within threading.TIMEOUT_MAX')
        return self._stop.wait(timeout_s)

    def report(self, completed: int, total: Optional[int] = None, detail: str = '') -> None:
        """Publish inert progress at a cancellation checkpoint."""
        self.checkpoint()
        if isinstance(completed, bool) or not isinstance(completed, int) or completed < 0:
            raise ValueError('completed must be a nonnegative integer')
        if total is not None and (isinstance(total, bool) or not isinstance(total, int) or total < completed):
            raise ValueError('total must be an integer at least as large as completed')
        if not isinstance(detail, str):
            raise TypeError('progress detail must be text')
        if self._notify is not None:
            self._notify(TaskProgress(self._task_id, completed, total, detail))
