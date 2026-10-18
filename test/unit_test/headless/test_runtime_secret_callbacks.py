"""Callback owners mask errors through their final logging without changing results."""
import io
import logging

import pytest

from je_auto_control.utils.executor.action_executor import executor
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.secrets import default_secret_manager

FAKE = "fake-callback-private-value"
PROBE = "AC_callback_secret_probe"


@pytest.fixture
def output(monkeypatch):
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    autocontrol_logger.addHandler(handler)
    monkeypatch.setattr(default_secret_manager, "get", lambda name: FAKE)
    monkeypatch.setitem(executor.event_dict, PROBE, lambda value: value)
    try:
        yield stream
    finally:
        autocontrol_logger.removeHandler(handler)
        handler.close()


def _resolve():
    record = executor.execute_action([[PROBE, {"value": "${secrets.LOGIN}"}]])
    return next(iter(record.values()))


def _fail(*_args):
    value = _resolve()
    raise RuntimeError("private callback failure: " + value)


@pytest.mark.parametrize("phase", ["matcher", "handler"])
def test_watchdog_masks_both_detection_and_action_failures(output, phase):
    from je_auto_control.utils.watchdog.popup_watchdog import PopupWatchdog, WatchdogRule
    owner = PopupWatchdog()
    owner.add_rule(WatchdogRule("private", _fail if phase == "matcher" else lambda: True, _fail))
    assert owner.check_once() == 0
    assert FAKE not in output.getvalue() and "private callback failure: ***" in output.getvalue()


@pytest.mark.parametrize("phase", ["predicate", "handler"])
def test_observer_masks_predicate_and_handler_failures(output, phase):
    from je_auto_control.utils.observer.observer import ScreenObserver
    owner = ScreenObserver()
    owner.add("private", _fail if phase == "predicate" else lambda: True, _fail)
    events = owner.poll_once()
    assert len(events) == (0 if phase == "predicate" else 1)
    assert FAKE not in output.getvalue() and "private callback failure: ***" in output.getvalue()


@pytest.mark.parametrize("phase", ["trigger", "callback"])
def test_callback_executor_retains_the_trigger_mask_through_callback_logging(output, phase):
    from je_auto_control.utils.callback.callback_function_executor import CallbackFunctionExecutor
    owner = CallbackFunctionExecutor()
    owner.event_dict["AC_probe"] = _fail if phase == "trigger" else _resolve
    def callback():
        raise RuntimeError("private callback failure: " + FAKE)
    result = owner.callback_function("AC_probe", callback)
    assert result == (None if phase == "trigger" else FAKE)
    assert FAKE not in output.getvalue() and "private callback failure: ***" in output.getvalue()


def test_callback_calls_do_not_retain_an_earlier_invocations_mask(output):
    from je_auto_control.utils.callback.callback_function_executor import CallbackFunctionExecutor
    owner = CallbackFunctionExecutor()
    owner.event_dict["AC_resolve"] = _resolve
    owner.event_dict["AC_literal"] = lambda: FAKE
    assert owner.callback_function("AC_resolve", lambda: None) == FAKE
    assert FAKE not in output.getvalue()
    assert owner.callback_function("AC_literal", lambda: autocontrol_logger.info("unrelated: %s", FAKE)) == FAKE
    assert "unrelated: " + FAKE in output.getvalue()


@pytest.mark.parametrize("kind", ["watchdog", "observer"])
def test_independent_rules_have_independent_masks(output, kind):
    def unrelated(*_args):
        autocontrol_logger.info("unrelated rule: %s", FAKE)
        return False
    if kind == "watchdog":
        from je_auto_control.utils.watchdog.popup_watchdog import PopupWatchdog, WatchdogRule
        owner = PopupWatchdog()
        owner.add_rule(WatchdogRule("private", _fail, lambda: None))
        owner.add_rule(WatchdogRule("unrelated", unrelated, lambda: None))
        owner.check_once()
    else:
        from je_auto_control.utils.observer.observer import ScreenObserver
        owner = ScreenObserver()
        owner.add("private", _fail, lambda *_args: None)
        owner.add("unrelated", unrelated, lambda *_args: None)
        owner.poll_once()
    assert "private callback failure: ***" in output.getvalue()
    assert "unrelated rule: " + FAKE in output.getvalue()


def test_direct_observer_callback_boundary_also_masks_its_own_error(output):
    from je_auto_control.utils.observer.observer import ScreenObserver, WatchRule
    owner = ScreenObserver()
    owner._fire(WatchRule("private", lambda: True, _fail), "appear", True)
    assert FAKE not in output.getvalue() and "private callback failure: ***" in output.getvalue()


@pytest.mark.parametrize("kind", ["watchdog", "observer"])
def test_detection_and_callback_share_the_same_mask_until_diagnostics_finish(output, kind):
    def later_failure(*_args):
        raise RuntimeError("later callback failure: " + FAKE)
    if kind == "watchdog":
        from je_auto_control.utils.watchdog.popup_watchdog import PopupWatchdog, WatchdogRule
        owner = PopupWatchdog()
        owner.add_rule(WatchdogRule("private", lambda: bool(_resolve()), later_failure))
        assert owner.check_once() == 0
    else:
        from je_auto_control.utils.observer.observer import ScreenObserver
        owner = ScreenObserver()
        owner.add("private", _resolve, later_failure)
        assert len(owner.poll_once()) == 1
    assert FAKE not in output.getvalue() and "later callback failure: ***" in output.getvalue()
