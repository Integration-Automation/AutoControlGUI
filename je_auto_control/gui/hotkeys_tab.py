"""Hotkeys tab: bind global hotkeys to action JSON files."""
from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from je_auto_control.utils.hotkey.hotkey_daemon import default_hotkey_daemon


class HotkeysTab(QWidget):
    """Add / remove hotkey bindings and toggle the daemon."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._combo_input = QLineEdit()
        self._combo_input.setPlaceholderText("ctrl+alt+1")
        self._script_input = QLineEdit()
        self._status = QLabel("Daemon stopped")
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(
            ["ID", "Combo", "Script", "Fired"]
        )
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._refresh)
        self._build_layout()

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        form = QHBoxLayout()
        form.addWidget(QLabel("Combo:"))
        form.addWidget(self._combo_input)
        form.addWidget(QLabel("Script:"))
        form.addWidget(self._script_input, stretch=1)
        browse = QPushButton("Browse")
        browse.clicked.connect(self._browse)
        form.addWidget(browse)
        add = QPushButton("Bind")
        add.clicked.connect(self._on_bind)
        form.addWidget(add)
        root.addLayout(form)

        root.addWidget(self._table, stretch=1)

        ctl = QHBoxLayout()
        for label, handler in (
            ("Remove selected", self._on_remove),
            ("Start daemon", self._on_start),
            ("Stop daemon", self._on_stop),
        ):
            btn = QPushButton(label)
            btn.clicked.connect(handler)
            ctl.addWidget(btn)
        ctl.addStretch()
        root.addLayout(ctl)
        root.addWidget(self._status)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select script", "", "JSON (*.json)")
        if path:
            self._script_input.setText(path)

    def _on_bind(self) -> None:
        combo = self._combo_input.text().strip()
        script = self._script_input.text().strip()
        if not combo or not script:
            QMessageBox.warning(self, "Error", "Combo and script path are required")
            return
        try:
            default_hotkey_daemon.bind(combo, script)
        except ValueError as error:
            QMessageBox.warning(self, "Error", str(error))
            return
        self._refresh()

    def _on_remove(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        bid = self._table.item(row, 0).text()
        default_hotkey_daemon.unbind(bid)
        self._refresh()

    def _on_start(self) -> None:
        try:
            default_hotkey_daemon.start()
        except NotImplementedError as error:
            QMessageBox.warning(self, "Error", str(error))
            return
        self._timer.start()
        self._status.setText("Daemon running")

    def _on_stop(self) -> None:
        default_hotkey_daemon.stop()
        self._timer.stop()
        self._status.setText("Daemon stopped")

    def _refresh(self) -> None:
        bindings = default_hotkey_daemon.list_bindings()
        self._table.setRowCount(len(bindings))
        for row, binding in enumerate(bindings):
            for col, value in enumerate((binding.binding_id, binding.combo,
                                         binding.script_path, str(binding.fired))):
                self._table.setItem(row, col, QTableWidgetItem(value))
