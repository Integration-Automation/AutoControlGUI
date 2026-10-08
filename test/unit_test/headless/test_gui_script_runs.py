"""The tabs that execute a script do it off the GUI thread, one run at a time, and can stop it.

Offscreen Qt. Every command a script runs here is a fake registered on the
executor for the test: nothing touches the mouse, the keyboard or the screen.
"""
import json
import os
import threading
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtCore import QCoreApplication, QEvent, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget  # noqa: E402

from headless._qt_settle import settle  # noqa: E402
from headless._tab_hosts import RecordHost, ScriptHost  # noqa: E402
from je_auto_control.gui._tab_task import TabTask, stop_all_script_runs, was_stopped  # noqa: E402
from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper  # noqa: E402
from je_auto_control.utils.executor.action_executor import executor  # noqa: E402
from je_auto_control.utils.executor.run_control import (  # noqa: E402
    ExecutionStopped, active_executions, current_stop_token,
)

_WAIT = 10.0
_LONG = [["AC_fake_mark"], ["AC_sleep", {"seconds": 60}], ["AC_fake_after"]]


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


def _pump(predicate, timeout: float = _WAIT) -> bool:
    app = QApplication.instance()
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()
    return bool(predicate())


class _Script:
    """Fake commands: where they ran, what ran, and a gate a test can hold shut."""

    def __init__(self) -> None:
        self.calls: list = []
        self.threads: list = []
        self.entered = threading.Event()
        self.gate = threading.Event()

    def mark(self) -> str:
        self.threads.append(threading.get_ident())
        self.calls.append("mark")
        self.entered.set()
        return "marked"

    def held(self) -> str:
        self.mark()
        self.gate.wait(_WAIT)
        return "released"

    def after(self) -> None:
        self.calls.append("after")


@pytest.fixture()
def script(monkeypatch):
    QApplication.instance() or QApplication([])
    fake = _Script()
    for name, command in (("AC_fake_mark", fake.mark), ("AC_fake_held", fake.held),
                          ("AC_fake_after", fake.after)):
        monkeypatch.setitem(executor.event_dict, name, command)
    boxes = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: boxes.append(args[-1]))
    monkeypatch.setattr(QMessageBox, "information", lambda *args: boxes.append(args[-1]))
    fake.boxes = boxes
    yield fake
    fake.gate.set()
    assert _pump(lambda: active_executions() == []), "a script run outlived its test"


# --- TabTask ---------------------------------------------------------------------------------------------

def test_one_run_at_a_time_and_the_outcome_arrives_on_the_gui_thread(script):
    owner = QWidget()
    runs = TabTask(owner)
    delivered = []
    runs.result.connect(lambda value: delivered.append((threading.get_ident(), value)))
    started = time.monotonic()
    assert runs.start_script(lambda: executor.execute_action([["AC_fake_held"]]))
    assert time.monotonic() - started < 5.0, "starting a run held the GUI thread"
    assert runs.running and not runs.stopping
    assert script.entered.wait(_WAIT)
    assert not runs.start_script(lambda: None), "a second run started while one was running"
    assert not runs.start(lambda: None)
    script.gate.set()
    assert settle(runs, "task")
    assert [ident for ident, _value in delivered] == [threading.get_ident()]
    assert script.threads and script.threads[0] != threading.get_ident()
    assert not runs.running
    assert runs.start(lambda: 7)        # free again once the outcome was delivered
    assert settle(runs, "task")
    assert delivered[-1][1] == 7


def test_stop_ends_a_waiting_script_and_reports_it_once_the_worker_has_unwound(script):
    owner = QWidget()
    runs = TabTask(owner)
    errors, finished = [], []
    runs.error.connect(errors.append)
    runs.finished.connect(lambda: finished.append(runs.task))
    assert runs.start_script(lambda: executor.execute_action(_LONG))
    assert script.entered.wait(_WAIT)
    started = time.monotonic()
    assert runs.stop() is True
    assert time.monotonic() - started < 5.0, "Stop waited for the worker"
    assert runs.stopping
    assert settle(runs, "task")
    assert len(errors) == 1 and was_stopped(errors[0]) and isinstance(errors[0], ExecutionStopped)
    assert finished == [None]           # the tab is free before `finished` is emitted
    assert script.calls == ["mark"]
    assert runs.stop() is False         # nothing left to stop


def test_destroying_the_owner_stops_its_script(script):
    owner = QWidget()
    runs = TabTask(owner)
    seen = []

    def work():
        seen.append(current_stop_token())
        return executor.execute_action(_LONG)

    assert runs.start_script(work)
    assert script.entered.wait(_WAIT)
    owner.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert _pump(lambda: seen[0].stopped)
    assert _pump(lambda: active_executions() == [])
    assert script.calls == ["mark"]


def test_ctrl_4_stops_every_running_script(script):
    first, second = QWidget(), QWidget()
    runs = [TabTask(first), TabTask(second)]
    for run in runs:
        assert run.start_script(lambda: executor.execute_action([["AC_sleep", {"seconds": 60}]]))
    assert _pump(lambda: len(active_executions()) == 2)
    assert stop_all_script_runs() == 2
    assert all(settle(run, "task") for run in runs)


def test_the_auto_click_stop_also_stops_scripts(script):
    from je_auto_control.gui._auto_click_tab import AutoClickTabMixin
    owner = QWidget()
    runs = TabTask(owner)
    errors = []
    runs.error.connect(errors.append)
    assert runs.start_script(lambda: executor.execute_action(_LONG))
    assert script.entered.wait(_WAIT)

    class _Host:
        timer = QTimer()

    AutoClickTabMixin._stop_auto_click(_Host())
    assert settle(runs, "task")
    assert errors and was_stopped(errors[0])


# --- re-entrancy: a script that drives this window ----------------------------------------------------------

def test_a_script_that_clicks_this_tabs_run_does_not_deadlock_or_nest(script, monkeypatch):
    """The script asks the GUI thread to run again and waits for the answer.

    On the GUI thread that wait could never be answered. Now the GUI thread
    is free: it answers (and refuses the nested run) while the script waits.
    """
    host = ScriptHost()
    answered = threading.Event()
    seen = []

    def click_run_again() -> str:
        def on_gui_thread() -> None:
            host._execute_manual_script()
            seen.append(host.script_result_text.toPlainText())
            answered.set()
        QTimer.singleShot(0, host, on_gui_thread)
        return "answered" if answered.wait(_WAIT) else "the GUI thread never answered"

    monkeypatch.setitem(executor.event_dict, "AC_fake_click_run", click_run_again)
    host.script_editor.setPlainText(json.dumps([["AC_fake_click_run"], ["AC_fake_after"]]))
    host._execute_manual_script()
    assert settle(host._script_runs, "task")
    assert seen == [_t("task_busy")]
    result = json.loads(host.script_result_text.toPlainText())
    assert list(result.values())[0] == "answered"
    assert script.calls == ["after"]    # one run, not two


def test_a_script_that_clicks_stop_stops_itself(script, monkeypatch):
    host = ScriptHost()

    def click_stop() -> None:
        QTimer.singleShot(0, host, host._stop_script)

    monkeypatch.setitem(executor.event_dict, "AC_fake_click_stop", click_stop)
    host.script_editor.setPlainText(json.dumps(
        [["AC_fake_click_stop"], ["AC_sleep", {"seconds": 60}], ["AC_fake_after"]]))
    host._execute_manual_script()
    assert settle(host._script_runs, "task")
    assert host.script_result_text.toPlainText() == _t("task_stopped")
    assert script.calls == []


# --- the script tab -----------------------------------------------------------------------------------------

def test_script_tab_runs_the_editor_a_file_and_a_folder(script, tmp_path):
    host = ScriptHost()
    host.script_editor.setPlainText('[["AC_fake_mark"]]')
    host._execute_manual_script()
    assert host.script_result_text.toPlainText() == _t("task_running")
    assert settle(host._script_runs, "task")
    assert "marked" in host.script_result_text.toPlainText()

    path = tmp_path / "one.json"
    path.write_text('[["AC_fake_mark"]]', encoding="utf-8")
    host.script_path_input.setText(str(path))
    host._execute_script()
    assert settle(host._script_runs, "task")
    assert "marked" in host.script_result_text.toPlainText()

    host.script_dir_input.setText(str(tmp_path))
    host._execute_dir()
    assert settle(host._script_runs, "task")
    assert "marked" in host.script_result_text.toPlainText()
    assert script.calls == ["mark"] * 3
    assert all(ident != threading.get_ident() for ident in script.threads)


def test_script_tab_stop_action(script):
    host = ScriptHost()
    host.script_editor.setPlainText(json.dumps(_LONG))
    host._execute_manual_script()
    assert script.entered.wait(_WAIT)
    host._stop_script()
    assert host.script_result_text.toPlainText() == _t("task_stopping")
    assert settle(host._script_runs, "task")
    assert host.script_result_text.toPlainText() == _t("task_stopped")
    host._stop_script()                 # with nothing running it changes nothing
    assert host.script_result_text.toPlainText() == _t("task_stopped")


def test_bad_json_in_the_editor_is_reported(script):
    host = ScriptHost()
    host.script_editor.setPlainText("[not json")
    host._execute_manual_script()
    assert settle(host._script_runs, "task")
    assert host.script_result_text.toPlainText().startswith("Error")


# --- record playback ----------------------------------------------------------------------------------------

def test_playback_runs_off_thread_shows_its_state_and_stops(script):
    host = RecordHost(_LONG)
    host._playback_record()
    assert _t("record_playing") in host.record_status_label.text()
    assert script.entered.wait(_WAIT)
    host._record_data.clear()           # the playback has its own copy
    host._playback_record()             # refused: nothing to play, and one is running
    host._stop_playback()
    assert settle(host._playback_runs, "task")
    assert _t("record_idle") in host.record_status_label.text()
    assert script.calls == ["mark"]
    assert script.boxes == ["No recorded data"]     # a stop is not an error box


def test_playback_to_the_end_returns_to_idle(script):
    host = RecordHost([["AC_fake_mark"]])
    host._playback_record()
    assert settle(host._playback_runs, "task")
    assert _t("record_idle") in host.record_status_label.text()
    assert script.calls == ["mark"] and script.boxes == []


# --- script builder -----------------------------------------------------------------------------------------

def _builder(steps):
    import je_auto_control.gui.script_builder.builder_tab as builder_tab
    tab = builder_tab.ScriptBuilderTab()
    for command, params in steps:
        tab._tree.add_step(builder_tab.Step(command=command, params=params))
    return tab


def test_builder_run_and_stop(script):
    tab = _builder([("AC_fake_mark", {})])
    tab._on_run()
    assert tab._result.toPlainText() == _t("task_running")
    assert settle(tab._runs, "task")
    assert "marked" in tab._result.toPlainText()

    tab = _builder([("AC_fake_mark", {}), ("AC_sleep", {"seconds": 60})])
    script.entered.clear()
    tab._on_run()
    assert script.entered.wait(_WAIT)
    tab._on_run()
    assert tab._result.toPlainText() == _t("task_busy")
    tab._on_stop()
    assert settle(tab._runs, "task")
    assert tab._result.toPlainText() == _t("task_stopped")
    assert script.boxes == []


def test_builder_with_no_steps_starts_nothing(script):
    tab = _builder([])
    tab._on_run()
    assert tab._runs.task is None and script.boxes == ["No steps to run"]


# --- LLM planner --------------------------------------------------------------------------------------------

def test_planner_run_and_stop(script):
    from je_auto_control.gui.llm_planner_tab import LLMPlannerTab
    tab = LLMPlannerTab()
    tab._on_run()
    assert tab._status.text() == _t("llm_no_plan") and tab._runs.task is None
    tab._planned_actions = [["AC_fake_mark"]]
    tab._on_run()
    assert tab._status.text() == _t("llm_running")
    assert settle(tab._runs, "task")
    assert tab._status.text() == _t("llm_run_done") and "marked" in tab._result_view.toPlainText()

    tab._planned_actions = list(_LONG)
    script.entered.clear()
    tab._on_run()
    assert script.entered.wait(_WAIT)
    tab._on_stop()
    assert settle(tab._runs, "task")
    assert tab._status.text() == _t("task_stopped")
    assert script.boxes == []
    assert "task_stop" in dict(tab.menu_actions())


# --- test suite ---------------------------------------------------------------------------------------------

def test_suite_run_and_stop(script):
    from je_auto_control.gui.test_suite_tab import TestSuiteTab
    tab = TestSuiteTab()
    tab._spec.setPlainText(json.dumps({"name": "s", "cases": [
        {"name": "ok", "actions": [["AC_fake_mark"]]}]}))
    tab._on_run()
    assert tab._summary.text() == _t("task_running")
    assert settle(tab._runs, "task")
    assert tab._table.rowCount() == 1 and tab._last_result is not None

    tab._spec.setPlainText(json.dumps({"name": "s", "cases": [
        {"name": "long", "actions": _LONG}, {"name": "never", "actions": [["AC_fake_after"]]}]}))
    script.entered.clear()
    tab._on_run()
    assert script.entered.wait(_WAIT)
    tab._on_stop()
    assert settle(tab._runs, "task")
    assert tab._summary.text() == _t("task_stopped")
    assert "after" not in script.calls      # the stop ended the suite, not one case
    assert tab._table.rowCount() == 1       # the earlier result is still shown

    tab._spec.setPlainText("{not json")
    tab._on_run()
    assert tab._runs.task is None and "{error}" not in tab._summary.text()


# --- ChatOps ------------------------------------------------------------------------------------------------

def test_chatops_dispatch_runs_off_thread(script, tmp_path):
    from je_auto_control.gui.chatops_tab import ChatOpsTab
    (tmp_path / "job.json").write_text('[["AC_fake_held"]]', encoding="utf-8")
    tab = ChatOpsTab()
    tab._script_root.setText(str(tmp_path))
    tab._command_input.setText("/run job.json")
    tab._on_send()
    assert script.entered.wait(_WAIT), tab._output.toPlainText()
    assert tab._runs.running
    tab._on_send()
    assert _t("task_busy") in tab._output.toPlainText()
    script.gate.set()
    assert settle(tab._runs, "task")
    assert "ran job.json" in tab._output.toPlainText()
    assert script.threads[0] != threading.get_ident()

    tab._command_input.setText("not a command")
    tab._on_send()
    assert settle(tab._runs, "task")
    assert "no match for: 'not a command'" in tab._output.toPlainText()
    assert "task_stop" in dict(tab.menu_actions())
