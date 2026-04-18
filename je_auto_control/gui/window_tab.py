"""Window Manager tab: list, focus, close windows."""
from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from je_auto_control.wrapper.auto_control_window import (
    close_window_by_title, focus_window, list_windows,
)


class WindowManagerTab(QWidget):
    """Browse top-level windows and trigger focus / close actions."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["HWND", "Title"])
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("Filter by title substring")
        self._filter.textChanged.connect(self._apply_filter)
        self._status = QLabel("")
        self._build_layout()
        self.refresh()

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        top = QHBoxLayout()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        top.addWidget(refresh)
        top.addWidget(self._filter, stretch=1)
        root.addLayout(top)
        root.addWidget(self._table, stretch=1)
        actions = QHBoxLayout()
        for label, handler in (
            ("Focus selected", self._on_focus),
            ("Close selected", self._on_close),
        ):
            btn = QPushButton(label)
            btn.clicked.connect(handler)
            actions.addWidget(btn)
        actions.addStretch()
        root.addLayout(actions)
        root.addWidget(self._status)

    def refresh(self) -> None:
        try:
            windows = list_windows()
        except NotImplementedError as error:
            self._status.setText(str(error))
            self._table.setRowCount(0)
            return
        self._table.setRowCount(len(windows))
        for row, (hwnd, title) in enumerate(windows):
            self._table.setItem(row, 0, QTableWidgetItem(str(hwnd)))
            self._table.setItem(row, 1, QTableWidgetItem(title))
        self._status.setText(f"{len(windows)} windows")
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
        except (NotImplementedError, RuntimeError, OSError) as error:
            QMessageBox.warning(self, "Error", str(error))

    def _on_close(self) -> None:
        title = self._selected_title()
        if not title:
            return
        try:
            close_window_by_title(title, case_sensitive=True)
            self.refresh()
        except (NotImplementedError, RuntimeError, OSError) as error:
            QMessageBox.warning(self, "Error", str(error))
