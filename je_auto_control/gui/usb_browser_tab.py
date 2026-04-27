"""Viewer-side USB device browser.

Lets a viewer point at a remote AutoControl host's REST API, list the
host's USB devices via :http:get:`/usb/devices`, and (when a WebRTC
``usb`` DataChannel is wired up — Phase 2 follow-up) issue OPEN against
a row.

This tab is **read-only by default**: clicking *Open* in this Phase 2a.1
build raises a clear "WebRTC channel not wired" message, because the
viewer-side ``UsbPassthroughClient`` needs a transport callable that
actually drives the host's ``usb`` DataChannel — that wiring is a
separate piece of work in the WebRTC viewer integration. The browse +
enumerate path works against any reachable REST server today.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


_TEST_SCHEME = "http"  # NOSONAR localhost-friendly default; users may type https://


def fetch_remote_devices(*, base_url: str,
                         token: str,
                         timeout_s: float = 5.0) -> List[Dict[str, Any]]:
    """Pure helper — call /usb/devices on a remote AutoControl REST host.

    Separated from the Qt widget so it can be unit-tested without
    instantiating PySide6.
    """
    if not base_url:
        raise ValueError("base_url is required")
    base = base_url.rstrip("/")
    if not base.startswith(("http://", "https://")):
        base = f"{_TEST_SCHEME}://{base}"
    url = f"{base}/usb/devices"
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    request = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(  # nosec B310  # reason: scheme validated above
            request, timeout=float(timeout_s),
    ) as response:
        body = json.loads(response.read().decode("utf-8"))
    devices = body.get("devices", [])
    if not isinstance(devices, list):
        raise ValueError(f"unexpected response shape: {body!r}")
    return devices


class _FetchWorker(QObject):
    """Background fetch — keeps the Qt thread responsive."""

    finished = Signal(list)
    failed = Signal(str)

    def __init__(self, *, base_url: str, token: str) -> None:
        super().__init__()
        self._base_url = base_url
        self._token = token

    def run(self) -> None:
        try:
            devices = fetch_remote_devices(
                base_url=self._base_url, token=self._token,
            )
        except (urllib.error.URLError, ValueError, OSError, TimeoutError) as error:
            self.failed.emit(str(error))
            return
        self.finished.emit(devices)


class UsbBrowserTab(TranslatableMixin, QWidget):
    """Read-only browser of a remote host's USB devices."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._url_input = QLineEdit("http://127.0.0.1:9939")
        self._token_input = QLineEdit()
        self._token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._status_label = QLabel("")
        self._table = QTableWidget(0, 5)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents,
        )
        self._fetch_thread: Optional[QThread] = None
        self._build_layout()
        self._apply_table_headers()

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        root.addWidget(self._build_target_group())
        root.addLayout(self._build_button_row())
        root.addWidget(self._status_label)
        root.addWidget(self._table, stretch=1)

    def _build_target_group(self) -> QGroupBox:
        group = self._tr(QGroupBox(), "usb_browser_target_group")
        form = QVBoxLayout(group)
        url_row = QHBoxLayout()
        url_row.addWidget(self._tr(QLabel(), "usb_browser_url"))
        url_row.addWidget(self._url_input, stretch=1)
        form.addLayout(url_row)
        token_row = QHBoxLayout()
        token_row.addWidget(self._tr(QLabel(), "usb_browser_token"))
        token_row.addWidget(self._token_input, stretch=1)
        form.addLayout(token_row)
        return group

    def _build_button_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        refresh = self._tr(QPushButton(), "usb_browser_fetch")
        refresh.clicked.connect(self._on_fetch)
        row.addWidget(refresh)
        open_btn = self._tr(QPushButton(), "usb_browser_open")
        open_btn.clicked.connect(self._on_open_selected)
        row.addWidget(open_btn)
        row.addStretch(1)
        return row

    def _apply_table_headers(self) -> None:
        self._table.setHorizontalHeaderLabels([
            _t("usb_browser_col_vid"),
            _t("usb_browser_col_pid"),
            _t("usb_browser_col_manufacturer"),
            _t("usb_browser_col_product"),
            _t("usb_browser_col_serial"),
        ])

    def _on_fetch(self) -> None:
        if self._fetch_thread is not None:
            return
        thread = QThread(self)
        worker = _FetchWorker(
            base_url=self._url_input.text().strip(),
            token=self._token_input.text().strip(),
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._apply_devices)
        worker.failed.connect(self._apply_failure)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(self._on_fetch_done)
        self._fetch_thread = thread
        self._status_label.setText(_t("usb_browser_fetching"))
        thread.start()

    def _on_fetch_done(self) -> None:
        self._fetch_thread = None

    def _apply_devices(self, devices: list) -> None:
        self._status_label.setText(
            _t("usb_browser_fetched").format(count=len(devices)),
        )
        self._table.setRowCount(len(devices))
        for row_index, device in enumerate(devices):
            cells = [
                device.get("vendor_id") or "-",
                device.get("product_id") or "-",
                device.get("manufacturer") or "",
                device.get("product") or "",
                device.get("serial") or "",
            ]
            for col_index, text in enumerate(cells):
                self._table.setItem(row_index, col_index, QTableWidgetItem(text))

    def _apply_failure(self, message: str) -> None:
        self._status_label.setText(
            _t("usb_browser_fetch_failed").format(error=message),
        )

    def _on_open_selected(self) -> None:
        rows = sorted({i.row() for i in self._table.selectedIndexes()})
        if not rows:
            QMessageBox.information(
                self, _t("usb_browser_open"),
                _t("usb_browser_open_select_first"),
            )
            return
        # Phase 2a.1 ships the host-side claim path and the
        # UsbPassthroughClient blocking API, but the viewer GUI does not
        # yet have a WebRTC `usb` DataChannel to drive. Surface that
        # honestly instead of pretending a click does something.
        QMessageBox.information(
            self, _t("usb_browser_open"),
            _t("usb_browser_open_unwired"),
        )


__all__ = ["UsbBrowserTab", "fetch_remote_devices"]
