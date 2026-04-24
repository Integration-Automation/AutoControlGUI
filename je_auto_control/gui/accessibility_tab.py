"""Accessibility tab: browse the OS UI tree and click elements by role/name."""
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.accessibility.accessibility_api import (
    click_accessibility_element, list_accessibility_elements,
)
from je_auto_control.utils.accessibility.element import (
    AccessibilityNotAvailableError,
)

_COLUMN_COUNT = 5


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


class AccessibilityTab(TranslatableMixin, QWidget):
    """Discover GUI elements via UIA / AX and click them headlessly."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._app_filter = QLineEdit()
        self._name_filter = QLineEdit()
        self._table = QTableWidget(0, _COLUMN_COUNT)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.verticalHeader().setVisible(False)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)
        self._status = QLabel()
        self._apply_table_headers()
        self._build_layout()

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        self._apply_table_headers()
        self._app_filter.setPlaceholderText(_t("a11y_app_placeholder"))
        self._name_filter.setPlaceholderText(_t("a11y_name_placeholder"))

    def _apply_table_headers(self) -> None:
        self._table.setHorizontalHeaderLabels([
            _t("a11y_col_app"), _t("a11y_col_role"),
            _t("a11y_col_name"), _t("a11y_col_bounds"),
            _t("a11y_col_center"),
        ])

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(self._tr(QLabel(), "a11y_app_label"))
        self._app_filter.setPlaceholderText(_t("a11y_app_placeholder"))
        row.addWidget(self._app_filter, stretch=1)
        row.addWidget(self._tr(QLabel(), "a11y_name_label"))
        self._name_filter.setPlaceholderText(_t("a11y_name_placeholder"))
        row.addWidget(self._name_filter, stretch=1)
        refresh = self._tr(QPushButton(), "a11y_refresh")
        refresh.clicked.connect(self._refresh)
        row.addWidget(refresh)
        root.addLayout(row)
        root.addWidget(self._table, stretch=1)
        action_row = QHBoxLayout()
        click_btn = self._tr(QPushButton(), "a11y_click_selected")
        click_btn.clicked.connect(self._click_selected)
        action_row.addWidget(click_btn)
        action_row.addStretch()
        root.addLayout(action_row)
        root.addWidget(self._status)

    def _refresh(self) -> None:
        app = self._app_filter.text().strip() or None
        try:
            elements = list_accessibility_elements(app_name=app)
        except AccessibilityNotAvailableError as error:
            self._status.setText(str(error))
            self._table.setRowCount(0)
            return
        name_filter = self._name_filter.text().strip().lower()
        if name_filter:
            elements = [e for e in elements
                        if name_filter in e.name.lower()]
        self._populate(elements)
        self._status.setText(
            _t("a11y_count_label").replace("{n}", str(len(elements))),
        )

    def _populate(self, elements) -> None:
        self._table.setRowCount(len(elements))
        for row, element in enumerate(elements):
            values = (
                element.app_name, element.role, element.name,
                f"({element.bounds[0]},{element.bounds[1]}) "
                f"{element.bounds[2]}x{element.bounds[3]}",
                f"{element.center[0]},{element.center[1]}",
            )
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self._table.setItem(row, col, item)

    def _click_selected(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            self._status.setText(_t("a11y_no_selection"))
            return
        app = self._table.item(row, 0).text() or None
        role = self._table.item(row, 1).text() or None
        name = self._table.item(row, 2).text() or None
        try:
            ok = click_accessibility_element(
                name=name, role=role, app_name=app,
            )
        except AccessibilityNotAvailableError as error:
            QMessageBox.warning(self, _t("a11y_click_selected"), str(error))
            return
        if not ok:
            self._status.setText(_t("a11y_click_not_found"))
