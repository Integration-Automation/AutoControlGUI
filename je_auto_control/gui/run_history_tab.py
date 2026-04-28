"""Run History tab: browse past scheduler / trigger / hotkey fires."""
import datetime as _dt
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QTimer, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QMessageBox, QPushButton, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.gui.run_history_timeline import RunHistoryTimeline
from je_auto_control.utils.run_history.history_store import (
    SOURCE_HOTKEY, SOURCE_MANUAL, SOURCE_REST, SOURCE_SCHEDULER,
    SOURCE_TRIGGER, STATUS_ERROR, STATUS_OK, STATUS_RUNNING, RunRecord,
    default_history_store,
)

_COLUMN_COUNT = 8
_REFRESH_INTERVAL_MS = 2000
_SOURCES = (
    ("rh_source_all", None),
    ("rh_source_scheduler", SOURCE_SCHEDULER),
    ("rh_source_trigger", SOURCE_TRIGGER),
    ("rh_source_hotkey", SOURCE_HOTKEY),
    ("rh_source_manual", SOURCE_MANUAL),
    ("rh_source_rest", SOURCE_REST),
)
_STATUS_LABEL_KEYS = {
    STATUS_OK: "rh_status_ok",
    STATUS_ERROR: "rh_status_error",
    STATUS_RUNNING: "rh_status_running",
}


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


def _format_time(epoch: float) -> str:
    try:
        return _dt.datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M:%S")
    except (OSError, ValueError, OverflowError):
        return str(epoch)


def _format_duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return "-"
    if seconds < 1.0:
        return f"{int(seconds * 1000)} ms"
    return f"{seconds:.2f} s"


class RunHistoryTab(TranslatableMixin, QWidget):
    """Timeline view of every fired scheduler job / trigger / hotkey."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._records: List[RunRecord] = []
        self._filter = QComboBox()
        self._populate_filter()
        self._filter.currentIndexChanged.connect(self._refresh)
        self._table = QTableWidget(0, _COLUMN_COUNT)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._apply_table_headers()
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)
        self._count_label = QLabel()
        self._timeline = RunHistoryTimeline()
        self._timeline.run_clicked.connect(self._on_timeline_clicked)
        self._thumb_label = QLabel()
        self._thumb_label.setAlignment(Qt.AlignCenter)
        self._thumb_label.setMinimumSize(220, 160)
        self._thumb_label.setFrameShape(QFrame.StyledPanel)
        self._thumb_label.setScaledContents(False)
        self._thumb_caption = QLabel()
        self._thumb_caption.setWordWrap(True)
        self._thumb_caption.setAlignment(Qt.AlignTop)
        self._thumb_caption.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._timer = QTimer(self)
        self._timer.setInterval(_REFRESH_INTERVAL_MS)
        self._timer.timeout.connect(self._refresh)
        self._auto_refresh = True
        self._build_layout()
        self._refresh()
        self._timer.start()

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        self._apply_table_headers()
        self._repopulate_filter_labels()
        self._refresh()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh_preview()

    def _populate_filter(self) -> None:
        self._filter.blockSignals(True)
        for label_key, source_value in _SOURCES:
            self._filter.addItem(_t(label_key), source_value)
        self._filter.blockSignals(False)

    def _repopulate_filter_labels(self) -> None:
        self._filter.blockSignals(True)
        current = self._filter.currentIndex()
        for row, (label_key, _source) in enumerate(_SOURCES):
            self._filter.setItemText(row, _t(label_key))
        self._filter.setCurrentIndex(max(0, current))
        self._filter.blockSignals(False)

    def _apply_table_headers(self) -> None:
        self._table.setHorizontalHeaderLabels([
            _t("rh_col_id"), _t("rh_col_source"), _t("rh_col_target"),
            _t("rh_col_script"), _t("rh_col_started"),
            _t("rh_col_duration"), _t("rh_col_status"),
            _t("rh_col_artifact"),
        ])

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(self._tr(QLabel(), "rh_filter_label"))
        top.addWidget(self._filter)
        top.addStretch()
        refresh_btn = self._tr(QPushButton(), "rh_refresh")
        refresh_btn.clicked.connect(self._refresh)
        top.addWidget(refresh_btn)
        clear_btn = self._tr(QPushButton(), "rh_clear")
        clear_btn.clicked.connect(self._on_clear)
        top.addWidget(clear_btn)
        root.addLayout(top)

        self._tr(QLabel(), "rh_timeline_heading")
        timeline_label = self._tr(QLabel(), "rh_timeline_heading")
        root.addWidget(timeline_label)
        root.addWidget(self._timeline)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._table)
        preview = QWidget()
        preview_layout = QVBoxLayout(preview)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.addWidget(self._tr(QLabel(), "rh_preview_heading"))
        preview_layout.addWidget(self._thumb_label, stretch=1)
        preview_layout.addWidget(self._thumb_caption)
        splitter.addWidget(preview)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, stretch=1)

        self._table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        open_row = QHBoxLayout()
        self._open_artifact_btn = self._tr(QPushButton(), "rh_open_artifact")
        self._open_artifact_btn.clicked.connect(self._open_selected_artifact)
        open_row.addWidget(self._open_artifact_btn)
        open_row.addStretch()
        root.addLayout(open_row)
        root.addWidget(self._count_label)

    def _on_clear(self) -> None:
        reply = QMessageBox.question(
            self, _t("rh_clear"), _t("rh_confirm_clear"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            default_history_store.clear()
            self._refresh()

    def _refresh(self) -> None:
        source = self._filter.currentData()
        try:
            runs = default_history_store.list_runs(limit=500, source_type=source)
        except ValueError:
            runs = []
        self._records = runs
        self._table.setRowCount(len(runs))
        for row, record in enumerate(runs):
            self._set_row(row, record)
        self._count_label.setText(
            _t("rh_count_label").replace("{n}", str(len(runs))),
        )
        self._timeline.set_records(runs)
        self._refresh_preview()

    def _set_row(self, row: int, record) -> None:
        status_key = _STATUS_LABEL_KEYS.get(record.status, record.status)
        status_text = _t(status_key) if record.error_text is None \
            else f"{_t(status_key)}: {record.error_text}"
        artifact_text = record.artifact_path or "-"
        values = (
            str(record.id),
            record.source_type,
            record.source_id,
            record.script_path,
            _format_time(record.started_at),
            _format_duration(record.duration_seconds),
            status_text,
            artifact_text,
        )
        for col, text in enumerate(values):
            item = QTableWidgetItem(text)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self._table.setItem(row, col, item)

    def _selected_record(self) -> Optional[RunRecord]:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._records):
            return None
        return self._records[row]

    def _on_selection_changed(self) -> None:
        record = self._selected_record()
        self._timeline.set_highlighted(record.id if record is not None else None)
        self._refresh_preview()

    def _on_timeline_clicked(self, run_id: int) -> None:
        for row, record in enumerate(self._records):
            if record.id == run_id:
                self._table.selectRow(row)
                return

    def _refresh_preview(self) -> None:
        record = self._selected_record()
        if record is None:
            self._thumb_label.clear()
            self._thumb_label.setText(_t("rh_preview_empty"))
            self._thumb_caption.setText("")
            return
        path = record.artifact_path
        if not path:
            self._thumb_label.clear()
            self._thumb_label.setText(_t("rh_preview_no_artifact"))
        else:
            pixmap = QPixmap(path)
            if pixmap.isNull():
                self._thumb_label.clear()
                self._thumb_label.setText(_t("rh_artifact_missing"))
            else:
                self._thumb_label.setPixmap(pixmap.scaled(
                    self._thumb_label.size(), Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                ))
        caption = (
            f"#{record.id} • {record.source_type}/{record.source_id}\n"
            f"{record.script_path}\n"
            f"{_format_time(record.started_at)} • "
            f"{_format_duration(record.duration_seconds)}"
        )
        if record.error_text:
            caption += f"\n{record.error_text}"
        self._thumb_caption.setText(caption)

    def _selected_artifact_path(self) -> Optional[str]:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, _COLUMN_COUNT - 1)
        if item is None:
            return None
        text = item.text()
        if not text or text == "-":
            return None
        return text

    def _open_selected_artifact(self) -> None:
        path = self._selected_artifact_path()
        if path is None:
            QMessageBox.information(
                self, _t("rh_open_artifact"), _t("rh_no_artifact"),
            )
            return
        self._open_path(path)

    def _on_cell_double_clicked(self, row: int, column: int) -> None:
        if column != _COLUMN_COUNT - 1:
            return
        item = self._table.item(row, column)
        if item is None:
            return
        text = item.text()
        if text and text != "-":
            self._open_path(text)

    def _open_path(self, path: str) -> None:
        resolved = Path(path)
        if not resolved.exists():
            QMessageBox.warning(
                self, _t("rh_open_artifact"), _t("rh_artifact_missing"),
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(resolved)))
