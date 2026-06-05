"""Data Sources tab: preview rows loaded by the headless data-source layer.

Thin wrapper over :func:`je_auto_control.load_rows` — the widget only
builds a source spec dict from the form and renders the returned rows.
"""
import json
from typing import Any, Dict, List, Optional

from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.data_source import data_source_kinds, load_rows


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


class DataSourceTab(TranslatableMixin, QWidget):
    """Build a data-source spec, load rows, and show them in a table."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._kind = QComboBox()
        self._kind.addItems(data_source_kinds())
        self._kind.currentTextChanged.connect(self._sync_visibility)
        self._path = QLineEdit()
        self._query = QLineEdit()
        self._inline = QPlainTextEdit()
        self._inline.setPlaceholderText('[{"user": "alice"}, {"user": "bob"}]')
        self._limit = QSpinBox()
        self._limit.setRange(0, 100000)
        self._table = QTableWidget(0, 0)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._status = QLabel()
        self._build_layout()
        self._sync_visibility(self._kind.currentText())

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        row1 = QHBoxLayout()
        row1.addWidget(QLabel(_t("ds_kind")))
        row1.addWidget(self._kind)
        row1.addStretch()
        root.addLayout(row1)

        self._path_row = QHBoxLayout()
        self._path_label = QLabel(_t("ds_path"))
        self._path_row.addWidget(self._path_label)
        self._path_row.addWidget(self._path, stretch=1)
        self._browse_btn = self._tr(QPushButton(), "ds_browse")
        self._browse_btn.clicked.connect(self._on_browse)
        self._path_row.addWidget(self._browse_btn)
        root.addLayout(self._path_row)

        self._query_label = QLabel(_t("ds_query"))
        root.addWidget(self._query_label)
        root.addWidget(self._query)

        self._inline_label = QLabel(_t("ds_inline"))
        root.addWidget(self._inline_label)
        root.addWidget(self._inline)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel(_t("ds_limit")))
        row2.addWidget(self._limit)
        load_btn = self._tr(QPushButton(), "ds_load")
        load_btn.clicked.connect(self._on_load)
        row2.addWidget(load_btn)
        row2.addStretch()
        root.addLayout(row2)

        root.addWidget(self._table, stretch=1)
        root.addWidget(self._status)

    def _sync_visibility(self, kind: str) -> None:
        is_file = kind in ("csv", "json", "sqlite", "excel")
        for widget in (self._path_label, self._path, self._browse_btn):
            widget.setVisible(is_file)
        self._query_label.setVisible(kind == "sqlite")
        self._query.setVisible(kind == "sqlite")
        self._inline_label.setVisible(kind == "inline")
        self._inline.setVisible(kind == "inline")

    def _on_browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, _t("ds_browse"))
        if path:
            self._path.setText(path)

    def _build_source(self) -> Dict[str, Any]:
        kind = self._kind.currentText()
        if kind == "inline":
            return {"kind": "inline", "rows": json.loads(self._inline.toPlainText() or "[]")}
        source: Dict[str, Any] = {"kind": kind, "path": self._path.text().strip()}
        if kind == "sqlite":
            source["query"] = self._query.text().strip()
        return source

    def _on_load(self) -> None:
        try:
            limit = self._limit.value() or None
            rows = load_rows(self._build_source(), limit=limit)
        except (ValueError, OSError, RuntimeError) as error:
            self._status.setText(_t("ds_error").replace("{error}", str(error)))
            return
        self._render_rows(rows)
        self._status.setText(_t("ds_row_count").replace("{n}", str(len(rows))))

    def _render_rows(self, rows: List[Dict[str, Any]]) -> None:
        columns: List[str] = []
        for row in rows:
            for key in row:
                if key not in columns:
                    columns.append(key)
        self._table.setColumnCount(len(columns))
        self._table.setHorizontalHeaderLabels(columns)
        self._table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, key in enumerate(columns):
                self._table.setItem(
                    r, c, QTableWidgetItem(str(row.get(key, ""))),
                )
