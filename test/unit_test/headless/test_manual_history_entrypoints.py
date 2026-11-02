"""Manual CLI and action commands opt in without changing result payloads."""
import json

import pytest

import je_auto_control as ac
from je_auto_control.cli import main
from je_auto_control.utils.executor.action_executor import Executor, executor
from je_auto_control.utils.run_history import manual as manual_module
from je_auto_control.utils.rbac import AuthorizationContext, Role, authorization_scope


@pytest.fixture
def store(tmp_path, monkeypatch):
    value = ac.HistoryStore(tmp_path / "history.sqlite")
    monkeypatch.setattr(manual_module, "default_history_store", value)
    yield value
    value.close()


def _script(tmp_path, actions):
    path = tmp_path / "script.json"
    path.write_text(json.dumps(actions), encoding="utf-8")
    return str(path)


def test_cli_history_and_journal_preserve_stdout_and_link(tmp_path, store, capsys):
    script = _script(tmp_path, [["AC_set_var", {"name": "message", "value": "${seed}"}]])
    journal = tmp_path / "events.jsonl"
    assert main(["run", script, "--history", "--var", "seed=hello", "--journal", str(journal)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert "history_id" not in payload and "journal_path" not in payload
    rows = store.list_runs()
    assert len(rows) == 1 and rows[0].source_type == "manual" and rows[0].script_path == script
    assert rows[0].status == "ok" and len(store.journals_for_run(rows[0].id)) == 1


def test_cli_custom_history_database_is_explicit(tmp_path, store, capsys):
    script = _script(tmp_path, [["AC_set_var", {"name": "x", "value": 1}]])
    custom = tmp_path / "custom.sqlite"
    assert main(["run", script, "--history", "--history-db", str(custom)]) == 0
    capsys.readouterr()
    check = ac.HistoryStore(custom)
    try:
        assert check.list_runs()[0].status == "ok" and store.list_runs() == []
    finally:
        check.close()


def test_cli_disabled_history_uses_no_store(tmp_path, store, capsys, monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail("history was not requested")
    monkeypatch.setattr(store, "start_run", fail)
    script = _script(tmp_path, [["AC_set_var", {"name": "x", "value": 1}]])
    assert main(["run", script]) == 0
    capsys.readouterr()
    assert store._conn is None


def test_cli_history_failure_keeps_exit_code_and_result(tmp_path, store, capsys, monkeypatch):
    def fail():
        raise ValueError("controlled")
    monkeypatch.setitem(executor.event_dict, "AC_manual_cli_fail", fail)
    script = _script(tmp_path, [["AC_manual_cli_fail"]])
    assert main(["run", script, "--history"]) == 1
    output = capsys.readouterr()
    assert json.loads(output.out) and "1 action(s) failed" in output.err
    assert store.list_runs()[0].status == "error"


def test_cli_history_preview_has_no_action_effects(tmp_path, store, capsys, monkeypatch):
    def fail():
        pytest.fail("preview dispatched")
    monkeypatch.setitem(executor.event_dict, "AC_manual_cli_preview", fail)
    script = _script(tmp_path, [["AC_manual_cli_preview"]])
    assert main(["run", script, "--history", "--dry-run"]) == 0
    assert "dry-run" in capsys.readouterr().out and store.list_runs()[0].status == "ok"
    assert store.list_runs()[0].source_id == "cli.preview"


def test_cli_history_database_requires_opt_in(tmp_path, store, capsys, monkeypatch):
    effects = []
    monkeypatch.setitem(executor.event_dict, "AC_manual_cli_probe", lambda: effects.append(1))
    script = _script(tmp_path, [["AC_manual_cli_probe"]])
    assert main(["run", script, "--history-db", str(tmp_path / "unused.sqlite")]) == 1
    assert "requires --history" in capsys.readouterr().err and effects == [] and store._conn is None


def test_named_history_body_defers_values_and_keeps_private_executor(store):
    private = Executor()
    private.variables.set("message", "before")
    body = [["AC_set_var", {"name": "message", "value": "after"}], ["AC_get_var", {"name": "message"}]]
    result = private.execute_action([["AC_history_capture", {"body": body, "source_id": "nested"}]],
                                    raise_on_error=True)
    summary = next(iter(result.values()))
    assert private.variables.get("message") == "after" and "after" in summary["record"].values()
    assert store.get_run(summary["history_id"]).status == "ok" and summary["failed_actions"] == 0


def test_history_command_validation_is_before_any_prior_action(store, monkeypatch):
    effects = []
    monkeypatch.setitem(executor.event_dict, "AC_manual_command_probe", lambda: effects.append(1))
    with pytest.raises(ac.AutoControlActionException, match="unknown command"):
        executor.execute_action([["AC_manual_command_probe"],
                                 ["AC_history_capture", {"body": [["AC_unknown_manual_body"]]}]], raise_on_error=True)
    assert effects == [] and store._conn is None


def test_positional_capture_is_rejected_without_body_effects(store):
    with pytest.raises(TypeError):
        executor.execute_action([["AC_history_capture", [[["AC_set_var", {"name": "x", "value": 1}]]]]],
                                raise_on_error=True)
    assert store._conn is None


def test_history_command_viewer_denied_before_row(store):
    with authorization_scope(AuthorizationContext("viewer", Role.VIEWER)):
        with pytest.raises(ac.AuthorizationError):
            executor.execute_action([["AC_history_capture", {"body": [["AC_screen_size"]]}]],
                                    raise_on_error=True)
    assert store._conn is None


def test_outer_command_dry_run_opens_no_history(store):
    executor.execute_action([["AC_history_capture", {"body": [["AC_screen_size"]]}]], dry_run=True)
    assert store._conn is None


def test_command_body_data_is_interpolated_once(store, monkeypatch):
    from je_auto_control.utils.script_vars.execution import execution_scope
    seen = []
    monkeypatch.setitem(executor.event_dict, "AC_manual_data_probe", lambda value: seen.append(value))
    monkeypatch.setattr(ac.default_secret_manager, "get", lambda name: pytest.fail("data reinterpreted as secret"))
    with execution_scope({"message": "${secrets.PRIVATE}"}):
        executor.execute_action([["AC_history_capture", {"body": [
            ["AC_manual_data_probe", {"value": "${message}"}]]}]], raise_on_error=True)
    assert seen == ["${secrets.PRIVATE}"] and store.list_runs()[0].status == "ok"


def test_mcp_generic_execute_rejects_admin_body_before_manual_history(store):
    from je_auto_control.utils.mcp_server import MCPServer, build_default_tool_registry
    tool = next(tool for tool in build_default_tool_registry(read_only=False, aliases=False)
                if tool.name == "ac_execute_actions")
    server = MCPServer(tools=[tool])
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": tool.name, "arguments": {"actions": [["AC_history_capture", {"body": [["AC_admin_list_hosts"]]}]]}}}
    with authorization_scope(AuthorizationContext("operator", Role.OPERATOR)):
        reply = json.loads(server.handle_line(json.dumps(request)))
    assert "error" in reply and store._conn is None


@pytest.mark.parametrize("signal,rows", [("AC_break", 1), ("AC_continue", 3)])
def test_normal_loop_signals_do_not_mark_manual_history_failed(store, signal, rows):
    actions = [["AC_loop", {"times": 3, "body": [
        ["AC_history_capture", {"body": [[signal]]}]]}]]
    executor.execute_action(actions, raise_on_error=True)
    history = store.list_runs()
    assert len(history) == rows and all(row.status == "ok" for row in history)


def test_loop_signal_keeps_preceding_recorded_failure(store, monkeypatch):
    def fail():
        raise ValueError("controlled")
    monkeypatch.setitem(executor.event_dict, "AC_manual_command_fail", fail)
    executor.execute_action([["AC_loop", {"times": 2, "body": [
        ["AC_history_capture", {"body": [["AC_manual_command_fail"], ["AC_break"]]}]]}]])
    assert len(store.list_runs()) == 1 and store.list_runs()[0].status == "error"


def test_mcp_generic_execute_records_an_explicit_manual_owner(store):
    from je_auto_control.utils.mcp_server import MCPServer, build_default_tool_registry
    tool = next(tool for tool in build_default_tool_registry(read_only=False, aliases=False)
                if tool.name == "ac_execute_actions")
    server = MCPServer(tools=[tool])
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": tool.name, "arguments": {"actions": [["AC_history_capture", {
            "body": [["AC_set_var", {"name": "x", "value": 1}]]}]]}}}
    with authorization_scope(AuthorizationContext("operator", Role.OPERATOR)):
        reply = json.loads(server.handle_line(json.dumps(request)))
    assert reply["result"]["isError"] is False
    data = json.loads(reply["result"]["content"][0]["text"])
    assert "history_id" in json.dumps(data)
    assert store.list_runs()[0].status == "ok" and store.list_runs()[0].source_type == "manual"
