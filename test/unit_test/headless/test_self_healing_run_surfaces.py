"""Structured self-healing requests retain permissions, cancellation and command failure semantics."""
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
from je_auto_control.utils.self_healing.commands import run_json_request
from je_auto_control.utils.vision.backends.base import VLMBackend

FIXTURES = Path(__file__).resolve().parents[3] / "benchmarks/self_healing/fixtures"


def tool():
    return next(item for item in build_default_tool_registry() if item.name == "ac_self_heal_run")


@pytest.fixture(autouse=True)
def controlled(monkeypatch, tmp_path):
    def forbidden(*_a, **_k):
        pytest.fail("native capture/input is not authorized")

    monkeypatch.setattr("je_auto_control.utils.monitor_layout.logical_frame._load_image_grab", forbidden)
    monkeypatch.setattr("je_auto_control.utils.cv2_utils.region_capture.grab_screen_region", forbidden)
    monkeypatch.setattr("je_auto_control.utils.self_healing.locator._click_at", forbidden)
    monkeypatch.setattr("je_auto_control.wrapper.auto_control_image.locate_image_center", lambda *_a, **_k: (2, 3))
    log = ac.HealEventLog(tmp_path / "events.jsonl")
    monkeypatch.setattr("je_auto_control.utils.self_healing.locator.default_heal_log", log)
    return log


def test_command_mcp_and_builder_default_to_locate(controlled):
    request = {"template_path": str(FIXTURES / "new.png")}
    actions = [["AC_self_heal_run", {"request": request}]]
    result = next(iter(executor.execute_action(actions, raise_on_error=True).values()))
    remote = tool().handler(request)
    assert result["coordinates"] == remote["coordinates"] == [2, 3]
    assert result["operation_status"] == "not_requested" and result["verified"] is None
    assert not remote.is_error
    assert COMMAND_SPECS["AC_self_heal_run"].fields[0].name == "request"
    assert capability_for_tool(tool().name, True) == "drive_input"
    assert not tool().annotations.read_only


def test_mcp_does_not_assume_dict_annotation_promises_verification_key(monkeypatch):
    monkeypatch.setattr("je_auto_control.utils.self_healing.commands.run_json_request", lambda *_a, **_k: {})
    result = tool().handler({})
    assert result == {} and not result.is_error


def test_cli_uses_json_request_without_native_effects(tmp_path, capsys):
    path = tmp_path / "run.json"
    # Controlled template branch avoids selecting a real backend.
    content = [["AC_self_heal_run", {"request": {"template_path": str(FIXTURES / "new.png")}}]]
    path.write_text(json.dumps(content), encoding="utf-8")
    assert main(["run", str(path)]) == 0
    assert '"verified": null' in capsys.readouterr().out


def test_viewer_cannot_dispatch_before_capture_or_path_access():
    with authorization_scope(AuthorizationContext("reader", Role.VIEWER)):
        with pytest.raises(AuthorizationError):
            executor.execute_action([["AC_self_heal_run", {"request": {"template_path": "private.png"}}]],
                                    raise_on_error=True)


def test_nested_template_honors_roots_and_notification_revocation(tmp_path, controlled):
    request = {"template_path": str(FIXTURES / "new.png")}
    with pytest.raises(PathNotAllowedError):
        tool().handler(request, ctx=ToolCallContext("roots", path_policy=PathPolicy([tmp_path])))
    policy = PathPolicy(use_client_roots=True)
    policy.set_client_roots([FIXTURES])
    ctx = ToolCallContext("roots", progress_token="p", path_policy=policy)
    ctx.notifier = lambda *_: policy.set_client_roots([])
    with pytest.raises(PathNotAllowedError):
        tool().handler(request, ctx=ctx)
    assert not controlled.list_events()


@pytest.mark.parametrize("options", [{"description": "submit", "extra": 1},
                                    {"description": "submit", "verification": {"verifier": "arbitrary"}},
                                    {"description": "submit", "verification": {"description": "done"}},
                                    {"description": "submit", "screen_region": [0, 0, False, 5]}])
def test_json_boundary_refuses_invalid_or_python_only_fields(options):
    with pytest.raises(ac.SelfHealRequestError):
        run_json_request(options)


class FakeVerifier(VLMBackend):
    name, available = "controlled", True

    def locate(self, *_a, **_k):
        pytest.fail("template should locate without VLM fallback")

    def verify(self, *_a, **_k):
        return False


@pytest.fixture
def false_verification(monkeypatch):
    from PIL import Image
    calls = []
    monkeypatch.setattr("je_auto_control.utils.monitor_layout.logical_frame.grab_logical",
                        lambda *_a, **_k: (Image.new("RGB", (8, 8)), 0, 0))
    monkeypatch.setattr("je_auto_control.utils.self_healing.locator._click_at", lambda *_: calls.append("click"))
    monkeypatch.setattr("je_auto_control.utils.self_healing.verification.get_backend", lambda: FakeVerifier())
    return calls, {"template_path": str(FIXTURES / "new.png"), "operation": "click",
                   "verification": {"description": "done"}}


def test_false_postcondition_is_command_error_and_mcp_structured_error(false_verification, controlled):
    calls, request = false_verification
    with pytest.raises(ac.SelfHealVerificationError) as caught:
        executor.execute_action([["AC_self_heal_run", {"request": request}]], raise_on_error=True)
    assert caught.value.result["verified"] is False
    result = tool().handler(request)
    assert result.is_error and result["found"] and result["operation_status"] == "verification_failed"
    assert calls == ["click", "click"] and len(controlled.list_events()) == 2


def test_false_postcondition_makes_cli_fail(false_verification, tmp_path, capsys):
    _, request = false_verification
    path = tmp_path / "verify.json"
    path.write_text(json.dumps([["AC_self_heal_run", {"request": request}]]), encoding="utf-8")
    assert main(["run", str(path)]) == 1
    capsys.readouterr()


@pytest.mark.parametrize("phase", ["locating", "clicking", "verifying", "settling"])
def test_mcp_cancellation_at_each_phase_has_no_completion(false_verification, controlled, phase):
    calls, request = false_verification
    ctx = ToolCallContext("cancel", progress_token="p")

    def notify(_method, params):
        if params["message"] == phase:
            ctx.cancelled_event.set()

    ctx.notifier = notify
    with pytest.raises(OperationCancelledError):
        tool().handler(request, ctx=ctx)
    assert calls == (["click"] if phase in ("verifying", "settling") else [])
    assert not controlled.list_events()
