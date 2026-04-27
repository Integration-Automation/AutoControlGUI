"""WebRTC inspector tab: live summary + recent stat samples."""
from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.remote_desktop.webrtc_inspector import (
    default_webrtc_inspector,
)


_REFRESH_MS = 1000
_RECENT_N = 30
_METRIC_KEYS = ("rtt_ms", "fps", "bitrate_kbps",
                "packet_loss_pct", "jitter_ms")


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


class InspectorTab(TranslatableMixin, QWidget):
    """Read-only view over :data:`default_webrtc_inspector`."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._summary_label = QLabel()
        self._metric_labels: dict = {}
        self._table = QTableWidget(0, 6)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents,
        )
        self._build_layout()
        self._apply_table_headers()
        self._refresh()
        self._timer = QTimer(self)
        self._timer.setInterval(_REFRESH_MS)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        root.addWidget(self._summary_label)
        root.addWidget(self._build_metrics_group())
        root.addLayout(self._build_button_row())
        root.addWidget(self._table, stretch=1)

    def _build_metrics_group(self) -> QGroupBox:
        group = self._tr(QGroupBox(), "inspector_metrics_group")
        form = QFormLayout(group)
        for key in _METRIC_KEYS:
            label_widget = self._tr(QLabel(), f"inspector_metric_{key}")
            value_widget = QLabel("-")
            self._metric_labels[key] = value_widget
            form.addRow(label_widget, value_widget)
        return group

    def _build_button_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        for key, handler in (
            ("inspector_refresh", self._refresh),
            ("inspector_reset", self._reset),
        ):
            btn = self._tr(QPushButton(), key)
            btn.clicked.connect(handler)
            row.addWidget(btn)
        row.addStretch(1)
        return row

    def _apply_table_headers(self) -> None:
        self._table.setHorizontalHeaderLabels([
            _t("inspector_col_age"), _t("inspector_metric_rtt_ms"),
            _t("inspector_metric_fps"), _t("inspector_metric_bitrate_kbps"),
            _t("inspector_metric_packet_loss_pct"),
            _t("inspector_metric_jitter_ms"),
        ])

    def _refresh(self) -> None:
        inspector = default_webrtc_inspector()
        summary = inspector.summary()
        self._summary_label.setText(_t("inspector_summary_text").format(
            count=summary["sample_count"],
            window=summary["window_seconds"],
        ))
        for key in _METRIC_KEYS:
            stats = summary["metrics"].get(key, {}) or {}
            self._metric_labels[key].setText(_format_metric_row(stats))
        recent = inspector.recent(_RECENT_N)
        self._table.setRowCount(len(recent))
        for row_index, sample in enumerate(recent):
            self._table.setItem(
                row_index, 0,
                QTableWidgetItem(f"{sample.get('age_seconds', 0.0):.1f}s"),
            )
            for col, key in enumerate(_METRIC_KEYS, start=1):
                value = sample.get(key)
                text = "-" if value is None else f"{value:.2f}"
                self._table.setItem(row_index, col, QTableWidgetItem(text))

    def _reset(self) -> None:
        default_webrtc_inspector().reset()
        self._refresh()


def _format_metric_row(stats: dict) -> str:
    if not stats or stats.get("last") is None:
        return "-"
    return (f"last={stats['last']:.2f} "
            f"avg={stats['avg']:.2f} "
            f"min={stats['min']:.2f} "
            f"max={stats['max']:.2f} "
            f"p95={stats['p95']:.2f}")


__all__ = ["InspectorTab"]
