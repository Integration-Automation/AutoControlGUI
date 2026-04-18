"""Hotkeys tab: bind global hotkeys to action JSON files."""
from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.hotkey.hotkey_daemon import default_hotkey_daemon


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


class HotkeysTab(TranslatableMixin, QWidget):
    """Add / remove hotkey bindings and toggle the daemon."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._combo_input = QLineEdit()
        self._combo_input.setPlaceholderText("ctrl+alt+1")
        self._script_input = QLineEdit()
        self._daemon_running = False
        self._status = QLabel()
        self._table = QTableWidget(0, 4)
        self._apply_status_label()
        self._apply_table_headers()
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._refresh)
        self._build_layout()

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        form = QHBoxLayout()
        form.addWidget(self._tr(QLabel(), "hk_combo_label"))
        form.addWidget(self._combo_input)
        form.addWidget(self._tr(QLabel(), "hk_script_label"))
        form.addWidget(self._script_input, stretch=1)
        browse = self._tr(QPushButton(), "browse")
        browse.clicked.connect(self._browse)
        form.addWidget(browse)
        add = self._tr(QPushButton(), "hk_bind")
        add.clicked.connect(self._on_bind)
        form.addWidget(add)
        root.addLayout(form)

        root.addWidget(self._table, stretch=1)

        ctl = QHBoxLayout()
        for key, handler in (
            ("hk_remove_selected", self._on_remove),
            ("hk_start_daemon", self._on_start),
            ("hk_stop_daemon", self._on_stop),
        ):
            btn = self._tr(QPushButton(), key)
            btn.clicked.connect(handler)
            ctl.addWidget(btn)
        ctl.addStretch()
        root.addLayout(ctl)
        root.addWidget(self._status)

    def _apply_status_label(self) -> None:
        key = "hk_daemon_running" if self._daemon_running else "hk_daemon_stopped"
        self._status.setText(_t(key))

    def _apply_table_headers(self) -> None:
        self._table.setHorizontalHeaderLabels([
            _t("hk_col_id"), _t("hk_col_combo"),
            _t("hk_col_script"), _t("hk_col_fired"),
        ])

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        self._apply_status_label()
        self._apply_table_headers()

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, _t("hk_dialog_select_script"), "", "JSON (*.json)",
        )
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
        self._daemon_running = True
        self._apply_status_label()

    def _on_stop(self) -> None:
        default_hotkey_daemon.stop()
        self._timer.stop()
        self._daemon_running = False
        self._apply_status_label()

    def _refresh(self) -> None:
        bindings = default_hotkey_daemon.list_bindings()
        self._table.setRowCount(len(bindings))
        for row, binding in enumerate(bindings):
            for col, value in enumerate((binding.binding_id, binding.combo,
                                         binding.script_path, str(binding.fired))):
                self._table.setItem(row, col, QTableWidgetItem(value))
