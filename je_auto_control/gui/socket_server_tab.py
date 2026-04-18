"""Socket + REST server control panel."""
from typing import Optional

from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QCheckBox, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.rest_api.rest_server import RestApiServer
from je_auto_control.utils.socket_server.auto_control_socket_server import (
    start_autocontrol_socket_server,
)


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


class SocketServerTab(TranslatableMixin, QWidget):
    """Start / stop the TCP socket server and the REST API server."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._tcp_server = None
        self._rest_server: Optional[RestApiServer] = None
        self._tcp_host = QLineEdit("127.0.0.1")
        self._tcp_port = QLineEdit("9938")
        self._tcp_port.setValidator(QIntValidator(1, 65535))
        self._tcp_any = self._tr(QCheckBox(), "ss_tcp_any_check")
        self._tcp_status = QLabel()
        self._tcp_listening: Optional[str] = None
        self._tcp_start_btn = self._tr(QPushButton(), "ss_tcp_start")
        self._tcp_stop_btn = self._tr(QPushButton(), "ss_tcp_stop")
        self._tcp_stop_btn.setEnabled(False)

        self._rest_host = QLineEdit("127.0.0.1")
        self._rest_port = QLineEdit("9939")
        self._rest_port.setValidator(QIntValidator(1, 65535))
        self._rest_any = self._tr(QCheckBox(), "ss_rest_any_check")
        self._rest_status = QLabel()
        self._rest_listening: Optional[str] = None
        self._rest_start_btn = self._tr(QPushButton(), "ss_rest_start")
        self._rest_stop_btn = self._tr(QPushButton(), "ss_rest_stop")
        self._rest_stop_btn.setEnabled(False)

        self._apply_tcp_status()
        self._apply_rest_status()
        self._build_layout()

    def _apply_tcp_status(self) -> None:
        if self._tcp_listening:
            self._tcp_status.setText(f"Listening on {self._tcp_listening}")
        else:
            self._tcp_status.setText(_t("ss_tcp_stopped"))

    def _apply_rest_status(self) -> None:
        if self._rest_listening:
            self._rest_status.setText(f"Listening on {self._rest_listening}")
        else:
            self._rest_status.setText(_t("ss_rest_stopped"))

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        self._apply_tcp_status()
        self._apply_rest_status()

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)

        tcp_group = self._tr(QGroupBox(), "ss_tcp_group")
        tcp_layout = QVBoxLayout(tcp_group)
        tcp_form = QHBoxLayout()
        tcp_form.addWidget(self._tr(QLabel(), "ss_host_label"))
        tcp_form.addWidget(self._tcp_host)
        tcp_form.addWidget(self._tr(QLabel(), "ss_port_label"))
        tcp_form.addWidget(self._tcp_port)
        tcp_layout.addLayout(tcp_form)
        tcp_layout.addWidget(self._tcp_any)
        tcp_btns = QHBoxLayout()
        self._tcp_start_btn.clicked.connect(self._start_tcp)
        self._tcp_stop_btn.clicked.connect(self._stop_tcp)
        tcp_btns.addWidget(self._tcp_start_btn)
        tcp_btns.addWidget(self._tcp_stop_btn)
        tcp_btns.addStretch()
        tcp_layout.addLayout(tcp_btns)
        tcp_layout.addWidget(self._tcp_status)
        root.addWidget(tcp_group)

        rest_group = self._tr(QGroupBox(), "ss_rest_group")
        rest_layout = QVBoxLayout(rest_group)
        rest_form = QHBoxLayout()
        rest_form.addWidget(self._tr(QLabel(), "ss_host_label"))
        rest_form.addWidget(self._rest_host)
        rest_form.addWidget(self._tr(QLabel(), "ss_port_label"))
        rest_form.addWidget(self._rest_port)
        rest_layout.addLayout(rest_form)
        rest_layout.addWidget(self._rest_any)
        rest_btns = QHBoxLayout()
        self._rest_start_btn.clicked.connect(self._start_rest)
        self._rest_stop_btn.clicked.connect(self._stop_rest)
        rest_btns.addWidget(self._rest_start_btn)
        rest_btns.addWidget(self._rest_stop_btn)
        rest_btns.addStretch()
        rest_layout.addLayout(rest_btns)
        rest_layout.addWidget(self._rest_status)
        root.addWidget(rest_group)

        root.addStretch()

    def _resolved_host(self, input_field: QLineEdit, any_addr: QCheckBox) -> str:
        if any_addr.isChecked():
            return "0.0.0.0"  # noqa: S104  # nosec B104  # reason: explicit opt-in via checkbox
        return input_field.text().strip() or "127.0.0.1"

    def _start_tcp(self) -> None:
        if self._tcp_server is not None:
            return
        host = self._resolved_host(self._tcp_host, self._tcp_any)
        try:
            port = int(self._tcp_port.text() or "9938")
            self._tcp_server = start_autocontrol_socket_server(host, port)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Error", str(error))
            return
        self._tcp_listening = f"{host}:{port}"
        self._apply_tcp_status()
        self._tcp_start_btn.setEnabled(False)
        self._tcp_stop_btn.setEnabled(True)

    def _stop_tcp(self) -> None:
        if self._tcp_server is None:
            return
        try:
            self._tcp_server.shutdown()
            self._tcp_server.server_close()
        except OSError as error:
            QMessageBox.warning(self, "Error", str(error))
        self._tcp_server = None
        self._tcp_listening = None
        self._apply_tcp_status()
        self._tcp_start_btn.setEnabled(True)
        self._tcp_stop_btn.setEnabled(False)

    def _start_rest(self) -> None:
        if self._rest_server is not None:
            return
        host = self._resolved_host(self._rest_host, self._rest_any)
        try:
            port = int(self._rest_port.text() or "9939")
            self._rest_server = RestApiServer(host=host, port=port)
            self._rest_server.start()
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Error", str(error))
            self._rest_server = None
            return
        self._rest_listening = f"{host}:{port}"
        self._apply_rest_status()
        self._rest_start_btn.setEnabled(False)
        self._rest_stop_btn.setEnabled(True)

    def _stop_rest(self) -> None:
        if self._rest_server is None:
            return
        self._rest_server.stop()
        self._rest_server = None
        self._rest_listening = None
        self._apply_rest_status()
        self._rest_start_btn.setEnabled(True)
        self._rest_stop_btn.setEnabled(False)
