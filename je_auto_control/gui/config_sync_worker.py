"""Run explicit workspace requests with immutable inputs, live authority and cooperative cancellation."""
from asyncio import CancelledError as AsyncCancelledError
from concurrent.futures import CancelledError
from contextvars import copy_context
from dataclasses import dataclass
import json
import os
from threading import Event
from typing import Callable, Literal, Optional, cast

from PySide6.QtCore import QObject, Signal, Slot

from je_auto_control.utils.config_sync.contract import ConfigSyncError, _encoded
from je_auto_control.utils.config_sync.workspace_commands import _sync_workspace
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.secret_scope import remember_secret, scrub_secret_text, secret_log_scope
from je_auto_control.utils.path_guard import PathPolicy
from je_auto_control.utils.rbac.deferred import DeferredAuthorization
from je_auto_control.utils.rbac.policy import authorize_command
from je_auto_control.utils.run_history.run_outcome import _ordinary_error_text, is_run_interruption


@dataclass(frozen=True)
class SyncUIRequest:
    """One immutable snapshot of private configuration and explicitly requested options."""

    request_id: int
    operation: str
    configuration_json: str
    options_json: str = '{}'


@dataclass(frozen=True)
class SyncUIOutcome:
    """A completed operation; committed writes remain successful after a late stop request."""

    request_id: int
    operation: str
    status: Literal['ok', 'cancelled', 'error']
    data: Optional[dict[str, object]] = None
    error: str = ''


def _object(text: str) -> dict[str, object]:
    if len(text.encode('utf-8')) > 1024 * 1024:
        raise ConfigSyncError('workspace GUI input exceeds one MiB')
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ConfigSyncError('workspace GUI input must be a JSON object')
    _encoded(value)
    return cast(dict[str, object], value)


class ConfigSyncWorker(QObject):
    """Refresh captured DRIVE authority at every core checkpoint and again before GUI delivery."""

    finished = Signal(object)

    def __init__(self, request: SyncUIRequest, *, path_policy: Optional[PathPolicy] = None) -> None:
        super().__init__()
        self._request = request
        self._stop = Event()
        self._context = copy_context()
        self._authority = DeferredAuthorization.capture()
        self._policy = path_policy

    @Slot()
    def request_stop(self) -> None:
        """Stop before the next checkpoint; an already committed write is not rolled back."""
        self._stop.set()

    def _poll(self) -> bool:
        if self._stop.is_set():
            raise CancelledError()
        with self._authority.scope():
            authorize_command('AC_sync_workspace')
        return False

    def deliver(self, callback: Callable[[], None], *, require_active: bool = False) -> None:
        """Deliver on the GUI thread under refreshed captured authority, after the worker context exits."""
        def apply() -> None:
            if require_active and self._stop.is_set():
                raise CancelledError()
            with self._authority.scope():
                authorize_command('AC_sync_workspace')
                callback()
        self._context.run(apply)

    @Slot()
    def run(self) -> None:
        """Emit one scrubbed outcome after releasing the captured execution context."""
        self.finished.emit(self._context.run(self._perform))

    def _perform(self) -> SyncUIOutcome:
        request = self._request
        with secret_log_scope():
            try:
                self._poll()
                configuration, options = _object(request.configuration_json), _object(request.options_json)
                if request.operation in {'sync', 'register', 'ack', 'retire', 'collect', 'full_resync'}:
                    environment = options.get('secret_env')
                    if isinstance(environment, str):
                        remember_secret(os.environ.get(environment, ''))
                with self._authority.scope():
                    data = _sync_workspace(configuration, request.operation, options,
                                           path_policy=self._policy, cancelled=self._poll)
            except (CancelledError, AsyncCancelledError):
                return SyncUIOutcome(request.request_id, request.operation, 'cancelled')
            except (AutoControlException, OSError, ValueError, TypeError, RuntimeError) as error:
                if is_run_interruption(error):
                    return SyncUIOutcome(request.request_id, request.operation, 'cancelled')
                return SyncUIOutcome(request.request_id, request.operation, 'error',
                                     error=scrub_secret_text(_ordinary_error_text(error)))
        return SyncUIOutcome(request.request_id, request.operation, 'ok', data)
