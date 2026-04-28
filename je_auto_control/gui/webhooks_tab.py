"""Webhooks tab: bind HTTP requests to action scripts."""
from typing import Optional

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QFileDialog, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.triggers.webhook_server import (
    default_webhook_server,
)


_REFRESH_MS = 1000
_DEFAULT_METHODS = ("POST", "GET", "PUT", "DELETE")


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


class WebhooksTab(TranslatableMixin, QWidget):
    """GUI front-end for :data:`default_webhook_server`."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._host_input = QLineEdit("127.0.0.1")
        self._port_input = QSpinBox()
        self._port_input.setRange(0, 65535)
        self._port_input.setValue(0)
        self._status_label = QLabel()
        self._path_input = QLineEdit()
        self._path_input.setPlaceholderText("/jobs")
        self._script_input = QLineEdit()
        self._token_input = QLineEdit()
        self._token_input.setEchoMode(QLineEdit.Password)
        self._method_checks = {
            method: QCheckBox(method) for method in _DEFAULT_METHODS
        }
        self._method_checks["POST"].setChecked(True)
        self._table = QTableWidget(0, 6)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Interactive,
        )
        self._table.horizontalHeader().setStretchLastSection(True)
        self._apply_table_headers()
        self._build_layout()
        self._timer = QTimer(self)
        self._timer.setInterval(_REFRESH_MS)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()
        self._refresh()

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        self._apply_table_headers()
        self._refresh()

    def _apply_table_headers(self) -> None:
        self._table.setHorizontalHeaderLabels([
            _t("wh_col_id"), _t("wh_col_path"), _t("wh_col_methods"),
            _t("wh_col_script"), _t("wh_col_fired"), _t("wh_col_token"),
        ])

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)

        server_box = self._tr(QGroupBox(), "wh_server_group")
        server_layout = QHBoxLayout(server_box)
        server_layout.addWidget(self._tr(QLabel(), "wh_host_label"))
        server_layout.addWidget(self._host_input)
        server_layout.addWidget(self._tr(QLabel(), "wh_port_label"))
        server_layout.addWidget(self._port_input)
        start_btn = self._tr(QPushButton(), "wh_start")
        start_btn.clicked.connect(self._on_start)
        server_layout.addWidget(start_btn)
        stop_btn = self._tr(QPushButton(), "wh_stop")
        stop_btn.clicked.connect(self._on_stop)
        server_layout.addWidget(stop_btn)
        server_layout.addStretch()
        root.addWidget(server_box)
        root.addWidget(self._status_label)

        add_box = self._tr(QGroupBox(), "wh_add_group")
        add_layout = QVBoxLayout(add_box)
        path_row = QHBoxLayout()
        path_row.addWidget(self._tr(QLabel(), "wh_path_label"))
        path_row.addWidget(self._path_input)
        add_layout.addLayout(path_row)
        script_row = QHBoxLayout()
        script_row.addWidget(self._tr(QLabel(), "wh_script_label"))
        script_row.addWidget(self._script_input)
        browse_btn = self._tr(QPushButton(), "wh_browse")
        browse_btn.clicked.connect(self._on_browse)
        script_row.addWidget(browse_btn)
        add_layout.addLayout(script_row)
        method_row = QHBoxLayout()
        method_row.addWidget(self._tr(QLabel(), "wh_methods_label"))
        for method, check in self._method_checks.items():
            method_row.addWidget(check)
        method_row.addStretch()
        add_layout.addLayout(method_row)
        token_row = QHBoxLayout()
        token_row.addWidget(self._tr(QLabel(), "wh_token_label"))
        self._token_input.setPlaceholderText(_t("wh_token_placeholder"))
        token_row.addWidget(self._token_input)
        register_btn = self._tr(QPushButton(), "wh_register")
        register_btn.clicked.connect(self._on_register)
        token_row.addWidget(register_btn)
        add_layout.addLayout(token_row)
        root.addWidget(add_box)

        root.addWidget(self._table, stretch=1)
        action_row = QHBoxLayout()
        remove_btn = self._tr(QPushButton(), "wh_remove")
        remove_btn.clicked.connect(self._on_remove)
        action_row.addWidget(remove_btn)
        action_row.addStretch()
        root.addLayout(action_row)

    def _on_start(self) -> None:
        host = self._host_input.text().strip() or "127.0.0.1"
        port = int(self._port_input.value())
        try:
            bound_host, bound_port = default_webhook_server.start(host, port)
        except OSError as error:
            QMessageBox.warning(self, _t("wh_start"), str(error))
            return
        self._port_input.setValue(bound_port)
        QMessageBox.information(
            self, _t("wh_start"),
            _t("wh_started").replace("{host}", bound_host)
                            .replace("{port}", str(bound_port)),
        )
        self._refresh()

    def _on_stop(self) -> None:
        default_webhook_server.stop()
        self._refresh()

    def _on_browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, _t("wh_browse"), "", "JSON (*.json)",
        )
        if path:
            self._script_input.setText(path)

    def _selected_methods(self) -> list:
        return [m for m, c in self._method_checks.items() if c.isChecked()]

    def _on_register(self) -> None:
        path = self._path_input.text().strip()
        script = self._script_input.text().strip()
        if not path or not script:
            QMessageBox.warning(self, _t("wh_register"),
                                _t("wh_path_and_script_required"))
            return
        token = self._token_input.text().strip() or None
        try:
            default_webhook_server.add(
                path=path, script_path=script,
                methods=self._selected_methods(),
                token=token,
            )
        except ValueError as error:
            QMessageBox.warning(self, _t("wh_register"), str(error))
            return
        self._token_input.clear()
        self._refresh()

    def _on_remove(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        item = self._table.item(row, 0)
        if item is None:
            return
        default_webhook_server.remove(item.text())
        self._refresh()

    def _refresh(self) -> None:
        bound = default_webhook_server.bound_address
        if default_webhook_server.is_running and bound is not None:
            self._status_label.setText(
                _t("wh_running")
                .replace("{host}", bound[0])
                .replace("{port}", str(bound[1])),
            )
        else:
            self._status_label.setText(_t("wh_stopped"))
        rows = default_webhook_server.list_webhooks()
        self._table.setRowCount(len(rows))
        for row, trigger in enumerate(rows):
            values = (
                trigger.webhook_id,
                trigger.path,
                ",".join(trigger.methods),
                trigger.script_path,
                str(trigger.fired),
                _t("wh_yes") if trigger.token else _t("wh_no"),
            )
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self._table.setItem(row, col, item)
