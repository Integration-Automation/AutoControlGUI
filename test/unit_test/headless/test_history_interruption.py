"""Interrupted runs never look successful or drive a later screenshot/action."""
import asyncio
import json
from concurrent.futures import CancelledError as FutureCancelledError

import pytest

from je_auto_control.utils.action_journal import ActionJournal, journal_scope, read_events
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.executor.action_executor import executor
from je_auto_control.utils.mcp_server.context import OperationCancelledError
from je_auto_control.utils.run_history.history_store import (
    HistoryStore, HistoryStoreError, STATUS_ERROR, STATUS_RUNNING,
)

KINDS = ("scheduler", "trigger", "hotkey", "webhook", "email")
SIGNALS = (KeyboardInterrupt, SystemExit, GeneratorExit, asyncio.CancelledError,
           FutureCancelledError, OperationCancelledError)


@pytest.fixture
def environment(tmp_path, monkeypatch):
    from je_auto_control.utils.hotkey import hotkey_daemon
    from je_auto_control.utils.scheduler import scheduler
    from je_auto_control.utils.triggers import email_trigger, trigger_engine, webhook_server
    history, snapshots = HistoryStore(), []
    for module in (hotkey_daemon, scheduler, email_trigger, trigger_engine, webhook_server):
        monkeypatch.setattr(module, "default_history_store", history)
        monkeypatch.setattr(module, "capture_error_snapshot", lambda run: snapshots.append(run))
    script = tmp_path / "actions.json"
    script.write_text(json.dumps([["AC_interruption_probe"], ["AC_after_interruption"]]), encoding="utf-8")
    try:
        yield history, snapshots, script, tmp_path / "events.jsonl"
    finally:
        history.close()


def _fire(kind, script, execute):
    if kind == "scheduler":
        from je_auto_control.utils.scheduler.scheduler import Scheduler
        owner = Scheduler(executor=execute)
        job = owner.add_job(str(script), 60)
        return lambda: owner._fire(job, 0, 1_800_000_000)
    if kind == "trigger":
        from je_auto_control.utils.triggers.trigger_engine import FilePathTrigger, TriggerEngine
        owner = TriggerEngine(executor=execute)
        trigger = FilePathTrigger("probe", str(script))
        owner.add(trigger)
        return lambda: owner._fire(trigger, 0)
    if kind == "hotkey":
        from je_auto_control.utils.hotkey.hotkey_daemon import HotkeyDaemon
        owner = HotkeyDaemon(executor=execute)
        owner.bind("ctrl+alt+a", str(script), binding_id="probe")
        return lambda: owner._fire_binding("probe")
    if kind == "webhook":
        from je_auto_control.utils.triggers.webhook_server import WebhookTriggerServer
        owner = WebhookTriggerServer(executor=lambda actions, _variables: execute(actions))
        trigger = owner.add(path="/probe", script_path=str(script))
        return lambda: owner.fire(trigger, {})
    from je_auto_control.utils.triggers.email_trigger import EmailTriggerWatcher
    owner = EmailTriggerWatcher(executor=lambda actions, _variables: execute(actions))
    trigger = owner.add("imap.invalid", "user", "unused", str(script))
    return lambda: owner._execute_with_history(trigger, {})


def _execution(environment, monkeypatch, failure):
    _history, _snapshots, script, path = environment
    reached = []
    def fail():
        raise failure
    monkeypatch.setitem(executor.event_dict, "AC_interruption_probe", fail)
    monkeypatch.setitem(executor.event_dict, "AC_after_interruption", lambda: reached.append(True))
    def execute(actions):
        with journal_scope(ActionJournal(path), run_id="interrupted"):
            return executor.execute_action(actions)
    return execute, reached, script, path


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("signal", SIGNALS)
def test_interruption_records_failure_and_never_captures_or_runs_the_next_action(
        kind, signal, environment, monkeypatch):
    history, snapshots, _script, _path = environment
    failure = signal("controlled")
    execute, reached, script, path = _execution(environment, monkeypatch, failure)
    fire = _fire(kind, script, execute)
    if not isinstance(failure, Exception) or kind == "email":
        with pytest.raises(signal) as raised:
            fire()
        assert raised.value is failure
    else:
        fire()
    row = history.list_runs()[0]
    assert row.status == STATUS_ERROR and type(failure).__name__ in row.error_text
    assert snapshots == [] and reached == []
    assert len(history.journals_for_run(row.id)) == 1
    assert read_events(path)[-1].status == "cancelled"


@pytest.mark.parametrize("kind", KINDS)
def test_history_outage_cannot_replace_a_pending_hard_interruption(kind, environment, monkeypatch):
    history, snapshots, _script, _path = environment
    failure = KeyboardInterrupt("original control flow")
    execute, reached, script, path = _execution(environment, monkeypatch, failure)
    def unavailable(*_args, **_kwargs):
        raise HistoryStoreError("controlled history outage")
    monkeypatch.setattr(history, "finish_run", unavailable)
    with pytest.raises(KeyboardInterrupt) as raised:
        _fire(kind, script, execute)()
    assert raised.value is failure
    assert history.list_runs()[0].status == STATUS_RUNNING
    assert snapshots == [] and reached == [] and read_events(path)[-1].status == "cancelled"


@pytest.mark.parametrize("kind", KINDS)
def test_ordinary_soft_failures_still_capture_and_keep_their_existing_containment(kind, environment, monkeypatch):
    history, snapshots, _script, _path = environment
    failure = ValueError("ordinary failure")
    execute, reached, script, _path = _execution(environment, monkeypatch, failure)
    fire = _fire(kind, script, execute)
    if kind == "email":
        with pytest.raises(AutoControlException):
            fire()
    else:
        fire()
    assert history.list_runs()[0].status == STATUS_ERROR
    assert len(snapshots) == 1 and reached == [True]


def test_mcp_cancellation_keeps_its_deliberate_control_signal_contract():
    failure = OperationCancelledError("controlled")
    assert isinstance(failure, RuntimeError) and not isinstance(failure, AutoControlException)


@pytest.mark.parametrize("block", ["parallel", "dag"])
@pytest.mark.parametrize("signal", SIGNALS)
def test_worker_interruptions_reach_the_owner_without_becoming_success_or_an_ordinary_failure(
        block, signal, environment, monkeypatch):
    history, snapshots, script, path = environment
    failure = signal("controlled")
    execute, reached, _script, _path = _execution(environment, monkeypatch, failure)
    body = [["AC_interruption_probe"], ["AC_after_interruption"]]
    actions = ([["AC_parallel", {"branches": [body]}]] if block == "parallel" else
               [["AC_run_dag", {"definition": {"nodes": [{"id": "first", "actions": body},
                   {"id": "later", "depends_on": ["first"], "actions": [["AC_after_interruption"]]}]}}]])
    script.write_text(json.dumps(actions), encoding="utf-8")
    fire = _fire("scheduler", script, execute)
    if not isinstance(failure, Exception):
        with pytest.raises(signal) as raised:
            fire()
        assert raised.value is failure
    else:
        fire()
    assert history.list_runs()[0].status == STATUS_ERROR
    assert snapshots == [] and reached == []
    assert read_events(path)[-1].status == "cancelled"


@pytest.mark.parametrize("boundary", ["callback_trigger", "callback_handler", "watchdog_matcher", "watchdog_action",
                                      "observer_predicate", "observer_handler", "try", "retry", "image_condition"])
@pytest.mark.parametrize("signal", [FutureCancelledError, OperationCancelledError])
def test_nested_recovery_and_callback_boundaries_cannot_swallow_cancellation(
        boundary, signal, environment, monkeypatch):
    history, snapshots, script, path = environment
    failure = signal("controlled")
    execute, reached, _script, _path = _execution(environment, monkeypatch, failure)
    def probe(*_args):
        return executor.execute_action([["AC_interruption_probe"]])
    if boundary.startswith("callback"):
        from je_auto_control.utils.callback.callback_function_executor import CallbackFunctionExecutor
        owner = CallbackFunctionExecutor()
        owner.event_dict["AC_probe"] = probe if boundary == "callback_trigger" else lambda: None
        def invoke():
            return owner.callback_function("AC_probe", probe if boundary == "callback_handler" else lambda: None)
    elif boundary.startswith("watchdog"):
        from je_auto_control.utils.watchdog.popup_watchdog import PopupWatchdog, WatchdogRule
        owner = PopupWatchdog()
        owner.add_rule(WatchdogRule("probe", probe if boundary == "watchdog_matcher" else lambda: True, probe))
        invoke = owner.check_once
    elif boundary.startswith("observer"):
        from je_auto_control.utils.observer.observer import ScreenObserver
        owner = ScreenObserver()
        owner.add("probe", probe if boundary == "observer_predicate" else lambda: True, probe)
        invoke = owner.poll_once
    else:
        def invoke():
            return None
    if boundary == "try":
        actions = [["AC_try", {"body": [["AC_interruption_probe"]], "catch": [["AC_after_interruption"]]}]]
    elif boundary == "retry":
        actions = [["AC_retry", {"body": [["AC_interruption_probe"]], "max_attempts": 2, "backoff": 0}]]
    elif boundary == "image_condition":
        from je_auto_control.utils.executor import flow_control
        monkeypatch.setattr(flow_control, "locate_image_center", probe)
        actions = [["AC_if_image_found", {"image": "unused.png", "then": [["AC_after_interruption"]],
                                   "else": [["AC_after_interruption"]]}]]
    else:
        monkeypatch.setitem(executor.event_dict, "AC_control_boundary", invoke)
        actions = [["AC_control_boundary"]]
    script.write_text(json.dumps(actions), encoding="utf-8")
    _fire("scheduler", script, execute)()
    assert history.list_runs()[0].status == STATUS_ERROR
    assert snapshots == [] and reached == []
    assert read_events(path)[-1].status == "cancelled"
