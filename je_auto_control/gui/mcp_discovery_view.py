"""Passive MCP metadata search for Diagnostics; commands are exposed through Actions."""
from __future__ import annotations

import json
from typing import Callable

from PySide6.QtWidgets import (  # pylint: disable=no-name-in-module  # reason: compiled Qt exports, tested offscreen
    QCheckBox, QFormLayout, QLineEdit, QPlainTextEdit, QVBoxLayout, QWidget,
)

from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.mcp_server.discovery import search_mcp_tools, get_mcp_tool_schema
from je_auto_control.utils.rbac.policy import authorize_command


class MCPDiscoveryView(QWidget):
    """Inspect the local default registry without starting a server or granting access."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.query, self.name = QLineEdit(), QLineEdit()
        self.read_only = QCheckBox()
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(2000)
        form = QFormLayout()
        form.addRow(self.query)
        form.addRow(self.name)
        form.addRow(self.read_only)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.output)
        self.retranslate()

    def retranslate(self) -> None:
        """Update labels without scanning metadata or changing any server configuration."""
        translate = language_wrapper.translate
        self.query.setPlaceholderText(translate("mcp_discovery_query", "mcp_discovery_query"))
        self.name.setPlaceholderText(translate("mcp_discovery_name", "mcp_discovery_name"))
        self.read_only.setText(translate("mcp_discovery_readonly", "mcp_discovery_readonly"))

    def menu_actions(self) -> list[tuple[str, Callable[[], None]]]:
        """Offer search and single-schema inspection through the owning tab's Actions menu."""
        return [("mcp_discovery_search", lambda: self._inspect(False)),
                ("mcp_discovery_schema", lambda: self._inspect(True))]

    def _inspect(self, schema: bool) -> None:
        try:
            authorize_command("AC_mcp_tool_schema" if schema else "AC_mcp_tool_search")
            read_only = True if self.read_only.isChecked() else None
            result = (get_mcp_tool_schema(self.name.text(), read_only=read_only) if schema
                      else search_mcp_tools(self.query.text(), read_only=read_only))
            self.output.setPlainText(json.dumps(result, ensure_ascii=False, indent=2))
        except AutoControlException as error:
            self.output.setPlainText(str(error))
