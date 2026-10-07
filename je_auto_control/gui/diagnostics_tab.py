"""System diagnostics tab: run subsystem checks and display results."""
import sys
from typing import Optional

from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QHeaderView, QLabel, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui._panel_tasks import PanelTasks, call_native
from je_auto_control.gui._task_state import TaskResult
from functools import partial
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.diagnostics.diagnostics import run_diagnostics


_SEVERITY_COLOR = {
    "info": QColor("#1e8a3a"),
    "warn": QColor("#b08400"),
    "error": QColor("#c0392b"),
}


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


class DiagnosticsTab(TranslatableMixin, QWidget):
    """Run :func:`run_diagnostics` and render the results."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._summary_label = QLabel("-")
        self._tasks = PanelTasks(self, self._summary_label)
        self._table = QTableWidget(0, 4)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch,
        )
        self._build_layout()
        self._wayland_panel = None
        from je_auto_control.linux_wayland._detect import is_wayland_session
        if sys.platform.startswith('linux') and is_wayland_session():
            from je_auto_control.gui.wayland_input_panel import WaylandInputPanel
            self._wayland_panel = WaylandInputPanel(self)
            self.layout().addWidget(self._wayland_panel)
        self._apply_table_headers()
        self._refresh()

    def _build_layout(self) -> None:
        # The run command runs from the Actions menu; the tab keeps only
        # the summary label and the results table.
        root = QVBoxLayout(self)
        root.addWidget(self._summary_label)
        root.addWidget(self._table, stretch=1)

    def menu_actions(self) -> list:
        """Expose tab commands to the window-level Actions menu."""
        actions = [
            ("diag_run", self._refresh),
        ]
        from je_auto_control.linux_wayland._detect import is_wayland_session
        if sys.platform.startswith("linux") and is_wayland_session():
            actions.extend([
                ("diag_stop_input", self._stop_input),
                ("diag_retry_input", self._retry_input),
                ('workspace_cancel_task', self._tasks.cancel),
        ])
        if self._wayland_panel is not None:
            actions.extend(self._wayland_panel.menu_actions())
        return actions

    def _stop_input(self) -> None:
        from je_auto_control.linux_wayland.libei import stop_input_control
        if hasattr(self, '_tasks'):
            self._tasks.submit(partial(call_native, stop_input_control), self._input_reset_done)
            return
        stop_input_control()
        self._refresh()

    def _retry_input(self) -> None:
        from je_auto_control.linux_wayland.libei import reset_default_backend
        if hasattr(self, '_tasks'):
            self._tasks.submit(partial(call_native, reset_default_backend), self._input_reset_done)
            return
        reset_default_backend()
        self._refresh()

    def _input_reset_done(self, _result: TaskResult) -> None:
        self._refresh()

    def _apply_table_headers(self) -> None:
        self._table.setHorizontalHeaderLabels([
            _t("diag_col_name"), _t("diag_col_severity"),
            _t("diag_col_status"), _t("diag_col_detail"),
        ])

    def _refresh(self) -> None:
        if hasattr(self, '_tasks'):
            self._tasks.submit(partial(call_native, partial(run_diagnostics, include_active=False)),
                               self._diagnostics_done)
            return
        self._render_diagnostics(run_diagnostics(include_active=False))

    def _diagnostics_done(self, result: TaskResult) -> None:
        from je_auto_control.utils.diagnostics.diagnostics import DiagnosticsReport
        if isinstance(result.value, DiagnosticsReport):
            self._render_diagnostics(result.value)

    def _render_diagnostics(self, report) -> None:
        summary = report.to_dict()
        if report.ok:
            self._summary_label.setText(_t("diag_summary_ok").format(
                count=summary["count"],
            ))
        else:
            self._summary_label.setText(_t("diag_summary_failed").format(
                failed=summary["failed"], count=summary["count"],
            ))
        self._table.setRowCount(len(report.checks))
        for row, check in enumerate(report.checks):
            cells = [
                check.name,
                check.severity,
                _t("diag_status_ok") if check.ok else _t("diag_status_fail"),
                check.detail,
            ]
            color = _SEVERITY_COLOR.get(check.severity)
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if color is not None and col == 1:
                    item.setForeground(QBrush(color))
                self._table.setItem(row, col, item)


__all__ = ["DiagnosticsTab"]
