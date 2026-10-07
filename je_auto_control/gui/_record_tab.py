"""Record / playback tab builder (extracted mixin)."""
import json
from functools import partial

from typing import TYPE_CHECKING, Any, Callable, Optional

from PySide6.QtWidgets import (
    QFileDialog, QLabel, QMessageBox, QTextEdit, QVBoxLayout, QWidget,
)

from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.executor.action_executor import execute_action
from je_auto_control.utils.json.json_file import read_action_json, write_action_json
from je_auto_control.wrapper.auto_control_record import record, stop_record
from je_auto_control.wrapper._record_panel_owner import RecordPanelOwner
from je_auto_control.gui.task_controller import CancellationToken, TaskController, TaskError, TaskHandle, TaskResult

_JSON_FILE_FILTER = "JSON (*.json)"


def _start_owned(owner: RecordPanelOwner, token: CancellationToken) -> object:
    try:
        token.checkpoint()
        owner.start(token.event)
        token.checkpoint()
    except BaseException:
        owner.request_close()
        raise
    return True


def _stop_owned(owner: RecordPanelOwner, token: CancellationToken) -> object:
    token.checkpoint()
    return owner.stop()


def _playback_owned(actions: list, token: CancellationToken) -> object:
    token.checkpoint()
    return execute_action(actions)


def _t(key: str) -> str:
    """language_wrapper shorthand"""
    return language_wrapper.translate(key, key)


class RecordTabMixin:
    """Provides the record/playback tab builder/handlers.

    Host widget must expose the ``TranslatableMixin`` API (``self._tr(...)``,
    ``self._translate(...)``) and a ``self._record_data`` list holding the
    last recording.
    """

    if TYPE_CHECKING:
        # Declared, never defined: the widget this mixin is mixed into owns
        # every one of these. The block is stripped at runtime, so nothing
        # here can shadow what the host actually binds.
        _tr: Callable[..., Any]
        _translate: Callable[[str], str]

    def _build_record_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout()
        self._record_panel = tab
        self._record_owner = RecordPanelOwner()
        self._record_tasks = TaskController(timeout_s=300)
        self._record_job: Optional[TaskHandle] = None
        tab.destroyed.connect(self._record_owner.request_close)

        # Record/playback/save/load all run from the Actions menu.
        self._record_status_key = "record_idle"
        self.record_status_label = QLabel()
        self._apply_record_status_label()
        layout.addWidget(self.record_status_label)

        layout.addWidget(self._tr(QLabel(), "record_list_label"))
        self.record_list_text = QTextEdit()
        self.record_list_text.setReadOnly(True)
        layout.addWidget(self.record_list_text)
        tab.setLayout(layout)
        return tab

    def _apply_record_status_label(self) -> None:
        if hasattr(self, "record_status_label"):
            self.record_status_label.setText(
                self._translate("record_status") + " "
                + self._translate(self._record_status_key),
            )

    def _record_retranslate(self) -> None:
        self._apply_record_status_label()

    def _start_record(self) -> None:
        if hasattr(self, '_record_owner'):
            if self._record_job is None:
                if self._record_owner.revoked:
                    if self._record_owner.cleanup_running or self._record_owner.cleanup_error:
                        self.record_status_label.setText(self._record_owner.cleanup_error or 'Cleanup pending')
                        return
                    self._record_owner = RecordPanelOwner()
                    self._record_panel.destroyed.connect(self._record_owner.request_close)
                self._submit_record(partial(_start_owned, self._record_owner), self._record_started)
            return
        try:
            if not record():
                # record() logs its failure and returns False; the status
                # said "Recording..." while nothing was recorded.
                QMessageBox.warning(self, "Error", "Recording could not start; see the log")
                return
            self._record_status_key = "record_recording"
            self._apply_record_status_label()
        except (AutoControlException, OSError, ValueError, TypeError, RuntimeError) as error:
            QMessageBox.warning(self, "Error", str(error))

    def _stop_record(self) -> None:
        if hasattr(self, '_record_owner'):
            self._submit_record(partial(_stop_owned, self._record_owner), self._record_stopped)
            return
        try:
            self._record_data = stop_record() or []
            self._record_status_key = "record_idle"
            self._apply_record_status_label()
            self.record_list_text.setText(json.dumps(self._record_data, indent=2, ensure_ascii=False))
        except (AutoControlException, OSError, ValueError, TypeError, RuntimeError) as error:
            QMessageBox.warning(self, "Error", str(error))

    def _playback_record(self) -> None:
        try:
            if not self._record_data:
                QMessageBox.warning(self, "Warning", "No recorded data")
                return
            if hasattr(self, '_record_tasks'):
                self._submit_record(partial(_playback_owned, json.loads(json.dumps(self._record_data))),
                                    self._record_played)
            else:
                execute_action(self._record_data)
        except (AutoControlException, OSError, ValueError, TypeError, RuntimeError) as error:
            QMessageBox.warning(self, "Error", str(error))

    def _submit_record(self, work: Callable[[CancellationToken], object],
                       callback: Callable[[TaskResult], None]) -> None:
        self._record_job = self._record_tasks.submit(work, owner=self._record_panel)
        self._record_job.completed.connect(callback)
        self._record_job.failed.connect(self._record_failed)
        self._record_job.finished.connect(self._record_released)

    def _record_started(self, _result: TaskResult) -> None:
        self._record_status_key = 'record_recording'
        self._apply_record_status_label()

    def _record_stopped(self, result: TaskResult) -> None:
        self._record_data = result.value if isinstance(result.value, list) else []
        self._record_status_key = 'record_idle'
        self._apply_record_status_label()
        self.record_list_text.setText(json.dumps(self._record_data, indent=2, ensure_ascii=False))

    def _record_played(self, _result: TaskResult) -> None:
        self._apply_record_status_label()

    def _record_failed(self, error: TaskError) -> None:
        self.record_status_label.setText(error.message)

    def _record_released(self) -> None:
        self._record_job = None

    def _save_record(self):
        try:
            if not self._record_data:
                QMessageBox.warning(self, "Warning", "No recorded data")
                return
            path, _ = QFileDialog.getSaveFileName(self, _t("save_record"), "", _JSON_FILE_FILTER)
            if path:
                write_action_json(path, self._record_data)
        except (AutoControlException, OSError, ValueError, TypeError, RuntimeError) as error:
            QMessageBox.warning(self, "Error", str(error))

    def _load_record(self):
        try:
            path, _ = QFileDialog.getOpenFileName(self, _t("load_record"), "", _JSON_FILE_FILTER)
            if path:
                self._record_data = read_action_json(path)
                self.record_list_text.setText(json.dumps(self._record_data, indent=2, ensure_ascii=False))
        except (AutoControlException, OSError, ValueError, TypeError, RuntimeError) as error:
            QMessageBox.warning(self, "Error", str(error))
