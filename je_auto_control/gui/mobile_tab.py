"""Mobile device workspace with owner-bound operations exposed only through Actions."""
from __future__ import annotations

import json
from functools import partial
from typing import Any, Callable, Optional

from PySide6.QtCore import QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFormLayout, QLabel, QLineEdit, QPlainTextEdit, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.task_controller import CancellationToken, TaskController, TaskError, TaskHandle, TaskResult
from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.wrapper._mobile_panel_owner import MobilePanelOwner
from je_auto_control.wrapper.mobile_surfaces import mobile_surface_matrix


def _mobile_work(owner: MobilePanelOwner, fn: Callable[[], Any], token: CancellationToken) -> object:
    """Execute copied inputs headlessly; cancellation also revokes the owned native session."""
    try:
        token.checkpoint()
        result = fn()
        token.checkpoint()
        return result
    finally:
        if token.event.is_set():
            owner.request_close()


class MobileTab(TranslatableMixin, QWidget):  # pylint: disable=too-many-instance-attributes  # reason: form widgets plus independent owner/worker state
    """Keep native work and cleanup off Qt; a persistent owner permits app/frame workflows."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._owner = MobilePanelOwner()
        self.destroyed.connect(self._owner.request_close)  # pylint: disable=no-member  # reason: Qt SignalInstance runtime binding
        self._tasks = TaskController(timeout_s=300)
        self._worker: Optional[TaskHandle] = None
        self._job_generation = 0
        self._platform = QComboBox()
        self._platform.addItems(['android', 'ios'])
        self._target = QLineEdit('emulator-5554')
        self._adb_path = QLineEdit()
        self._timeout = QDoubleSpinBox()
        self._timeout.setRange(.1, 300)
        self._timeout.setValue(10)
        self._operation = QComboBox()
        self._rows = mobile_surface_matrix(False)['operations']
        self._options = QPlainTextEdit()
        self._actions = QPlainTextEdit()
        self._actions.setPlainText('[["AC_mobile_app", {"action":"state", "app_id":"com.example.demo"}]]')
        self._output = QPlainTextEdit()
        self._output.setReadOnly(True)
        self._poll = QTimer(self)
        self._poll.setInterval(100)
        self._poll.timeout.connect(self._cleanup_status)  # pylint: disable=no-member  # reason: Qt SignalInstance runtime binding
        self._build_layout()
        self._fill_operations()
        self._operation.currentIndexChanged.connect(self._fill_options)  # pylint: disable=no-member  # reason: Qt SignalInstance runtime binding
        self._fill_options()

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        form = QFormLayout()
        for key, widget in [('mobile_platform', self._platform), ('mobile_target', self._target),
                            ('mobile_adb_path', self._adb_path), ('mobile_timeout', self._timeout),
                            ('mobile_operation', self._operation)]:
            label = QLabel()
            self._tr(label, key)
            form.addRow(label, widget)
        root.addLayout(form)
        root.addWidget(self._options)
        root.addWidget(self._actions)
        root.addWidget(self._output)
        self._tr(self._options, 'mobile_options_hint', 'setPlaceholderText')
        self._tr(self._actions, 'mobile_actions_hint', 'setPlaceholderText')

    def _fill_operations(self) -> None:
        selected = self._operation.currentData()
        self._operation.blockSignals(True)
        self._operation.clear()
        for row in self._rows:
            self._operation.addItem(language_wrapper.translate('mobile_op_' + row['operation'], row['operation']),
                                    row['operation'])
        index = self._operation.findData(selected)
        self._operation.setCurrentIndex(max(0, index))
        self._operation.blockSignals(False)

    def _fill_options(self, _index: int = 0) -> None:
        operation = self._operation.currentData()
        row = next(entry for entry in self._rows if entry['operation'] == operation)
        options = dict(row['options'])
        if operation in ('launch_app', 'wait_for_app', 'app_state', 'stop_app'):
            options.pop('action', None)
        elif operation in ('install', 'files', 'clipboard', 'recording'):
            options = options['options']
        self._options.setPlainText(json.dumps(options, ensure_ascii=False, indent=2))

    def retranslate(self) -> None:
        """Refresh labels without changing selected operation or the user's JSON options."""
        TranslatableMixin.retranslate(self)
        self._fill_operations()

    def menu_actions(self) -> list[tuple[str, Callable[[], None]]]:
        """Make every operation and batch accessible through the window Actions menu."""
        return [('mobile_open', self._on_open), ('mobile_probe', self._on_probe),
                ('mobile_diagnose', self._on_diagnose), ('mobile_run_operation', self._on_operation),
                ('mobile_run_actions', self._on_actions), ('workspace_cancel_task', self._on_cancel),
                ('mobile_close', self._on_close_owner)]

    def _on_open(self) -> None:
        if self._worker is not None:
            return
        try:
            self._owner.open({'platform': self._platform.currentText(), 'target': self._target.text(),
                              'adb_path': self._adb_path.text() or None, 'timeout_s': self._timeout.value()})
        except AutoControlException as failure:
            self._failed(str(failure))
            return
        self._poll.stop()
        self._show(self._owner.snapshot())

    def _on_probe(self) -> None:
        self._start(partial(self._owner.diagnose, False))

    def _on_diagnose(self) -> None:
        self._start(partial(self._owner.diagnose, True))

    def _on_operation(self) -> None:
        try:
            options = json.loads(self._options.toPlainText())
        except ValueError as failure:
            self._failed(str(failure))
            return
        self._start(partial(self._owner.operation, self._operation.currentData(), options))

    def _on_actions(self) -> None:
        try:
            actions = json.loads(self._actions.toPlainText())
        except ValueError as failure:
            self._failed(str(failure))
            return
        self._start(partial(self._owner.actions, actions))

    def _start(self, fn: Callable[[], Any]) -> None:
        if self._worker is not None:
            return
        self._job_generation = self._owner.snapshot()['generation']
        self._worker = self._tasks.submit(partial(_mobile_work, self._owner, fn), owner=self)
        self._worker.completed.connect(self._done)
        self._worker.failed.connect(self._worker_failed)
        self._worker.finished.connect(self._thread_done)

    def _done(self, result: TaskResult) -> None:
        if self._job_generation == self._owner.snapshot()['generation']:
            self._show(result.value)

    def _thread_done(self) -> None:
        self._worker = None

    def _worker_failed(self, error: TaskError) -> None:
        if self._job_generation == self._owner.snapshot()['generation']:
            self._failed(error.message)

    def _failed(self, message: str) -> None:
        self._output.setPlainText(message)

    def _show(self, result: Any) -> None:
        self._output.setPlainText(json.dumps(result, ensure_ascii=False, indent=2))

    def _on_close_owner(self) -> None:
        self._tasks.cancel_owner(self)
        self._owner.request_close()
        self._show(self._owner.snapshot())
        self._poll.start()

    def _on_cancel(self) -> None:
        self._on_close_owner()

    def _cleanup_status(self) -> None:
        state = self._owner.snapshot()
        self._show(state)
        if state['cleanup_error']:
            self.setProperty('execution_state', 'error')
            self.setProperty('execution_reason', state['cleanup_error'])
        if not state['cleanup_running']:
            self._poll.stop()

    def closeEvent(self, event: QCloseEvent) -> None:  # pylint: disable=invalid-name  # reason: exact Qt virtual callback
        """Invalidate input before Qt closes; native cleanup retains no widget references."""
        self._tasks.cancel_owner(self)
        self._owner.request_close()
        super().closeEvent(event)
