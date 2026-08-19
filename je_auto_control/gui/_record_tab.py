"""Record / playback tab builder (extracted mixin)."""
import json

from PySide6.QtWidgets import (
    QFileDialog, QLabel, QMessageBox, QTextEdit, QVBoxLayout, QWidget,
)

from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.executor.action_executor import execute_action
from je_auto_control.utils.json.json_file import read_action_json, write_action_json
from je_auto_control.wrapper.auto_control_record import record, stop_record

_JSON_FILE_FILTER = "JSON (*.json)"


def _t(key: str) -> str:
    """language_wrapper shorthand"""
    return language_wrapper.translate(key, key)


class RecordTabMixin:
    """Provides the record/playback tab builder/handlers.

    Host widget must expose the ``TranslatableMixin`` API (``self._tr(...)``,
    ``self._translate(...)``) and a ``self._record_data`` list holding the
    last recording.
    """

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
            record()
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
        try:
            if not self._record_data:
                QMessageBox.warning(self, "Warning", "No recorded data")
                return
            execute_action(self._record_data)
        except (AutoControlException, OSError, ValueError, TypeError, RuntimeError) as error:
            QMessageBox.warning(self, "Error", str(error))

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
