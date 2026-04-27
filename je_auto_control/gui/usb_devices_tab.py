"""USB devices tab: read-only enumeration + hotplug watcher controls."""
from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.usb.usb_devices import list_usb_devices
from je_auto_control.utils.usb.usb_watcher import default_usb_watcher


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
        self._build_layout()
        self._apply_table_headers()
        self._refresh()

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        header = QHBoxLayout()
        header.addWidget(self._tr(QLabel(), "usb_backend_label"))
        header.addWidget(self._backend_label)
        header.addStretch(1)
        self._tr(self._auto_check, "usb_auto_refresh")
        header.addWidget(self._auto_check)
        refresh = self._tr(QPushButton(), "usb_refresh")
        refresh.clicked.connect(self._refresh)
        header.addWidget(refresh)
        root.addLayout(header)
        root.addWidget(self._error_label)
        root.addWidget(self._events_label)
        root.addWidget(self._table, stretch=1)

    def _on_auto_toggled(self, on: bool) -> None:
        watcher = default_usb_watcher()
        if on:
            watcher.start()
            self._timer.start()
        else:
            self._timer.stop()
            watcher.stop()

    def _apply_table_headers(self) -> None:
        self._table.setHorizontalHeaderLabels([
            _t("usb_col_vid"), _t("usb_col_pid"),
            _t("usb_col_manufacturer"), _t("usb_col_product"),
            _t("usb_col_serial"), _t("usb_col_location"),
        ])

    def _refresh(self) -> None:
        result = list_usb_devices()
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


__all__ = ["UsbDevicesTab"]
