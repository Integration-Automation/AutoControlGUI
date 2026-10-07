"""Headless mobile panel lifetime: immediate revocation and retryable asynchronous cleanup."""
from __future__ import annotations

import threading
from typing import Any, Mapping, Optional

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.wrapper.device_context import DeviceContext, DeviceSession, DeviceSessionError, open_device
from je_auto_control.wrapper.mobile_dispatch import android_mobile_action, ios_mobile_action, run_mobile_actions
from je_auto_control.wrapper.mobile_setup import inspect_device_setup


class MobilePanelOwner:
    """Keep all lifecycle/input logic callable without Qt; cleanup threads retain no widgets."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._session: Optional[DeviceSession] = None
        self._cleanup: Optional[threading.Thread] = None
        self._error: Optional[str] = None
        self._generation = 0

    @property
    def session(self) -> DeviceSession:
        """Return the selected open owner; never silently create a default device."""
        with self._lock:
            session = self._session
        if session is None:
            raise DeviceSessionError('open a selected device session first')
        session.ensure_open()
        return session

    def open(self, device: Mapping[str, Any]) -> None:
        """Open a passive owner only after all previous native cleanup is resolved."""
        context = DeviceContext.from_spec(device)
        with self._lock:
            if self._session is not None or (self._cleanup is not None and self._cleanup.is_alive()):
                raise DeviceSessionError('close the existing mobile owner and resolve cleanup before opening another')
            self._session = open_device(context)
            self._generation += 1
            self._error = None

    def diagnose(self, connect: bool = False) -> dict[str, Any]:
        """Read metadata or perform an explicitly requested read-only transport diagnostic."""
        return inspect_device_setup(self.session, connect=connect).to_dict()

    def operation(self, operation: str, options: Mapping[str, Any]) -> Any:
        """Dispatch through the public platform alias on the persistent selected owner."""
        session = self.session
        handler = android_mobile_action if session.context.platform == 'android' else ios_mobile_action
        with session.bind():
            return handler(operation, options)

    def actions(self, actions: list[Any]) -> list[Any]:
        """Run a prevalidated mobile-only batch without borrowing the desktop."""
        return run_mobile_actions(self.session, actions)

    def request_close(self, _destroyed: object = None) -> None:
        """Invalidate synchronously; native cleanup runs off the UI thread and can be retried."""
        with self._lock:
            session = self._session
            if session is None:
                return
            session.revoke()
            self._generation += 1
            if self._cleanup is not None and self._cleanup.is_alive():
                return
            self._cleanup = threading.Thread(target=self._reclaim, args=(session,), daemon=True,
                                             name='AutoControl mobile cleanup')
            self._cleanup.start()

    def _reclaim(self, session: DeviceSession) -> None:
        error = None
        try:
            session.close()
        except AutoControlException as failure:
            error = str(failure)
            autocontrol_logger.error('mobile owner cleanup failed; retry close: %s', error)
        with self._lock:
            self._error = error
            if error is None and self._session is session:
                self._session = None

    def snapshot(self) -> dict[str, Any]:
        """Return passive UI/test state; a failed cleanup retains its revoked session."""
        with self._lock:
            session = self._session
            return {'generation': self._generation,
                    'device': None if session is None else session.context.device_id,
                    'connected': session is not None and session.connected,
                    'cleanup_running': self._cleanup is not None and self._cleanup.is_alive(),
                    'cleanup_error': self._error}

    def wait_cleanup(self, timeout_s: float) -> bool:
        """Optional headless/test join; GUI polling never calls this blocking method."""
        with self._lock:
            thread = self._cleanup
        if thread is not None:
            thread.join(timeout_s)
        return thread is None or not thread.is_alive()
