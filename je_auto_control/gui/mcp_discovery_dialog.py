"""Passive MCP registry search and single-schema dialog with cancellable Actions."""
from __future__ import annotations

from functools import partial

from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QLabel, QLineEdit, QMenu, QMenuBar, QPlainTextEdit, QSpinBox, QVBoxLayout, QWidget,
)

from je_auto_control.gui._panel_tasks import PanelTasks, call_native
from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.utils.mcp_server.discovery import discover_tools, get_tool_schema


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


class MCPDiscoveryDialog(QDialog):
    """Inspect the local default registry; schema inspection never executes or enables tools."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(_t('mcp_discovery_title'))
        self.resize(760, 560)
        layout = QVBoxLayout(self)
        menu_bar = QMenuBar(self)
        actions = menu_bar.addMenu(_t('menu_actions'))
        actions.setObjectName('menu_actions')
        layout.setMenuBar(menu_bar)
        form = QFormLayout()
        self.query = QLineEdit(self)
        self.limit = QSpinBox(self)
        self.limit.setRange(1, 100)
        self.limit.setValue(10)
        self.name = QLineEdit(self)
        for key, field in (('mcp_discovery_query', self.query), ('mcp_discovery_limit', self.limit),
                           ('mcp_discovery_name', self.name)):
            label = QLabel(_t(key), self)
            label.setObjectName(key)
            form.addRow(label, field)
        layout.addLayout(form)
        explanation = QLabel(_t('mcp_discovery_local_note'), self)
        explanation.setObjectName('mcp_discovery_local_note')
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        self.output = QPlainTextEdit(self)
        self.output.setReadOnly(True)
        layout.addWidget(self.output)
        self._tasks = PanelTasks(self, self.output)
        for key, handler in (('mcp_discovery_search', self.search), ('mcp_discovery_schema', self.read_schema),
                             ('workspace_cancel_task', self._tasks.cancel)):
            actions.addAction(_t(key), handler).setObjectName(key)
        listener = self._retranslate
        language_wrapper.add_listener(listener)
        self.destroyed.connect(  # pylint: disable=no-member  # reason: native Qt lifetime signal
            lambda *_args: language_wrapper.remove_listener(listener))

    def search(self) -> None:
        """Snapshot inputs on Qt and search through the shared headless API off Qt."""
        if self._tasks.handle is None:
            operation = partial(discover_tools, self.query.text(), limit=self.limit.value())
            self._tasks.submit(partial(call_native, operation))

    def read_schema(self) -> None:
        """Read one named descriptor using the same authorization as headless callers."""
        if self._tasks.handle is None:
            self._tasks.submit(partial(call_native, partial(get_tool_schema, self.name.text())))

    def _retranslate(self, _language: str) -> None:
        """Refresh presentation while retaining input text and task ownership."""
        self.setWindowTitle(_t('mcp_discovery_title'))
        for label in self.findChildren(QLabel):
            if label.objectName():
                label.setText(_t(label.objectName()))
        for action in self.findChildren(QAction):
            if action.objectName():
                action.setText(_t(action.objectName()))
        for menu in self.findChildren(QMenu):
            if menu.objectName():
                menu.setTitle(_t(menu.objectName()))

    def reject(self) -> None:
        """Escape/reject cancels owned work before the dialog hides."""
        self._tasks.cancel()
        super().reject()
