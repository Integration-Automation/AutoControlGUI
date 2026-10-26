"""Runtime-owned transfer serialization coordinates source consent and service-owned destination imports."""
from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
from threading import Lock, RLock
import time
from typing import Any, Callable, Mapping, Iterator

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.transfer_records import TransferRecords
from je_auto_control.utils.agent_runtime.transfer_models import _object
from je_auto_control.utils.agent_runtime.transfer_evidence import RemoteEvidenceSource
from je_auto_control.utils.agent_runtime.transfer_evidence_contract import EVIDENCE_FIELDS
from je_auto_control.utils.agent_runtime.transfer_source import TransferSource, source_maintenance_pending
from je_auto_control.utils.agent_runtime.transfer_routing import RoutedTransfers
from je_auto_control.utils.agent_runtime.transfer_import import (
    IMPORT_FIELDS, TransferImporter, import_maintenance_pending,
)
from je_auto_control.utils.config_sync.contract import ConfigStoreError, ConfigSyncError
from je_auto_control.utils.rbac.authorization import AuthorizationError
from je_auto_control.utils.exception.cancellation import cancellation_checkpoint


@dataclass
class _Lifecycle:
    """A short state lock guards one finite operation and the controller's permanent retirement."""

    closed: bool = False
    busy: bool = False
    deadline: float = 0.0
    importer: Any = None
    evidence: Any = None
    activities: int = 0


class AgentTransfers:
    """One host-owned controller; GUI observers and direct callers never own or fabricate source authority."""

    def __init__(self, runtime: Any, peer: Any = None, *, host: Any, task_active: Callable[[], bool]) -> None:
        self.remote = peer
        self.source = TransferSource(runtime, TransferRecords(runtime.store), host, self._checkpoint)
        self._routing = RoutedTransfers(runtime, self.source.records, peer, runtime.batches.transfer_binding,
                                        self._remaining)
        self._mutex = RLock()
        self._state = Lock()
        self._life = _Lifecycle(importer=TransferImporter(runtime, self.source.records, host, peer, self._remaining))
        self._life.evidence = RemoteEvidenceSource(runtime, self.source.records, host, self._checkpoint)
        self._task_active = task_active

    @property
    def runtime(self) -> Any:
        """Retain read access to this controller's owning runtime through its existing source collaborator."""
        return self.source.runtime

    @staticmethod
    def maintenance_pending(store: Any) -> bool:
        """Find source or destination retirement left by a prior runtime without dispatching new work."""
        return source_maintenance_pending(store) or import_maintenance_pending(store)

    def control(self, operation: str, request: Mapping[str, Any] | None = None) -> dict:
        """Apply one finite local management operation without recursively dispatching agents."""
        if self._task_active():
            raise AgentTaskError('active tasks cannot invoke transfer management')
        return self._invoke(operation, {} if request is None else request, peer=False)

    def peer(self, operation: str, request: Mapping[str, Any]) -> dict:
        """Serve only closed authenticated source reads, never local management delegation."""
        return self._invoke(operation, request, peer=True)

    def skill_evidence(self, connection: Any, source_task: str, task_id: str, grant_id: str) -> Any:
        """Retain runtime ownership without taking the transfer mutex under a caller's skill writer."""
        with self.activity():
            return self._life.evidence.skill_access(connection, source_task, task_id, grant_id)

    def enable(self) -> None:
        """Enable service-owned import delivery after the actual listener has started."""
        with self._mutex:
            if self._life.closed:
                raise AgentTaskError('transfer controller is closed')
            self._life.importer.enable()

    def maintain(self) -> None:
        """Retain runtime ownership through serialized source and import cleanup, independently of observers."""
        with self._mutex:
            with self._state:
                if self._life.closed or self._life.busy:
                    return
                self._life.busy = True
            try:
                self.source.maintain()
                self._life.evidence.maintain()
                self._life.importer.maintain()
            finally:
                with self._state:
                    self._life.busy = False

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
                handler = self._peer if peer else self._management
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
        if host != 'local':
            return self._routing.control(host, operation, value)
        if isinstance(operation, str) and operation in IMPORT_FIELDS:
            return self._life.importer.control(operation, value)
        if isinstance(operation, str) and operation in EVIDENCE_FIELDS:
            return self._life.evidence.control(operation, value)
        return self.source.control(operation, value)

    def _peer(self, operation: str, request: Mapping[str, Any]) -> dict:
        if operation == 'evidence':
            value = _object(request, {'grant_id', 'binding'})
            return self._life.evidence.resolve(value['grant_id'], value['binding'])
        return self.source.peer(operation, request)

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
            if self._life.busy or self._life.activities:
                raise AgentTaskError('runtime still has an active transfer operation')
            self._life.closed = True
            self._routing.close()
            self._life.importer.close()
            self._life.evidence.close()

    @contextmanager
    def activity(self) -> Iterator[None]:
        """Retain this runtime owner through independent coordinator work without serializing remote readers."""
        with self._state:
            if self._life.closed:
                raise AgentTaskError('transfer runtime is closed')
            self._life.activities += 1
        try:
            yield
        finally:
            with self._state:
                self._life.activities -= 1
