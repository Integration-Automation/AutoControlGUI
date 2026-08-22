"""Script-executor tab builder (extracted mixin)."""
import json

from typing import TYPE_CHECKING, Any, Callable

from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QLineEdit, QTextEdit, QVBoxLayout,
    QWidget,
)

from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.executor.action_executor import execute_action, execute_files
from je_auto_control.utils.file_process.get_dir_file_list import get_dir_files_as_list
from je_auto_control.utils.json.json_file import read_action_json

_JSON_FILE_FILTER = "JSON (*.json)"


def _t(key: str) -> str:
    """language_wrapper shorthand"""
    return language_wrapper.translate(key, key)


class ScriptTabMixin:
    """Provides the script-executor tab builder/handlers.

    Host widget must expose the ``TranslatableMixin`` API (``self._tr(...)``).
    """

    if TYPE_CHECKING:
        # Declared, never defined: the widget this mixin is mixed into owns
        # every one of these. The block is stripped at runtime, so nothing
        # here can shadow what the host actually binds.
        _tr: Callable[..., Any]

    def _build_script_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout()

        # Load/execute commands run from the Actions menu; the tab keeps
        # only the path inputs, the editor, and the result view.
        file_h = QHBoxLayout()
        file_h.addWidget(self._tr(QLabel(), "file_path_label"))
        self.script_path_input = QLineEdit()
        file_h.addWidget(self.script_path_input)
        layout.addLayout(file_h)

        dir_h = QHBoxLayout()
        dir_h.addWidget(self._tr(QLabel(), "execute_dir_label"))
        self.script_dir_input = QLineEdit()
        dir_h.addWidget(self.script_dir_input)
        layout.addLayout(dir_h)

        layout.addWidget(self._tr(QLabel(), "script_content"))
        self.script_editor = QTextEdit()
        self.script_editor.setPlaceholderText('[["AC_type_keyboard", {"keycode": "a"}]]')
        layout.addWidget(self.script_editor)

        layout.addWidget(self._tr(QLabel(), "execution_result"))
        self.script_result_text = QTextEdit()
        self.script_result_text.setReadOnly(True)
        layout.addWidget(self.script_result_text)
        tab.setLayout(layout)
        return tab

    def _browse_script(self):
        path, _ = QFileDialog.getOpenFileName(self, _t("load_script"), "", _JSON_FILE_FILTER)
        if path:
            self.script_path_input.setText(path)
            try:
                data = read_action_json(path)
                self.script_editor.setText(json.dumps(data, indent=2, ensure_ascii=False))
            except (AutoControlException, OSError, ValueError, TypeError, RuntimeError) as error:
                self.script_result_text.setText(f"Error loading: {error}")

    def _execute_script(self):
        try:
            path = self.script_path_input.text()
            if not path:
                return
            data = read_action_json(path)
            result = execute_action(data)
            self.script_result_text.setText(json.dumps(result, indent=2, default=str, ensure_ascii=False))
        except (AutoControlException, OSError, ValueError, TypeError, RuntimeError) as error:
            self.script_result_text.setText(f"Error: {error}")

    def _browse_script_dir(self):
        path = QFileDialog.getExistingDirectory(self, _t("execute_dir_label"))
        if path:
            self.script_dir_input.setText(path)

    def _execute_dir(self):
        try:
            path = self.script_dir_input.text()
            if not path:
                return
            files = get_dir_files_as_list(path)
            result = execute_files(files)
            self.script_result_text.setText(json.dumps(result, indent=2, default=str, ensure_ascii=False))
        except (AutoControlException, OSError, ValueError, TypeError, RuntimeError) as error:
            self.script_result_text.setText(f"Error: {error}")

    def _execute_manual_script(self):
        try:
            text = self.script_editor.toPlainText().strip()
            if not text:
                return
            data = json.loads(text)
            result = execute_action(data)
            self.script_result_text.setText(json.dumps(result, indent=2, default=str, ensure_ascii=False))
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            self.script_result_text.setText(f"Error: {error}")
