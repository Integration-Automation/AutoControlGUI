"""Passive MCP registry search and single-schema dialog with cancellable Actions."""
from __future__ import annotations

from functools import partial
from typing import cast

from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QLabel, QLineEdit, QMenu, QMenuBar, QPlainTextEdit, QSpinBox,
    QVBoxLayout, QWidget,
)

from je_auto_control.gui._panel_tasks import PanelTasks, call_native
from je_auto_control.gui._task_state import TaskResult
from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.utils.mcp_server.discovery import default_tool_index, discover_tools, get_tool_schema
from je_auto_control.utils.mcp_server.disclosure import DisclosureMode, ToolDisclosureError, ToolView


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


class MCPDiscoveryDialog(QDialog):  # pylint: disable=too-many-instance-attributes  # reason: controls, owned view and cursor
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
        self.mode = QComboBox(self)
        for mode in ('progressive', 'full', 'static'):
            self.mode.addItem(_t('mcp_disclosure_' + mode), mode)
        self._view: ToolView | None = ToolView(default_tool_index)
        self._cursor: str | None = None
        for key, field in (('mcp_discovery_query', self.query), ('mcp_discovery_limit', self.limit),
                           ('mcp_discovery_name', self.name), ('mcp_disclosure_mode', self.mode)):
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
                             ('workspace_cancel_task', self._tasks.cancel),
                             ('mcp_disclosure_apply', self.apply_mode), ('mcp_disclosure_list', self.list_visible),
                             ('mcp_disclosure_enable', self.enable_names),
                             ('mcp_disclosure_disable', self.disable_names),
                             ('mcp_disclosure_next', self.next_page)):
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
        for i in range(self.mode.count()):
            self.mode.setItemText(i, _t('mcp_disclosure_' + str(self.mode.itemData(i))))
        for menu in self.findChildren(QMenu):
            if menu.objectName():
                menu.setTitle(_t(menu.objectName()))

    def reject(self) -> None:
        """Escape/reject cancels owned work before the dialog hides."""
        self._close_view()
        self._tasks.cancel()
        super().reject()

    def apply_mode(self) -> None:
        """Reset this local preview owner; deployment/session settings are unchanged."""
        if self._tasks.handle is None:
            self._close_view()
            self.list_visible()

    def _names(self) -> tuple[str, ...]:
        return tuple(name.strip() for name in self.name.text().split(',') if name.strip())

    def _owned_view(self) -> ToolView | None:
        if self._view is None:
            mode = cast(DisclosureMode, self.mode.currentData())
            try:
                self._view = ToolView(default_tool_index, mode=mode, profile=self._names() if mode == 'static' else ())
            except ToolDisclosureError as error:
                self.output.setPlainText(str(error))
        return self._view

    def list_visible(self) -> None:
        """Render the local preview's first page; network clients receive their own opaque cursor."""
        if self._tasks.handle is None:
            view = self._owned_view()
            if view is not None:
                self._cursor = None
                self._tasks.submit(partial(call_native, lambda: view.list_page().to_dict()), self._page_result)

    def _page_result(self, result: TaskResult) -> None:
        if isinstance(result.value, dict):
            cursor = result.value.get('nextCursor')
            self._cursor = cursor if isinstance(cursor, str) else None

    def next_page(self) -> None:
        """Read the existing local snapshot with its opaque cursor, off Qt."""
        if self._tasks.handle is None and self._cursor is not None:
            view, cursor = self._owned_view(), self._cursor
            if view is not None:
                self._tasks.submit(partial(call_native, lambda: view.list_page(cursor).to_dict()), self._page_result)

    def enable_names(self) -> None:
        """Enable copied comma-separated names in this progressive local preview only."""
        self._change_preview(True)

    def disable_names(self) -> None:
        """Disable copied names in this preview; native tools are never invoked."""
        self._change_preview(False)

    def _change_preview(self, enable: bool) -> None:
        if self._tasks.handle is None:
            view = self._owned_view()
            if view is not None:
                change = view.enable if enable else view.disable
                operation = partial(change, self._names())
                self._tasks.submit(partial(call_native, lambda: operation().to_dict()))

    def _close_view(self) -> None:
        self._cursor = None
        if self._view is not None:
            self._view.close()
            self._view = None

    def closeEvent(self, event: QCloseEvent) -> None:  # pylint: disable=invalid-name  # reason: Qt callback
        """Revoke the pure metadata preview before its widget is hidden."""
        self._close_view()
        super().closeEvent(event)
