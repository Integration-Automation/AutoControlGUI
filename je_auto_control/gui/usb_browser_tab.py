"""Viewer-side USB device browser.

Lets a viewer point at a remote AutoControl host's REST API, list the
host's USB devices via :http:get:`/usb/devices`, and (when a WebRTC
``usb`` DataChannel is wired up — Phase 2 follow-up) issue OPEN against
a row.

Clicking *Open* against a **localhost** target opens the device on this
machine over the in-process loopback transport and reads its descriptor
(a full protocol-stack round trip). Against a **remote** target it shows
a clear "WebRTC channel not wired" message, because driving a remote
host's ``usb`` DataChannel is a separate piece of the WebRTC viewer
integration. The browse + enumerate path works against any reachable
REST server today; for the simple share/use flow see the *USB Sharing*
panel.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional

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
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", ""})
# Standard USB GET_DESCRIPTOR (device) — a harmless liveness probe.
_DESC_REQUEST_TYPE = 0x80
_DESC_REQUEST = 0x06
_DESC_VALUE = 0x0100
_DESC_LENGTH = 18


def _is_loopback_target(base_url: str) -> bool:
    """True if ``base_url`` points at this machine (so a local open is valid)."""
    text = base_url.strip()
    if not text.startswith(("http://", "https://")):
        text = f"{_TEST_SCHEME}://{text}"
    host = urllib.parse.urlsplit(text).hostname or ""
    return host.lower() in _LOOPBACK_HOSTS


def open_local_descriptor(*, vendor_id: str, product_id: str,
                          serial: Optional[str]) -> bytes:
    """Open a device on this machine over loopback and read its descriptor.

    Headless helper (no Qt) so the local-open path is unit-testable.
    Raises ``RuntimeError`` / ``UsbClientError`` if the device can't be
    claimed (e.g. not bound to WinUSB, or denied by the ACL).
    """
    from je_auto_control.utils.usb.passthrough import UsbAcl, UsbLoopback
    # Gate on the operator's persisted ACL — opening a local device the
    # user hasn't allowed should fail closed, same as a remote claim.
    with UsbLoopback(acl=UsbAcl(), viewer_id="usb-browser") as loop:
        handle = loop.open(
            vendor_id=vendor_id, product_id=product_id, serial=serial,
        )
        try:
            return handle.control_transfer(
                bm_request_type=_DESC_REQUEST_TYPE, b_request=_DESC_REQUEST,
                w_value=_DESC_VALUE, length=_DESC_LENGTH,
            )
        finally:
            handle.close()


class _CallWorker(QObject):
    """Runs one callable off the GUI thread and reports the outcome."""

    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[[], Any]) -> None:
        super().__init__()
        self._fn = fn

    def run(self) -> None:
        try:
            result = self._fn()
        except Exception as error:  # noqa: BLE001  # pylint: disable=broad-except  # reason: surface any backend/transport error to the status line
            self.failed.emit(str(error))
            return
        self.finished.emit(result)


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
    if not base.startswith(("http://", "https://")):  # NOSONAR — scheme allowlist check, not a URL emission
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
        except (ValueError, OSError, TimeoutError) as error:  # NOSONAR — TimeoutError is not an OSError on Python 3.10; URLError already is, so it was dropped
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
        self._open_thread: Optional[QThread] = None
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
        if not _is_loopback_target(self._url_input.text()):
            # A true remote host needs the WebRTC `usb` DataChannel, which
            # the viewer GUI does not yet drive. Surface that honestly.
            QMessageBox.information(
                self, _t("usb_browser_open"),
                _t("usb_browser_open_unwired"),
            )
            return
        if self._open_thread is not None:
            return
        row = rows[0]
        vid = self._row_text(row, 0)
        pid = self._row_text(row, 1)
        serial = self._row_text(row, 4) or None
        self._start_local_open(vid, pid, serial)

    def _start_local_open(self, vid: str, pid: str,
                          serial: Optional[str]) -> None:
        thread = QThread(self)
        worker = _CallWorker(lambda: open_local_descriptor(
            vendor_id=vid, product_id=pid, serial=serial,
        ))
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(
            lambda descriptor: self._on_local_opened(vid, pid, descriptor),
        )
        worker.failed.connect(self._apply_failure)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(self._on_open_done)
        self._open_thread = thread
        thread.start()

    def _on_open_done(self) -> None:
        self._open_thread = None

    def _on_local_opened(self, vid: str, pid: str, descriptor: bytes) -> None:
        self._status_label.setText(
            _t("usb_browser_open_loopback").format(
                vid=vid, pid=pid, hex=descriptor.hex() or "(empty)",
            ),
        )

    def _row_text(self, row: int, col: int) -> str:
        item = self._table.item(row, col)
        text = item.text() if item is not None else ""
        return "" if text == "-" else text


__all__ = ["UsbBrowserTab", "fetch_remote_devices"]
