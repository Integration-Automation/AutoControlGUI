"""Agent tools must share executor authorization, cancellation and capture."""
from unittest.mock import patch

import pytest

from je_auto_control.utils.exception.cancellation import CancellationToken, cancellation_scope
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
from je_auto_control.utils.rbac.authorization import AuthorizationError
from je_auto_control.utils.tool_use_schema import run_tool_call


def test_agent_tool_cannot_bypass_viewer_authority():
    calls = []
    with patch("je_auto_control.utils.executor.action_executor.executor.event_dict",
               {"AC_click_mouse": lambda: calls.append(True)}):
        with authorization_scope(AuthorizationContext("reader", "viewer")):
            with pytest.raises(AuthorizationError):
                run_tool_call("AC_click_mouse", {})
    assert calls == []


def test_cancelled_tool_never_calls_handler():
    from concurrent.futures import CancelledError
    token = CancellationToken(1)
    token.cancel()
    calls = []
    with patch("je_auto_control.utils.executor.action_executor.executor.event_dict",
               {"AC_noop": lambda: calls.append(True)}):
        with cancellation_scope(token), pytest.raises(CancelledError):
            run_tool_call("AC_noop", {})
    assert calls == []


def test_tool_rejects_private_executor_arguments():
    with patch("je_auto_control.utils.executor.action_executor.executor.event_dict",
               {"AC_execute_action": lambda **kwargs: None}):
        with pytest.raises(ValueError, match="private"):
            run_tool_call("AC_execute_action", {"action_list": [], "_validated": True})


def test_single_dispatch_returns_raw_value_and_interpolates():
    from je_auto_control.utils.executor.action_executor import Executor
    executor = Executor()
    executor.event_dict = {"AC_echo": lambda value: {"value": value}}
    executor.variables.set("answer", 42)
    assert executor.execute_one("AC_echo", {"value": "${answer}"}) == {"value": 42}


def test_single_dispatch_restores_executor_and_strictness():
    from je_auto_control.utils.executor.action_executor import Executor, _RUNNING, _STRICT_BODIES
    previous = getattr(_RUNNING, "value", None)
    executor = Executor()
    executor.event_dict = {"AC_fail": lambda: (_ for _ in ()).throw(ValueError("failure"))}
    with pytest.raises(ValueError, match="failure"):
        executor.execute_one("AC_fail", {})
    assert getattr(_RUNNING, "value", None) is previous
    assert not getattr(_STRICT_BODIES, "value", False)


def test_task_guard_survives_parallel_worker_boundary():
    from je_auto_control.utils.executor.action_executor import Executor
    from je_auto_control.utils.executor.dispatch import command_guard
    from je_auto_control.utils.exception.exceptions import AutoControlException
    executor = Executor()
    calls = []
    executor.event_dict["AC_forbidden_test"] = lambda: calls.append(True)

    def guard(name, _arguments):
        if name == "AC_forbidden_test":
            raise AutoControlException("task guard refused child")

    with command_guard(guard), pytest.raises(AutoControlException, match="refused"):
        executor.execute_one("AC_parallel", {"branches": [[["AC_forbidden_test"]]]})
    assert calls == []
