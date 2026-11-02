"""Diagnostics offers passive MCP metadata through Actions and never scans on construction."""
import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402  # reason: optional Qt after skip
from je_auto_control.gui import mcp_discovery_view  # noqa: E402  # reason: optional Qt after skip
from je_auto_control.gui.diagnostics_tab import DiagnosticsTab  # noqa: E402  # reason: optional Qt after skip


def test_metadata_controls_only_scan_through_actions(monkeypatch):
    app = QApplication.instance() or QApplication([])
    calls = []
    monkeypatch.setattr(mcp_discovery_view, "search_mcp_tools",
                        lambda query, **options: calls.append((query, options)) or [{"name": "fixture"}])
    monkeypatch.setattr(mcp_discovery_view, "get_mcp_tool_schema",
                        lambda name, **options: {"name": name, "inputSchema": {}})
    tab = DiagnosticsTab()
    try:
        view = tab._mcp_discovery
        assert calls == [] and view.findChildren(QPushButton) == []
        view.query.setText("fixture")
        view.read_only.setChecked(True)
        actions = dict(tab.menu_actions())
        actions["mcp_discovery_search"]()
        assert calls == [("fixture", {"read_only": True})]
        assert json.loads(view.output.toPlainText()) == [{"name": "fixture"}]
        view.name.setText("fixture")
        actions["mcp_discovery_schema"]()
        assert json.loads(view.output.toPlainText())["name"] == "fixture"
        view.mode.setCurrentText("static")
        view.profile.setText("ac_screen_size")
        actions["mcp_disclosure_plan"]()
        plan = json.loads(view.output.toPlainText())
        assert plan["mode"] == "static" and plan["read_only"] is True
        assert plan["names"] == ["ac_screen_size"]
    finally:
        tab.close()
        tab.deleteLater()
        app.processEvents()
