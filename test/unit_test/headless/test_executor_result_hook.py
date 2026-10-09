"""A caller can be told the result of every command one run executes, nested ones included.

A block command records its own summary, so the result of a command in its
body is in no execution record. ``execute_action(..., result_callback=...)``
/ ``observe_results`` report it, for one run on one thread, without changing
what the run returns or logs.

Every command here is a fake registered on a private executor; nothing drives
an input device.
"""
import logging
import threading

import pytest

from je_auto_control.utils.exception.exceptions import AutoControlActionException
from je_auto_control.utils.executor import action_executor, result_hook
from je_auto_control.utils.executor.action_executor import Executor, execute_action
from je_auto_control.utils.executor.result_hook import StepPosition, observe_results
from je_auto_control.utils.logging.logging_instance import autocontrol_logger


@pytest.fixture()
def runner():
    """An executor with three fake commands: one answers, one fails, one hands back its argument."""
    executor = Executor()
    executor.event_dict["AC_fake_issue"] = lambda name="n": {"token": f"issued-{name}"}
    executor.event_dict["AC_fake_echo"] = lambda value=None: value

    def fail():
        raise AutoControlActionException("nope")
    executor.event_dict["AC_fake_fail"] = fail
    return executor


def _recorder():
    seen = []

    def hook(command, arguments, result, path):
        seen.append((command, arguments, result, path))
    return seen, hook


def test_a_top_level_command_is_reported_with_its_arguments_result_and_position(runner):
    seen, hook = _recorder()
    record = runner.execute_action(
        [["AC_fake_echo", {"value": 1}], ["AC_fake_issue", {"name": "a"}], ["AC_fake_echo"]],
        result_callback=hook)
    assert seen == [
        ("AC_fake_echo", {"value": 1}, 1, (StepPosition(1, 1, "AC_fake_echo"),)),
        ("AC_fake_issue", {"name": "a"}, {"token": "issued-a"}, (StepPosition(1, 2, "AC_fake_issue"),)),
        ("AC_fake_echo", None, None, (StepPosition(1, 3, "AC_fake_echo"),)),
    ]
    assert seen[1][2] is list(record.values())[1], "the hook is handed the recorded object, not a copy"


def test_a_command_in_a_loop_is_reported_once_per_iteration_with_its_path(runner):
    seen, hook = _recorder()
    record = runner.execute_action([
        ["AC_fake_echo", {"value": 0}],
        ["AC_loop", {"times": 3, "body": [["AC_fake_echo", {"value": 9}], ["AC_fake_issue"]]}],
    ], result_callback=hook)
    issued = [(result, path) for command, _arguments, result, path in seen if command == "AC_fake_issue"]
    assert issued == [
        ({"token": "issued-n"}, (StepPosition(1, 2, "AC_loop"), StepPosition(run, 2, "AC_fake_issue")))
        for run in (1, 2, 3)]
    assert seen[-1][0] == "AC_loop" and seen[-1][3] == (StepPosition(1, 2, "AC_loop"),), \
        "the block itself is reported last, at its own position"
    assert "issued-n" not in repr(record), "the block still records only its summary"


def test_the_path_names_every_enclosing_block(runner):
    seen, hook = _recorder()
    runner.execute_action([["AC_loop", {"times": 2, "body": [
        ["AC_try", {"body": [["AC_fake_issue", {"name": "deep"}]], "catch": []}]]}]],
        result_callback=hook)
    paths = [path for command, _arguments, _result, path in seen if command == "AC_fake_issue"]
    assert paths == [
        (StepPosition(1, 1, "AC_loop"), StepPosition(run, 1, "AC_try"), StepPosition(1, 1, "AC_fake_issue"))
        for run in (1, 2)]


def test_a_failed_command_and_a_dry_run_report_nothing(runner):
    seen, hook = _recorder()
    record = runner.execute_action([["AC_fake_fail"], ["AC_fake_issue"]], result_callback=hook)
    assert [entry[0] for entry in seen] == ["AC_fake_issue"]
    assert seen[0][3] == (StepPosition(1, 2, "AC_fake_issue"),), "a failure still counts as a position"
    assert "nope" in list(record.values())[0]
    del seen[:]
    runner.execute_action([["AC_fake_issue"]], dry_run=True, result_callback=hook)
    assert seen == []


def test_the_run_returns_and_logs_the_same_with_and_without_a_hook(runner, caplog):
    actions = [["AC_fake_issue", {"name": "a"}],
               ["AC_loop", {"times": 2, "body": [["AC_fake_issue", {"name": "b"}]]}],
               ["AC_fake_fail"]]

    def run(**keywords):
        caplog.clear()
        autocontrol_logger.addHandler(caplog.handler)
        try:
            with caplog.at_level(logging.DEBUG, logger=autocontrol_logger.name):
                record = runner.execute_action(actions, **keywords)
        finally:
            autocontrol_logger.removeHandler(caplog.handler)
        return record, [entry.getMessage() for entry in caplog.records]

    plain_record, plain_log = run()
    seen, hook = _recorder()
    hooked_record, hooked_log = run(result_callback=hook)
    assert hooked_record == plain_record and hooked_log == plain_log
    assert len(seen) == 4 and "issued-" not in "\n".join(hooked_log)


def test_a_hook_that_raises_does_not_fail_the_run_and_only_its_type_is_logged(runner, caplog):
    def hook(_command, _arguments, result, _path):
        raise ValueError(f"saw {result}")

    autocontrol_logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.DEBUG, logger=autocontrol_logger.name):
            record = runner.execute_action([["AC_fake_issue"], ["AC_fake_echo", {"value": 2}]],
                                           raise_on_error=True, result_callback=hook)
    finally:
        autocontrol_logger.removeHandler(caplog.handler)
    assert list(record.values()) == [{"token": "issued-n"}, 2]
    logged = "\n".join(entry.getMessage() for entry in caplog.records)
    assert "result hook raised ValueError" in logged
    assert "issued-n" not in logged and "saw" not in logged


def test_the_hook_ends_with_its_run_and_with_its_block(runner):
    seen, hook = _recorder()
    runner.execute_action([["AC_fake_issue"]], result_callback=hook)
    runner.execute_action([["AC_fake_issue"]])
    assert len(seen) == 1, "the next run of the same thread is not observed"
    with observe_results(hook):
        runner.execute_action([["AC_fake_issue"]])
        runner.execute_action([["AC_fake_issue"]])
    assert [entry[3] for entry in seen[1:]] == [
        (StepPosition(1, 1, "AC_fake_issue"),), (StepPosition(2, 1, "AC_fake_issue"),)], \
        "inside one block the second list is run 2"
    runner.execute_action([["AC_fake_issue"]])
    assert len(seen) == 3
    assert result_hook.enter_list() is None, "nothing is left registered"


def test_the_hook_ends_when_the_run_raises(runner):
    seen, hook = _recorder()
    with pytest.raises(AutoControlActionException):
        runner.execute_action([["AC_loop", {"times": 1, "body": [["AC_fake_fail"]]}]],
                              raise_on_error=True, result_callback=hook)
    runner.execute_action([["AC_fake_issue"]])
    assert seen == [] and result_hook.enter_list() is None


def test_another_thread_and_a_thread_started_by_the_run_are_not_observed(runner):
    seen, hook = _recorder()
    started = threading.Event()
    release = threading.Event()
    other: list = []

    def elsewhere():
        started.wait(10)
        other.append(runner.execute_action([["AC_fake_issue", {"name": "other"}]]))
        release.set()

    def spawn(value=None):
        child = threading.Thread(
            target=lambda: other.append(runner.execute_action([["AC_fake_issue", {"name": "child"}]])))
        child.start()
        child.join(10)
        started.set()
        release.wait(10)
        return value

    runner.event_dict["AC_fake_spawn"] = spawn
    thread = threading.Thread(target=elsewhere)
    thread.start()
    runner.execute_action([["AC_fake_spawn", {"value": 1}]], result_callback=hook)
    thread.join(10)
    assert len(other) == 2, "both other threads really ran a command during the observed run"
    assert [entry[0] for entry in seen] == ["AC_fake_spawn"]


def test_a_parallel_branch_runs_on_its_own_thread_and_is_not_reported(runner):
    seen, hook = _recorder()
    record = execute_action(
        [["AC_parallel", {"branches": [[["AC_get_var", {"name": "missing", "default": 5}]]]}]],
        result_callback=hook)
    assert [entry[0] for entry in seen] == ["AC_parallel"]
    assert seen[0][2] is list(record.values())[0], "what the branch answered is in the block's result"


def test_no_hook_means_no_frame_and_no_call(runner, monkeypatch):
    def refuse(*_args, **_kwargs):
        raise AssertionError("no path is built when nothing is registered")
    monkeypatch.setattr(result_hook, "StepPosition", refuse)
    assert result_hook.enter_list() is None
    result_hook.leave_list(None)
    result_hook.report_result(["AC_fake_issue"], {"token": "x"})
    assert list(runner.execute_action([["AC_fake_issue"]]).values()) == [{"token": "issued-n"}]


def test_a_callback_that_cannot_be_called_is_refused_before_anything_runs(runner):
    ran: list = []
    runner.event_dict["AC_fake_note"] = lambda: ran.append(1)
    with pytest.raises(AutoControlActionException):
        runner.execute_action([["AC_fake_note"]], result_callback="not a function")
    assert ran == []
    with pytest.raises(AutoControlActionException):
        with observe_results(None):
            ran.append(2)
    assert ran == []


def test_step_callback_keeps_its_contract_beside_the_result_hook(runner):
    """Before each top-level action, with the action alone; not handed to nested bodies."""
    before: list = []
    seen, hook = _recorder()
    actions = [["AC_loop", {"times": 2, "body": [["AC_fake_issue"]]}], ["AC_fake_echo"]]
    runner.execute_action(actions, step_callback=before.append, result_callback=hook)
    assert before == actions
    assert [entry[0] for entry in seen] == ["AC_fake_issue", "AC_fake_issue", "AC_loop", "AC_fake_echo"]


def test_the_module_function_forwards_the_keyword():
    seen, hook = _recorder()
    execute_action([["AC_get_var", {"name": "missing", "default": 3}]], result_callback=hook)
    assert [(entry[0], entry[2]) for entry in seen] == [("AC_get_var", 3)]
    assert "result_callback" in action_executor.execute_action.__kwdefaults__
