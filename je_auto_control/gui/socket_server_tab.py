"""Socket + REST server control panel."""
from typing import Optional

from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QCheckBox, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QVBoxLayout, QWidget,
)

from je_auto_control.utils.rest_api.rest_server import RestApiServer
from je_auto_control.utils.socket_server.auto_control_socket_server import (
    start_autocontrol_socket_server,
)


class SocketServerTab(QWidget):
    """Start / stop the TCP socket server and the REST API server."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tcp_server = None
        self._rest_server: Optional[RestApiServer] = None
        self._tcp_host = QLineEdit("127.0.0.1")
        self._tcp_port = QLineEdit("9938")
        self._tcp_port.setValidator(QIntValidator(1, 65535))
        self._tcp_any = QCheckBox("Bind TCP to 0.0.0.0 (exposes to network)")
        self._tcp_status = QLabel("TCP stopped")
        self._tcp_start_btn = QPushButton("Start TCP")
        self._tcp_stop_btn = QPushButton("Stop TCP")
        self._tcp_stop_btn.setEnabled(False)

        self._rest_host = QLineEdit("127.0.0.1")
        self._rest_port = QLineEdit("9939")
        self._rest_port.setValidator(QIntValidator(1, 65535))
        self._rest_any = QCheckBox("Bind REST to 0.0.0.0 (exposes to network)")
        self._rest_status = QLabel("REST stopped")
        self._rest_start_btn = QPushButton("Start REST")
        self._rest_stop_btn = QPushButton("Stop REST")
        self._rest_stop_btn.setEnabled(False)

        self._build_layout()

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)

        tcp_group = QGroupBox("TCP socket server")
        tcp_layout = QVBoxLayout(tcp_group)
        tcp_form = QHBoxLayout()
        tcp_form.addWidget(QLabel("Host:"))
        tcp_form.addWidget(self._tcp_host)
        tcp_form.addWidget(QLabel("Port:"))
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

        rest_group = QGroupBox("REST API server")
        rest_layout = QVBoxLayout(rest_group)
        rest_form = QHBoxLayout()
        rest_form.addWidget(QLabel("Host:"))
        rest_form.addWidget(self._rest_host)
        rest_form.addWidget(QLabel("Port:"))
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
        self._tcp_status.setText(f"Listening on {host}:{port}")
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
        self._tcp_status.setText("TCP stopped")
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
        self._rest_status.setText(f"Listening on {host}:{port}")
        self._rest_start_btn.setEnabled(False)
        self._rest_stop_btn.setEnabled(True)

    def _stop_rest(self) -> None:
        if self._rest_server is None:
            return
        self._rest_server.stop()
        self._rest_server = None
        self._rest_status.setText("REST stopped")
        self._rest_start_btn.setEnabled(True)
        self._rest_stop_btn.setEnabled(False)
