"""An explicitly started runtime service owns import workers independently of GUI observers."""
from __future__ import annotations

from contextvars import Context
from threading import Event, Lock, Thread
from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.transfer_import_ledger import QUEUE, TransferImportLedger
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.work_queue.work_queue import WorkQueue

_ERRORS = (AutoControlException, OSError, RuntimeError, ValueError, TypeError, LookupError)


class TransferImportJobs:
    """Use real WorkQueue claims; a closed observer never cancels or replaces a service delivery."""

    def __init__(self, importer: Any) -> None:
        self.importer = importer
        self.queue = WorkQueue(importer.runtime.store.path, QUEUE)
        self.ledger = TransferImportLedger(importer.runtime.store)
        self._stop = Event()
        self._mutex = Lock()
        self._worker: Thread | None = None
        self._active: str | None = None
        with importer.runtime.store.connection(write=True) as connection:
            self.ledger.initialize(connection)
            self.ledger.recover(connection)

    def start_pending(self) -> None:
        """Start only durable approved work whose exact queue item has never been claimed."""
        with self.importer.runtime.store.connection() as connection:
            queued = connection.execute(
                "SELECT 1 FROM agent_transfer_deliveries d JOIN work_items w ON w.id=d.queue_id "
                "WHERE d.state='queued' AND w.queue=? AND w.status='new' LIMIT 1", (QUEUE,)).fetchone()
        if queued is not None:
            self.wake()

    def wake(self) -> None:
        """Wake only this service's bounded worker after the caller commits its approved intent."""
        with self._mutex:
            if self._stop.is_set():
                raise AgentTaskError('destination import service is closed')
            if self._worker is None:
                self._worker = Thread(target=lambda: Context().run(self._drain),
                                      name='AgentImportWorker', daemon=True)
                self._worker.start()

    def _drain(self) -> None:
        while not self._stop.is_set():
            try:
                item = self.queue.get_next()
                if item is None:
                    self._stop.wait(0.1)
                    continue
                self._deliver(item)
            except _ERRORS as error:
                autocontrol_logger.warning('destination import worker requires review: %s', type(error).__name__)
                self._stop.wait(0.1)

    def _deliver(self, item: Any) -> None:
        with self._mutex:
            self._active = item.reference
        try:
            self.ledger.claim(item)
            def check() -> None:
                if self._stop.is_set():
                    raise AgentTaskError('destination import service is retiring')
                with self.importer.runtime.store.connection() as connection:
                    self.ledger.check(connection, item.reference, item.data['generation'])
            result = self.importer.deliver(item.reference, item.data['generation'], check)
            self.queue.complete(item.id, output=result, claim=item.claim)
        except _ERRORS:
            self.importer.delivery_failed(item.reference, item.data['generation'])
            with self.importer.runtime.store.connection() as connection:
                row = connection.execute('SELECT status,claim FROM work_items WHERE id=?', (item.id,)).fetchone()
            if row is not None and row['status'] == 'in_progress' and row['claim'] == item.claim:
                self.queue.fail(item.id, 'import requires explicit review', kind='business', claim=item.claim)
        finally:
            with self._mutex:
                self._active = None

    def retired(self, identifier: str) -> bool:
        """Prove that this service has no active producer for a separately fenced terminal import."""
        with self._mutex:
            return self._active != identifier

    def close(self) -> None:
        """Keep runtime ownership while a blocked producer has not yet retired."""
        self._stop.set()
        with self._mutex:
            worker = self._worker
        if worker is not None:
            worker.join(timeout=3)
            if worker.is_alive():
                raise AgentTaskError('destination import producer has not retired')
