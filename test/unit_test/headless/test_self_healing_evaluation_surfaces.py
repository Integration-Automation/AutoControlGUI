"""Registered comparison operations retain bounded input, permissions and cancellation."""
import json
from pathlib import Path

import pytest

import je_auto_control as ac
from je_auto_control.cli import main
from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS
from je_auto_control.utils.executor.action_executor import executor
from je_auto_control.utils.mcp_server.context import OperationCancelledError, ToolCallContext
from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
from je_auto_control.utils.path_guard import PathNotAllowedError, PathPolicy
from je_auto_control.utils.rbac import AuthorizationContext, Role, authorization_scope
from je_auto_control.utils.rbac.authorization import AuthorizationError
from je_auto_control.utils.rbac.policy import capability_for_tool

DATASET = Path(__file__).resolve().parents[3] / "benchmarks/self_healing/dataset.json"


def tool():
    return next(item for item in build_default_tool_registry() if item.name == "ac_self_heal_evaluate")


def test_facade_command_mcp_and_builder_return_shared_report():
    assert ac.evaluate_locators and ac.TemplateFrameLocator and ac.VLMFrameLocator
    actions = [["AC_self_heal_evaluate", {"path": str(DATASET)}]]
    result = next(iter(executor.execute_action(actions, raise_on_error=True).values()))
    remote = tool().handler(str(DATASET))
    assert result["versions"]["new"]["accuracy"] == remote["versions"]["new"]["accuracy"]
    assert len(remote["attempts"]) == 10
    assert COMMAND_SPECS["AC_self_heal_evaluate"].fields[0].name == "path"
    assert tool().annotations.read_only
    assert capability_for_tool(tool().name, True) == "drive_input"


def test_cli_can_compare_through_action_file_without_device_effects(tmp_path, capsys):
    path = tmp_path / "compare.json"
    path.write_text(json.dumps([["AC_self_heal_evaluate", {"path": str(DATASET)}]]), encoding="utf-8")
    assert main(["run", str(path)]) == 0
    assert '"schema_version": 1' in capsys.readouterr().out


def test_command_refuses_readonly_identity_before_private_file_read():
    with authorization_scope(AuthorizationContext("reader", Role.VIEWER)):
        with pytest.raises(AuthorizationError):
            executor.execute_action([["AC_self_heal_evaluate", {"path": str(DATASET)}]], raise_on_error=True)


def test_mcp_checks_explicit_policy_on_nested_assets(tmp_path):
    manifest = tmp_path / "dataset.json"
    manifest.write_bytes(DATASET.read_bytes())
    # The manifest itself is allowed; no asset is in its isolated root.
    ctx = ToolCallContext("evaluation", path_policy=PathPolicy([manifest]))
    with pytest.raises(PathNotAllowedError):
        tool().handler(str(manifest), ctx=ctx)


def test_mcp_cancels_between_pairs_without_partial_success():
    ctx = ToolCallContext("evaluation", progress_token="p")
    counts = []

    def notify(_method, params):
        counts.append(params["progress"])
        if params["progress"] == 1:
            ctx.cancelled_event.set()

    ctx.notifier = notify
    with pytest.raises(OperationCancelledError):
        tool().handler(str(DATASET), ctx=ctx)
    assert 1 in counts and 2 not in counts
