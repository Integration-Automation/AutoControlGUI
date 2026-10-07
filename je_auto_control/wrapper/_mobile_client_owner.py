"""Publish lazy SDK handles atomically and dispose only owned helper resources."""
from __future__ import annotations

from contextlib import contextmanager
import threading
from typing import Any, Callable, Iterator, Optional

from je_auto_control.wrapper._mobile_models import DeviceSessionError


class LazyMobileHandle:
    """Keep native construction outside the lifecycle lock so close can revoke it."""

    def __init__(self, handle: Any, guard: Optional[Callable[[], None]],
                 dispose: Optional[Callable[[Any], None]]) -> None:
        self._handle = handle
        self._guard = guard
        self._dispose = dispose
        self._state = threading.Lock()
        self._connection = threading.Lock()
        self._closed = False

    def _check(self) -> None:
        if self._closed:
            raise DeviceSessionError('device client is closed; create a new explicit session')
        if self._guard is not None:
            self._guard()

    def get(self, factory: Callable[[], Any]) -> Any:
        """Resolve once; a constructor finishing after close cannot publish a handle."""
        with self._connecting():
            with self._state:
                self._check()
                if self._handle is not None:
                    return self._handle
            handle = factory()
            try:
                with self._state:
                    self._check()
                    self._handle = handle
            except BaseException:  # reason: a completed native constructor must be disposed on cancelled publication
                self._release(handle)
                raise
            return handle

    @contextmanager
    def _connecting(self) -> Iterator[None]:
        with self._state:
            self._check()
        while not self._connection.acquire(timeout=0.1):
            with self._state:
                self._check()
        try:
            yield
        finally:
            self._connection.release()

    def close(self) -> None:
        """Detach under a short lock; never wait for an unanswered constructor."""
        with self._state:
            self._closed = True
            handle, self._handle = self._handle, None
        if handle is not None:
            self._release(handle)

    def _release(self, handle: Any) -> None:
        if self._dispose is not None:
            try:
                self._dispose(handle)
            except Exception as failure:  # reason: contain optional-SDK cleanup failures
                raise DeviceSessionError('owned mobile SDK cleanup failed') from failure
