"""Accessibility tab: browse the OS UI tree and click elements by role/name.

The three commands run off the GUI thread (:class:`~je_auto_control.gui._tab_task.TabTask`):
a desktop listing is hundreds of cross-process calls, and the tree being read
includes this window, which can only answer while its own thread is free. The
backend gives each thread its own automation object, so the worker is safe.
"""
import functools
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from je_auto_control.gui._dispose import release_resources
from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui._tab_task import TabTask
from je_auto_control.gui._qt_typed import filled_item
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.accessibility.accessibility_api import (
    click_accessibility_element, focused_accessibility_element,
    list_accessibility_elements,
)
from je_auto_control.utils.accessibility.element import (
    AccessibilityElement, AccessibilityNotAvailableError,
)

_COLUMN_COUNT = 5
_LIST, _FOCUSED, _CLICK = "list", "focused", "click"


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


def _list_matching(app: Optional[str], window: Optional[str], name_filter: str) -> List[AccessibilityElement]:
    """Worker thread: list the elements and keep those whose name contains ``name_filter``."""
    # Scoping to one window is not just a filter: the desktop tree is orders
    # of magnitude larger, so this is both faster and less ambiguous than
    # listing everything and filtering by name.
    elements = list_accessibility_elements(app_name=app, window_title=window)
    if name_filter:
        elements = [element for element in elements if name_filter in element.name.lower()]
    return elements


def _focused(app: Optional[str]) -> List[AccessibilityElement]:
    """Worker thread: the focused element as a list of none or one."""
    element = focused_accessibility_element(app_name=app)
    return [] if element is None else [element]


def _click(name: Optional[str], role: Optional[str], app: Optional[str]) -> bool:
    """Worker thread: click the element; whether one matched."""
    return bool(click_accessibility_element(name=name, role=role, app_name=app))


class AccessibilityTab(TranslatableMixin, QWidget):
    """Discover GUI elements via UIA / AX and click them headlessly."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._app_filter = QLineEdit()
        self._window_filter = QLineEdit()
        self._name_filter = QLineEdit()
        self._table = QTableWidget(0, _COLUMN_COUNT)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self._status = QLabel()
        self._task = TabTask(self)          # one command at a time, off the GUI thread
        self._task.result.connect(self._on_result)
        self._task.error.connect(self._on_error)
        self._apply_table_headers()
        self._build_layout()

    def dispose(self) -> None:
        """Release what the tab holds beyond its widgets: the command still running, whose answer is dropped.

        Called by ``close_tab(key, release=True)`` before the widget is deleted; safe to call twice.
        """
        release_resources(self)

    def _start(self, tag: str, work) -> None:
        """Run ``work`` off the GUI thread as the command ``tag``; say so, or that one is still running."""
        self._task.start(work, tag=tag)     # False while busy: the status below is true either way
        self._status.setText(_t("task_running"))

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        self._apply_table_headers()
        self._app_filter.setPlaceholderText(_t("a11y_app_placeholder"))
        self._window_filter.setPlaceholderText(_t("a11y_window_placeholder"))
        self._name_filter.setPlaceholderText(_t("a11y_name_placeholder"))

    def _apply_table_headers(self) -> None:
        self._table.setHorizontalHeaderLabels([
            _t("a11y_col_app"), _t("a11y_col_role"),
            _t("a11y_col_name"), _t("a11y_col_bounds"),
            _t("a11y_col_center"),
        ])

    def _build_layout(self) -> None:
        # Refresh/click commands run from the Actions menu; the tab keeps
        # only the filter inputs, the element table, and the status line.
        root = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(self._tr(QLabel(), "a11y_app_label"))
        self._app_filter.setPlaceholderText(_t("a11y_app_placeholder"))
        row.addWidget(self._app_filter, stretch=1)
        row.addWidget(self._tr(QLabel(), "a11y_window_label"))
        self._window_filter.setPlaceholderText(_t("a11y_window_placeholder"))
        row.addWidget(self._window_filter, stretch=1)
        row.addWidget(self._tr(QLabel(), "a11y_name_label"))
        self._name_filter.setPlaceholderText(_t("a11y_name_placeholder"))
        row.addWidget(self._name_filter, stretch=1)
        root.addLayout(row)
        root.addWidget(self._table, stretch=1)
        root.addWidget(self._status)

    def menu_actions(self) -> list:
        """Expose tab commands to the window-level Actions menu."""
        return [
            ("a11y_refresh", self._refresh),
            ("a11y_click_selected", self._click_selected),
            ("a11y_show_focused", self._show_focused),
        ]

    def _refresh(self) -> None:
        app = self._app_filter.text().strip() or None
        window = self._window_filter.text().strip() or None
        name_filter = self._name_filter.text().strip().lower()
        self._start(_LIST, functools.partial(_list_matching, app, window, name_filter))

    def _show_focused(self) -> None:
        app = self._app_filter.text().strip() or None
        self._start(_FOCUSED, functools.partial(_focused, app))

    def _on_result(self, value: object) -> None:
        """GUI thread: the command ``self._task.tag`` answered."""
        tag = self._task.tag
        if tag == _CLICK:
            self._status.setText("" if value else _t("a11y_click_not_found"))
            return
        elements = list(value) if isinstance(value, list) else []
        self._populate(elements)
        if tag == _FOCUSED and not elements:
            self._status.setText(_t("a11y_no_focus"))
            return
        self._status.setText(_t("a11y_count_label").replace("{n}", str(len(elements))))

    def _on_error(self, error: object) -> None:
        """GUI thread: the command failed -- typically no accessibility backend on this machine."""
        tag = self._task.tag
        self._status.setText(str(error))
        if tag == _LIST:
            self._table.setRowCount(0)
        elif tag == _CLICK and isinstance(error, AccessibilityNotAvailableError):
            QMessageBox.warning(self, _t("a11y_click_selected"), str(error))

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
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._table.setItem(row, col, item)

    def _click_selected(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            self._status.setText(_t("a11y_no_selection"))
            return
        app = filled_item(self._table, row, 0).text() or None
        role = filled_item(self._table, row, 1).text() or None
        name = filled_item(self._table, row, 2).text() or None
        self._start(_CLICK, functools.partial(_click, name, role, app))
