"""Searchable, keyboard-accessible navigation over passive tab catalog metadata."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtWidgets import QLabel, QLineEdit, QStyle, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from je_auto_control.gui.language_wrapper.english import english_word_dict
from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.gui.tab_registry import TabRegistry

_GROUPS = ('record_scripts', 'locate_inspect', 'devices_remote', 'run_reports', 'settings_diagnostics')
_RECORD = frozenset(('auto_click', 'record', 'script_builder', 'script', 'flow_editor', 'recording_editor'))
_DEVICES = frozenset(('mobile', 'device_matrix', 'remote_desktop', 'presence', 'usb_devices', 'usb_browser',
                      'usb_share', 'admin_console', 'inspector', 'window_manager'))
_SETTINGS = frozenset(('config_sync', 'variables', 'secrets', 'plugins', 'audit_log', 'diagnostics'))
_INSPECT = frozenset(('screenshot', 'image_detect', 'assertions', 'a11y_audit', 'media_checks'))


def _group(key: str, category: str) -> str:
    if key in _RECORD:
        return 'record_scripts'
    if key in _DEVICES:
        return 'devices_remote'
    if key in _SETTINGS:
        return 'settings_diagnostics'
    if key in _INSPECT or category == 'detection':
        return 'locate_inspect'
    return 'run_reports'


class NavigationPane(QWidget):  # pylint: disable=too-many-instance-attributes  # reason: search/tree/state plus passive metadata maps
    """Search labels, English aliases and stable keys without opening feature factories."""

    activated = Signal(str)

    def __init__(self, registry: TabRegistry, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._specs = registry.specs
        self._items: dict[str, QTreeWidgetItem] = {}
        self._groups: dict[str, QTreeWidgetItem] = {}
        self._selected: Optional[str] = None
        self.setMinimumWidth(148)
        self.setProperty('role', 'surface')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 12, 10, 12)
        self._title = QLabel()
        self._title.setProperty('role', 'heading')
        self.search = QLineEdit()
        self.search.setClearButtonEnabled(True)
        self.search.installEventFilter(self)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(10)
        self.empty_state = QLabel()
        self.empty_state.setWordWrap(True)
        self.empty_state.setProperty('role', 'muted')
        for widget in (self._title, self.search, self.tree, self.empty_state):
            layout.addWidget(widget)
        self.search.textChanged.connect(self._filter)  # pylint: disable=no-member  # reason: Qt SignalInstance runtime binding
        self.search.returnPressed.connect(self._open_first)  # pylint: disable=no-member  # reason: Qt SignalInstance runtime binding
        self.tree.itemActivated.connect(self._activate_item)  # pylint: disable=no-member  # reason: Qt SignalInstance runtime binding
        self.tree.itemClicked.connect(self._activate_item)  # pylint: disable=no-member  # reason: Qt SignalInstance runtime binding
        self.retranslate()

    def retranslate(self) -> None:
        """Rebuild labels while preserving filter text, selection and unopened factories."""
        self._title.setText(language_wrapper.translate('workspace_title'))
        self.search.setPlaceholderText(language_wrapper.translate('workspace_search'))
        self.empty_state.setText(language_wrapper.translate('workspace_no_results'))
        self.tree.clear()
        self._items.clear()
        self._groups.clear()
        for group in _GROUPS:
            item = QTreeWidgetItem(self.tree, [language_wrapper.translate('workspace_group_' + group)])
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            item.setExpanded(True)
            self._groups[group] = item
        for spec in self._specs:
            item = QTreeWidgetItem(self._groups[_group(spec.key, spec.category)],
                                  [language_wrapper.translate(spec.title_key, spec.key)])
            item.setData(0, Qt.ItemDataRole.UserRole, spec.key)
            item.setToolTip(0, spec.key)
            item.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon))
            self._items[spec.key] = item
        self._filter(self.search.text())
        if self._selected in self._items:
            self.tree.setCurrentItem(self._items[self._selected])

    def _filter(self, query: str) -> None:
        needle = query.strip().casefold()
        for spec in self._specs:
            group = _group(spec.key, spec.category)
            text = ' '.join((spec.key, spec.title_key, spec.category,
                             language_wrapper.translate(spec.title_key), english_word_dict.get(spec.title_key, ''),
                             language_wrapper.translate('workspace_group_' + group))).casefold()
            self._items[spec.key].setHidden(needle not in text)
        for item in self._groups.values():
            item.setHidden(all(item.child(index).isHidden() for index in range(item.childCount())))
        self.empty_state.setVisible(not self.visible_keys())

    def visible_keys(self) -> list[str]:
        """Return reachable leaf identities in registry order without running factories."""
        return [spec.key for spec in self._specs if not self._items[spec.key].isHidden()]

    def label_for_key(self, key: str) -> str:
        """Return the current translated label for one stable feature key."""
        return self._items[key].text(0)

    def open_key(self, key: str) -> None:
        """Activate a known catalog leaf regardless of current search filter."""
        if key in self._items:
            self._selected = key
            self.tree.setCurrentItem(self._items[key])
            self.activated.emit(key)

    def select_key(self, key: str) -> None:
        """Follow a tab change without opening it again."""
        if key in self._items:
            self._selected = key
            self.tree.setCurrentItem(self._items[key])

    def _activate_item(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        key = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(key, str):
            self.open_key(key)

    def _open_first(self) -> None:
        keys = self.visible_keys()
        if keys:
            self.open_key(keys[0])

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # pylint: disable=invalid-name  # reason: Qt virtual callback name
        """Move from search to the first matching feature with the Down key."""
        if watched is self.search and event.type() == QEvent.Type.KeyPress:
            key = getattr(event, 'key', lambda: None)()
            keys = self.visible_keys()
            if key == Qt.Key.Key_Down and keys:
                self.tree.setCurrentItem(self._items[keys[0]])
                self.tree.setFocus()
                return True
        return super().eventFilter(watched, event)
