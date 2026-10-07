"""Qt-free panel input ownership; cancelled work only releases its own native holds."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from functools import partial
import threading
from typing import Callable, Hashable, Iterator

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.executor.cancellation import _check_cancelled
from je_auto_control.utils.executor.cleanup_jobs import _submit_cleanup
from je_auto_control.utils.executor.request_context import RequestBinding

_CURRENT: ContextVar[InputOwner | None] = ContextVar('autocontrol_input_owner', default=None)
_RUN: ContextVar[str | None] = ContextVar('autocontrol_input_run', default=None)
_LOCK = threading.RLock()
_CLAIMS: dict[Hashable, InputOwner] = {}


class InputOwnershipError(AutoControlException, NotImplementedError):
    """Raw GUI input cannot establish ownership or its original owner has closed."""


class InputOwner:
    """Keep raw holds across successful runs; release them on cancellation or owner death."""

    def __init__(self) -> None:
        self._held: dict[Hashable, tuple[str | None, Callable[[], object]]] = {}
        self._state_lock = threading.Lock()
        self._borrowed: set[Hashable] = set()
        self._closed = threading.Event()

    def hold(self, key: Hashable, state: Callable[[], bool | None],
             press: Callable[[], object], release: Callable[[], object]) -> None:
        """Snapshot known state before allocation and retain cleanup even if press fails."""
        with _LOCK:
            _check_cancelled()
            if self._closed.is_set():
                raise InputOwnershipError('input owner has closed')
            if key in self._held:
                return
            initial = True if key in _CLAIMS else state()
            if initial is True:
                self._borrowed.add(key)
                return
            if initial is not False:
                raise InputOwnershipError('raw GUI input requires a known initial key/button state')
            self._borrowed.discard(key)
            binding = RequestBinding.capture()
            with self._state_lock:
                self._held[key] = (_RUN.get(), partial(binding.run, release))
            _CLAIMS[key] = self
            press()

    def release(self, key: Hashable, release: Callable[[], object]) -> None:
        """A balanced GUI release preserves a previously pressed or other-owned input."""
        with _LOCK:
            if key in self._borrowed or (key in _CLAIMS and _CLAIMS[key] is not self):
                return
            entry = self._held.get(key)
            callback = entry[1] if entry is not None else release
            callback()
            with self._state_lock:
                self._held.pop(key, None)
            if _CLAIMS.get(key) is self:
                _CLAIMS.pop(key)

    def release_all(self) -> None:
        """Attempt every owned hold independently; failures remain owned and retryable."""
        self._drain(self._snapshot())

    def _snapshot(self, run_id: str | None = None) -> tuple[tuple[Hashable, Callable[[], object]], ...]:
        with self._state_lock:
            return tuple((key, entry[1]) for key, entry in self._held.items()
                         if run_id is None or entry[0] == run_id)

    def _drain(self, snapshot: tuple[tuple[Hashable, Callable[[], object]], ...]) -> None:
        failures = []
        with _LOCK:
            for key, callback in reversed(snapshot):
                current = self._held.get(key)
                if current is None or current[1] is not callback:
                    continue
                try:
                    self.release(key, callback)
                except Exception as failure:  # pylint: disable=broad-exception-caught  # reason: attempt every hold and re-raise with failed ownership retained
                    failures.append(failure)
        if failures:
            raise failures[0]

    def request_cleanup(self, run_id: str | None = None) -> None:
        """Schedule retained cleanup without waiting on native input from Qt."""
        snapshot = self._snapshot(run_id)
        if snapshot:
            _submit_cleanup((partial(self._drain, snapshot),))

    def close(self, *_args: object) -> None:
        """Revoke allocation immediately and drain owned input in a retained background job."""
        self._closed.set()
        self.request_cleanup()


@contextmanager
def _input_scope(owner: InputOwner | None, run_id: str | None = None) -> Iterator[None]:
    token = _CURRENT.set(owner)
    run_token = _RUN.set(run_id)
    try:
        yield
    finally:
        _CURRENT.reset(token)
        _RUN.reset(run_token)


def _input_owner() -> InputOwner | None:
    return _CURRENT.get()


def _hold_input(key: Hashable, state: Callable[[], bool | None],
                press: Callable[[], object], release: Callable[[], object]) -> None:
    owner = _CURRENT.get()
    if owner is None:
        press()
    else:
        owner.hold(key, state, press, release)


def _release_input(key: Hashable, release: Callable[[], object]) -> None:
    owner = _CURRENT.get()
    if owner is None:
        release()
    else:
        owner.release(key, release)
