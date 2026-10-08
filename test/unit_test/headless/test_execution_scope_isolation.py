"""Each top-level run gets its own variable scope (2026-09-24 audit, plan A3).

``execute_action_with_vars`` seeded its variables into the module executor and
never removed them, and REST, MCP and the socket server ran on that same
executor: the next run's ``${user}`` quietly resolved to the previous caller's
value instead of failing with ``Unknown variable``. ``AC_run_dag`` ran its
nodes on the module executor from pool threads, so inside an ``AC_parallel``
branch they read the parent's variables rather than the branch's.

Nothing here touches the real mouse, keyboard or screen: the only commands
run are variable commands and a probe registered for the test.
"""
import json
import socket
import threading
import types

import pytest

from je_auto_control.utils.executor.action_executor import (
    Executor, execute_action, execute_action_with_vars, executor,
)
from je_auto_control.utils.script_vars import VariableScope, execution_scope
from je_auto_control.utils.script_vars.execution import current_scope

PROBE = "AC_scope_probe"
_SET_USER = ["AC_set_var", {"name": "user", "value": "alice"}]
_READ_USER = [PROBE, {"value": "${user}"}]


@pytest.fixture
def seen():
    """Register a probe command on the module executor; restore it afterwards."""
    values = []
    saved = executor.variables.as_dict()
    executor.variables.clear()
    executor.event_dict[PROBE] = lambda value=None: values.append(value) or value
    yield values
    executor.event_dict.pop(PROBE, None)
    executor.variables.clear()
    executor.variables.update_many(saved)


def _failed(record):
    return [value for value in record.values() if "Unknown variable" in str(value)]


# --- the defect -------------------------------------------------------------

def test_top_level_vars_do_not_leak(seen):
    first = execute_action_with_vars([_READ_USER], {"user": "alice"})
    second = execute_action_with_vars([_READ_USER], {})
    assert seen == ["alice"]
    assert not _failed(first)
    second_run_unknown_variable = bool(_failed(second))
    assert second_run_unknown_variable is True
    assert "user" not in executor.variables


def test_set_var_loop_and_macro_variables_end_with_the_run(seen):
    execute_action_with_vars([
        _SET_USER,
        ["AC_for_each", {"items": [1, 2], "as": "item", "body": [[PROBE, {"value": "${item}"}]]}],
        ["AC_define_macro", {"name": "scope_probe_macro", "params": ["label"],
                             "body": [[PROBE, {"value": "${label}"}]]}],
        ["AC_call_macro", {"name": "scope_probe_macro", "args": {"label": "m"}}],
    ], {})
    executor.macros.pop("scope_probe_macro", None)
    assert seen == [1, 2, "m"]
    assert executor.variables.as_dict() == {}


def test_set_var_still_works_within_one_run(seen):
    record = execute_action_with_vars([_SET_USER, _READ_USER], {})
    assert seen == ["alice"]
    assert not _failed(record)


def test_the_seed_still_rejects_an_invalid_name(seen):
    with pytest.raises(ValueError):
        execute_action_with_vars([_READ_USER], {"": 1})
    assert current_scope() is None


# --- the context manager ----------------------------------------------------

def test_execution_scope_is_restored_after_an_error(seen):
    with pytest.raises(RuntimeError):
        with execution_scope({"user": "alice"}) as scope:
            assert isinstance(scope, VariableScope)
            assert executor.variables is scope
            raise RuntimeError("boom")
    assert current_scope() is None
    assert "user" not in executor.variables


def test_a_nested_scope_gives_the_outer_one_back(seen):
    with execution_scope({"user": "outer"}) as outer:
        with execution_scope({"user": "inner"}):
            execute_action([_READ_USER])
        assert executor.variables is outer
        execute_action([_READ_USER])
    assert seen == ["inner", "outer"]


def test_concurrent_runs_keep_their_own_variables(seen):
    barrier = threading.Barrier(2, timeout=10)
    executor.event_dict["AC_scope_meet"] = lambda: barrier.wait() and None
    records = {}

    def run(name):
        records[name] = execute_action_with_vars(
            [["AC_scope_meet"], _READ_USER], {"user": name})

    threads = [threading.Thread(target=run, args=(name,)) for name in ("left", "right")]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)
    finally:
        executor.event_dict.pop("AC_scope_meet", None)
    assert sorted(seen) == ["left", "right"]
    assert "user" not in executor.variables


# --- what stays as it was ---------------------------------------------------

def test_direct_calls_on_the_module_executor_keep_the_process_scope(seen):
    executor.execute_action([_SET_USER], raise_on_error=True)
    execute_action([_READ_USER])
    assert seen == ["alice"]
    assert executor.variables.get("user") == "alice"


def test_a_private_executor_keeps_its_own_scope_inside_a_run(seen):
    private = Executor()
    with execution_scope({"user": "run"}):
        private.variables.set("user", "private")
        assert executor.variables.get("user") == "run"
    assert private.variables.get("user") == "private"


# --- server and daemon entry points -----------------------------------------

def _rest(body):
    from je_auto_control.utils.rest_api.rest_handlers import handle_execute
    return handle_execute(types.SimpleNamespace(
        body=body, query={}, headers={}, path="/execute"))


@pytest.mark.parametrize("strict", [False, True])
def test_rest_execute_does_not_leak(seen, strict):
    status, _body = _rest({"actions": [_SET_USER], "raise_on_error": strict})
    assert status == 200
    _status, body = _rest({"actions": [_READ_USER], "raise_on_error": strict})
    assert "Unknown variable" in json.dumps(body)
    assert seen == []
    assert "user" not in executor.variables


def test_rest_execute_file_does_not_leak(seen, tmp_path):
    from je_auto_control.utils.rest_api.rest_handlers import handle_execute_file
    script = tmp_path / "set_user.json"
    script.write_text(json.dumps([_SET_USER]), encoding="utf-8")
    status, _body = handle_execute_file(types.SimpleNamespace(
        body={"path": str(script)}, query={}, headers={}, path="/execute_file"))
    assert status == 200
    assert "user" not in executor.variables


def test_mcp_tool_calls_do_not_leak(seen, tmp_path):
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    tools = {tool.name: tool for tool in build_default_tool_registry()}
    tools["ac_execute_actions"].invoke({"actions": [_SET_USER]})
    record = tools["ac_execute_actions"].invoke({"actions": [_READ_USER]})
    assert _failed(record)
    script = tmp_path / "set_user.json"
    script.write_text(json.dumps([_SET_USER]), encoding="utf-8")
    tools["ac_execute_action_file"].invoke({"file_path": str(script)})
    assert seen == []
    assert "user" not in executor.variables


def test_socket_commands_do_not_leak(seen):
    from je_auto_control.utils.socket_server import auto_control_socket_server as module
    server = module.start_autocontrol_socket_server("127.0.0.1", 0)
    try:
        replies = [_socket_exchange(server, actions)
                   for actions in ([_SET_USER], [_READ_USER])]
    finally:
        server.shutdown()
        server.server_close()
    assert "Unknown variable" in replies[1]
    assert seen == []
    assert "user" not in executor.variables


def _socket_exchange(server, actions):
    with socket.create_connection(server.server_address, timeout=10) as sock:
        sock.sendall((json.dumps(actions) + "\n").encode("utf-8"))
        reply = b""
        while b"Return_Data_Over_JE" not in reply:
            chunk = sock.recv(65536)
            if not chunk:
                break
            reply += chunk
    return reply.decode("utf-8")


def test_scheduler_trigger_and_hotkey_runs_do_not_leak(seen):
    from je_auto_control.utils.run_history.run_outcome import run_counting_failures
    run_counting_failures(lambda: execute_action([_SET_USER]))
    with pytest.raises(Exception, match="action"):
        run_counting_failures(lambda: execute_action([_READ_USER]))
    assert seen == []
    assert "user" not in executor.variables


def test_chatops_run_does_not_leak(seen, tmp_path):
    from je_auto_control.utils.chatops.handlers import cmd_run
    (tmp_path / "set_user.json").write_text(json.dumps([_SET_USER]), encoding="utf-8")
    cmd_run(["set_user.json"], {"script_root": str(tmp_path)})
    assert "user" not in executor.variables


def test_voice_commands_do_not_leak(seen):
    from je_auto_control.utils.voice.voice_router import _default_runner
    _default_runner([_SET_USER])
    assert "user" not in executor.variables


# --- nested helpers inside AC_parallel --------------------------------------

def _circuit(name):
    return ["AC_circuit_call", {"name": f"scope-{name}", "actions": [[PROBE, {"value": "${who}"}]]}]


def _bulkhead(name):
    return ["AC_bulkhead_run", {"name": f"scope-{name}", "max_concurrent": 1,
                                "actions": [[PROBE, {"value": "${who}"}]]}]


def _chaos(_name):
    return ["AC_run_chaos", {"spec": {"title": "scope", "method": [
        {"name": "probe", "action": [[PROBE, {"value": "${who}"}]]}]}}]


def _dag(_name):
    return ["AC_run_dag", {"definition": {"nodes": [
        {"id": "a", "actions": [[PROBE, {"value": "${who}"}]]}]}}]


@pytest.mark.parametrize("helper", [_circuit, _bulkhead, _chaos, _dag])
def test_parallel_nested_helpers_use_branch_scope(seen, helper):
    branches = [[["AC_set_var", {"name": "who", "value": name}], helper(name)]
                for name in ("left", "right")]
    execute_action_with_vars([["AC_parallel", {"branches": branches}]], {"who": "parent"})
    branch_results = list(seen)
    assert sorted(branch_results) == ["left", "right"]


@pytest.mark.parametrize("helper", [_circuit, _bulkhead, _chaos, _dag])
def test_nested_helpers_use_the_run_scope_at_top_level(seen, helper):
    execute_action_with_vars([helper("top")], {"who": "run"})
    assert seen == ["run"]
    assert "who" not in executor.variables


def test_a_parallel_branch_forks_the_parent_scope(seen):
    record = execute_action_with_vars([
        ["AC_parallel", {"branches": [
            [[PROBE, {"value": "${who}"}], ["AC_set_var", {"name": "who", "value": "branch"}]],
        ]}],
        [PROBE, {"value": "${who}"}],
    ], {"who": "parent"})
    assert not _failed(record)
    assert seen == ["parent", "parent"]
