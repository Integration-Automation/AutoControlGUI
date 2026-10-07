"""Lazy tab workspace preserving legacy show/hide/list and core handler contracts."""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import partial
from typing import Any, Callable, Optional, TYPE_CHECKING
import weakref

from PySide6.QtCore import QTimer, Signal
from PySide6.QtGui import QCloseEvent, QKeyEvent, Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTabWidget

from je_auto_control.gui._core_tab_proxy import CoreTabMethods
from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui._tab_catalog import TAB_CATALOG
from je_auto_control.gui._tab_factories import build_tab, call_core_action
from je_auto_control.gui.tab_registry import TabRegistry, TabSpec
from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.json.json_file import read_action_json

if TYPE_CHECKING:
    from PySide6.QtWidgets import QLineEdit, QTextEdit


@dataclass
class _TabEntry:
    key: str
    title_key: str
    widget: Optional[QWidget] = None
    category: str = 'core'
    default_visible: bool = False
    actions: tuple[tuple[str, Callable[[], Any]], ...] = ()


class AutoControlGUIWidget(  # pylint: disable=too-many-instance-attributes  # reason: independent registry/tab/timer/recording state
        TranslatableMixin, CoreTabMethods, QWidget):
    """Own the tab workspace; metadata never creates or imports unopened features."""

    tabs_changed = Signal()
    current_tab_changed = Signal()
    if TYPE_CHECKING:
        script_path_input: QLineEdit
        script_editor: QTextEdit
        script_result_text: QTextEdit

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_registry: list[tuple[QWidget, str, str]] = []
        self._tr_tabs: list[tuple[QTabWidget, int, str]] = []
        self.timer = QTimer(self)
        self.repeat_count = 0
        self.repeat_max = 0
        self._record_data: list[Any] = []
        self.tabs = QTabWidget(self)
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self._on_tab_close_requested)  # pylint: disable=no-member  # reason: Qt SignalInstance runtime binding
        self.tabs.currentChanged.connect(self._on_current_tab_changed)  # pylint: disable=no-member  # reason: Qt SignalInstance runtime binding
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        specs = [TabSpec(key, title, category, partial(build_tab, weakref.ref(self), module, target), actions, visible)
                 for key, title, category, visible, module, target, actions in TAB_CATALOG]
        self.registry = TabRegistry(specs, parent=self)
        self._tab_entries = [_TabEntry(spec.key, spec.title_key, category=spec.category,
                                       default_visible=spec.default_visible) for spec in specs]
        for spec in specs:
            if spec.default_visible:
                self.show_tab(spec.key)

    def _add_tab(self, key: str, title_key: str, widget: QWidget, category: str = 'core',
                 default_visible: bool = False, actions: tuple[tuple[str, Callable[[], Any]], ...] = ()) -> None:
        """Retain the legacy private widget-registration hook for existing embedders."""
        self._tab_entries.append(_TabEntry(key, title_key, widget, category, default_visible, actions))
        widget.setParent(self)
        widget.setProperty('tab_key', key)
        if default_visible:
            self.tabs.addTab(widget, language_wrapper.translate(title_key, title_key))
        else:
            widget.hide()

    def _find_entry(self, key: str) -> Optional[_TabEntry]:
        return next((entry for entry in self._tab_entries if entry.key == key), None)

    def _on_current_tab_changed(self, _index: int) -> None:
        self.current_tab_changed.emit()

    def current_tab_menu_actions(self) -> list[tuple[str, Callable[[], Any]]]:
        """Bind actions only for a constructed active tab, retaining legacy handler names."""
        widget = self.tabs.currentWidget()
        entry = next((item for item in self._tab_entries if item.widget is widget), None)
        if widget is None or entry is None:
            return []
        if entry.actions:
            return list(entry.actions)
        provider = getattr(widget, 'menu_actions', None)
        return list(provider()) if callable(provider) else []

    def sync_engine_tabs(self) -> None:
        """Refresh only instantiated engine views after Tools starts an engine."""
        for entry in self._tab_entries:
            callback = getattr(entry.widget, 'sync_with_engine', None)
            if callable(callback):
                callback()

    def list_registered_tabs(self) -> list[dict[str, Any]]:
        """List the complete catalog with legacy key/title/visible/category fields."""
        return [{'key': entry.key, 'title': language_wrapper.translate(entry.title_key, entry.title_key),
                 'visible': entry.widget is not None and self.tabs.indexOf(entry.widget) != -1,
                 'category': entry.category} for entry in self._tab_entries]

    def show_tab(self, key: str) -> None:
        """Open on first access or reveal the retained hidden widget, preserving catalog order."""
        entry = self._find_entry(key)
        if entry is None:
            return
        if entry.widget is None:
            entry.widget = self.registry.open(key)
            self._bind_core_actions(entry)
        if self.tabs.indexOf(entry.widget) == -1:
            index = sum(candidate.widget is not None and self.tabs.indexOf(candidate.widget) != -1
                        for candidate in self._tab_entries[:self._tab_entries.index(entry)])
            self.tabs.insertTab(index, entry.widget, language_wrapper.translate(entry.title_key, entry.title_key))
            self.tabs_changed.emit()
        self.tabs.setCurrentWidget(entry.widget)

    def _bind_core_actions(self, entry: _TabEntry) -> None:
        row = next((item for item in TAB_CATALOG if item[0] == entry.key), None)
        if row is not None and not row[4] and entry.key != 'remote_desktop':
            entry.actions = tuple((label, partial(call_core_action, weakref.WeakMethod(getattr(self, method))))
                                  for label, method in row[6])

    def hide_tab(self, key: str) -> None:
        """Hide without losing entered data or importing an unopened feature."""
        entry = self._find_entry(key)
        if entry is not None and entry.widget is not None:
            index = self.tabs.indexOf(entry.widget)
            if index != -1:
                self.tabs.removeTab(index)
                entry.widget.hide()
                self.tabs_changed.emit()

    def close_tab(self, key: str) -> None:
        """Release an explicitly closed panel; reopening retains its stable catalog identity."""
        entry = self._find_entry(key)
        if entry is None or entry.widget is None:
            return
        widget = entry.widget
        if key == 'auto_click':
            self.timer.stop()
        self.hide_tab(key)
        self._forget_translations(widget)
        if self.registry.instance(key) is widget:
            self.registry.close(key)
        else:
            widget.close()
            widget.deleteLater()
        entry.widget = None
        entry.actions = ()
        self.tabs_changed.emit()

    def _forget_translations(self, widget: QWidget) -> None:
        self._tr_registry = [(target, key, setter) for target, key, setter in self._tr_registry
                             if target is not widget and not widget.isAncestorOf(target)]
        self._tr_tabs = [(target, index, key) for target, index, key in self._tr_tabs
                         if target is not widget and not widget.isAncestorOf(target)]

    def _on_tab_close_requested(self, index: int) -> None:
        widget = self.tabs.widget(index)
        entry = next((item for item in self._tab_entries if item.widget is widget), None)
        if entry is not None:
            self.close_tab(entry.key)

    def _translate(self, key: str) -> str:
        return language_wrapper.translate(key, key)

    def retranslate(self) -> None:
        """Relabel metadata and existing panels without creating unopened widgets."""
        TranslatableMixin.retranslate(self)
        for entry in self._tab_entries:
            if entry.widget is None:
                continue
            index = self.tabs.indexOf(entry.widget)
            if index != -1:
                self.tabs.setTabText(index, language_wrapper.translate(entry.title_key, entry.title_key))
            hook = {'auto_click': '_auto_click_retranslate', 'screenshot': '_screenshot_retranslate',
                    'record': '_record_retranslate'}.get(entry.key)
            if hook:
                getattr(self, hook)()
            callback = getattr(entry.widget, 'retranslate', None)
            if callable(callback):
                callback()

    def open_script_file(self, path: str) -> None:
        """Load a JSON script into its lazily constructed executor tab and focus it."""
        entry = self._find_entry('script')
        if entry is not None:
            self.show_tab('script')
        self.script_path_input.setText(path)
        try:
            data = read_action_json(path)
            self.script_editor.setText(json.dumps(data, indent=2, ensure_ascii=False))
        except (AutoControlException, OSError, ValueError, TypeError, RuntimeError) as error:
            self.script_result_text.setText(f'Error loading: {error}')
            return
        if entry is not None and entry.widget is not None:
            self.tabs.setCurrentWidget(entry.widget)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Keep Ctrl+4 cancellation without opening an unused auto-click panel."""
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_4:
            self.timer.stop()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Stop UI timers and close instantiated owners before the workspace closes."""
        self.timer.stop()
        for entry in self._tab_entries:
            self.close_tab(entry.key)
        super().closeEvent(event)
