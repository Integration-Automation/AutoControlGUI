"""Window Manager tab: list, focus, close windows."""
from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.wrapper.auto_control_window import (
    close_window_by_title, focus_window, list_windows,
)


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


class WindowManagerTab(TranslatableMixin, QWidget):
    """Browse top-level windows and trigger focus / close actions."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._table = QTableWidget(0, 2)
        self._apply_table_headers()
        self._filter = QLineEdit()
        self._apply_filter_placeholder()
        self._filter.textChanged.connect(self._apply_filter)
        self._status_count: Optional[int] = None
        self._status_error: Optional[str] = None
        self._status = QLabel("")
        self._build_layout()
        self.refresh()

    def _apply_table_headers(self) -> None:
        self._table.setHorizontalHeaderLabels([_t("win_col_hwnd"), _t("win_col_title")])

    def _apply_filter_placeholder(self) -> None:
        self._filter.setPlaceholderText(_t("win_filter_placeholder"))

    def _apply_status(self) -> None:
        if self._status_error is not None:
            self._status.setText(self._status_error)
        elif self._status_count is not None:
            self._status.setText(_t("win_status_count").replace("{n}", str(self._status_count)))
        else:
            self._status.setText("")

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        self._apply_table_headers()
        self._apply_filter_placeholder()
        self._apply_status()

    def _build_layout(self) -> None:
        # Refresh/focus/close commands run from the Actions menu; the tab
        # keeps only the filter input, the window table, and the status.
        root = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(self._filter, stretch=1)
        root.addLayout(top)
        root.addWidget(self._table, stretch=1)
        root.addWidget(self._status)

    def menu_actions(self) -> list:
        """Expose tab commands to the window-level Actions menu."""
        return [
            ("win_refresh", self.refresh),
            ("win_focus_selected", self._on_focus),
            ("win_close_selected", self._on_close),
        ]

    def refresh(self) -> None:
        try:
            windows = list_windows()
        except NotImplementedError as error:
            self._status_error = str(error)
            self._status_count = None
            self._apply_status()
            self._table.setRowCount(0)
            return
        self._status_error = None
        self._table.setRowCount(len(windows))
        for row, (hwnd, title) in enumerate(windows):
            self._table.setItem(row, 0, QTableWidgetItem(str(hwnd)))
            self._table.setItem(row, 1, QTableWidgetItem(title))
        self._status_count = len(windows)
        self._apply_status()
        QTimer.singleShot(0, self._apply_filter)

    def _apply_filter(self) -> None:
        needle = self._filter.text().strip().lower()
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 1)
            visible = not needle or (item is not None and needle in item.text().lower())
            self._table.setRowHidden(row, not visible)

    def _selected_title(self) -> Optional[str]:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 1)
        return item.text() if item is not None else None

    def _on_focus(self) -> None:
        title = self._selected_title()
        if not title:
            return
        try:
            focus_window(title, case_sensitive=True)
        except (RuntimeError, OSError) as error:
            QMessageBox.warning(self, "Error", str(error))

    def _on_close(self) -> None:
        title = self._selected_title()
        if not title:
            return
        try:
            close_window_by_title(title, case_sensitive=True)
            self.refresh()
        except (RuntimeError, OSError) as error:
            QMessageBox.warning(self, "Error", str(error))
