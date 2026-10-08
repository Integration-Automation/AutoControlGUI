"""The workspace's tab widget: pages that scroll, and tabs filled on first use.

Each page sits in a holder inside the ``QTabWidget``. A scrollable holder is a
``QScrollArea``, so a window narrower than the page shows scroll bars instead
of squeezing the form below its minimum size; a panel that already scrolls
its own content (Remote Desktop) asks for a plain holder and is not
put inside a second scroll area.

Callers keep speaking in pages: ``addTab`` / ``insertTab`` take the page,
``indexOf`` / ``widget`` / ``currentWidget`` / ``setCurrentWidget`` find and
return it. That is the relation ``tabs.indexOf(entry.widget)`` embedders and
tests rely on, and it holds whether or not the page is wrapped.

A deferred tab is a holder with a title and no page yet; whoever owns the tab
fills it the first time it is selected.

Restyling. A style sheet set on the window is re-applied by Qt to every widget
below it, visible or not: with all 50 tabs open that is about 2,600 widgets and
most of a second in one slot, for the 80 or so that can be seen.
:meth:`WorkspaceTabWidget.restyle` takes the pages of the tabs that are not
selected out of the window's tree first ("parks" them under a hidden widget of
their own), so the change itself touches only what is on screen, and then puts
them back one per event-loop turn -- Qt styles a widget when it gains a styled
parent -- or at once for a tab that gets selected meanwhile. A parked page is
still the tab's page for every method here; only its Qt parent differs, and
only until the queue has drained.
"""
from typing import Any, Callable, List, Optional

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QFrame, QScrollArea, QTabWidget, QVBoxLayout, QWidget


class PageHolder(QWidget):
    """What the tab widget really holds for one tab: the page, scrolled or not."""

    def __init__(self, scrollable: bool = True, pending_key: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("WorkspacePage")
        self.pending_key = pending_key
        self._page: Optional[QWidget] = None
        self._parked = False
        self._area: Optional[QScrollArea] = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        if scrollable:
            self._area = QScrollArea(self)
            self._area.setObjectName("WorkspacePageScroll")
            self._area.setWidgetResizable(True)
            self._area.setFrameShape(QFrame.Shape.NoFrame)
            self._area.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            layout.addWidget(self._area)

    @property
    def scrollable(self) -> bool:
        """Whether the page is inside a scroll area."""
        return self._area is not None

    @property
    def page(self) -> Optional[QWidget]:
        """The page, or ``None`` for a deferred tab not filled yet."""
        return self._page

    @property
    def parked(self) -> bool:
        """Whether the page is out of the window's tree for a restyle (see the module docstring)."""
        return self._parked

    def park(self, parking: QWidget) -> bool:
        """Move the page under ``parking`` until :meth:`unpark`; ``False`` when there is nothing to move."""
        page = self._page
        if page is None or self._parked:
            return False
        self._detach(page)
        page.setParent(parking)
        self._parked = True
        return True

    def unpark(self) -> bool:
        """Put a parked page back, which is when Qt gives it the window's current style."""
        page = self._page
        if page is None or not self._parked:
            return False
        self._parked = False
        self.set_page(page)
        return True

    def _detach(self, page: QWidget) -> None:
        if self._area is not None:
            self._area.takeWidget()
        else:
            self.layout().removeWidget(page)

    def set_page(self, page: QWidget) -> None:
        """Put ``page`` in the holder."""
        self._page = page
        self._parked = False
        if self._area is None:
            self.layout().addWidget(page)
            page.show()
            return
        self._area.setWidget(page)
        # setWidget() turns this on; the page then paints the palette's window
        # colour over the pane instead of sitting on it like an unwrapped page.
        page.setAutoFillBackground(False)

    def take_page(self) -> Optional[QWidget]:
        """Detach and return the page; the caller gives it a new parent."""
        page, self._page = self._page, None
        if page is None:
            return None
        if self._parked:
            self._parked = False        # already out of the holder: under the parking widget
        else:
            self._detach(page)
        return page


class WorkspaceTabWidget(QTabWidget):
    """``QTabWidget`` whose pages scroll when the window is smaller than they are."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        # Where the pages of unselected tabs wait during a restyle; made on
        # first use and dropped once empty.
        self._parking: Optional[QWidget] = None
        self._unpark_timer = QTimer(self)
        self._unpark_timer.setInterval(0)
        self._unpark_timer.timeout.connect(self._unpark_one)
        self.currentChanged.connect(self._unpark_index)

    # --- restyling -----------------------------------------------------------

    def restyle(self, apply: Callable[[], object]) -> int:
        """Run ``apply`` -- a style sheet or palette change above this widget -- touching only what shows.

        The pages of the tabs that are not selected are parked first and come
        back afterwards, one per event-loop turn. Returns how many pages were
        parked for this call.
        """
        if self._parking is None:
            self._parking = QWidget()
        current = self._holder(self.currentIndex())
        parked = 0
        for holder in self._holders():
            if holder is not current and holder.park(self._parking):
                parked += 1
        try:
            apply()
        finally:
            if self.parked_pages():
                self._unpark_timer.start()
            else:
                self._drop_parking()
        return parked

    def parked_pages(self) -> int:
        """How many pages are still waiting to be put back after a restyle."""
        return sum(1 for holder in self._holders() if holder.parked)

    def finish_restyle(self) -> None:
        """Put every parked page back now instead of over the next event-loop turns."""
        for holder in self._holders():
            holder.unpark()
        self._unpark_timer.stop()
        self._drop_parking()

    def _holders(self) -> List[PageHolder]:
        holders = (self._holder(index) for index in range(self.count()))
        return [holder for holder in holders if holder is not None]

    def _unpark_index(self, index: int) -> None:
        """A tab was selected: its page must be in place, and styled, before it is painted."""
        holder = self._holder(index)
        if holder is not None:
            holder.unpark()

    def _unpark_one(self) -> None:
        for holder in self._holders():
            if holder.unpark():
                return
        self._unpark_timer.stop()
        self._drop_parking()

    def _drop_parking(self) -> None:
        parking, self._parking = self._parking, None
        if parking is not None:
            parking.deleteLater()

    # --- adding --------------------------------------------------------------

    def insertTab(self, index: int, page: QWidget, *label: Any,  # noqa: N802  # reason: Qt name
                  scrollable: bool = True) -> int:
        """Insert ``page`` at ``index``; ``label`` is the title, or an icon and the title."""
        holder = PageHolder(scrollable)
        holder.set_page(page)
        return int(super().insertTab(index, holder, *label))

    def addTab(self, page: QWidget, *label: Any, scrollable: bool = True) -> int:  # noqa: N802  # reason: Qt name
        """Append ``page``; see :meth:`insertTab`."""
        return self.insertTab(self.count(), page, *label, scrollable=scrollable)

    def insert_deferred_tab(self, index: int, key: str, label: str, scrollable: bool = True) -> int:
        """Insert a titled tab with no page yet, known by ``key`` until it is filled."""
        return int(super().insertTab(index, PageHolder(scrollable, key), label))

    def fill_deferred(self, key: str, page: QWidget) -> bool:
        """Give the deferred tab ``key`` its page; ``False`` when there is no such tab."""
        holder = self._holder(self.index_of_deferred(key))
        if holder is None:
            return False
        holder.pending_key = ""
        holder.set_page(page)
        return True

    # --- finding -------------------------------------------------------------

    def _holder(self, index: int) -> Optional[PageHolder]:
        raw = super().widget(index) if index >= 0 else None
        return raw if isinstance(raw, PageHolder) else None

    def index_of_deferred(self, key: str) -> int:
        """Index of the unfilled tab ``key``, or -1."""
        if not key:
            return -1
        for index in range(self.count()):
            holder = self._holder(index)
            if holder is not None and holder.pending_key == key:
                return index
        return -1

    def deferred_key(self, index: int) -> str:
        """Key of the tab at ``index`` if it has no page yet, else ``""``."""
        holder = self._holder(index)
        return holder.pending_key if holder is not None and holder.page is None else ""

    def indexOf(self, page: Optional[QWidget]) -> int:  # noqa: N802  # reason: Qt name
        """Index of the tab showing ``page`` (or holding it), or -1."""
        if page is None:
            return -1
        for index in range(self.count()):
            raw = super().widget(index)
            if raw is page or (isinstance(raw, PageHolder) and raw.page is page):
                return index
        return -1

    def widget(self, index: int) -> Optional[QWidget]:
        """The page of the tab at ``index``; ``None`` for a deferred tab not filled yet."""
        raw = super().widget(index)
        return raw.page if isinstance(raw, PageHolder) else raw

    def currentWidget(self) -> Optional[QWidget]:  # noqa: N802  # reason: Qt name
        """The page of the selected tab."""
        return self.widget(self.currentIndex())

    def setCurrentWidget(self, page: QWidget) -> None:  # noqa: N802  # reason: Qt name
        """Select the tab showing ``page``."""
        index = self.indexOf(page)
        if index != -1:
            self.setCurrentIndex(index)

    def is_scrollable(self, index: int) -> bool:
        """Whether the tab at ``index`` scrolls its page."""
        holder = self._holder(index)
        return holder is not None and holder.scrollable

    # --- removing ------------------------------------------------------------

    def removeTab(self, index: int) -> None:  # noqa: N802  # reason: Qt name
        """Remove the tab; its page is kept, hidden, as a child of this widget."""
        holder = self._holder(index)
        super().removeTab(index)
        if holder is None:
            return
        page = holder.take_page()
        if page is not None:
            page.setParent(self)
            page.hide()
        holder.setParent(None)
        holder.deleteLater()

    def clear(self) -> None:
        """Remove every tab, keeping the pages."""
        while self.count():
            self.removeTab(0)
