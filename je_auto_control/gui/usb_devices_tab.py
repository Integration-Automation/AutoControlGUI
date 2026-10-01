"""USB devices tab: read-only enumeration + hotplug watcher controls."""
from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox, QHBoxLayout, QHeaderView, QLabel, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui._worker_thread import CallWorker, WorkerHandle, start_worker
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.usb.usb_devices import list_usb_devices
from je_auto_control.utils.usb.usb_watcher import (
    default_usb_watcher, hold_default_watcher, release_default_watcher,
)


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


class UsbDevicesTab(TranslatableMixin, QWidget):
    """Show currently connected USB devices via the headless enumerator."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._backend_label = QLabel("-")
        self._error_label = QLabel("")
        self._events_label = QLabel("")
        self._auto_check = QCheckBox()
        self._auto_check.toggled.connect(self._on_auto_toggled)
        self._table = QTableWidget(0, 6)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents,
        )
        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._refresh)
        self._last_seen_seq = 0
        # Enumerated off the GUI thread, first when the tab is shown: the
        # PowerShell query took ~5 s and ran at start-up for a hidden tab.
        self._list_thread: Optional[WorkerHandle] = None
        self._listed = False
        self._hold = _WatcherHold()
        self.destroyed.connect(self._hold.release)
        self._build_layout()
        self._apply_table_headers()

    def _build_layout(self) -> None:
        # The refresh command runs from the Actions menu; the tab keeps
        # only the backend labels, the auto-refresh toggle, and the table.
        root = QVBoxLayout(self)
        header = QHBoxLayout()
        header.addWidget(self._tr(QLabel(), "usb_backend_label"))
        header.addWidget(self._backend_label)
        header.addStretch(1)
        self._tr(self._auto_check, "usb_auto_refresh")
        header.addWidget(self._auto_check)
        root.addLayout(header)
        root.addWidget(self._error_label)
        root.addWidget(self._events_label)
        root.addWidget(self._table, stretch=1)

    def menu_actions(self) -> list:
        """Expose tab commands to the window-level Actions menu."""
        return [
            ("usb_refresh", self._refresh),
        ]

    def showEvent(self, event) -> None:  # noqa: N802  # reason: Qt override
        """List the devices the first time the tab is shown."""
        super().showEvent(event)
        if not self._listed:
            self._refresh()

    def _on_auto_toggled(self, on: bool) -> None:
        if on:
            self._hold.take()
            self._timer.start()
        else:
            self._timer.stop()
            self._hold.release()

    def _apply_table_headers(self) -> None:
        self._table.setHorizontalHeaderLabels([
            _t("usb_col_vid"), _t("usb_col_pid"),
            _t("usb_col_manufacturer"), _t("usb_col_product"),
            _t("usb_col_serial"), _t("usb_col_location"),
        ])

    def _refresh(self) -> None:
        if self._list_thread is not None:
            return          # one enumeration at a time; a tick during one is skipped
        self._listed = True
        self._list_thread = start_worker(
            self, CallWorker(list_usb_devices), on_done=self._apply_devices,
            on_fail=self._error_label.setText, on_thread_done=self._on_list_done)

    def _on_list_done(self) -> None:
        self._list_thread = None

    def _apply_devices(self, result) -> None:
        self._backend_label.setText(result.backend)
        self._error_label.setText(result.error or "")
        self._update_event_summary()
        self._table.setRowCount(len(result.devices))
        for row_index, device in enumerate(result.devices):
            cells = [
                device.vendor_id or "-",
                device.product_id or "-",
                device.manufacturer or "",
                device.product or "",
                device.serial or "",
                device.bus_location or "",
            ]
            for col, text in enumerate(cells):
                self._table.setItem(row_index, col, QTableWidgetItem(text))

    def _update_event_summary(self) -> None:
        watcher = default_usb_watcher()
        if not watcher.is_running:
            self._events_label.setText("")
            return
        events = watcher.recent_events(since=self._last_seen_seq, limit=10)
        if not events:
            self._events_label.setText(_t("usb_events_idle"))
            return
        self._last_seen_seq = events[-1]["seq"]
        summary_parts = [
            f"{event['kind']}: {event['device'].get('product') or '?'}"
            for event in events[-3:]
        ]
        self._events_label.setText(
            _t("usb_events_recent").format(text=" / ".join(summary_parts)),
        )


class _WatcherHold:
    """This tab's share of the default USB watcher, given back once."""

    def __init__(self) -> None:
        self.held = False

    def take(self) -> None:
        if not self.held:
            hold_default_watcher()
            self.held = True

    def release(self, *_args) -> None:
        if self.held:
            self.held = False
            release_default_watcher(background=True)


__all__ = ["UsbDevicesTab"]
