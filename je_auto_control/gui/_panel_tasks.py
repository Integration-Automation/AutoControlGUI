"""Shared task-backed result rendering and close cancellation for existing workflow panels."""
from __future__ import annotations

import json
from functools import partial
from typing import Any, Callable, Optional
import weakref

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QLabel, QPlainTextEdit, QTextEdit, QWidget

from je_auto_control.gui.task_controller import CancellationToken, TaskController, TaskError, TaskHandle, TaskResult


def execute_actions(actions: list[Any], token: CancellationToken) -> object:
    """Run an already copied action list under the task's nested cancellation scope."""
    # pylint: disable=import-outside-toplevel  # reason: only action panels load the executor
    from je_auto_control.utils.executor.action_executor import execute_action
    # pylint: enable=import-outside-toplevel
    token.checkpoint()
    return execute_action(actions)


def call_native(fn: Callable[[], object], token: CancellationToken) -> object:
    """Call a snapshotted headless operation inside the shared cancellation scope."""
    token.checkpoint()
    return fn()


def start_native(fn: Callable[[], object], owner: QWidget) -> None:
    """Start an independently owned native service off Qt; its owner handles service shutdown."""
    TaskController(timeout_s=30).submit(partial(call_native, fn), owner=owner)


class PanelTasks(QObject):
    """Keep widget access on Qt while headless work receives only copied inputs and a token."""

    def __init__(self, owner: QWidget, output: QPlainTextEdit | QTextEdit | QLabel | None = None,
                 timeout_s: float = 300) -> None:
        super().__init__(owner)
        self._owner = weakref.ref(owner)
        self._output = weakref.ref(output) if output is not None else lambda: None
        self._tasks = TaskController(timeout_s)
        self.handle: Optional[TaskHandle] = None
        owner.installEventFilter(self)

    def submit(self, work: Callable[[CancellationToken], object],
               on_done: Callable[[TaskResult], None] | None = None) -> None:
        """Start one owner-bound operation with typed result/error delivery."""
        owner = self._owner()
        if owner is None:
            return
        self.handle = self._tasks.submit(work, owner=owner)
        self.handle.completed.connect(self._done)
        self.handle.failed.connect(self._failed)
        self.handle.finished.connect(self._released)
        if on_done is not None:
            self.handle.completed.connect(on_done)

    def cancel(self) -> None:
        """Stop between actions or bounded requests; cleanup remains the headless work's responsibility."""
        owner = self._owner()
        if owner is not None:
            self._tasks.cancel_owner(owner)

    def _done(self, result: TaskResult) -> None:
        output = self._output()
        if output is not None:
            value = result.value
            text = value if isinstance(value, str) else json.dumps(value, indent=2, default=str, ensure_ascii=False)
            if isinstance(output, QLabel):
                output.setText(text)
            else:
                output.setPlainText(text)

    def _failed(self, error: TaskError) -> None:
        output = self._output()
        if output is not None:
            if isinstance(output, QLabel):
                output.setText(error.message)
            else:
                output.setPlainText(error.message)

    def _released(self) -> None:
        self.handle = None

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # pylint: disable=invalid-name  # reason: Qt virtual callback
        """Revoke delivery on explicit close before deferred QWidget destruction."""
        owner_ref = getattr(self, '_owner', None)
        if owner_ref is None:
            return False
        if watched is owner_ref() and event.type() == QEvent.Type.Close:
            self.cancel()
        return super().eventFilter(watched, event)
