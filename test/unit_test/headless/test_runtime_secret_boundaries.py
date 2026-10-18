"""Run owners keep vault-derived values out of diagnostics and persisted records."""
import http.client
import io
import json
import logging
import sys
from email.message import EmailMessage

import pytest

from je_auto_control.utils.exception.exceptions import AutoControlAssertionException
from je_auto_control.utils.executor.action_executor import executor
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.logging.secret_scope import remember_secret, secret_log_scope
from je_auto_control.utils.mcp_server.audit import AuditLogger
from je_auto_control.utils.run_history.history_store import HistoryStore, SOURCE_MANUAL, STATUS_ERROR
from je_auto_control.utils.secrets import default_secret_manager

FAKE = "fake-boundary-private-value"
PROBE = "AC_secret_boundary_probe"
ACTIONS = [[PROBE, {"value": "${secrets.LOGIN}"}]]


@pytest.fixture
def output(monkeypatch):
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    autocontrol_logger.addHandler(handler)
    monkeypatch.setattr(default_secret_manager, "get", lambda name: FAKE)
    def fail(value):
        raise AutoControlAssertionException("private failure: " + value)
    monkeypatch.setitem(executor.event_dict, PROBE, fail)
    try:
        yield stream
    finally:
        autocontrol_logger.removeHandler(handler)
        handler.close()


@pytest.fixture
def script(tmp_path):
    path = tmp_path / "actions.json"
    path.write_text(json.dumps(ACTIONS), encoding="utf-8")
    return path


@pytest.fixture
def history(monkeypatch):
    from je_auto_control.utils.hotkey import hotkey_daemon
    from je_auto_control.utils.scheduler import scheduler
    from je_auto_control.utils.triggers import email_trigger, trigger_engine, webhook_server
    store = HistoryStore()
    for module in (hotkey_daemon, scheduler, email_trigger, trigger_engine, webhook_server):
        monkeypatch.setattr(module, "default_history_store", store)
        monkeypatch.setattr(module, "capture_error_snapshot", lambda *_args: None)
    try:
        yield store
    finally:
        store.close()


@pytest.mark.parametrize("legacy", [False, True])
def test_cli_errors_are_masked_through_the_outer_error_handler(legacy, output, script, monkeypatch, capsys):
    if legacy:
        from je_auto_control import __main__ as cli
        monkeypatch.setattr(sys, "argv", ["je_auto_control", "-e", str(script)])
        with pytest.raises(SystemExit) as raised:
            cli._main()
        assert raised.value.code == 1
    else:
        from je_auto_control.cli import main
        assert main(["run", str(script)]) == 1
    error = capsys.readouterr().err
    assert FAKE not in output.getvalue() and FAKE not in error
    assert "private failure: ***" in error


@pytest.mark.parametrize("strict", [False, True])
def test_real_local_rest_request_keeps_the_mask_until_error_handling_finishes(output, strict):
    from je_auto_control.utils.rest_api.rest_server import RestApiServer
    server = RestApiServer("127.0.0.1", 0, enable_audit=False)
    server.start()
    connection = http.client.HTTPConnection(*server.address, timeout=5)
    try:
        connection.request("POST", "/execute", json.dumps({"actions": ACTIONS, "raise_on_error": strict}),
                           {"Content-Type": "application/json", "Authorization": "Bearer " + server.token})
        response = connection.getresponse()
        payload = json.loads(response.read())
        assert response.status == (200 if strict else 500)
        if strict:
            assert payload["ok"] is False and FAKE in payload["error"]
        assert FAKE not in output.getvalue()
    finally:
        connection.close()
        server.stop()


def test_mcp_error_audit_is_masked_while_the_result_contract_stays_intact(output, tmp_path, monkeypatch):
    from je_auto_control.utils.mcp_server import server as module
    from je_auto_control.utils.mcp_server.tools import MCPTool
    monkeypatch.setattr(module, "_capture_error_screenshot", lambda *_args: None)
    path = tmp_path / "audit.jsonl"
    tool = MCPTool("probe", "controlled error", {"type": "object", "properties": {}},
                   lambda: executor.execute_action(ACTIONS))
    server = module.MCPServer(tools=[tool], audit_logger=AuditLogger(str(path)))
    response = json.loads(server.handle_line(json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "probe"},
    })))
    assert response["result"]["isError"] is True
    assert FAKE in response["result"]["content"][0]["text"]
    assert FAKE not in output.getvalue()
    assert FAKE not in path.read_text(encoding="utf-8")
    assert "***" in json.loads(path.read_text(encoding="utf-8"))["error"]


@pytest.mark.parametrize("value", [FAKE, 'fake"line\nprivate'])
def test_audit_masks_fields_before_json_encoding_without_mutating_arguments(tmp_path, value):
    path = tmp_path / "audit.jsonl"
    arguments = {"nested": [value], "reference": "${secrets.LOGIN}"}
    with secret_log_scope():
        remember_secret(value)
        AuditLogger(str(path)).record(tool="probe", arguments=arguments, status="error",
                                      duration_seconds=0, error_text="failed " + value)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["arguments"]["nested"] == ["***"]
    assert payload["arguments"]["reference"] == "${secrets.LOGIN}"
    assert payload["error"] == "failed ***"
    assert arguments["nested"] == [value]


def test_history_masks_before_the_sqlite_write(history):
    run = history.start_run(SOURCE_MANUAL, "manual", "script.json")
    with secret_log_scope():
        remember_secret(FAKE)
        history.finish_run(run, STATUS_ERROR, "failed " + FAKE)
    assert history.get_run(run).error_text == "failed ***"


@pytest.mark.parametrize("kind", ["interval", "cron", "trigger", "hotkey", "webhook", "email"])
def test_background_run_owner_masks_history_and_outer_error_logs(kind, output, script, history, monkeypatch):
    if kind in ("interval", "cron"):
        from je_auto_control.utils.scheduler.scheduler import Scheduler
        owner = Scheduler()
        job = (owner.add_job(str(script), 60) if kind == "interval"
               else owner.add_cron_job(str(script), "* * * * *"))
        owner._fire(job, 0, 1_800_000_000)
    elif kind == "trigger":
        from je_auto_control.utils.triggers.trigger_engine import FilePathTrigger, TriggerEngine
        owner = TriggerEngine()
        trigger = FilePathTrigger("trigger", str(script))
        owner.add(trigger)
        owner._fire(trigger, 0)
    elif kind == "hotkey":
        from je_auto_control.utils.hotkey.hotkey_daemon import HotkeyDaemon
        owner = HotkeyDaemon()
        owner.bind("ctrl+alt+a", str(script), binding_id="probe")
        owner._fire_binding("probe")
    elif kind == "webhook":
        from je_auto_control.utils.triggers.webhook_server import WebhookTriggerServer
        owner = WebhookTriggerServer()
        trigger = owner.add(path="/probe", script_path=str(script))
        assert owner.fire(trigger, {}) is not None
    else:
        from je_auto_control.utils.triggers import email_trigger
        owner = email_trigger.EmailTriggerWatcher()
        trigger = owner.add("imap.invalid", "user", "unused", str(script), mark_seen=False)
        message = EmailMessage()
        message.set_content("controlled message")
        monkeypatch.setattr(email_trigger, "_fetch_message", lambda *_args: message)
        assert owner._fire_for_uid(object(), trigger, "1") == 1
        assert FAKE not in trigger.last_error
    row = history.list_runs()[0]
    assert row.status == STATUS_ERROR
    assert FAKE not in row.error_text and "***" in row.error_text
    assert FAKE not in output.getvalue()


def test_direct_email_history_preserves_the_raised_exception_but_not_its_persisted_secret(output, script, history):
    from je_auto_control.utils.triggers.email_trigger import EmailTriggerWatcher
    owner = EmailTriggerWatcher()
    trigger = owner.add("imap.invalid", "user", "unused", str(script))
    with pytest.raises(AutoControlAssertionException, match=FAKE):
        owner._execute_with_history(trigger, {})
    assert FAKE not in history.list_runs()[0].error_text


def test_later_reports_cannot_persist_a_resolved_secret_from_the_action_record(output, monkeypatch):
    from je_auto_control.utils.test_record.record_test_class import record_action_to_list, test_record_instance
    source = {}
    def probe(value):
        source["value"] = value
        record_action_to_list("probe", source, "failed " + value)
        return value
    monkeypatch.setitem(executor.event_dict, PROBE, probe)
    monkeypatch.setattr(test_record_instance, "init_record", True)
    monkeypatch.setattr(test_record_instance, "test_record_list", [])
    result = executor.execute_action(ACTIONS)
    assert list(result.values()) == [FAKE] and source == {"value": FAKE}
    assert FAKE not in json.dumps(test_record_instance.test_record_list)
    assert test_record_instance.test_record_list[0]["local_param"]["value"] == "***"


def test_secret_diagnostics_snapshot_cycles_and_opaque_values_without_repr():
    from je_auto_control.utils.logging.secret_scope import scrub_secret_data
    class Unsafe:
        def __repr__(self):
            raise AssertionError("a diagnostic must not format this object")
    source = {"value": FAKE, "opaque": Unsafe(), "tuple": (FAKE, 1, True, None)}
    source[Unsafe()] = "visible"
    source["cycle"] = source
    with secret_log_scope():
        remember_secret(FAKE)
        result = scrub_secret_data(source)
    assert result == {"value": "***", "opaque": "<opaque>", "tuple": ("***", 1, True, None),
                      "cycle": "<recursive>", "<opaque-key>": "visible"}
    assert source["value"] == FAKE and source["cycle"] is source
    assert FAKE not in json.dumps(result)


def test_audit_masks_dynamic_argument_keys_before_writing(tmp_path):
    path = tmp_path / "audit.jsonl"
    with secret_log_scope():
        remember_secret(FAKE)
        AuditLogger(str(path)).record(tool="probe", arguments={FAKE: "visible"}, status="ok", duration_seconds=0)
    assert json.loads(path.read_text(encoding="utf-8"))["arguments"] == {"***": "visible"}
