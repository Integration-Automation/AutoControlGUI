"""Device Matrix tab: run one action list across many devices in parallel.

Thin wrapper over :func:`je_auto_control.run_on_devices`. The run talks to
every device (adb, WebDriverAgent) and takes as long as the slowest one, so it
goes through the task controller: the window stays responsive, and a tab
destroyed mid-run hears nothing of the result.
"""
import json
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QLabel, QPlainTextEdit,
    QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from je_auto_control.gui._dispose import release_resources
from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.task_controller import TaskHandle, task_controller
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
            '[{"platform": "android", "serial": "emulator-5554", '
            '"app_id": "com.example.app"}]',
        )
        self._actions = QPlainTextEdit()
        # No serial needed: each device's own session is bound while it runs.
        self._actions.setPlaceholderText(
            '[["AC_android_tap", {"x": 1, "y": 2}]]',
        )
        self._parallel = QSpinBox()
        self._parallel.setRange(1, 64)
        self._parallel.setValue(4)
        self._table = QTableWidget(0, len(_COLS))
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._summary = QLabel()
        self._task: Optional[TaskHandle] = None     # one run at a time
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

    def dispose(self) -> None:
        """Release what the tab holds beyond its widgets: the command still running in the background.

        A script run is stopped; other work cannot be interrupted, so it runs to its end and its
        result is dropped. Called by ``close_tab(key, release=True)``; safe to call twice.
        """
        release_resources(self)

    def menu_actions(self) -> list:
        """Expose tab commands to the window-level Actions menu."""
        return [
            ("dm_run", self._on_run),
        ]

    def _on_run(self) -> None:
        if self._task is not None:
            return
        try:
            devices = json.loads(self._devices.toPlainText() or "[]")
            actions = json.loads(self._actions.toPlainText() or "[]")
        except ValueError as error:
            self._show_error(error)
            return
        max_parallel = self._parallel.value()
        self._summary.setText(_t("dm_running"))
        # run_on_devices takes neither a timeout nor a cancel signal, so a
        # cancelled run finishes on its own and its report is dropped.
        self._task = task_controller().submit(
            lambda _token: ac.run_on_devices(actions, devices, max_parallel=max_parallel).to_dict(),
            owner=self)
        self._task.result.connect(self._render)
        self._task.error.connect(self._show_error)
        self._task.finished.connect(self._on_run_finished)

    def _on_run_finished(self) -> None:
        self._task = None

    def _show_error(self, error: object) -> None:
        self._summary.setText(_t("dm_error").replace("{error}", str(error)))

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
