"""AnyDesk-style USB passthrough panel.

One simple two-pane screen:

* **Left — "Share USB on this machine":** toggle sharing on/off, see the
  local USB devices, and Allow / Block each one in the ACL with a click.
  An integrity badge surfaces an ACL signature mismatch.
* **Right — "Use a USB device":** list the shareable devices over the
  in-process channel and open one (a device-descriptor read proves the
  whole protocol stack works end to end), plus browse a remote host's
  devices over REST.

The widget is a thin wrapper: every action calls the headless
:class:`UsbLoopback`, :class:`UsbAcl`, and ``list_usb_devices`` — no USB
business logic lives here. Blocking calls run on a worker thread so the
GUI stays responsive.
"""
from __future__ import annotations

from typing import Any, Callable, List, Optional

from PySide6.QtCore import QObject, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMessageBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.gui.remote_desktop._helpers import _StatusBadge
from je_auto_control.gui.usb_browser_tab import fetch_remote_devices
from je_auto_control.utils.usb.passthrough import (
    AclRule, UsbAcl, UsbLoopback, describe_descriptor, enable_usb_passthrough,
    export_acl_to_file, import_acl_from_file,
)
from je_auto_control.utils.usb.usb_devices import list_usb_devices
from je_auto_control.utils.usb.usb_watcher import default_usb_watcher


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


# Standard USB GET_DESCRIPTOR (device) request — a harmless liveness probe.
_DESC_REQUEST_TYPE = 0x80
_DESC_REQUEST = 0x06
_DESC_VALUE = 0x0100
_DESC_LENGTH = 18


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


class UsbPassthroughPanel(TranslatableMixin, QWidget):
    """Simple AnyDesk-style share + use surface for USB passthrough."""

    def __init__(self, parent: Optional[QWidget] = None, *,
                 acl: Optional[UsbAcl] = None,
                 loopback_factory: Optional[Callable[[], UsbLoopback]] = None,
                 remote_client_provider: Optional[
                     Callable[[], Optional[Any]]
                 ] = None,
                 ) -> None:
        super().__init__(parent)
        self._tr_init()
        self._acl = acl if acl is not None else UsbAcl()
        self._loopback_factory = loopback_factory or self._default_loopback
        self._remote_client_provider = (
            remote_client_provider or _default_remote_client
        )
        self._loopback: Optional[UsbLoopback] = None
        self._thread: Optional[QThread] = None
        self._host_badge = _StatusBadge()
        self._viewer_status = QLabel("")
        self._source_combo = QComboBox()
        self._auto_check = QCheckBox()
        self._auto_check.toggled.connect(self._on_auto_toggled)
        self._hotplug_timer = QTimer(self)
        self._hotplug_timer.setInterval(2000)
        self._hotplug_timer.timeout.connect(self._poll_hotplug)
        self._last_seen_seq = 0
        self._local_table = _make_table(5)
        self._shared_table = _make_table(4)
        self._remote_url = QLineEdit("http://127.0.0.1:9939")
        self._remote_token = QLineEdit()
        self._remote_token.setEchoMode(QLineEdit.EchoMode.Password)
        self._build_layout()
        self._populate_source_combo()
        self._apply_local_headers()
        self._apply_shared_headers()
        self._refresh_local_devices()
        self._refresh_host_badge()

    def _default_loopback(self) -> UsbLoopback:
        return UsbLoopback(acl=self._acl, viewer_id="gui-local")

    # --- layout ------------------------------------------------------------

    def _build_layout(self) -> None:
        # Share/ACL/use/remote-fetch commands run from the Actions menu;
        # the panel keeps only the badge, tables, inputs, and status.
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(16)
        root.addWidget(self._build_host_section(), stretch=1)
        root.addWidget(self._build_viewer_section(), stretch=1)

    def menu_actions(self) -> list:
        """Expose tab commands to the window-level Actions menu."""
        return [
            ("usb_share_enable", self._enable_sharing),
            ("usb_share_disable", self._disable_sharing),
            ("usb_share_refresh_local", self._refresh_local_devices),
            ("usb_share_allow", self._allow_selected),
            ("usb_share_block", self._block_selected),
            ("usb_share_export_acl", self._export_acl),
            ("usb_share_import_acl", self._import_acl),
            ("usb_share_fetch_shared", self._list_shared),
            ("usb_share_open_selected", self._open_selected),
            ("usb_share_remote_fetch", self._fetch_remote),
        ]

    def _build_host_section(self) -> QWidget:
        group = QGroupBox()
        self._tr(group, "usb_share_host_group", setter="setTitle")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)
        layout.addWidget(self._host_badge)
        layout.addWidget(self._tr(QLabel(), "usb_share_local_devices"))
        layout.addWidget(self._local_table, stretch=1)
        acl_row = QHBoxLayout()
        self._tr(self._auto_check, "usb_share_auto_refresh")
        acl_row.addWidget(self._auto_check)
        acl_row.addStretch(1)
        layout.addLayout(acl_row)
        return group

    def _build_viewer_section(self) -> QWidget:
        group = QGroupBox()
        self._tr(group, "usb_share_viewer_group", setter="setTitle")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)
        intro = self._tr(QLabel(), "usb_share_intro")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        source_row = QHBoxLayout()
        source_row.addWidget(self._tr(QLabel(), "usb_share_source_label"))
        source_row.addWidget(self._source_combo, stretch=1)
        layout.addLayout(source_row)
        layout.addWidget(self._shared_table, stretch=1)
        layout.addWidget(self._viewer_status)
        layout.addWidget(self._build_remote_box())
        return group

    def _build_remote_box(self) -> QWidget:
        box = QGroupBox()
        self._tr(box, "usb_share_remote_group", setter="setTitle")
        layout = QVBoxLayout(box)
        url_row = QHBoxLayout()
        url_row.addWidget(self._tr(QLabel(), "usb_share_remote_url"))
        url_row.addWidget(self._remote_url, stretch=1)
        layout.addLayout(url_row)
        token_row = QHBoxLayout()
        token_row.addWidget(self._tr(QLabel(), "usb_share_remote_token"))
        token_row.addWidget(self._remote_token, stretch=1)
        layout.addLayout(token_row)
        return box

    def _apply_local_headers(self) -> None:
        self._local_table.setHorizontalHeaderLabels([
            _t("usb_share_col_vid"), _t("usb_share_col_pid"),
            _t("usb_share_col_product"), _t("usb_share_col_serial"),
            _t("usb_share_col_policy"),
        ])

    def _apply_shared_headers(self) -> None:
        self._shared_table.setHorizontalHeaderLabels([
            _t("usb_share_col_vid"), _t("usb_share_col_pid"),
            _t("usb_share_col_product"), _t("usb_share_col_serial"),
        ])

    def _populate_source_combo(self) -> None:
        index = max(0, self._source_combo.currentIndex())
        self._source_combo.blockSignals(True)
        self._source_combo.clear()
        self._source_combo.addItem(_t("usb_share_source_local"))
        self._source_combo.addItem(_t("usb_share_source_remote"))
        self._source_combo.setCurrentIndex(index)
        self._source_combo.blockSignals(False)

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        self._populate_source_combo()
        self._apply_local_headers()
        self._apply_shared_headers()
        self._refresh_host_badge()

    # --- sharing lifecycle -------------------------------------------------

    def _enable_sharing(self) -> None:
        if self._loopback is not None:
            return
        enable_usb_passthrough(True)
        try:
            self._loopback = self._loopback_factory()
        except (RuntimeError, OSError) as error:
            enable_usb_passthrough(False)
            QMessageBox.warning(self, _t("usb_share_host_group"), str(error))
            return
        self._refresh_host_badge()

    def _disable_sharing(self) -> None:
        loop = self._loopback
        self._loopback = None
        if loop is not None:
            loop.close()
        enable_usb_passthrough(False)
        self._shared_table.setRowCount(0)
        self._refresh_host_badge()

    def _refresh_host_badge(self) -> None:
        if self._loopback is None:
            self._host_badge.set_state("stopped", _t("usb_share_sharing_off"))
        else:
            self._host_badge.set_state("running", _t("usb_share_sharing_on"))
        if not self._acl.verify_integrity():
            self._viewer_status.setText(_t("usb_share_acl_tampered"))

    # --- local devices + ACL ----------------------------------------------

    def _refresh_local_devices(self) -> None:
        result = list_usb_devices()
        devices = result.devices
        self._local_table.setRowCount(len(devices))
        for row, device in enumerate(devices):
            policy = self._acl.decide(
                vendor_id=device.vendor_id or "", product_id=device.product_id or "",
                serial=device.serial or None,
            )
            cells = [
                device.vendor_id or "-", device.product_id or "-",
                device.product or "", device.serial or "",
                _t(f"usb_share_policy_{policy}"),
            ]
            for col, text in enumerate(cells):
                self._local_table.setItem(row, col, QTableWidgetItem(text))

    def _on_auto_toggled(self, on: bool) -> None:
        watcher = default_usb_watcher()
        if on:
            watcher.start()
            self._hotplug_timer.start()
        else:
            self._hotplug_timer.stop()
            watcher.stop()

    def _poll_hotplug(self) -> None:
        watcher = default_usb_watcher()
        if not watcher.is_running:
            return
        events = watcher.recent_events(since=self._last_seen_seq, limit=20)
        if not events:
            return
        self._last_seen_seq = events[-1]["seq"]
        self._refresh_local_devices()

    def _allow_selected(self) -> None:
        self._set_policy(True)

    def _block_selected(self) -> None:
        self._set_policy(False)

    def _set_policy(self, allow: bool) -> None:
        row = _selected_row(self._local_table)
        if row is None:
            self._info(_t("usb_share_select_first"))
            return
        vid = self._cell(self._local_table, row, 0)
        pid = self._cell(self._local_table, row, 1)
        serial = self._cell(self._local_table, row, 3) or None
        self._acl.remove_rule(vendor_id=vid, product_id=pid, serial=serial)
        self._acl.add_rule(AclRule(
            vendor_id=vid, product_id=pid, serial=serial,
            label=f"gui {vid}:{pid}", allow=allow, prompt_on_open=False,
        ))
        key = "usb_share_allowed" if allow else "usb_share_blocked"
        self._viewer_status.setText(_t(key).format(vid=vid, pid=pid))
        self._refresh_local_devices()

    def _export_acl(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, _t("usb_share_export_acl"), "usb_acl_export.json",
            "JSON (*.json)",
        )
        if not path:
            return
        try:
            export_acl_to_file(self._acl, path)
        except OSError as error:
            self._viewer_status.setText(
                _t("usb_share_acl_import_failed").format(error=str(error)),
            )
            return
        self._viewer_status.setText(_t("usb_share_acl_exported"))

    def _import_acl(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, _t("usb_share_import_acl"), "", "JSON (*.json)",
        )
        if not path:
            return
        try:
            count = import_acl_from_file(self._acl, path)
        except (OSError, ValueError) as error:
            self._viewer_status.setText(
                _t("usb_share_acl_import_failed").format(error=str(error)),
            )
            return
        self._viewer_status.setText(
            _t("usb_share_acl_imported").format(count=count),
        )
        self._refresh_local_devices()

    # --- use (loopback or live WebRTC) -------------------------------------

    def _source_is_remote(self) -> bool:
        return self._source_combo.currentIndex() == 1

    def _active_use_client(self) -> Any:
        """Return the client for the selected source, or raise a friendly error.

        Both the loopback bundle and the WebRTC ``UsbChannelClient``
        expose ``list_devices`` and ``open`` with the same signatures, so
        the use actions are source-agnostic.
        """
        if self._source_is_remote():
            client = self._remote_client_provider()
            if client is None:
                raise RuntimeError(_t("usb_share_no_webrtc"))
            return client
        if self._loopback is None:
            raise RuntimeError(_t("usb_share_enable_first"))
        return self._loopback

    def _use_client_or_warn(self) -> Any:
        try:
            return self._active_use_client()
        except RuntimeError as error:
            self._info(str(error))
            return None

    def _list_shared(self) -> None:
        client = self._use_client_or_warn()
        if client is None:
            return
        self._viewer_status.setText(_t("usb_share_listing"))
        self._run_async(client.list_devices, self._apply_shared, self._fail)

    def _apply_shared(self, devices: List[dict]) -> None:
        self._viewer_status.setText(
            _t("usb_share_listed").format(count=len(devices)),
        )
        self._shared_table.setRowCount(len(devices))
        for row, device in enumerate(devices):
            cells = [
                device.get("vendor_id") or "-", device.get("product_id") or "-",
                device.get("product") or "", device.get("serial") or "",
            ]
            for col, text in enumerate(cells):
                self._shared_table.setItem(row, col, QTableWidgetItem(str(text)))

    def _open_selected(self) -> None:
        client = self._use_client_or_warn()
        if client is None:
            return
        row = _selected_row(self._shared_table)
        if row is None:
            self._info(_t("usb_share_select_first"))
            return
        vid = self._cell(self._shared_table, row, 0)
        pid = self._cell(self._shared_table, row, 1)
        serial = self._cell(self._shared_table, row, 3) or None
        self._viewer_status.setText(
            _t("usb_share_opening").format(vid=vid, pid=pid),
        )
        self._run_async(
            lambda: _probe_device(client, vid, pid, serial),
            lambda descriptor: self._opened(vid, pid, descriptor),
            self._fail,
        )

    def _opened(self, vid: str, pid: str, descriptor: bytes) -> None:
        self._viewer_status.setText(
            _t("usb_share_opened").format(
                vid=vid, pid=pid, hex=describe_descriptor(descriptor),
            ),
        )

    # --- remote browse (REST) ---------------------------------------------

    def _fetch_remote(self) -> None:
        url = self._remote_url.text().strip()
        token = self._remote_token.text().strip()
        self._viewer_status.setText(_t("usb_browser_fetching"))
        self._run_async(
            lambda: fetch_remote_devices(base_url=url, token=token),
            self._apply_shared, self._fail_remote,
        )

    def _fail_remote(self, message: str) -> None:
        self._viewer_status.setText(
            _t("usb_browser_fetch_failed").format(error=message),
        )

    def _fail(self, message: str) -> None:
        self._viewer_status.setText(
            _t("usb_share_open_failed").format(error=message),
        )

    # --- worker plumbing ---------------------------------------------------

    def _run_async(self, fn: Callable[[], Any],
                   on_done: Callable[[Any], None],
                   on_fail: Callable[[str], None]) -> None:
        if self._thread is not None:
            return
        thread = QThread(self)
        worker = _CallWorker(fn)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(on_done)
        worker.failed.connect(on_fail)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(self._on_thread_done)
        self._thread = thread
        thread.start()

    def _on_thread_done(self) -> None:
        self._thread = None

    # --- helpers -----------------------------------------------------------

    def _info(self, message: str) -> None:
        QMessageBox.information(self, _t("usb_share_viewer_group"), message)

    @staticmethod
    def _cell(table: QTableWidget, row: int, col: int) -> str:
        item = table.item(row, col)
        text = item.text() if item is not None else ""
        return "" if text == "-" else text

    def closeEvent(self, event) -> None:  # noqa: N802  # Qt override name
        self._hotplug_timer.stop()
        if self._auto_check.isChecked():
            default_usb_watcher().stop()
        self._disable_sharing()
        super().closeEvent(event)


def _make_table(columns: int) -> QTableWidget:
    table = QTableWidget(0, columns)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.horizontalHeader().setSectionResizeMode(
        QHeaderView.ResizeMode.ResizeToContents,
    )
    return table


def _selected_row(table: QTableWidget) -> Optional[int]:
    rows = sorted({i.row() for i in table.selectedIndexes()})
    return rows[0] if rows else None


def _default_remote_client() -> Optional[Any]:
    """Return the live WebRTC viewer's USB client, or None if unavailable."""
    try:
        from je_auto_control.utils.remote_desktop.registry import registry
    except ImportError:
        return None
    return registry.webrtc_usb_client()


def _probe_device(client: Any, vid: str, pid: str,
                  serial: Optional[str]) -> bytes:
    """Open the device, read its descriptor as a liveness proof, close.

    ``client`` is either a :class:`UsbLoopback` or a WebRTC
    ``UsbChannelClient`` — both expose the same ``open`` signature.
    """
    handle = client.open(vendor_id=vid, product_id=pid, serial=serial)
    try:
        return handle.control_transfer(
            bm_request_type=_DESC_REQUEST_TYPE, b_request=_DESC_REQUEST,
            w_value=_DESC_VALUE, length=_DESC_LENGTH,
        )
    finally:
        handle.close()


__all__ = ["UsbPassthroughPanel"]
