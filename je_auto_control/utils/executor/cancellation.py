"""Internal Qt-free cancellation context shared by nested executors and device workers."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import time
from typing import Iterator, Optional, Protocol


class CancellationBoundary(Protocol):
    """Minimal cooperative boundary; implementations can remain independent of GUI code."""

    def checkpoint(self) -> None:
        """Reject cancelled work before the next action."""

    def remaining_s(self) -> float:
        """Return the remaining bounded backend timeout."""

    def wait(self, seconds: float) -> None:
        """Wait cooperatively, waking on cancellation or the deadline."""


_ACTIVE: ContextVar[Optional[CancellationBoundary]] = ContextVar('autocontrol_cancellation', default=None)


@contextmanager
def _task_scope(boundary: CancellationBoundary) -> Iterator[None]:
    token = _ACTIVE.set(boundary)
    try:
        yield
    finally:
        _ACTIVE.reset(token)


def _check_cancelled() -> None:
    boundary = _ACTIVE.get()
    if boundary is not None:
        boundary.checkpoint()


def _request_timeout(default: float) -> float:
    boundary = _ACTIVE.get()
    return min(default, boundary.remaining_s()) if boundary is not None else default


def _cooperative_sleep(seconds: float) -> None:
    boundary = _ACTIVE.get()
    if boundary is None:
        time.sleep(seconds)
    else:
        boundary.wait(seconds)
