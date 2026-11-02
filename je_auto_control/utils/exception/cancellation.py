"""Cooperative task cancellation and inert progress data without Qt dependencies."""
from concurrent.futures import CancelledError
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import math
from threading import Event, TIMEOUT_MAX
from typing import Callable, Iterator, Optional


@dataclass(frozen=True)
class TaskProgress:
    """One task's immutable progress observation, independent of any widget."""

    task_id: int
    completed: int
    total: Optional[int] = None
    detail: str = ''


class CancellationToken:
    """Thread-safe cooperative cancellation; work owns and releases its own resources."""

    def __init__(self, task_id: int, notify: Optional[Callable[[TaskProgress], None]] = None,
                 *, event: Optional[Event] = None) -> None:
        self._task_id = task_id
        self._notify = notify
        self._stop = event if event is not None else Event()

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


_CURRENT: ContextVar[Optional[CancellationToken]] = ContextVar('je_auto_control_cancellation', default=None)
_POLL_SECONDS = 0.1


def current_cancellation_token() -> Optional[CancellationToken]:
    """Return only this context's token; its presence grants no authority."""
    return _CURRENT.get()


@contextmanager
def cancellation_scope(token: Optional[CancellationToken]) -> Iterator[None]:
    """Bind one operation's token, or temporarily suspend it for bounded owned cleanup."""
    if token is not None and not isinstance(token, CancellationToken):
        raise TypeError('cancellation scope requires a CancellationToken or None')
    binding = _CURRENT.set(token)
    try:
        yield
    finally:
        _CURRENT.reset(binding)


def cancellation_checkpoint() -> None:
    """Observe cancellation at a safe boundary, without changing unscoped calls."""
    token = current_cancellation_token()
    if token is not None:
        token.checkpoint()


def cancellation_timeout(timeout_s: float) -> float:
    """Limit one poll interval within the caller's existing total deadline."""
    return min(timeout_s, _POLL_SECONDS) if current_cancellation_token() is not None else timeout_s


def cancellation_progress(completed: int, total: int, detail: str = '') -> None:
    """Report a scoped checkpoint without requiring progress machinery for ordinary calls."""
    token = current_cancellation_token()
    if token is not None:
        token.report(completed, total, detail)


__all__ = ['CancellationToken', 'TaskProgress', 'cancellation_scope']
