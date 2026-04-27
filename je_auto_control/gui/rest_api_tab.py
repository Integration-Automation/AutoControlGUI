"""REST API tab: start/stop the HTTP front-end and surface URL + token."""
from typing import Optional

import json
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.config_bundle import (
    ConfigBundleError, export_config_bundle, import_config_bundle,
)
from je_auto_control.utils.rest_api.rest_registry import rest_api_registry


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


class RestApiTab(TranslatableMixin, QWidget):
    """Thin Qt surface over :data:`rest_api_registry`."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._host_input = QLineEdit("127.0.0.1")
        self._port_input = QSpinBox()
        self._port_input.setRange(0, 65535)
        self._port_input.setValue(9939)
        self._token_input = QLineEdit()
        self._token_input.setPlaceholderText(_t("rest_token_ph"))
        self._audit_check = QCheckBox()
        self._audit_check.setChecked(True)
        self._url_value = QLabel("-")
        self._url_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._token_value = QLabel("-")
        self._token_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._status_label = QLabel()
        self._build_layout()
        self._refresh_status()
        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._refresh_status)
        self._timer.start()

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        root.addWidget(self._build_config_group())
        root.addLayout(self._build_button_row())
        root.addWidget(self._build_status_group())
        root.addStretch(1)

    def _build_config_group(self) -> QGroupBox:
        group = self._tr(QGroupBox(), "rest_config_group")
        form = QVBoxLayout(group)
        addr_row = QHBoxLayout()
        addr_row.addWidget(self._tr(QLabel(), "rest_host"))
        addr_row.addWidget(self._host_input, stretch=1)
        addr_row.addWidget(self._tr(QLabel(), "rest_port"))
        addr_row.addWidget(self._port_input)
        form.addLayout(addr_row)
        token_row = QHBoxLayout()
        token_row.addWidget(self._tr(QLabel(), "rest_token"))
        token_row.addWidget(self._token_input, stretch=1)
        form.addLayout(token_row)
        self._tr(self._audit_check, "rest_enable_audit")
        form.addWidget(self._audit_check)
        return group

    def _build_button_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        start = self._tr(QPushButton(), "rest_start")
        start.clicked.connect(self._on_start)
        row.addWidget(start)
        stop = self._tr(QPushButton(), "rest_stop")
        stop.clicked.connect(self._on_stop)
        row.addWidget(stop)
        copy_url = self._tr(QPushButton(), "rest_copy_url")
        copy_url.clicked.connect(self._on_copy_url)
        row.addWidget(copy_url)
        copy_token = self._tr(QPushButton(), "rest_copy_token")
        copy_token.clicked.connect(self._on_copy_token)
        row.addWidget(copy_token)
        export_btn = self._tr(QPushButton(), "rest_config_export")
        export_btn.clicked.connect(self._on_config_export)
        row.addWidget(export_btn)
        import_btn = self._tr(QPushButton(), "rest_config_import")
        import_btn.clicked.connect(self._on_config_import)
        row.addWidget(import_btn)
        row.addStretch(1)
        return row

    def _on_config_export(self) -> None:
        path_str, _ = QFileDialog.getSaveFileName(
            self, _t("rest_config_export"),
            "autocontrol-config.json",
            "JSON (*.json)",
        )
        if not path_str:
            return
        try:
            bundle = export_config_bundle()
            Path(path_str).write_text(
                json.dumps(bundle, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, _t("rest_config_export"), str(error))
            return
        QMessageBox.information(
            self, _t("rest_config_export"),
            _t("rest_config_export_done").format(
                count=len(bundle["files"]), path=path_str,
            ),
        )

    def _on_config_import(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self, _t("rest_config_import"), "", "JSON (*.json)",
        )
        if not path_str:
            return
        try:
            bundle = json.loads(Path(path_str).read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, _t("rest_config_import"), str(error))
            return
        confirm = QMessageBox.question(
            self, _t("rest_config_import"),
            _t("rest_config_import_confirm"),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            report = import_config_bundle(bundle)
        except ConfigBundleError as error:
            QMessageBox.warning(self, _t("rest_config_import"), str(error))
            return
        QMessageBox.information(
            self, _t("rest_config_import"),
            _t("rest_config_import_done").format(
                written=len(report.written), skipped=len(report.skipped),
            ),
        )

    def _build_status_group(self) -> QGroupBox:
        group = self._tr(QGroupBox(), "rest_status_group")
        form = QVBoxLayout(group)
        url_row = QHBoxLayout()
        url_row.addWidget(self._tr(QLabel(), "rest_url"))
        url_row.addWidget(self._url_value, stretch=1)
        form.addLayout(url_row)
        token_row = QHBoxLayout()
        token_row.addWidget(self._tr(QLabel(), "rest_active_token"))
        token_row.addWidget(self._token_value, stretch=1)
        form.addLayout(token_row)
        form.addWidget(self._status_label)
        return group

    def _on_start(self) -> None:
        host = self._host_input.text().strip() or "127.0.0.1"
        port = int(self._port_input.value())
        token = self._token_input.text().strip() or None
        try:
            rest_api_registry.start(
                host=host, port=port, token=token,
                enable_audit=self._audit_check.isChecked(),
            )
        except OSError as error:
            QMessageBox.warning(self, _t("rest_start"), str(error))
            return
        self._refresh_status()

    def _on_stop(self) -> None:
        rest_api_registry.stop()
        self._refresh_status()

    def _on_copy_url(self) -> None:
        text = self._url_value.text()
        if text and text != "-":
            QGuiApplication.clipboard().setText(text)

    def _on_copy_token(self) -> None:
        text = self._token_value.text()
        if text and text != "-":
            QGuiApplication.clipboard().setText(text)

    def _refresh_status(self) -> None:
        status = rest_api_registry.status()
        if status["running"]:
            self._url_value.setText(status["url"])
            self._token_value.setText(status["token"])
            self._status_label.setText(_t("rest_running"))
        else:
            self._url_value.setText("-")
            self._token_value.setText("-")
            self._status_label.setText(_t("rest_stopped"))


__all__ = ["RestApiTab"]
