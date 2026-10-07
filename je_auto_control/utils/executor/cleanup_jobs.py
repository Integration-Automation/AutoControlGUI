"""Internal headless cleanup jobs retaining failed owned callbacks for retry."""
from __future__ import annotations

import threading
from typing import Callable, Iterable

from je_auto_control.utils.logging.logging_instance import autocontrol_logger

_PENDING: set[_CleanupJob] = set()
_LOCK = threading.Lock()


class _CleanupJob:  # pylint: disable=too-few-public-methods  # reason: one retryable cleanup lifecycle
    def __init__(self, callbacks: Iterable[Callable[[], object]]) -> None:
        self.pending = list(callbacks)
        self.errors: tuple[str, ...] = ()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._retry_requested = threading.Event()

    def retry(self) -> None:
        """Start or queue another cleanup attempt without waiting on native callbacks."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                self._retry_requested.set()
                return
            if not self.pending:
                return
            with _LOCK:
                _PENDING.add(self)
            self._thread = threading.Thread(target=self._run, name='gui-owned-cleanup', daemon=True)
            self._thread.start()

    def _run(self) -> None:
        while True:
            self._run_once()
            with self._lock:
                if self.pending and self._retry_requested.is_set():
                    self._retry_requested.clear()
                    continue
                self._thread = None
                return

    def _run_once(self) -> None:
        retained, errors = [], []
        for callback in self.pending:
            try:
                callback()
            except Exception as failure:  # pylint: disable=broad-exception-caught  # reason: each owned cleanup is attempted and failures remain retryable
                retained.append(callback)
                errors.append(str(failure))
                autocontrol_logger.warning('owned GUI cleanup failed: %s', type(failure).__name__)
        self.pending, self.errors = retained, tuple(errors)
        if not retained:
            with _LOCK:
                _PENDING.discard(self)


def _submit_cleanup(callbacks: Iterable[Callable[[], object]]) -> _CleanupJob:
    job = _CleanupJob(callbacks)
    job.retry()
    return job


def _retry_cleanup() -> None:
    with _LOCK:
        jobs = tuple(_PENDING)
    for job in jobs:
        job.retry()
