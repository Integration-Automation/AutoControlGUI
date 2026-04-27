"""Audit log tab: browse and verify the tamper-evident chain."""
from datetime import datetime
from typing import List, Optional, Sequence

from PySide6.QtWidgets import (
    QComboBox, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.remote_desktop.audit_log import default_audit_log


_ALL_SENTINEL = "(all)"
# Pinned at the top of the dropdown so operators can jump straight to
# them even on a fresh DB where they haven't been recorded yet.
_PINNED_PRESETS = (
    "rest_api",
    "usb_open_allowed",
    "usb_open_denied",
    "usb_open_rejected_max_claims",
    "usb_open_backend_error",
    "usb_close",
)


def build_event_type_choices(observed: Sequence[str]) -> List[str]:
    """Return the dropdown values: all-sentinel + pinned presets +
    any other event types observed in the log, deduped & ordered.
    """
    choices: List[str] = [_ALL_SENTINEL]
    seen = {_ALL_SENTINEL}
    for preset in _PINNED_PRESETS:
        if preset not in seen:
            choices.append(preset)
            seen.add(preset)
    for value in observed:
        if value and value not in seen:
            choices.append(value)
            seen.add(value)
    return choices


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


class AuditLogTab(TranslatableMixin, QWidget):
    """Browse the audit log + run chain integrity verification."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._type_filter = QComboBox()
        self._type_filter.setEditable(True)
        self._type_filter.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._host_filter = QLineEdit()
        self._limit_input = QSpinBox()
        self._limit_input.setRange(1, 5000)
        self._limit_input.setValue(200)
        self._table = QTableWidget(0, 5)
        self._table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Stretch,
        )
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._verify_status = QLabel()
        self._build_layout()
        self._refresh()

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        root.addWidget(self._build_filter_group())
        root.addWidget(self._table, stretch=1)
        root.addLayout(self._build_button_row())
        root.addWidget(self._verify_status)

    def _build_filter_group(self) -> QGroupBox:
        group = self._tr(QGroupBox(), "audit_filter_group")
        row = QHBoxLayout(group)
        row.addWidget(self._tr(QLabel(), "audit_filter_type"))
        row.addWidget(self._type_filter)
        row.addWidget(self._tr(QLabel(), "audit_filter_host"))
        row.addWidget(self._host_filter)
        row.addWidget(self._tr(QLabel(), "audit_filter_limit"))
        row.addWidget(self._limit_input)
        return group

    def _build_button_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        for key, handler in (
            ("audit_refresh", self._refresh),
            ("audit_verify", self._verify),
            ("audit_clear", self._clear),
        ):
            btn = self._tr(QPushButton(), key)
            btn.clicked.connect(handler)
            row.addWidget(btn)
        row.addStretch(1)
        return row

    def _refresh(self) -> None:
        self._apply_table_headers()
        # Pull a wide window so the dropdown reflects everything the user
        # might want to filter on. Cheap — query() caps internally.
        all_rows = default_audit_log().query(limit=5000)
        self._sync_event_type_dropdown(all_rows)
        event_type = self._current_event_type_filter()
        rows = default_audit_log().query(
            event_type=event_type,
            host_id=self._host_filter.text().strip() or None,
            limit=int(self._limit_input.value()),
        )
        self._table.setRowCount(len(rows))
        for row_index, entry in enumerate(rows):
            for col_index, text in enumerate(_format_row(entry)):
                self._table.setItem(
                    row_index, col_index, QTableWidgetItem(text),
                )

    def _sync_event_type_dropdown(self, all_rows: List[dict]) -> None:
        observed = [r.get("event_type", "") for r in all_rows]
        choices = build_event_type_choices(observed)
        current = self._type_filter.currentText()
        self._type_filter.blockSignals(True)
        self._type_filter.clear()
        self._type_filter.addItems(choices)
        # Restore previous selection if still valid; otherwise default
        # to the all-sentinel.
        if current and current in choices:
            self._type_filter.setCurrentText(current)
        else:
            self._type_filter.setCurrentIndex(0)
        self._type_filter.blockSignals(False)

    def _current_event_type_filter(self) -> Optional[str]:
        text = self._type_filter.currentText().strip()
        if not text or text == _ALL_SENTINEL:
            return None
        return text

    def _verify(self) -> None:
        result = default_audit_log().verify_chain()
        if result.ok:
            self._verify_status.setText(
                _t("audit_verify_ok").format(total=result.total_rows)
            )
        else:
            self._verify_status.setText(
                _t("audit_verify_broken").format(
                    row_id=result.broken_at_id, total=result.total_rows,
                )
            )

    def _clear(self) -> None:
        confirm = QMessageBox.question(
            self, _t("audit_clear"), _t("audit_clear_confirm"),
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        deleted = default_audit_log().clear()
        self._verify_status.setText(
            _t("audit_clear_done").format(count=deleted),
        )
        self._refresh()

    def _apply_table_headers(self) -> None:
        self._table.setHorizontalHeaderLabels([
            _t("audit_col_ts"), _t("audit_col_type"),
            _t("audit_col_host"), _t("audit_col_viewer"),
            _t("audit_col_detail"),
        ])


def _format_row(entry: dict) -> List[str]:
    ts = entry.get("ts", "")
    try:
        ts = datetime.fromisoformat(ts).astimezone().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    except (TypeError, ValueError):
        pass
    return [
        ts,
        entry.get("event_type", ""),
        (entry.get("host_id") or "")[:32],
        (entry.get("viewer_id") or "")[:32],
        entry.get("detail") or "",
    ]


__all__ = ["AuditLogTab"]
