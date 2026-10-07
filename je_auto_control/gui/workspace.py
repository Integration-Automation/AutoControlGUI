"""Responsive navigation, retained workflow workspace and collapsible execution details."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QCloseEvent, QKeySequence, QResizeEvent, QShortcut
from PySide6.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QSplitter, QStyle, QToolButton, QVBoxLayout, QWidget

from je_auto_control.gui._lazy_widget import AutoControlGUIWidget
from je_auto_control.gui._workspace_details import WorkspaceDetails
from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.gui.navigation import NavigationPane
from je_auto_control.gui.tab_registry import TabRegistry, TabRegistryError
from je_auto_control.gui.theme import ThemeTokens, apply_theme


class WorkspaceShell(QWidget):  # pylint: disable=too-many-instance-attributes  # reason: three panes, shortcuts and responsive details preference
    """Embed one registry owner without duplicating factories, panel data or native sessions."""

    def __init__(self, registry: TabRegistry, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        owner = registry.owner
        if owner is not None and not isinstance(owner, AutoControlGUIWidget):
            raise TabRegistryError('workspace requires an unbound registry or its tab widget owner')
        self.workspace = owner if owner is not None else AutoControlGUIWidget(self, registry)
        self.navigation = NavigationPane(registry, self)
        self.details = WorkspaceDetails(self)
        self.workspace_scroll = QScrollArea(self)
        self.workspace_scroll.setWidgetResizable(True)
        self.workspace_scroll.setMinimumWidth(160)
        self.workspace_scroll.setWidget(self.workspace)
        self._splitter = QSplitter(Qt.Orientation.Horizontal, self)
        for pane in (self.navigation, self.workspace_scroll, self.details):
            self._splitter.addWidget(pane)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes([230, 620, 250])
        self._details_override: Optional[bool] = None
        self._details_toggle = QToolButton(self)
        self._details_toggle.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView))
        self._details_toggle.clicked.connect(self.toggle_details)  # pylint: disable=no-member  # reason: Qt SignalInstance runtime binding
        toolbar = QHBoxLayout()
        self._empty_hint = QLabel(self)
        self._empty_hint.setWordWrap(True)
        self._empty_hint.setProperty('role', 'muted')
        toolbar.addWidget(self._empty_hint)
        toolbar.addStretch()
        toolbar.addWidget(self._details_toggle)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addLayout(toolbar)
        layout.addWidget(self._splitter)
        self._search_shortcut = QShortcut(QKeySequence('Ctrl+K'), self)
        self._search_shortcut.activated.connect(self.focus_search)  # pylint: disable=no-member  # reason: Qt SignalInstance runtime binding
        self._details_shortcut = QShortcut(QKeySequence('Ctrl+Shift+D'), self)
        self._details_shortcut.activated.connect(self.toggle_details)  # pylint: disable=no-member  # reason: Qt SignalInstance runtime binding
        self.navigation.activated.connect(self.workspace.show_tab)  # pylint: disable=no-member  # reason: Qt SignalInstance runtime binding
        self.workspace.current_tab_changed.connect(self._sync_active)
        self.workspace.tabs_changed.connect(self._sync_active)
        apply_theme(self, ThemeTokens.dark())
        self.retranslate()
        self._sync_active()

    def focus_search(self) -> None:
        """Make the full feature catalog reachable by keyboard without constructing panels."""
        self.navigation.search.setFocus()
        self.navigation.search.selectAll()

    def toggle_details(self) -> None:
        """Override the responsive default until the user toggles the details again."""
        self._details_override = self.details.isHidden()
        self.details.setVisible(self._details_override)

    def set_state(self, state: str, reason: str = '', recovery: str = '',
                  progress: Optional[int] = None) -> None:
        """Present an explicitly reported execution state without probing native permissions."""
        self.details.set_state(state, reason, recovery, progress)

    def _sync_active(self) -> None:
        widget = self.workspace.tabs.currentWidget()
        self._empty_hint.setVisible(widget is None)
        if widget is None:
            self.details.set_workflow('', ())
            self.set_state('empty')
            return
        key = str(widget.property('tab_key') or '')
        self.navigation.select_key(key)
        self.details.set_workflow(self.workspace.tabs.tabText(self.workspace.tabs.currentIndex()),
                                  tuple(label for label, _handler in self.workspace.current_tab_menu_actions()))
        widget.installEventFilter(self)
        capability_reason = widget.property('capability_reason')
        if capability_reason:
            self.set_state('needs_dependency', str(capability_reason),
                           language_wrapper.translate('feature_dependency_recovery'))
            return
        self.set_state(str(widget.property('execution_state') or 'ready'),
                       str(widget.property('execution_reason') or ''),
                       str(widget.property('execution_recovery') or ''), widget.property('execution_progress'))

    def retranslate(self) -> None:
        """Refresh chrome and constructed panels while retaining search text and workflow data."""
        self.navigation.retranslate()
        self.workspace.retranslate()
        self._empty_hint.setText(language_wrapper.translate('workspace_state_hint_empty'))
        self._details_toggle.setText(language_wrapper.translate('workspace_details_toggle'))
        self._details_toggle.setToolTip(language_wrapper.translate('workspace_details_toggle') + ' (Ctrl+Shift+D)')
        self._sync_active()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # pylint: disable=invalid-name  # reason: Qt virtual callback
        """Refresh reported task properties only for the active workflow owner."""
        if event.type() == QEvent.Type.DynamicPropertyChange and watched is self.workspace.tabs.currentWidget():
            self._sync_active()
        return super().eventFilter(watched, event)

    def resizeEvent(self, event: QResizeEvent) -> None:  # pylint: disable=invalid-name  # reason: Qt virtual callback
        """Collapse supplementary details first on small screens; preserve explicit preference."""
        self.details.setVisible(self.width() >= 900 if self._details_override is None else self._details_override)
        super().resizeEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:  # pylint: disable=invalid-name  # reason: Qt virtual callback
        """Propagate explicit workspace closure to constructed workflow owners."""
        self.workspace.close()
        super().closeEvent(event)


__all__ = ['WorkspaceShell']
