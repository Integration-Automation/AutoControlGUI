"""Runtime-owned transfer serialization keeps finite source operations separate from future import/evidence paths."""
from __future__ import annotations

from dataclasses import dataclass
from threading import Lock, RLock
import time
from typing import Any, Callable, Mapping

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.transfer_records import TransferRecords
from je_auto_control.utils.agent_runtime.transfer_source import TransferSource
from je_auto_control.utils.agent_runtime.transfer_routing import RoutedTransfers
from je_auto_control.utils.config_sync.contract import ConfigStoreError, ConfigSyncError
from je_auto_control.utils.rbac.authorization import AuthorizationError
from je_auto_control.utils.exception.cancellation import cancellation_checkpoint


@dataclass
class _Lifecycle:
    """A short state lock guards one finite operation and the controller's permanent retirement."""

    closed: bool = False
    busy: bool = False
    deadline: float = 0.0


class AgentTransfers:
    """One host-owned controller; GUI observers and direct callers never own or fabricate source authority."""

    def __init__(self, runtime: Any, peer: Any = None, *, host: Any, task_active: Callable[[], bool]) -> None:
        self.remote = peer
        self.source = TransferSource(runtime, TransferRecords(runtime.store), host, self._checkpoint)
        self._routing = RoutedTransfers(runtime, self.source.records, peer, runtime.batches.transfer_binding,
                                        self._remaining)
        self._mutex = RLock()
        self._state = Lock()
        self._life = _Lifecycle()
        self._task_active = task_active

    @property
    def runtime(self) -> Any:
        """Retain read access to this controller's owning runtime through its existing source collaborator."""
        return self.source.runtime

    def control(self, operation: str, request: Mapping[str, Any] | None = None) -> dict:
        """Apply one finite local management operation without recursively dispatching agents."""
        if self._task_active():
            raise AgentTaskError('active tasks cannot invoke transfer management')
        return self._invoke(operation, {} if request is None else request, peer=False)

    def peer(self, operation: str, request: Mapping[str, Any]) -> dict:
        """Serve only closed authenticated source reads, never local management delegation."""
        return self._invoke(operation, request, peer=True)

    def _invoke(self, operation: str, request: Mapping[str, Any], *, peer: bool) -> dict:
        with self._mutex:
            with self._state:
                if self._life.closed or self._life.busy:
                    raise AgentTaskError('transfer controller is closed or already active')
                self._life.busy = True
                self._life.deadline = time.monotonic() + 30
            try:
                self.source.host.check_open()
                self._checkpoint()
                handler = self.source.peer if peer else self._management
                result = handler(operation, request)
                self._checkpoint()
                return result
            except (AuthorizationError, ConfigStoreError, ConfigSyncError, OSError) as error:
                raise AgentTaskError('transfer authority or private asset operation is unavailable') from error
            finally:
                with self._state:
                    self._life.busy = False

    def _management(self, operation: str, request: Mapping[str, Any]) -> dict:
        if not isinstance(request, Mapping):
            raise AgentTaskError('transfer request must be an object')
        value = dict(request)
        host = value.pop('host', 'local')
        if not isinstance(host, str) or not host:
            raise AgentTaskError('transfer owning host must be local or a registered label')
        return (self.source.control(operation, value) if host == 'local'
                else self._routing.control(host, operation, value))

    def _checkpoint(self) -> None:
        cancellation_checkpoint()
        if time.monotonic() >= self._life.deadline:
            raise AgentTaskError('transfer operation deadline exhausted')

    def _remaining(self) -> float:
        self._checkpoint()
        return self._life.deadline - time.monotonic()

    def close(self) -> None:
        """Refuse premature runtime ownership release while a source operation is still in progress."""
        with self._state:
            if self._life.busy:
                raise AgentTaskError('runtime still has an active transfer operation')
            self._life.closed = True
            self._routing.close()
