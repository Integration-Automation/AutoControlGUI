"""Journal commands preserve nested execution and boundary policies."""
import asyncio
import json

import pytest

from je_auto_control.utils.action_journal import ActionJournal, read_events
from je_auto_control.utils.action_journal.capture import current_journal, journal_scope
from je_auto_control.utils.exception.exceptions import AutoControlActionException
from je_auto_control.utils.executor.action_executor import Executor, executor
from je_auto_control.utils.executor.action_schema import validate_actions
from je_auto_control.utils.rbac.authorization import AuthorizationContext, AuthorizationError, authorization_scope
from je_auto_control.utils.rbac.policy import denied_command_in
from je_auto_control.utils.rbac.users import Capability, Role
from je_auto_control.utils.script_vars.execution import execution_scope


def _capture(path, body, **metadata):
    return ["AC_journal_capture", {"path": str(path), "body": body, **metadata}]


def test_capture_defers_body_variables_and_preserves_owner_scope(tmp_path):
    path = tmp_path / "nested.jsonl"
    body = [["AC_set_var", {"name": "message", "value": "after"}],
            ["AC_get_var", {"name": "${variable_name}"}]]
    with execution_scope({"message": "before", "variable_name": "message"}):
        result = executor.execute_action([_capture(path, body, run_id="nested")], raise_on_error=True)
        assert executor.variables.get("message") == "after"
    summary = next(iter(result.values()))
    assert summary["run_id"] == "nested" and summary["failed_actions"] == 0
    assert "after" in summary["record"].values()
    assert body[-1][1]["name"] == "${variable_name}" and current_journal() is None
    assert [event.command for event in read_events(path) if event.status == "ok"] == ["AC_set_var", "AC_get_var"]


def test_capture_does_not_reinterpolate_variable_data_as_a_secret(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setitem(executor.event_dict, "AC_journal_command_probe", lambda value: seen.append(value))
    from je_auto_control.utils.secrets import default_secret_manager
    monkeypatch.setattr(default_secret_manager, "get", lambda name: pytest.fail("data was reinterpreted"))
    with execution_scope({"message": "${secrets.PRIVATE}"}):
        executor.execute_action([_capture(tmp_path / "data.jsonl", [
            ["AC_journal_command_probe", {"value": "${message}"}]])], raise_on_error=True)
    assert seen == ["${secrets.PRIVATE}"]


def test_capture_uses_private_executor_and_restores_outer_journal(tmp_path):
    private = Executor()
    private.variables.set("name", "private")
    inner, outer = tmp_path / "inner.jsonl", tmp_path / "outer.jsonl"
    with journal_scope(ActionJournal(outer), run_id="outer") as owner:
        result = private.execute_action([_capture(inner, [["AC_get_var", {"name": "name"}]], run_id="inner")],
                                        raise_on_error=True)
        assert current_journal() is owner
    assert "private" in next(iter(result.values()))["record"].values()
    assert all(event.run_id == "inner" and event.parent_id is None for event in read_events(inner))
    assert all(event.run_id == "outer" for event in read_events(outer))


def test_nested_validation_rejects_unknown_body_before_prior_actions(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setitem(executor.event_dict, "AC_journal_command_probe", lambda: seen.append(True))
    actions = [["AC_journal_command_probe"], _capture(tmp_path / "invalid.jsonl", [["AC_unknown_journal_body"]])]
    with pytest.raises(AutoControlActionException, match="unknown command"):
        executor.execute_action(actions, raise_on_error=True)
    assert seen == [] and not (tmp_path / "invalid.jsonl").exists()


@pytest.mark.parametrize("strict", [False, True])
def test_capture_inherits_strictness_and_records_failure(tmp_path, monkeypatch, strict):
    failure = ValueError("controlled failure")
    def fail():
        raise failure
    monkeypatch.setitem(executor.event_dict, "AC_journal_command_probe", fail)
    path = tmp_path / "failed.jsonl"
    actions = [_capture(path, [["AC_journal_command_probe"]])]
    if strict:
        with pytest.raises(ValueError) as caught:
            executor.execute_action(actions, raise_on_error=True)
        assert caught.value is failure
    else:
        result = executor.execute_action(actions)
        assert next(iter(result.values()))["failed_actions"] == 1
    assert [event.status for event in read_events(path)] == ["incomplete", "error"]
    assert current_journal() is None


def test_capture_preserves_break_and_cancellation_signals(tmp_path, monkeypatch):
    path = tmp_path / "break.jsonl"
    executor.execute_action([["AC_loop", {"times": 2, "body": [
        _capture(path, [["AC_break"]])]}]], raise_on_error=True)
    assert [event.status for event in read_events(path)] == ["incomplete", "ok"]
    signal = asyncio.CancelledError("controlled cancellation")
    def cancel():
        raise signal
    monkeypatch.setitem(executor.event_dict, "AC_journal_command_probe", cancel)
    cancelled = tmp_path / "cancelled.jsonl"
    with pytest.raises(asyncio.CancelledError) as caught:
        executor.execute_action([_capture(cancelled, [["AC_journal_command_probe"]])])
    assert caught.value is signal and current_journal() is None
    assert [event.status for event in read_events(cancelled)] == ["incomplete", "cancelled"]


def test_capture_is_inert_during_outer_dry_run(tmp_path):
    path = tmp_path / "dry.jsonl"
    result = executor.execute_action([_capture(path, [["AC_screen_size"]])], dry_run=True)
    assert any("dry-run" in key for key in result) and not path.exists()


@pytest.mark.parametrize("name", ["AC_journal_capture", "AC_journal_read"])
def test_viewer_cannot_hide_journal_operations_in_a_payload(name):
    viewer = AuthorizationContext("viewer", Role.VIEWER)
    action = [name, {"path": "private.jsonl", "body": [["AC_screen_size"]]}]
    assert denied_command_in({"nested": [action]}, viewer) == (name, Capability.DRIVE_INPUT)
    with authorization_scope(viewer), pytest.raises(AuthorizationError):
        executor.execute_action([action], raise_on_error=True)


def test_read_command_returns_sanitized_bounded_snapshots(tmp_path):
    path = tmp_path / "read.jsonl"
    executor.execute_action([_capture(path, [["AC_set_var", {"name": "x", "value": 1}]], run_id="first")],
                            raise_on_error=True)
    before = path.read_bytes()
    result = executor.execute_action([["AC_journal_read", {"path": str(path), "run_id": "first", "limit": 1}]],
                                     raise_on_error=True)
    payload = next(iter(result.values()))
    assert len(payload) == 1 and payload[0]["run_id"] == "first"
    assert payload[0]["status"] == "incomplete" and path.read_bytes() == before


def test_schema_exposes_capture_body_and_linter_checks_it(tmp_path):
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    from je_auto_control.utils.action_lint import lint_actions
    specs = {spec.command: spec for spec in _build_specs()}
    assert specs["AC_journal_capture"].body_keys == ("body",)
    assert {field.name for field in specs["AC_journal_read"].fields} == {"path", "run_id", "limit"}
    actions = [_capture(tmp_path / "bad.jsonl", [["AC_unknown_journal_body"]])]
    issues = lint_actions(actions)
    assert any(issue.code == "unknown-command" for issue in issues)
    with pytest.raises(AutoControlActionException):
        validate_actions(actions, executor.known_commands())


@pytest.mark.parametrize("name", ["AC_journal_capture", "AC_journal_read"])
def test_journal_commands_enforce_default_path_roots(tmp_path, monkeypatch, name):
    from je_auto_control.utils.path_guard import path_guard
    from je_auto_control.utils.path_guard import PathNotAllowedError
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    monkeypatch.setattr(path_guard, "default_allowed_roots", lambda: [allowed])
    path = tmp_path / "outside.jsonl"
    params = {"path": str(path)}
    if name == "AC_journal_capture":
        params["body"] = [["AC_set_var", {"name": "should_not_run", "value": 1}]]
    with pytest.raises(PathNotAllowedError):
        executor.execute_action([[name, params]], raise_on_error=True)
    assert not path.exists()


def test_public_inspection_matches_cli_and_rejects_noninteger_limits(tmp_path, capsys):
    import je_auto_control as ac
    from je_auto_control.cli import main
    path = tmp_path / "inspect.jsonl"
    ac.execute_action_with_journal([["AC_set_var", {"name": "x", "value": 1}]], path, run_id="inspect")
    assert main(["journal", str(path), "--limit", "1"]) == 0
    assert ac.inspect_journal(path, limit=1) == json.loads(capsys.readouterr().out)
    for invalid in (True, 0, -1, 10001, 1.5, "2"):
        with pytest.raises(ac.ActionJournalError):
            ac.inspect_journal(path, limit=invalid)


@pytest.mark.parametrize("worker", ["parallel", "dag"])
def test_worker_capture_keeps_variables_metadata_and_history_owner(tmp_path, worker):
    from je_auto_control.utils.run_history import HistoryStore
    from je_auto_control.utils.run_history.context import HistoryBinding, bound_history
    from je_auto_control.utils.run_history.history_store import SOURCE_MANUAL
    path = tmp_path / "worker.jsonl"
    nested = [_capture(path, [["AC_get_var", {"name": "message"}]], run_id="worker",
                       device_id="device", session_id="session")]
    action = ["AC_parallel", {"branches": [nested]}] if worker == "parallel" else [
        "AC_run_dag", {"definition": {"nodes": [{"id": "capture", "actions": nested}]}}]
    store = HistoryStore(tmp_path / "history.sqlite")
    try:
        row_id = store.start_run(SOURCE_MANUAL, "controlled worker", "actions.json")
        with bound_history(HistoryBinding(store, row_id)), execution_scope({"message": "owner"}):
            result = executor.execute_action([action], raise_on_error=True)
        assert "owner" in json.dumps(result)
        events = read_events(path)
        assert [event.status for event in events] == ["incomplete", "ok"]
        assert all((event.run_id, event.device_id, event.session_id) == ("worker", "device", "session")
                   for event in events)
        assert [(link.journal_run_id, link.journal_path) for link in store.journals_for_run(row_id)] == [
            ("worker", str(path.resolve()))]
    finally:
        store.close()


@pytest.mark.parametrize("field", ["run_id", "device_id", "session_id", "path"])
def test_resolved_secrets_cannot_enter_capture_identifiers_or_destination(tmp_path, monkeypatch, field):
    from je_auto_control.utils.action_journal import ActionJournalError
    from je_auto_control.utils.secrets import default_secret_manager
    monkeypatch.setattr(default_secret_manager, "get", lambda name: "fake-private-metadata")
    path = tmp_path / ("leaked-${secrets.PRIVATE}.jsonl" if field == "path" else "metadata.jsonl")
    metadata = {} if field == "path" else {field: "${secrets.PRIVATE}"}
    with execution_scope():
        with pytest.raises(ActionJournalError, match="resolved secret"):
            executor.execute_action([_capture(path, [["AC_set_var", {"name": "effect", "value": 1}]], **metadata)],
                                    raise_on_error=True)
        assert "effect" not in executor.variables
    assert list(tmp_path.glob("*.jsonl")) == []


def test_capture_rejects_positional_bodies_without_reinterpreting_variable_data(tmp_path, monkeypatch):
    from je_auto_control.utils.secrets import default_secret_manager
    monkeypatch.setattr(default_secret_manager, "get", lambda name: pytest.fail("data was reinterpreted"))
    path = tmp_path / "positional.jsonl"
    body = [["AC_set_var", {"name": "copied", "value": "${message}"}]]
    with execution_scope({"message": "${secrets.PRIVATE}"}):
        with pytest.raises(TypeError):
            executor.execute_action([["AC_journal_capture", [body, str(path)]]], raise_on_error=True)
    assert not path.exists()
