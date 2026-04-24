"""Composite widget that ties the step tree and form into a Script Builder tab."""
import json
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QMenu, QMessageBox, QPushButton, QSplitter,
    QTextEdit, QToolButton, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.gui.script_builder.command_schema import (
    CATEGORIES, COMMAND_SPECS, specs_in_category,
)
from je_auto_control.gui.script_builder.step_form_view import StepFormView
from je_auto_control.gui.script_builder.step_list_view import StepTreeView
from je_auto_control.gui.script_builder.step_model import (
    Step, actions_to_steps, steps_to_actions,
)
from je_auto_control.utils.executor.action_executor import execute_action
from je_auto_control.utils.json.json_file import read_action_json, write_action_json


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


class ScriptBuilderTab(TranslatableMixin, QWidget):
    """Visual editor for composing AC_* scripts."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._tree = StepTreeView()
        self._form = StepFormView()
        self._result = QTextEdit()
        self._result.setReadOnly(True)
        self._result.setMaximumHeight(140)
        self._add_btn: Optional[QToolButton] = None
        self._build_layout()
        self._wire_signals()

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        if self._add_btn is not None:
            self._add_btn.setText(_t("sb_add_step"))
        if hasattr(self._form, "retranslate"):
            self._form.retranslate()

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        root.addLayout(self._build_toolbar())
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._tree)
        splitter.addWidget(self._form)
        splitter.setSizes([320, 480])
        root.addWidget(splitter, stretch=1)
        root.addWidget(self._result)

    def _build_toolbar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.addWidget(self._add_button())
        for key, handler in (
            ("sb_delete", self._on_delete),
            ("sb_up", lambda: self._tree.move_selected(-1)),
            ("sb_down", lambda: self._tree.move_selected(1)),
        ):
            btn = self._tr(QPushButton(), key)
            btn.clicked.connect(handler)
            bar.addWidget(btn)
        bar.addStretch()
        for key, handler in (
            ("sb_load_json", self._on_load),
            ("sb_save_json", self._on_save),
            ("sb_run", self._on_run),
        ):
            btn = self._tr(QPushButton(), key)
            btn.clicked.connect(handler)
            bar.addWidget(btn)
        return bar

    def _add_button(self) -> QToolButton:
        button = QToolButton()
        button.setText(_t("sb_add_step"))
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(button)
        for category in CATEGORIES:
            submenu = menu.addMenu(category)
            for spec in specs_in_category(category):
                action = QAction(spec.label, submenu)
                action.triggered.connect(
                    lambda _checked=False, cmd=spec.command: self._add_step_from_command(cmd)
                )
                submenu.addAction(action)
        button.setMenu(menu)
        self._add_btn = button
        return button

    def _wire_signals(self) -> None:
        self._tree.selected_step_changed.connect(self._form.load_step)
        self._form.step_changed.connect(self._tree.refresh_current_label)

    def _add_step_from_command(self, command: str) -> None:
        spec = COMMAND_SPECS.get(command)
        if spec is None:
            return
        defaults = {
            f.name: f.default for f in spec.fields
            if f.default is not None and not f.optional
        }
        step = Step(command=command, params=defaults)
        self._tree.add_step(step)

    def _on_delete(self) -> None:
        self._tree.remove_selected()
        self._form.load_step(None)

    def _on_save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, _t("sb_dialog_save"), "", "JSON (*.json)",
        )
        if not path:
            return
        try:
            actions = steps_to_actions(self._tree.root_steps())
            write_action_json(path, actions)
            self._result.setPlainText(f"Saved: {path}")
        except (OSError, ValueError, TypeError) as error:
            QMessageBox.warning(self, "Error", str(error))

    def _on_load(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, _t("sb_dialog_load"), "", "JSON (*.json)",
        )
        if not path:
            return
        try:
            actions = read_action_json(path)
            self._tree.load_steps(actions_to_steps(actions))
            self._form.load_step(None)
            self._result.setPlainText(f"Loaded: {path}")
        except (OSError, ValueError, TypeError) as error:
            QMessageBox.warning(self, "Error", str(error))

    def _on_run(self) -> None:
        try:
            actions = steps_to_actions(self._tree.root_steps())
            if not actions:
                QMessageBox.information(self, "Info", "No steps to run")
                return
            result = execute_action(actions)
            self._result.setPlainText(
                json.dumps(result, indent=2, default=str, ensure_ascii=False)
            )
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            QMessageBox.warning(self, "Error", str(error))
