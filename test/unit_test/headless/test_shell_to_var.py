"""Tests for AC_shell_to_var (command stdout into a flow variable)."""
import sys

from je_auto_control.utils.executor.action_executor import Executor
from je_auto_control.utils.executor.flow_control import exec_shell_to_var


def test_shell_to_var_captures_stdout():
    executor = Executor()
    result = exec_shell_to_var(executor, {
        "command": [sys.executable, "-c", "print('hi-there')"],
        "var": "out",
    })
    assert result["output"] == "hi-there"
    assert result["returncode"] == 0
    assert executor.variables.get_value("out") == "hi-there"


def test_shell_to_var_uses_default_var_name():
    executor = Executor()
    exec_shell_to_var(executor, {
        "command": [sys.executable, "-c", "print('x')"],
    })
    assert executor.variables.get_value("shell_output") == "x"


def test_shell_to_var_reports_nonzero_returncode():
    executor = Executor()
    result = exec_shell_to_var(executor, {
        "command": [sys.executable, "-c", "import sys; sys.exit(3)"],
    })
    assert result["returncode"] == 3
    assert result["output"] == ""
