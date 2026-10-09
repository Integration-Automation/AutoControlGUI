"""A stopped ``/run`` is reported as stopped, not as a failed script.

The script below stops its own stoppable block (``AC_stop_execution`` with the
block's ``run_id``) and then sleeps: no input, no screen, and it returns at
once because the sleep is woken by the stop.
"""
import json

from je_auto_control.utils.chatops import CommandRouter
from je_auto_control.utils.chatops.handlers import register_default_commands
from je_auto_control.utils.chatops.router import CommandResult
from je_auto_control.utils.executor.run_control import ExecutionStopped, active_executions

_SCRIPT = [["AC_run_stoppable", {"run_id": "chat-run", "body": [
    ["AC_stop_execution", {"run_id": "chat-run", "reason": "operator said so"}],
    ["AC_sleep", {"seconds": 30}],
]}]]


def _router() -> CommandRouter:
    return register_default_commands(CommandRouter())


def test_a_stopped_run_answers_stopped(tmp_path):
    (tmp_path / "long.json").write_text(json.dumps(_SCRIPT), encoding="utf-8")
    result = _router().dispatch("/run long.json", context={"script_root": str(tmp_path)})
    assert isinstance(result, CommandResult)
    assert result.text == "run stopped. (operator said so)"
    assert "failed" not in result.text
    assert "ExecutionStopped" not in result.text
    assert result.succeeded is False
    assert result.metadata == {"stopped": True, "run_id": "chat-run",
                               "reason": "operator said so"}
    assert active_executions() == []


def test_a_stop_without_a_reason_has_no_trailing_parentheses():
    router = CommandRouter()

    def stopped(_argv, _context):
        raise ExecutionStopped("r1")

    router.register("job", stopped)
    result = router.dispatch("/job")
    assert result is not None
    assert result.text == "job stopped."
    assert result.metadata["run_id"] == "r1"


def test_a_real_failure_still_reads_as_a_failure(tmp_path):
    (tmp_path / "bad.json").write_text(json.dumps([["AC_no_such_command", {}]]), encoding="utf-8")
    result = _router().dispatch("/run bad.json", context={"script_root": str(tmp_path)})
    assert result is not None
    assert result.succeeded is False
    assert "stopped" not in result.text
