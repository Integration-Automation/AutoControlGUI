"""Accessibility Audit tab: surface a11y / i18n defects from the live tree.

Thin wrapper over :func:`je_auto_control.run_audit` and
:func:`je_auto_control.contrast_ratio`.
"""
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QLabel, QLineEdit,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
import je_auto_control as ac

_COLS = ("audit_col_kind", "audit_col_severity", "audit_col_target",
         "audit_col_message")


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


def _ints(raw: str):
    return [int(p.strip()) for p in raw.split(",") if p.strip()]


class A11yAuditTab(TranslatableMixin, QWidget):
    """Run the accessibility / i18n audit and render the issue list."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._app = QLineEdit()
        self._fg = QLineEdit()
        self._fg.setPlaceholderText("0, 0, 0")
        self._bg = QLineEdit()
        self._bg.setPlaceholderText("255, 255, 255")
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
        # Audit/contrast commands run from the Actions menu; the tab keeps
        # only the inputs, the issue table, and the summary line.
        root = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel(_t("audit_app")))
        row.addWidget(self._app, stretch=1)
        root.addLayout(row)
        crow = QHBoxLayout()
        crow.addWidget(QLabel(_t("audit_contrast_label")))
        crow.addWidget(self._fg)
        crow.addWidget(self._bg)
        root.addLayout(crow)
        root.addWidget(self._table, stretch=1)
        root.addWidget(self._summary)

    def menu_actions(self) -> list:
        """Expose tab commands to the window-level Actions menu."""
        return [
            ("audit_run", self._on_run),
            ("audit_contrast_run", self._on_contrast),
        ]

    def _on_run(self) -> None:
        app = self._app.text().strip() or None
        try:
            report = ac.run_audit(app_name=app)
        except (RuntimeError, OSError, ValueError) as error:
            self._summary.setText(str(error))
            return
        self._render(report.to_dict())

    def _render(self, report: dict) -> None:
        issues = report["issues"]
        self._table.setRowCount(len(issues))
        for row, issue in enumerate(issues):
            values = (issue["kind"], issue["severity"], issue["target"],
                      issue["message"])
            for col, text in enumerate(values):
                item = QTableWidgetItem(str(text))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self._table.setItem(row, col, item)
        self._summary.setText(
            _t("audit_summary")
            .replace("{errors}", str(report["error_count"]))
            .replace("{warnings}", str(report["warning_count"])),
        )

    def _on_contrast(self) -> None:
        try:
            ratio = ac.contrast_ratio(_ints(self._fg.text()),
                                      _ints(self._bg.text()))
        except (ValueError, IndexError) as error:
            self._summary.setText(str(error))
            return
        verdict = "PASS" if ratio >= 4.5 else "FAIL"
        self._summary.setText(f"contrast {ratio:.2f}:1 — AA {verdict}")
