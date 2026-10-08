"""Searchable feature list for the left side of the main window.

Every registered tab appears here under its category, open or not, so a
feature is one click or a few typed letters away instead of three menus deep.
The panel only reports which key was chosen; opening the tab stays with the
window that owns the tab registry.
"""
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QKeyEvent
from PySide6.QtWidgets import (
    QLabel, QLineEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)

Category = Tuple[str, str, str]
_KEY_ROLE = Qt.ItemDataRole.UserRole


def _t(key: str, default: str) -> str:
    return language_wrapper.translate(key, default)


def matches(query: str, entry: Dict[str, Any], category_label: str = "") -> bool:
    """Whether every word of ``query`` occurs in the entry's title, key or category."""
    haystack = " ".join((str(entry.get("title", "")), str(entry.get("key", "")).replace("_", " "),
                         str(entry.get("key", "")), category_label)).casefold()
    return all(word in haystack for word in query.casefold().split())


class _SearchField(QLineEdit):
    """Line edit that hands Down / Return to the list below it."""

    move_down = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802  # reason: Qt override
        if event.key() == Qt.Key.Key_Down:
            self.move_down.emit()
            return
        super().keyPressEvent(event)


class NavigationPanel(QWidget):
    """Search box over a category tree of every registered tab."""

    feature_activated = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("NavigationPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._entries: List[Dict[str, Any]] = []
        self._categories: Sequence[Category] = ()

        self.search = _SearchField(self)
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.apply_filter)
        self.search.returnPressed.connect(self.activate_first_match)
        self.search.move_down.connect(self._focus_first_match)

        self.tree = QTreeWidget(self)
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(False)
        self.tree.setIndentation(12)
        self.tree.setUniformRowHeights(True)
        self.tree.itemClicked.connect(self._on_item_chosen)
        self.tree.itemActivated.connect(self._on_item_chosen)

        self.empty = QLabel(self)
        self.empty.setObjectName("NavigationEmpty")
        self.empty.setWordWrap(True)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.empty.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        layout.addWidget(self.search)
        layout.addWidget(self.tree, 1)
        layout.addWidget(self.empty, 1)
        self.setMinimumWidth(200)
        self.retranslate()

    # --- content -------------------------------------------------------------

    def set_entries(self, entries: Iterable[Dict[str, Any]], categories: Sequence[Category]) -> None:
        """Show ``entries`` (``key`` / ``title`` / ``category`` / ``visible``) grouped by ``categories``.

        A category is ``(key, title_key, default_title)``; entries of a
        category not listed come last, under the category key itself.
        """
        self._entries = [dict(entry) for entry in entries]
        self._categories = tuple(categories)
        self._rebuild()

    def _category_labels(self) -> List[Tuple[str, str]]:
        labels = [(key, _t(title_key, default)) for key, title_key, default in self._categories]
        known = {key for key, _label in labels}
        for entry in self._entries:
            category = str(entry.get("category", ""))
            if category not in known:
                known.add(category)
                labels.append((category, category.title()))
        return labels

    def _rebuild(self) -> None:
        self.tree.clear()
        heading = QFont(self.font())
        heading.setBold(True)
        opened = QFont(self.font())
        opened.setBold(True)
        for category, label in self._category_labels():
            members = [entry for entry in self._entries if entry.get("category") == category]
            if not members:
                continue
            group = QTreeWidgetItem(self.tree, [label])
            group.setFont(0, heading)
            group.setFlags(Qt.ItemFlag.ItemIsEnabled)
            for entry in members:
                item = QTreeWidgetItem(group, [str(entry.get("title", entry.get("key", "")))])
                item.setData(0, _KEY_ROLE, entry.get("key"))
                if entry.get("visible"):
                    item.setFont(0, opened)
                    item.setToolTip(0, _t("nav_open_hint", "Open in the workspace"))
            group.setExpanded(True)
        self.apply_filter(self.search.text())

    # --- search --------------------------------------------------------------

    def apply_filter(self, text: str = "") -> int:
        """Hide what ``text`` does not match; return how many features remain."""
        shown = 0
        for index in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(index)
            in_group = 0
            for row in range(group.childCount()):
                item = group.child(row)
                entry = {"title": item.text(0), "key": item.data(0, _KEY_ROLE)}
                hit = matches(text, entry, group.text(0))
                item.setHidden(not hit)
                in_group += int(hit)
            group.setHidden(in_group == 0)
            shown += in_group
        self.tree.setVisible(shown > 0)
        self.empty.setVisible(shown == 0)
        return shown

    def visible_keys(self) -> List[str]:
        """Keys of the features the current search leaves on screen, top to bottom."""
        keys: List[str] = []
        for index in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(index)
            for row in range(group.childCount()):
                item = group.child(row)
                if not item.isHidden():
                    keys.append(str(item.data(0, _KEY_ROLE)))
        return keys

    def _first_match(self) -> Optional[QTreeWidgetItem]:
        for index in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(index)
            for row in range(group.childCount()):
                if not group.child(row).isHidden():
                    return group.child(row)
        return None

    def activate_first_match(self) -> None:
        """Open the first feature the search shows (Return in the search box)."""
        item = self._first_match()
        if item is not None:
            self._on_item_chosen(item)

    def _focus_first_match(self) -> None:
        item = self._first_match()
        if item is not None:
            self.tree.setCurrentItem(item)
            self.tree.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def focus_search(self) -> None:
        """Put the cursor in the search box with its text selected."""
        self.search.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search.selectAll()

    def _on_item_chosen(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        key = item.data(0, _KEY_ROLE)
        if key:
            self.feature_activated.emit(str(key))

    # --- language ------------------------------------------------------------

    def retranslate(self) -> None:
        """Re-read every label from the language wrapper."""
        self.search.setPlaceholderText(_t("nav_search_placeholder", "Search features (Ctrl+K)"))
        self.empty.setText(_t("nav_no_results", "No feature matches this search."))
        if self._entries:
            self._rebuild()
