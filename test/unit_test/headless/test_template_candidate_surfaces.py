"""All candidate adapters preserve explicit review, bounded files and controlled failures."""
import base64
import json

import pytest

from headless import test_template_candidates as candidate_fixtures
from je_auto_control.cli import main
from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS
from je_auto_control.utils.executor.action_executor import executor
from je_auto_control.utils.mcp_server.context import OperationCancelledError, ToolCallContext
from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
from je_auto_control.utils.path_guard import PathNotAllowedError, PathPolicy
from je_auto_control.utils.rbac import AuthorizationContext, Role, authorization_scope
from je_auto_control.utils.rbac.authorization import AuthorizationError
from je_auto_control.utils.rbac.policy import capability_for_tool

FIXTURES = candidate_fixtures.FIXTURES
no_device_or_backend = candidate_fixtures.no_device_or_backend
revision_files = candidate_fixtures.revision_files


def tool(operation):
    return next(item for item in build_default_tool_registry() if item.name == f"ac_template_candidate_{operation}")


def command(operation, **arguments):
    record = executor.execute_action([[f"AC_template_candidate_{operation}", arguments]], raise_on_error=True)
    return next(iter(record.values()))


def test_commands_builder_and_mcp_complete_the_same_revision_workflow(revision_files):
    target, bundle, dataset = revision_files
    original = target.read_bytes()
    created = command("create", template_path=str(target), candidate_path=str(FIXTURES / "new.png"),
                      bundle_path=str(bundle), threshold=0.99)
    preview = command("preview", bundle_path=str(bundle))
    images = tool("preview").handler(str(bundle))
    assert preview["revision"] == created["revision"]
    assert [block.type for block in images] == ["text", "image", "image"]
    assert all(base64.b64decode(block.data).startswith(b"\x89PNG") for block in images[1:])
    assert tool("verify").handler(str(bundle), str(dataset))["eligible"]
    accepted = command("accept", bundle_path=str(bundle), dataset_path=str(dataset),
                       expected_revision=created["revision"])
    assert accepted["changed"] and target.read_bytes() != original
    assert tool("revert").handler(str(bundle), created["revision"])["changed"]
    assert target.read_bytes() == original
    for operation in ("create", "preview", "verify", "accept", "revert"):
        assert f"AC_template_candidate_{operation}" in COMMAND_SPECS
        assert capability_for_tool(tool(operation).name, True) == "drive_input"
        assert tool(operation).annotations.read_only == (operation in ("preview", "verify"))


def test_cli_failure_cannot_activate_unverified_or_unreviewed_bytes(revision_files, tmp_path, capsys):
    target, bundle, dataset = revision_files
    original = target.read_bytes()
    command("create", template_path=str(target), candidate_path=str(FIXTURES / "new.png"), bundle_path=str(bundle))
    actions = [["AC_template_candidate_accept", {"bundle_path": str(bundle), "dataset_path": str(dataset),
                                                 "expected_revision": "0" * 64}]]
    script = tmp_path / "actions.json"
    script.write_text(json.dumps(actions), encoding="utf-8")
    assert main(["run", str(script)]) == 1
    assert target.read_bytes() == original
    capsys.readouterr()


@pytest.mark.parametrize("operation", ["create", "preview", "verify", "accept", "revert"])
def test_all_candidate_commands_refuse_viewer_identity(operation):
    with authorization_scope(AuthorizationContext("reader", Role.VIEWER)):
        with pytest.raises(AuthorizationError):
            command(operation)


def test_mcp_confines_the_target_hidden_inside_bundle(revision_files, tmp_path):
    target, bundle, _ = revision_files
    command("create", template_path=str(target), candidate_path=str(FIXTURES / "new.png"), bundle_path=str(bundle))
    ctx = ToolCallContext("preview", path_policy=PathPolicy([bundle]))
    with pytest.raises(PathNotAllowedError):
        tool("preview").handler(str(bundle), ctx=ctx)


def test_preview_rechecks_roots_after_progress_notification(revision_files):
    target, bundle, _ = revision_files
    command("create", template_path=str(target), candidate_path=str(FIXTURES / "new.png"), bundle_path=str(bundle))
    policy = PathPolicy(use_client_roots=True)
    policy.set_client_roots([target.parent])
    ctx = ToolCallContext("preview", progress_token="p", path_policy=policy)

    def revoke(_method, params):
        if params["progress"] == 1:
            policy.set_client_roots([])

    ctx.notifier = revoke
    with pytest.raises(PathNotAllowedError):
        tool("preview").handler(str(bundle), ctx=ctx)


@pytest.mark.parametrize("operation", ["verify", "accept", "revert"])
def test_cancelled_tool_checks_before_reading_private_bundle(operation, monkeypatch):
    def forbidden(*_a, **_k):
        pytest.fail("cancelled request must not read a bundle")

    monkeypatch.setattr("je_auto_control.utils.self_healing.template_candidates.read_bundle", forbidden)
    ctx = ToolCallContext("cancel")
    ctx.cancelled_event.set()
    arguments = {"bundle_path": "private.json", "ctx": ctx}
    if operation != "revert":
        arguments["dataset_path"] = "private-dataset.json"
    if operation != "verify":
        arguments["expected_revision"] = "0" * 64
    with pytest.raises(OperationCancelledError):
        tool(operation).handler(**arguments)
