"""System diagnostics tab: run subsystem checks and display results."""
from typing import Optional

from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
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
        self._table = QTableWidget(0, 4)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch,
        )
        self._build_layout()
        self._apply_table_headers()
        self._refresh()

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        header = QHBoxLayout()
        run_btn = self._tr(QPushButton(), "diag_run")
        run_btn.clicked.connect(self._refresh)
        header.addWidget(run_btn)
        header.addStretch(1)
        root.addLayout(header)
        root.addWidget(self._summary_label)
        root.addWidget(self._table, stretch=1)

    def _apply_table_headers(self) -> None:
        self._table.setHorizontalHeaderLabels([
            _t("diag_col_name"), _t("diag_col_severity"),
            _t("diag_col_status"), _t("diag_col_detail"),
        ])

    def _refresh(self) -> None:
        report = run_diagnostics()
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
