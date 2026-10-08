"""The MCP audit log is off unless a sink is named, and the documentation says so.

``audit.py``'s docstring promised a default ``mcp_audit.jsonl`` in the working
directory. The constructor never did that: with no path and no
``JE_AUTOCONTROL_MCP_AUDIT`` the logger is disabled. The behaviour is the one
to keep -- a server must not leave a file of tool arguments wherever it is
launched from -- so the docstring was corrected and these tests pin it.
"""
import json
import os

import pytest

from je_auto_control.utils.mcp_server import audit as audit_module
from je_auto_control.utils.mcp_server.audit import AuditLogger
from je_auto_control.utils.mcp_server.server import MCPServer
from je_auto_control.utils.mcp_server.tools import MCPTool
from je_auto_control.utils.mcp_server.tools._base import READ_ONLY, schema

_ENV = "JE_AUTOCONTROL_MCP_AUDIT"


@pytest.fixture()
def cwd(tmp_path, monkeypatch):
    """Run in an empty directory, so anything written to the cwd shows up."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _record(logger):
    logger.record(tool="peek", arguments={"x": 1}, status="ok", duration_seconds=0.0)


def test_without_a_path_or_the_variable_nothing_is_written(cwd, monkeypatch):
    monkeypatch.delenv(_ENV, raising=False)
    logger = AuditLogger()
    assert logger.enabled is False and logger.path is None
    _record(logger)
    assert os.listdir(cwd) == []


def test_an_empty_variable_is_the_same_as_unset(cwd, monkeypatch):
    monkeypatch.setenv(_ENV, "")
    logger = AuditLogger()
    _record(logger)
    assert logger.enabled is False and os.listdir(cwd) == []


def test_a_default_server_writes_no_audit_file_into_the_cwd(cwd, monkeypatch):
    monkeypatch.delenv(_ENV, raising=False)
    server = MCPServer(tools=[MCPTool(name="peek", description="peek", annotations=READ_ONLY,
                                      handler=lambda: {"ok": True}, input_schema=schema({}))])
    reply = json.loads(server.handle_line(json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "peek", "arguments": {}}})))
    assert reply["result"]["isError"] is False
    assert os.listdir(cwd) == []


def test_the_variable_names_the_sink(cwd, monkeypatch):
    target = cwd / "logs" / "audit.jsonl"
    target.parent.mkdir()
    monkeypatch.setenv(_ENV, str(target))
    logger = AuditLogger()
    assert logger.enabled and logger.path == os.path.realpath(target)
    _record(logger)
    assert json.loads(target.read_text(encoding="utf-8"))["tool"] == "peek"


def test_an_explicit_path_wins_over_the_variable(cwd, monkeypatch):
    monkeypatch.setenv(_ENV, str(cwd / "from_env.jsonl"))
    logger = AuditLogger(path=str(cwd / "explicit.jsonl"))
    _record(logger)
    assert os.listdir(cwd) == ["explicit.jsonl"]


def test_the_docstrings_no_longer_promise_a_file_in_the_cwd():
    module_text = " ".join(audit_module.__doc__.split())
    assert "off by default" in module_text
    assert "No version wrote one" in module_text
    assert "no-op without a sink" in AuditLogger.__doc__
