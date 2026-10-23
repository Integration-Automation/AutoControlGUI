"""Durable background dispatch over the existing fenced WorkQueue implementation."""
from __future__ import annotations

import threading
from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import TERMINAL
from je_auto_control.utils.agent_runtime.runner import run_task
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.work_queue.work_queue import WorkQueue


class BackgroundTasks:
    """A bounded service worker pool; accepted jobs survive client and view shutdown."""

    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime
        self._queue = WorkQueue(runtime.store.path, "agent_runtime")
        self._workers: list[threading.Thread] = []
        self._stop = threading.Event()
        self._lock = threading.Lock()
        with runtime.store.connection(write=True) as connection:
            connection.execute("UPDATE work_items SET status='new',claim=claim+1 WHERE queue='agent_runtime' "
                               "AND status='in_progress'")

    def start_pending(self) -> None:
        """Recover queued deliveries after exclusive service ownership has been established."""
        for row in self._runtime.store.list(1000):
            if row["state"] == "queued":
                self.start(row["id"])

    def start(self, task_id: str) -> None:
        """Persist internal task delivery; external tasks stay under client control."""
        row = self._runtime._row(task_id)
        if row["spec"]["mode"] == "external":
            return
        self._queue.add({"task_id": task_id}, reference=task_id)
        with self._lock:
            if self._workers:
                return
            for index in range(4):
                thread = threading.Thread(target=self._drain, name=f"AgentWorker-{index}", daemon=True)
                self._workers.append(thread)
                thread.start()

    def _drain(self) -> None:
        while not self._stop.is_set():
            item = self._queue.get_next()
            if item is None:
                self._stop.wait(0.1)
                continue
            task_id = item.data["task_id"]
            try:
                outcome = run_task(self._runtime, task_id)
                if outcome.state == "queued":
                    self._queue.defer(item.id, claim=item.claim)
                    self._stop.wait(0.25)
                else:
                    self._queue.complete(item.id, claim=item.claim, output=outcome.to_dict())
            except (AutoControlException, OSError, RuntimeError, TypeError, ValueError) as error:
                self._queue.fail(item.id, type(error).__name__, kind="business", claim=item.claim)
                if self._runtime.get(task_id).state not in TERMINAL:
                    self._runtime.store.update(task_id, "waiting_user", reason="background work requires review")
                self._runtime._retire(task_id)

    def close(self) -> None:
        """Cancel running tasks, retire workers, then permit the service to release input."""
        self._stop.set()
        for row in self._runtime.store.list(1000):
            if row["state"] in {"running", "verifying", "pausing", "cancelling"}:
                self._runtime.cancel(row["id"])
        for thread in self._workers:
            thread.join(timeout=2)
            if thread.is_alive():
                raise AgentTaskError("an agent worker has not retired yet")
