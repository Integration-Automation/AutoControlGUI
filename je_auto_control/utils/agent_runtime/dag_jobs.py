"""Service-owned durable DAG deliveries never replay an interrupted coordinator attempt."""
from __future__ import annotations

import json
import threading
import time
from contextvars import Context
from dataclasses import asdict
from typing import Any

from je_auto_control.utils.agent_runtime.dag_service_client import DagServiceClient
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.rbac.deferred import DeferredAuthorization
from je_auto_control.utils.work_queue.work_queue import WorkQueue

_ERRORS = (AutoControlException, OSError, RuntimeError, TypeError, ValueError, LookupError)


def fence_delivery(runtime: Any, started: dict) -> None:
    """Retire only this delivery's scheduling attempt, preserving all node delivery evidence."""
    # pylint: disable-next=protected-access  # reason: serialize internal retirement with public batch transitions
    with runtime._lock("dag:" + started["batch_id"]):
        with runtime.store.connection(write=True) as connection:
            connection.execute("UPDATE agent_dag_batches SET state='waiting_review',attempt='',updated=? "
                               "WHERE id=? AND attempt=? AND state='running'",
                               (time.time(), started["batch_id"], started["attempt"]))


class BackgroundDags:
    """A bounded service pool owns coordination independently of the submitting view or client."""

    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime
        self.queue = WorkQueue(runtime.store.path, "agent_dag")
        self._workers: list[threading.Thread] = []
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._enabled = False
        with runtime.store.connection(write=True) as connection:
            connection.execute("UPDATE work_items SET status='failed',claim=claim+1,error=?,updated=? "
                               "WHERE queue='agent_dag' AND status IN ('new','in_progress')",
                               ("runtime restarted; explicit DAG review required", time.time()))

    def enable(self) -> None:
        """Enable explicitly launched service dispatch after the listener is available."""
        with self._lock:
            self._enabled = True

    def enqueue(self, started: dict, owner: dict, actor: DeferredAuthorization) -> None:
        """Persist one already-authorized attempt; never reset a previous delivery or node claim."""
        data = {"started": started, "owner": owner,
                "actor": asdict(actor.context) if actor.context is not None else {}}
        try:
            with self._lock:
                self._available()
                added = self.queue.add(data, reference=started["batch_id"])
                if added is None:
                    raise AgentTaskError("background DAG attempt already queued")
                if not self._workers:
                    for index in range(4):
                        worker = threading.Thread(target=lambda: Context().run(self._drain),
                                                  name=f"AgentDagWorker-{index}", daemon=True)
                        self._workers.append(worker)
                        worker.start()
        except BaseException:  # reason: no failed acceptance may leave an authorized attempt dispatchable
            fence_delivery(self.runtime, started)
            raise

    def ensure_available(self) -> None:
        """Reject unavailable/full services before consuming an initial or approved attempt."""
        with self._lock:
            self._available()

    def _available(self) -> None:
        if not self._enabled or self._stop.is_set():
            raise AgentTaskError("background DAG service is not available")
        with self.runtime.store.connection() as connection:
            count = connection.execute("SELECT COUNT(*) FROM work_items WHERE queue='agent_dag' "
                                       "AND status IN ('new','in_progress')").fetchone()[0]
        if count >= 64:
            raise AgentTaskError("background DAG pending limit reached")

    def _drain(self) -> None:
        while not self._stop.is_set():
            item = self.queue.get_next()
            if item is None:
                self._stop.wait(0.1)
                continue
            self._run(item)

    def _run(self, item: Any) -> None:
        client = DagServiceClient(self.runtime, item.data)
        try:
            self._execute(client)
            if not client.completed():
                raise AgentTaskError("background DAG requires review")
            self.queue.complete(item.id, claim=item.claim, output={"outcome": "completed"})
        except _ERRORS as error:
            fence_delivery(self.runtime, client.started)
            self.queue.fail(item.id, type(error).__name__, kind="business", claim=item.claim)

    def _execute(self, client: DagServiceClient) -> None:
        # pylint: disable-next=import-outside-toplevel  # reason: runtime constructs this service before DAG transport imports
        from je_auto_control.utils.dag.batch_execution import execute_started
        # pylint: disable-next=import-outside-toplevel  # reason: avoid runtime/runner construction cycles
        from je_auto_control.utils.dag.runner import run_dag
        # pylint: disable-next=import-outside-toplevel  # reason: local service binding must not initialize a global client
        from je_auto_control.utils.dag.managed_tasks import managed_runtime_scope
        if self._stop.is_set():
            raise AgentTaskError("background DAG service is stopping")
        with client.owner.scope(), managed_runtime_scope(client.task_call, client.check):
            execute_started(client, client.started, self._stop, run_dag, client.started["max_parallel"])

    def close(self) -> None:
        """Fence accepted attempts and retire workers before the runtime or task workers are released."""
        with self._lock:
            self._stop.set()
        with self.runtime.store.connection() as connection:
            rows = connection.execute("SELECT id,data FROM work_items WHERE queue='agent_dag' "
                                      "AND status IN ('new','in_progress')").fetchall()
        for row in rows:
            fence_delivery(self.runtime, json.loads(row["data"])["started"])
        for worker in self._workers:
            worker.join(timeout=12)
            if worker.is_alive():
                raise AgentTaskError("background DAG worker has not retired")
        with self.runtime.store.connection(write=True) as connection:
            connection.execute("UPDATE work_items SET status='failed',claim=claim+1,error=?,updated=? "
                               "WHERE queue='agent_dag' AND status IN ('new','in_progress')",
                               ("service stopped; explicit DAG review required", time.time()))


def delivery_status(runtime: Any, batch_id: str) -> dict | None:
    """Publish bounded delivery state, withholding stored authority and coordination capabilities."""
    with runtime.store.connection() as connection:
        if connection.execute("SELECT 1 FROM sqlite_master WHERE name='work_items'").fetchone() is None:
            return None
        row = connection.execute("SELECT status FROM work_items WHERE queue='agent_dag' AND reference=? "
                                 "ORDER BY id DESC LIMIT 1", (batch_id,)).fetchone()
    return {"state": row["status"], "requires_review": row["status"] == "failed"} if row is not None else None
