"""Recording Editor tab: trim, filter and rescale recorded action lists."""
import json
from typing import Optional

from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox,
    QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from je_auto_control.utils.json.json_file import read_action_json, write_action_json
from je_auto_control.utils.recording_edit.editor import (
    adjust_delays, filter_actions, remove_action, scale_coordinates, trim_actions,
)


class RecordingEditorTab(QWidget):
    """Load a recording JSON and apply non-destructive edits."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._actions: list = []
        self._path_input = QLineEdit()
        self._list = QListWidget()
        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._status = QLabel("")
        self._trim_start = QLineEdit("0")
        self._trim_end = QLineEdit("")
        self._delay_factor = QLineEdit("1.0")
        self._delay_clamp = QLineEdit("0")
        self._scale_x = QLineEdit("1.0")
        self._scale_y = QLineEdit("1.0")
        self._build_layout()

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("File:"))
        top.addWidget(self._path_input, stretch=1)
        for label, handler in (
            ("Browse", self._browse),
            ("Load", self._load),
            ("Save As", self._save_as),
        ):
            btn = QPushButton(label)
            btn.clicked.connect(handler)
            top.addWidget(btn)
        root.addLayout(top)

        root.addWidget(self._list, stretch=1)

        ops1 = QHBoxLayout()
        ops1.addWidget(QLabel("Trim start:"))
        ops1.addWidget(self._trim_start)
        ops1.addWidget(QLabel("end:"))
        ops1.addWidget(self._trim_end)
        trim_btn = QPushButton("Apply trim")
        trim_btn.clicked.connect(self._apply_trim)
        ops1.addWidget(trim_btn)
        remove_btn = QPushButton("Remove selected")
        remove_btn.clicked.connect(self._remove_selected)
        ops1.addWidget(remove_btn)
        ops1.addStretch()
        root.addLayout(ops1)

        ops2 = QHBoxLayout()
        ops2.addWidget(QLabel("Delay x"))
        ops2.addWidget(self._delay_factor)
        ops2.addWidget(QLabel("floor ms:"))
        ops2.addWidget(self._delay_clamp)
        delay_btn = QPushButton("Apply delays")
        delay_btn.clicked.connect(self._apply_delays)
        ops2.addWidget(delay_btn)
        ops2.addWidget(QLabel("Scale x:"))
        ops2.addWidget(self._scale_x)
        ops2.addWidget(QLabel("y:"))
        ops2.addWidget(self._scale_y)
        scale_btn = QPushButton("Apply scale")
        scale_btn.clicked.connect(self._apply_scale)
        ops2.addWidget(scale_btn)
        ops2.addStretch()
        root.addLayout(ops2)

        ops3 = QHBoxLayout()
        keep_mouse = QPushButton("Keep mouse only")
        keep_mouse.clicked.connect(lambda: self._filter_prefix("AC_mouse"))
        keep_keyboard = QPushButton("Keep keyboard only")
        keep_keyboard.clicked.connect(
            lambda: self._filter_prefix(("AC_type_keyboard", "AC_press_keyboard_key",
                                         "AC_release_keyboard_key", "AC_hotkey", "AC_write"))
        )
        ops3.addWidget(keep_mouse)
        ops3.addWidget(keep_keyboard)
        ops3.addStretch()
        root.addLayout(ops3)

        root.addWidget(QLabel("Preview:"))
        root.addWidget(self._preview, stretch=1)
        root.addWidget(self._status)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open recording", "", "JSON (*.json)")
        if path:
            self._path_input.setText(path)

    def _load(self) -> None:
        path = self._path_input.text().strip()
        if not path:
            return
        try:
            self._actions = read_action_json(path)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Error", str(error))
            return
        self._refresh()

    def _save_as(self) -> None:
        if not self._actions:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save recording", "", "JSON (*.json)")
        if not path:
            return
        try:
            write_action_json(path, self._actions)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Error", str(error))
            return
        self._status.setText(f"Saved to {path}")

    def _refresh(self) -> None:
        self._list.clear()
        for idx, action in enumerate(self._actions):
            self._list.addItem(f"{idx}: {action[0]}")
        self._preview.setPlainText(json.dumps(self._actions, indent=2, ensure_ascii=False))
        self._status.setText(f"{len(self._actions)} actions")

    def _apply_trim(self) -> None:
        try:
            start = int(self._trim_start.text() or "0")
            end_text = self._trim_end.text().strip()
            end = int(end_text) if end_text else None
        except ValueError:
            QMessageBox.warning(self, "Error", "Trim indices must be integers")
            return
        self._actions = trim_actions(self._actions, start, end)
        self._refresh()

    def _remove_selected(self) -> None:
        row = self._list.currentRow()
        if row < 0:
            return
        try:
            self._actions = remove_action(self._actions, row)
        except IndexError as error:
            QMessageBox.warning(self, "Error", str(error))
            return
        self._refresh()

    def _apply_delays(self) -> None:
        try:
            factor = float(self._delay_factor.text() or "1.0")
            clamp = int(self._delay_clamp.text() or "0")
        except ValueError:
            QMessageBox.warning(self, "Error", "Factor/clamp must be numeric")
            return
        self._actions = adjust_delays(self._actions, factor=factor, clamp_ms=clamp)
        self._refresh()

    def _apply_scale(self) -> None:
        try:
            fx = float(self._scale_x.text() or "1.0")
            fy = float(self._scale_y.text() or "1.0")
        except ValueError:
            QMessageBox.warning(self, "Error", "Scale factors must be numeric")
            return
        self._actions = scale_coordinates(self._actions, fx, fy)
        self._refresh()

    def _filter_prefix(self, prefix) -> None:
        def keep(action: list) -> bool:
            if not (isinstance(action, list) and action):
                return False
            name = action[0]
            if isinstance(prefix, str):
                return name.startswith(prefix)
            return name in prefix
        self._actions = filter_actions(self._actions, keep)
        self._refresh()
