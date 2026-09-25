"""Runtime flow at the edges the audit found (fakes and fake clocks only).

Failed actions fail a scheduled/triggered run; macro parameters are the
caller's again after a call; ``*/15`` keeps its pace through the repeated DST
hour; a watchdog rule's error stays contained; a re-enabled cron job waits
for its next slot; interval jobs do not drift; a replaced trigger is not
charged for its predecessor's run; hotkey start/stop are serialised;
``AC_retry`` backoff is capped; a plugin cannot take a block command's name.
"""
import datetime as dt
import subprocess  # nosec B404  # reason: only TimeoutExpired is raised, nothing is run
import threading
import types
from dataclasses import dataclass

import pytest

from je_auto_control.utils.executor import flow_control
from je_auto_control.utils.run_history.run_outcome import run_counting_failures
from je_auto_control.utils.scheduler import scheduler as sm
from je_auto_control.utils.triggers import trigger_engine as tm


# --- failed actions fail the run ----------------------------------------------------------

def _failing_command():
    from je_auto_control.utils.exception.exceptions import ImageNotFoundException
    raise ImageNotFoundException("no such image")


def test_a_run_with_a_failed_action_is_an_error(monkeypatch):
    from je_auto_control.utils.exception.exceptions import AutoControlActionException
    from je_auto_control.utils.executor.action_executor import execute_action, executor
    monkeypatch.setitem(executor.event_dict, "AC_probe_fail", _failing_command)
    with pytest.raises(AutoControlActionException, match="1 action"):
        run_counting_failures(lambda: execute_action([["AC_probe_fail"]]))
    assert run_counting_failures(lambda: "fine") == "fine"


def test_the_scheduler_records_a_failed_action_as_an_error(monkeypatch):
    from je_auto_control.utils.executor.action_executor import execute_action, executor
    monkeypatch.setitem(executor.event_dict, "AC_probe_fail", _failing_command)
    finished, snapshots = [], []
    monkeypatch.setattr(sm, "default_history_store", types.SimpleNamespace(
        start_run=lambda *a, **k: 1,
        finish_run=lambda run_id, status, error, **kw: finished.append(status)))
    monkeypatch.setattr(sm, "capture_error_snapshot", lambda run_id: snapshots.append(run_id))
    monkeypatch.setattr(sm, "read_executable_action_json", lambda path: [["AC_probe_fail"]])
    scheduler = sm.Scheduler(executor=execute_action)
    job = scheduler.add_job("x.json", 60, job_id="J")
    job.next_run_ts = 0
    scheduler._tick_once()  # noqa: SLF001
    assert finished == [sm.STATUS_ERROR] and snapshots == [1]


# --- macros ----------------------------------------------------------------------------------

def test_macro_parameters_are_the_callers_again_after_a_nested_call():
    from je_auto_control.utils.executor.action_executor import Executor
    executor = Executor()
    trace = []
    executor.event_dict["AC_probe_trace"] = lambda value: trace.append(value)
    executor.execute_action([
        ["AC_define_macro", {"name": "show", "params": ["label"], "body": [
            ["AC_if_var", {"name": "label", "op": "eq", "value": "outer", "then": [
                ["AC_call_macro", {"name": "show", "args": {"label": "inner"}}]]}],
            ["AC_probe_trace", {"value": "${label}"}]]}],
        ["AC_set_var", {"name": "label", "value": "mine"}],
        ["AC_call_macro", {"name": "show", "args": {"label": "outer"}}],
        ["AC_probe_trace", {"value": "${label}"}],
    ])
    assert trace == ["inner", "outer", "mine"]


def test_retry_backoff_is_capped(monkeypatch):
    sleeps = []
    monkeypatch.setattr(flow_control.time, "sleep", sleeps.append)
    monkeypatch.setattr(flow_control, "_run_strict", lambda executor, body: (_ for _ in ()).throw(
        flow_control.AutoControlActionException("nope")))
    with pytest.raises(flow_control.AutoControlActionException, match="exhausted"):
        flow_control.exec_retry(object(), {"max_attempts": 1100, "backoff": 0.5, "body": []})
    assert len(sleeps) == 1099 and max(sleeps) <= flow_control._MAX_RETRY_BACKOFF_S  # noqa: SLF001


# --- the repeated DST hour ----------------------------------------------------------------------

_EDT, _EST = dt.timedelta(hours=-4), dt.timedelta(hours=-5)
_SWITCH_UTC = dt.datetime(2026, 11, 1, 6, 0)
_REPEAT = (dt.datetime(2026, 11, 1, 1, 0), dt.datetime(2026, 11, 1, 2, 0))


class _FallBack(dt.tzinfo):
    def utcoffset(self, when):
        local = when.replace(tzinfo=None, fold=0)
        if local < _REPEAT[0]:
            return _EDT
        if local >= _REPEAT[1]:
            return _EST
        return _EST if when.fold else _EDT

    def dst(self, when):
        return self.utcoffset(when) - _EST

    def tzname(self, when):
        return "EST" if self.utcoffset(when) == _EST else "EDT"

    def fromutc(self, when):
        utc = when.replace(tzinfo=None)
        if utc < _SWITCH_UTC:
            return (utc + _EDT).replace(tzinfo=self)
        local = utc + _EST
        return local.replace(tzinfo=self, fold=int(_REPEAT[0] <= local < _REPEAT[1]))


class _LocalDatetime(dt.datetime):
    @classmethod
    def fromtimestamp(cls, timestamp, tz=None):
        return dt.datetime.fromtimestamp(timestamp, tz=tz or _FallBack())


def _utc(hour, minute):
    return dt.datetime(2026, 11, 1, hour, minute, tzinfo=dt.timezone.utc).timestamp()


def test_every_quarter_hour_keeps_its_pace_through_the_repeated_hour(monkeypatch):
    monkeypatch.setattr(sm, "_dt", types.SimpleNamespace(datetime=_LocalDatetime,
                                                         timedelta=dt.timedelta))
    expression = sm.parse_cron("*/15 * * * *")
    # 01:45 EDT -> 01:00 EST (15 minutes later), not 02:00 EST.
    assert sm._next_cron_ts(expression, _utc(5, 45)) == _utc(6, 0)  # noqa: SLF001
    # A fixed-hour job still runs once that night.
    fixed = sm.parse_cron("30 1 * * *")
    assert sm._next_cron_ts(fixed, _utc(5, 30)) > _utc(7, 0)  # noqa: SLF001


# --- scheduler bookkeeping -----------------------------------------------------------------------

def test_a_re_enabled_cron_job_waits_for_its_next_slot(monkeypatch):
    now = [dt.datetime(2026, 9, 25, 8, 0).timestamp()]
    monkeypatch.setattr(sm.time, "time", lambda: now[0])
    scheduler = sm.Scheduler(executor=lambda actions: None)
    job = scheduler.add_cron_job("x.json", "0 9 * * *", job_id="C")
    scheduler.set_enabled("C", False)
    now[0] = dt.datetime(2026, 9, 25, 15, 0).timestamp()
    scheduler.set_enabled("C", True)
    assert job.next_run_ts == dt.datetime(2026, 9, 26, 9, 0).timestamp()


def test_interval_jobs_do_not_drift(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(sm.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(sm, "default_history_store", types.SimpleNamespace(
        start_run=lambda *a, **k: 1, finish_run=lambda *a, **k: None))
    monkeypatch.setattr(sm, "read_executable_action_json", lambda path: [])
    runs = []
    scheduler = sm.Scheduler(executor=lambda actions: runs.append(clock[0]))
    scheduler.add_job("x.json", 0.7, job_id="I")
    while clock[0] < 7.5:   # 10 deadlines of 0.7 s; one tick of float slack
        clock[0] = round(clock[0] + 0.5, 3)
        scheduler._tick_once()  # noqa: SLF001
    assert len(runs) == 10


# --- triggers, watchdog, hotkeys, plugins -----------------------------------------------------------

@dataclass
class _Once(tm._TriggerBase):  # noqa: SLF001
    def is_fired(self) -> bool:
        return True


def test_a_replacement_trigger_is_not_charged_for_the_old_run(monkeypatch):
    monkeypatch.setattr(tm, "default_history_store", types.SimpleNamespace(
        start_run=lambda *a, **k: 1, finish_run=lambda *a, **k: None))
    monkeypatch.setattr(tm, "read_executable_action_json", lambda path: [])
    engine = tm.TriggerEngine(executor=lambda actions: None)
    replacement = _Once(trigger_id="T", script_path="new.json", cooldown_seconds=0)

    def swap(actions):
        engine.remove("T")
        engine.add(replacement)

    engine._execute = swap  # noqa: SLF001
    engine.add(_Once(trigger_id="T", script_path="old.json", cooldown_seconds=0))
    engine._poll_once()  # noqa: SLF001
    assert engine._triggers.get("T") is replacement and replacement.fired == 0  # noqa: SLF001


def test_a_watchdog_rule_error_of_any_kind_is_contained():
    from je_auto_control.utils.watchdog.popup_watchdog import PopupWatchdog, WatchdogRule

    def matcher():
        raise subprocess.TimeoutExpired(cmd="x", timeout=1)  # nosemgrep  # reason: runs nothing

    watchdog = PopupWatchdog()
    assert watchdog._apply(WatchdogRule(name="a", matcher=matcher, action=lambda: None)) is False  # noqa: SLF001


def test_concurrent_hotkey_starts_make_one_loop(monkeypatch):
    from je_auto_control.utils.hotkey import backends, hotkey_daemon
    loops = []

    class _Backend:
        name = "fake"

        def run_forever(self, context):
            loops.append(1)
            context.stop_event.wait(5)

    monkeypatch.setattr(backends, "get_backend", lambda: _Backend())
    daemon = hotkey_daemon.HotkeyDaemon()
    barrier = threading.Barrier(4)

    def start():
        barrier.wait()
        daemon.start()

    threads = [threading.Thread(target=start) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    daemon.stop()
    assert len(loops) == 1
    assert not any(t.name == "AutoControlHotkey-fake" and t.is_alive()
                   for t in threading.enumerate())


def test_a_plugin_cannot_take_a_block_commands_name():
    from je_auto_control.utils.plugin_loader.plugin_loader import register_plugin_commands

    def fake_sleep(**kwargs):
        return kwargs

    assert register_plugin_commands({"AC_sleep": fake_sleep}, allow_override=True) == []
