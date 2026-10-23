"""Existing browser surfaces delegate to je_web_runner without launching a browser."""
import ast
from pathlib import Path

import pytest


def test_browser_engine_imports_remain_in_the_webrunner_project():
    package = Path(__file__).resolve().parents[3] / "je_auto_control"
    independent = {"selenium", "playwright", "webbrowser"}
    offenders = []
    for path in package.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            imports = []
            if isinstance(node, ast.Import):
                imports = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imports = [node.module or ""]
            if any(name.split(".")[0] in independent for name in imports):
                offenders.append(f"{path.relative_to(package)}:{node.lineno}")
    assert offenders == [], "Browser automation must use je_web_runner: " + ", ".join(offenders)


@pytest.mark.parametrize("surface", ["python", "executor", "mcp"])
def test_legacy_url_open_surfaces_share_the_webrunner_bridge(monkeypatch, surface):
    import je_auto_control as ac
    from je_auto_control.utils import webrunner_bridge
    calls = []
    monkeypatch.setattr(webrunner_bridge, "web_open", lambda url: calls.append(url))
    target = "https://example.invalid/workflow"
    if surface == "python":
        result = ac.open_path(target)
        assert result is True
    elif surface == "executor":
        assert ac.executor.execute_one("AC_open_path", {"target": target}) == {"opened": True}
    else:
        from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
        from je_auto_control.utils.mcp_server.context import ToolCallContext
        tool = next(item for item in build_default_tool_registry() if item.name == "ac_open_path")
        assert tool.invoke({"target": target}, ToolCallContext(1, session_id="browser-fixture")) == {"opened": True}
    assert calls == [target]
