"""Composite widget that ties the step tree and form into a Script Builder tab."""
import json
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QMenu, QMessageBox, QPushButton, QSplitter,
    QTextEdit, QToolButton, QVBoxLayout, QWidget,
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


class ScriptBuilderTab(QWidget):
    """Visual editor for composing AC_* scripts."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tree = StepTreeView()
        self._form = StepFormView()
        self._result = QTextEdit()
        self._result.setReadOnly(True)
        self._result.setMaximumHeight(140)
        self._build_layout()
        self._wire_signals()

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
        for label, handler in (
            ("Delete", self._on_delete),
            ("Up", lambda: self._tree.move_selected(-1)),
            ("Down", lambda: self._tree.move_selected(1)),
        ):
            btn = QPushButton(label)
            btn.clicked.connect(handler)
            bar.addWidget(btn)
        bar.addStretch()
        for label, handler in (
            ("Load JSON", self._on_load),
            ("Save JSON", self._on_save),
            ("Run", self._on_run),
        ):
            btn = QPushButton(label)
            btn.clicked.connect(handler)
            bar.addWidget(btn)
        return bar

    def _add_button(self) -> QToolButton:
        button = QToolButton()
        button.setText("Add Step")
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
        path, _ = QFileDialog.getSaveFileName(self, "Save script", "", "JSON (*.json)")
        if not path:
            return
        try:
            actions = steps_to_actions(self._tree.root_steps())
            write_action_json(path, actions)
            self._result.setPlainText(f"Saved: {path}")
        except (OSError, ValueError, TypeError) as error:
            QMessageBox.warning(self, "Error", str(error))

    def _on_load(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load script", "", "JSON (*.json)")
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
