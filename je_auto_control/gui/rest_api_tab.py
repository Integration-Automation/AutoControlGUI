"""REST API tab: start/stop the HTTP front-end, show how to authenticate, manage users.

Without a user store the server has one shared bearer token and the tab
shows it. With one (RBAC) the shared token opens nothing, so the tab says
whose tokens are accepted instead of displaying a credential the server
refuses; the users themselves are managed in the group below.
"""
from typing import Optional

import functools
import json
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QSpinBox, QVBoxLayout, QWidget,
)

from je_auto_control.gui._dispose import release_resources
from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui._slow_op import SlowOp
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.gui.rbac_users_panel import RbacUsersPanel
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
        self._url_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._token_value = QLabel("-")
        self._token_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._status_label = QLabel()
        # Start replaces a running server and Stop joins its thread: both off the GUI thread.
        self._server_op = SlowOp(self)
        self._pending_key = "gui_op_stopping"
        # The token label holds a copyable token only under the shared token.
        self._shared_token: Optional[str] = None
        self._users_panel = RbacUsersPanel()
        self._build_layout()
        self._refresh_status()
        self._users_panel.refresh()
        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._refresh_status)
        self._timer.start()

    def _build_layout(self) -> None:
        # Start/stop/copy/export/import commands run from the Actions
        # menu; the tab keeps only the config inputs and the status group.
        root = QVBoxLayout(self)
        root.addWidget(self._build_config_group())
        root.addWidget(self._build_status_group())
        root.addWidget(self._users_panel, stretch=1)

    def menu_actions(self) -> list:
        """Expose tab commands to the window-level Actions menu."""
        return [
            ("rest_start", self._on_start),
            ("rest_stop", self._on_stop),
            ("rest_copy_url", self._on_copy_url),
            ("rest_copy_token", self._on_copy_token),
            ("rest_config_export", self._on_config_export),
            ("rest_config_import", self._on_config_import),
            *self._users_panel.menu_actions(),
        ]

    def dispose(self) -> None:
        """Release what the tab holds beyond its widgets: its status timer (the server keeps running).

        Called by ``close_tab(key, release=True)`` before the widget is deleted; safe to call twice.
        """
        release_resources(self)

    def retranslate(self) -> None:
        """Re-translate the tab, its users group and the status texts."""
        super().retranslate()
        self._users_panel.retranslate()
        self._refresh_status()

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
        if self._server_op.busy:        # a start or stop is still out; a second click is ignored
            return
        host = self._host_input.text().strip() or "127.0.0.1"
        port = int(self._port_input.value())
        token = self._token_input.text().strip() or None
        # start() first stops a running server (a 2 s join), all under the
        # registry's lock, which used to hold the GUI thread.
        work = functools.partial(
            rest_api_registry.start, host=host, port=port, token=token,
            enable_audit=self._audit_check.isChecked(),
            user_store=self._users_panel.user_store(),
        )
        self._pending_key = "gui_op_starting"
        self._server_op.run(work, on_done=self._on_server_op_done, on_error=self._on_start_failed)
        self._refresh_status()

    def _on_start_failed(self, error: Exception) -> None:
        self._refresh_status()
        QMessageBox.warning(self, _t("rest_start"), str(error))

    def _on_stop(self) -> None:
        if self._server_op.busy:
            return
        self._pending_key = "gui_op_stopping"
        self._server_op.run(rest_api_registry.stop, on_done=self._on_server_op_done,
                            on_error=self._on_server_op_done)
        self._refresh_status()

    def _on_server_op_done(self, _outcome: object = None) -> None:
        self._refresh_status()

    def _on_copy_url(self) -> None:
        text = self._url_value.text()
        if text and text != "-":
            QGuiApplication.clipboard().setText(text)

    def _on_copy_token(self) -> None:
        if self._shared_token:
            QGuiApplication.clipboard().setText(self._shared_token)

    def _refresh_status(self) -> None:
        if self._server_op.busy:
            # Not status(): it waits for the registry's lock, which a start
            # holds until the previous server has been joined.
            self._shared_token = None
            self._url_value.setText("-")
            self._token_value.setText("-")
            self._status_label.setText(_t(self._pending_key))
            return
        status = rest_api_registry.status()
        self._shared_token = None
        if not status["running"]:
            self._url_value.setText("-")
            self._token_value.setText("-")
            self._status_label.setText(_t("rest_stopped"))
            return
        self._url_value.setText(status["url"])
        if status.get("rbac"):
            self._token_value.setText(
                _t("rest_token_rbac").format(path=status.get("users_path")))
            self._status_label.setText(_t("rest_running_rbac"))
            return
        self._shared_token = status["token"]
        self._token_value.setText(status["token"])
        self._status_label.setText(_t("rest_running"))


__all__ = ["RestApiTab"]
