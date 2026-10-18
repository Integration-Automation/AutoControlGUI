"""Scrollable tab pages that preserve the embedded workspace's widget API."""
from typing import Any

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPaintEvent, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QScrollArea, QTabBar, QTabWidget, QWidget

from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper


class _CloseButton(QAbstractButton):
    """Paint a palette-aware vector cross without loading an image asset."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setFixedSize(20, 20)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.retranslate()

    def retranslate(self) -> None:
        """Refresh the accessible label and tooltip in the active language."""
        self.setAccessibleName(language_wrapper.translate("close_tab", "Close tab"))
        self.setToolTip(self.accessibleName())

    def paintEvent(self, _event: QPaintEvent) -> None:  # noqa: N802  # reason: Qt override
        """Draw the close cross and keyboard focus indicator."""
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            colour = self.palette().highlight().color() if self.underMouse() else self.palette().text().color()
            painter.setPen(QPen(colour, 1.6))
            painter.drawLine(QPointF(6, 6), QPointF(14, 14))
            painter.drawLine(QPointF(14, 6), QPointF(6, 14))
            if self.hasFocus():
                painter.drawRoundedRect(2, 2, 16, 16, 3, 3)
        finally:
            painter.end()


class ScrollableTabs(QTabWidget):
    """Wrap pages in scroll areas while returning original pages to callers.

    ``widget``, ``currentWidget``, ``indexOf`` and ``setCurrentWidget`` retain
    the original page identity used by embedders and the tab registry.
    Removing a page keeps it owned by this widget for subsequent reopening.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTabsClosable(True)

    def scroll_area(self, index: int) -> QScrollArea | None:
        """Return the scroll container for a page, or None for an invalid index."""
        container = super().widget(index)
        return container if isinstance(container, QScrollArea) else None

    def widget(self, index: int) -> QWidget | None:
        """Return the original page at index."""
        container = self.scroll_area(index)
        return container.widget() if container is not None else None

    def currentWidget(self) -> QWidget | None:  # noqa: N802  # reason: Qt override
        """Return the original active page."""
        return self.widget(self.currentIndex())

    def indexOf(self, widget: QWidget) -> int:  # noqa: N802  # reason: Qt override
        """Find an original page without exposing its scroll container."""
        return next((index for index in range(self.count()) if self.widget(index) is widget), -1)

    def setCurrentWidget(self, widget: QWidget) -> None:  # noqa: N802  # reason: Qt override
        """Select an original page when it belongs to this tab widget."""
        index = self.indexOf(widget)
        if index >= 0:
            self.setCurrentIndex(index)

    def addTab(self, widget: QWidget, *args: Any) -> int:  # noqa: N802  # reason: Qt overloads
        """Append a page, accepting Qt's title and optional icon arguments."""
        return self.insertTab(self.count(), widget, *args)

    def insertTab(self, index: int, widget: QWidget, *args: Any) -> int:  # noqa: N802  # reason: Qt overloads
        """Insert a scrollable page and a vector close button."""
        container = QScrollArea(self)
        container.setWidgetResizable(True)
        container.setFrameShape(QScrollArea.Shape.NoFrame)
        container.setWidget(widget)
        result = super().insertTab(index, container, *args)
        tab_bar = self.tabBar()
        for side in (QTabBar.ButtonPosition.LeftSide, QTabBar.ButtonPosition.RightSide):
            old_button = tab_bar.tabButton(result, side)
            if old_button is not None:
                tab_bar.setTabButton(result, side, None)
                old_button.deleteLater()
        button = _CloseButton(tab_bar)
        button.clicked.connect(lambda: self.tabCloseRequested.emit(self.indexOf(widget)))
        tab_bar.setTabButton(result, QTabBar.ButtonPosition.RightSide, button)
        return result

    def removeTab(self, index: int) -> None:  # noqa: N802  # reason: Qt override
        """Remove the scroll container while retaining ownership of its page."""
        container = self.scroll_area(index)
        if container is None:
            return
        page = container.takeWidget()
        if page is not None:
            page.setParent(self)
            page.hide()
        super().removeTab(index)
        container.setParent(None)
        container.deleteLater()

    def clear(self) -> None:
        """Remove every tab while keeping its original page alive."""
        while self.count():
            self.removeTab(self.count() - 1)

    def retranslate(self) -> None:
        """Refresh the labels of the visible close buttons."""
        for index in range(self.count()):
            button = self.tabBar().tabButton(index, QTabBar.ButtonPosition.RightSide)
            if isinstance(button, _CloseButton):
                button.retranslate()
