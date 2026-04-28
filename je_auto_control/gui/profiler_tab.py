"""Profiler tab: visualise per-action wall-clock hot spots."""
from typing import List, Optional

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QProgressBar,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.profiler import default_profiler
from je_auto_control.utils.profiler.profiler import ActionStats

_REFRESH_INTERVAL_MS = 1000
_COLUMN_COUNT = 7


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


def _ms(seconds: float) -> str:
    if seconds <= 0:
        return "0 ms"
    if seconds < 1.0:
        return f"{seconds * 1000:.1f} ms"
    return f"{seconds:.3f} s"


class ProfilerTab(TranslatableMixin, QWidget):
    """Hot-spot table backed by :data:`default_profiler`."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._table = QTableWidget(0, _COLUMN_COUNT)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._apply_table_headers()
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)
        self._totalbar = QProgressBar()
        self._totalbar.setRange(0, 100)
        self._totalbar.setTextVisible(True)
        self._status = QLabel()
        self._build_layout()
        self._timer = QTimer(self)
        self._timer.setInterval(_REFRESH_INTERVAL_MS)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()
        self._refresh()

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        self._apply_table_headers()
        self._refresh()

    def _apply_table_headers(self) -> None:
        self._table.setHorizontalHeaderLabels([
            _t("prof_col_name"), _t("prof_col_calls"),
            _t("prof_col_total"), _t("prof_col_avg"),
            _t("prof_col_min"), _t("prof_col_max"),
            _t("prof_col_share"),
        ])

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        controls = QHBoxLayout()
        self._enable_btn = self._tr(QPushButton(), "prof_enable")
        self._enable_btn.clicked.connect(self._toggle_enable)
        controls.addWidget(self._enable_btn)
        reset_btn = self._tr(QPushButton(), "prof_reset")
        reset_btn.clicked.connect(self._on_reset)
        controls.addWidget(reset_btn)
        refresh_btn = self._tr(QPushButton(), "prof_refresh")
        refresh_btn.clicked.connect(self._refresh)
        controls.addWidget(refresh_btn)
        controls.addStretch()
        root.addLayout(controls)
        root.addWidget(self._table, stretch=1)
        root.addWidget(self._totalbar)
        root.addWidget(self._status)

    def _toggle_enable(self) -> None:
        if default_profiler.enabled:
            default_profiler.disable()
        else:
            default_profiler.enable()
        self._refresh()

    def _on_reset(self) -> None:
        default_profiler.reset()
        self._refresh()

    def _refresh(self) -> None:
        rows: List[ActionStats] = default_profiler.stats()
        self._table.setRowCount(len(rows))
        total_seconds = sum(r.total_seconds for r in rows)
        for index, row in enumerate(rows):
            share = 0.0 if total_seconds <= 0 else row.total_seconds / total_seconds
            self._set_row(index, row, share)
        self._totalbar.setValue(min(100, int(total_seconds * 1000) % 101))
        if rows:
            self._totalbar.setFormat(
                _t("prof_total_label").replace("{n}", str(len(rows)))
                + f"  •  {_ms(total_seconds)}",
            )
        else:
            self._totalbar.setFormat(_t("prof_total_empty"))
        running_text = _t("prof_running") if default_profiler.enabled \
            else _t("prof_paused")
        self._status.setText(running_text)
        self._enable_btn.setText(
            _t("prof_disable") if default_profiler.enabled
            else _t("prof_enable"),
        )

    def _set_row(self, row: int, stats: ActionStats, share: float) -> None:
        values = (
            stats.name,
            str(stats.calls),
            _ms(stats.total_seconds),
            _ms(stats.average_seconds),
            _ms(stats.min_seconds),
            _ms(stats.max_seconds),
            f"{share * 100:.1f}%",
        )
        for col, text in enumerate(values):
            item = QTableWidgetItem(text)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self._table.setItem(row, col, item)
