"""Record / playback tab builder (extracted mixin).

Playback runs off the GUI thread as a stoppable executor run, one at a time.
"""
import copy
import functools
import json

from typing import TYPE_CHECKING, Any, Callable

from PySide6.QtWidgets import (
    QFileDialog, QLabel, QMessageBox, QTextEdit, QVBoxLayout, QWidget,
)

from je_auto_control.gui._tab_task import TabTask, was_stopped
from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.executor.action_executor import execute_action
from je_auto_control.utils.json.json_file import read_action_json, write_action_json
from je_auto_control.wrapper.auto_control_record import record, stop_record

_JSON_FILE_FILTER = "JSON (*.json)"


def _t(key: str) -> str:
    """language_wrapper shorthand"""
    return language_wrapper.translate(key, key)


def _play_actions(actions: list) -> object:
    """Worker thread: replay a recording."""
    return execute_action(actions)


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
        self._playback_runs = TabTask(self)
        self._playback_runs.error.connect(self._on_playback_error)
        self._playback_runs.finished.connect(self._on_playback_finished)
        return tab

    def _apply_record_status_label(self) -> None:
        if hasattr(self, "record_status_label"):
            self.record_status_label.setText(
                self._translate("record_status") + " "
                + self._translate(self._record_status_key),
            )

    def _record_retranslate(self) -> None:
        self._apply_record_status_label()

    def _start_record(self):
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

    def _stop_record(self):
        try:
            self._record_data = stop_record() or []
            self._record_status_key = "record_idle"
            self._apply_record_status_label()
            self.record_list_text.setText(json.dumps(self._record_data, indent=2, ensure_ascii=False))
        except (AutoControlException, OSError, ValueError, TypeError, RuntimeError) as error:
            QMessageBox.warning(self, "Error", str(error))

    def _playback_record(self):
        if not self._record_data:
            QMessageBox.warning(self, "Warning", "No recorded data")
            return
        # The worker gets its own copy: loading or recording again while the
        # playback runs must not change the list under it.
        if not self._playback_runs.start_script(
                functools.partial(_play_actions, copy.deepcopy(self._record_data))):
            return
        self._record_status_key = "record_playing"
        self._apply_record_status_label()

    def _stop_playback(self) -> None:
        """Ask the running playback to stop; it ends at its next checkpoint."""
        self._playback_runs.stop()

    def _on_playback_error(self, error: object) -> None:
        if not was_stopped(error):
            QMessageBox.warning(self, "Error", str(error))

    def _on_playback_finished(self) -> None:
        self._record_status_key = "record_idle"
        self._apply_record_status_label()

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
