"""Independent GUI recording resources with revocation and retained failed native cleanup."""
from __future__ import annotations

from queue import Queue
import threading
from typing import Any, Callable, Optional, Protocol, cast

from je_auto_control.utils.exception.exceptions import AutoControlException, AutoControlUnsupportedOperationException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger


class _Recorder(Protocol):
    def record(self) -> None:
        """Start only this instance's capture/subscription."""

    def stop_record(self) -> Queue[Any]:
        """Stop only owned capture and return the legacy event queue."""


def _new_recorder() -> _Recorder:
    # pylint: disable=import-outside-toplevel  # reason: native recorder imports only when explicitly started
    from je_auto_control.wrapper.platform_wrapper import recorder
    from je_auto_control.utils.input_macro.recorder_base import InputRecorder
    if isinstance(recorder, InputRecorder):
        return cast(_Recorder, type(recorder)())
    if type(recorder).__name__ == 'X11LinuxRecorder':
        from je_auto_control.linux_with_x11.record.owned_record import X11OwnedRecorder
        return X11OwnedRecorder()
    # pylint: enable=import-outside-toplevel
    raise AutoControlUnsupportedOperationException(
        'owned replay recording is unavailable on this backend; use action journals or opt-in physical capture')


_RETIRED: set[RecordPanelOwner] = set()
_RETIRED_LOCK = threading.Lock()


def _retry_retired() -> None:
    """Retry only failed GUI-owned recorders, including owners of already deleted panels."""
    with _RETIRED_LOCK:
        owners = tuple(_RETIRED)
    for owner in owners:
        if owner.cleanup_error:
            owner.request_close()


class RecordPanelOwner:
    """Keep GUI recording separate from script/global helpers; close never borrows their stop."""

    def __init__(self, factory: Optional[Callable[[], _Recorder]] = None) -> None:
        self._factory = factory or _new_recorder
        self._backend: Optional[_Recorder] = None
        self._revoked = threading.Event()
        self._lock = threading.RLock()
        self._close_lock = threading.Lock()
        self._cleanup: Optional[threading.Thread] = None
        self.cleanup_error = ''

    def start(self, cancel: Optional[threading.Event] = None) -> None:
        """Construct/start on a worker; cancellation during construction still closes the owned result."""
        with self._lock:
            self._check(cancel)
            if self._backend is not None:
                raise AutoControlException('this panel already owns a recording')
            self._backend = self._factory()
            try:
                self._check(cancel)
                self._backend.record()
                self._check(cancel)
            except BaseException:
                self.request_close()
                raise

    def _check(self, cancel: Optional[threading.Event]) -> None:
        if self._revoked.is_set() or (cancel is not None and cancel.is_set()):
            raise AutoControlException('recording panel was cancelled or closed')

    def stop(self) -> list[Any]:
        """Stop owned capture; retain the backend if native stop fails so close can retry."""
        with self._lock:
            backend = self._backend
            if backend is None:
                return []
            queue = backend.stop_record()
            self._backend = None
            self.cleanup_error = ''
            with _RETIRED_LOCK:
                _RETIRED.discard(self)
            return [[action[0], {'keycode': action[1]}] if action[0] == 'AC_type_keyboard'
                    else [action[0], {'x': action[1], 'y': action[2]}] for action in queue.queue]

    def request_close(self, *_args: object) -> None:
        """Revoke immediately, then clean off Qt; repeated calls retry retained failures."""
        self._revoked.set()
        with self._close_lock:
            if self._cleanup is not None and self._cleanup.is_alive():
                return
            with _RETIRED_LOCK:
                _RETIRED.add(self)
            self._cleanup = threading.Thread(target=self._dispose, name='gui-owned-record-cleanup', daemon=True)
            self._cleanup.start()

    def _dispose(self) -> None:
        try:
            self.stop()
        except Exception as failure:  # pylint: disable=broad-exception-caught  # reason: retain failed owned resources for explicit cleanup retry
            self.cleanup_error = str(failure)
            autocontrol_logger.warning('owned recording cleanup failed: %s', type(failure).__name__)
        else:
            with _RETIRED_LOCK:
                _RETIRED.discard(self)

    @property
    def revoked(self) -> bool:
        """Whether this owner is closed; a later recording needs a fresh owned resource."""
        return self._revoked.is_set()

    @property
    def cleanup_running(self) -> bool:
        """Report thread state without taking the lock held by native work."""
        return self._cleanup is not None and self._cleanup.is_alive()
