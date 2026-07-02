"""Device Matrix tab: run one action list across many devices in parallel.

Thin wrapper over :func:`je_auto_control.run_on_devices`.
"""
import json
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QLabel, QPlainTextEdit,
    QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
import je_auto_control as ac

_COLS = ("dm_col_device", "dm_col_platform", "dm_col_result", "dm_col_time",
         "dm_col_error")


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


class DeviceMatrixTab(TranslatableMixin, QWidget):
    """Edit a device list + action list, run in parallel, show results."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._devices = QPlainTextEdit()
        self._devices.setPlaceholderText(
            '[{"platform": "android", "serial": "emulator-5554"}]',
        )
        self._actions = QPlainTextEdit()
        self._actions.setPlaceholderText(
            '[["AC_android_tap", {"x": 1, "y": 2, '
            '"serial": "${device.serial}"}]]',
        )
        self._parallel = QSpinBox()
        self._parallel.setRange(1, 64)
        self._parallel.setValue(4)
        self._table = QTableWidget(0, len(_COLS))
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._summary = QLabel()
        self._apply_headers()
        self._build_layout()

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        self._apply_headers()

    def _apply_headers(self) -> None:
        self._table.setHorizontalHeaderLabels([_t(k) for k in _COLS])

    def _build_layout(self) -> None:
        # The run command runs from the Actions menu; the tab keeps only
        # the device/action editors, the result table, and the summary.
        root = QVBoxLayout(self)
        root.addWidget(QLabel(_t("dm_devices")))
        root.addWidget(self._devices)
        root.addWidget(QLabel(_t("dm_actions")))
        root.addWidget(self._actions)
        row = QHBoxLayout()
        row.addWidget(QLabel(_t("dm_parallel")))
        row.addWidget(self._parallel)
        row.addStretch()
        root.addLayout(row)
        root.addWidget(self._table, stretch=1)
        root.addWidget(self._summary)

    def menu_actions(self) -> list:
        """Expose tab commands to the window-level Actions menu."""
        return [
            ("dm_run", self._on_run),
        ]

    def _on_run(self) -> None:
        try:
            devices = json.loads(self._devices.toPlainText() or "[]")
            actions = json.loads(self._actions.toPlainText() or "[]")
            report = ac.run_on_devices(
                actions, devices, max_parallel=self._parallel.value(),
            )
        except (ValueError, RuntimeError) as error:
            self._summary.setText(_t("dm_error").replace("{error}", str(error)))
            return
        self._render(report.to_dict())

    def _render(self, report: dict) -> None:
        results = report["results"]
        self._table.setRowCount(len(results))
        for row, res in enumerate(results):
            values = (res["device_id"], res["platform"],
                      "OK" if res["success"] else "FAIL",
                      f"{res['duration_s']:.2f}s", res.get("error") or "")
            for col, text in enumerate(values):
                item = QTableWidgetItem(str(text))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self._table.setItem(row, col, item)
        self._summary.setText(
            _t("dm_summary")
            .replace("{passed}", str(report["passed"]))
            .replace("{failed}", str(report["failed"]))
            .replace("{total}", str(report["total"])),
        )
