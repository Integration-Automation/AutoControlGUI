"""Resolved vault values stay out of application logs without changing outcomes."""
import io
import logging
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from je_auto_control.utils.executor.action_executor import executor
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.secrets import default_secret_manager

PROBE = "AC_runtime_secret_probe"
FAKE = "fake-runtime-private-value"


@pytest.fixture
def output(monkeypatch):
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    autocontrol_logger.addHandler(handler)
    monkeypatch.setattr(default_secret_manager, "get", lambda name: FAKE)
    try:
        yield stream
    finally:
        autocontrol_logger.removeHandler(handler)
        handler.close()


def test_outcomes_and_command_logs_are_scrubbed_without_changing_return_values(output, monkeypatch):
    def probe(value):
        autocontrol_logger.info("command received %s", value)
        return {"echo": value}
    monkeypatch.setitem(executor.event_dict, PROBE, probe)
    result = executor.execute_action([[PROBE, {"value": "${secrets.LOGIN}"}]])
    assert next(iter(result.values())) == {"echo": FAKE}
    assert FAKE not in output.getvalue()
    assert "command received ***" in output.getvalue()
    assert "${secrets.LOGIN}" in output.getvalue()


@pytest.mark.parametrize("strict", [False, True])
def test_errors_and_tracebacks_are_scrubbed(output, monkeypatch, strict):
    def fail(value):
        try:
            raise ValueError("failure: " + value)
        except ValueError:
            autocontrol_logger.exception("failed with %r", value)
            raise
    monkeypatch.setitem(executor.event_dict, PROBE, fail)
    actions = [[PROBE, {"value": "${secrets.LOGIN}"}]]
    if strict:
        with pytest.raises(ValueError, match=FAKE):
            executor.execute_action(actions, raise_on_error=True)
    else:
        assert FAKE in next(iter(executor.execute_action(actions).values()))
    assert FAKE not in output.getvalue()
    assert "Traceback" in output.getvalue() and "ValueError" in output.getvalue()


@pytest.mark.parametrize("block", ["loop", "parallel", "dag"])
def test_values_learned_by_nested_or_worker_actions_also_scrub_parent_logs(output, monkeypatch, block):
    monkeypatch.setitem(executor.event_dict, PROBE, lambda value: value)
    body = [[PROBE, {"value": "${secrets.LOGIN}"}]]
    scripts = {
        "loop": [["AC_loop", {"times": 1, "body": body}]],
        "parallel": [["AC_parallel", {"branches": [body]}]],
        "dag": [["AC_run_dag", {"definition": {"nodes": [{"id": "one", "actions": body}]}}]],
    }
    result = executor.execute_action(scripts[block])
    if block == "loop":
        assert next(iter(result.values())) == 1
    else:
        assert FAKE in str(result)
    assert FAKE not in output.getvalue()


def test_run_end_clears_the_mask_and_failure_restores_the_binding(output, monkeypatch):
    def fail(value):
        raise ValueError(value)
    monkeypatch.setitem(executor.event_dict, PROBE, fail)
    with pytest.raises(ValueError):
        executor.execute_action([[PROBE, {"value": "${secrets.LOGIN}"}]], raise_on_error=True)
    assert FAKE not in output.getvalue()
    autocontrol_logger.info("after run: %s", FAKE)
    assert "after run: " + FAKE in output.getvalue()


def test_concurrent_runs_do_not_share_their_secret_masks(output, monkeypatch):
    barrier = Barrier(2)
    monkeypatch.setattr(default_secret_manager, "get", lambda name: "private-" + name)
    def probe(value):
        barrier.wait(timeout=5)
        other = "private-RIGHT" if value == "private-LEFT" else "private-LEFT"
        autocontrol_logger.info("own=%s other=%s", value, other)
        return value
    monkeypatch.setitem(executor.event_dict, PROBE, probe)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda name: executor.execute_action(
            [[PROBE, {"value": "${secrets." + name + "}"}]]), ["LEFT", "RIGHT"]))
    assert len(results) == 2
    assert "own=*** other=private-RIGHT" in output.getvalue()
    assert "own=*** other=private-LEFT" in output.getvalue()


def test_escaped_secret_representations_are_scrubbed(output, monkeypatch):
    value = "fake\\path\n'quoted'\t終"
    monkeypatch.setattr(default_secret_manager, "get", lambda name: value)
    monkeypatch.setitem(executor.event_dict, PROBE, lambda value: value)
    result = executor.execute_action([[PROBE, {"value": "${secrets.LOGIN}"}]])
    assert next(iter(result.values())) == value
    assert value not in output.getvalue()
    assert repr(value)[1:-1] not in output.getvalue()


@pytest.mark.parametrize("strict", [False, True])
def test_parallel_failure_handler_keeps_its_traceback_and_mask(output, monkeypatch, strict):
    from je_auto_control.utils.exception.exceptions import AutoControlActionException
    def fail(value):
        raise ValueError(value)
    monkeypatch.setitem(executor.event_dict, PROBE, fail)
    actions = [["AC_parallel", {"branches": [[[PROBE, {"value": "${secrets.LOGIN}"}]]]}]]
    if strict:
        with pytest.raises(AutoControlActionException):
            executor.execute_action(actions, raise_on_error=True)
        assert "Traceback" in output.getvalue()
    else:
        executor.execute_action(actions)
    assert FAKE not in output.getvalue()


def test_closed_mask_cannot_retain_values_via_an_inherited_binding():
    from je_auto_control.utils.logging.secret_scope import (
        bound_secret_scope, current_secret_scope, remember_secret, secret_log_scope,
    )
    with secret_log_scope():
        scope = current_secret_scope()
        remember_secret(FAKE)
        assert scope.scrub(FAKE) == "***"
    assert not scope.active and not scope.has_values
    with bound_secret_scope(scope):
        remember_secret("later-private-value")
        assert current_secret_scope() is None
        assert scope.scrub(FAKE) == FAKE


def test_mask_uses_longest_match_and_preserves_empty_secret_behavior():
    from je_auto_control.utils.logging.secret_scope import SecretLogScope
    scope = SecretLogScope()
    for value in ["", "ab", "abc", "***"]:
        scope.remember(value)
    assert scope.scrub("abc-ab-***-visible") == "***-***-***-visible"
    scope.close()


def test_filter_masks_cached_exception_stack_and_unformattable_records():
    from je_auto_control.utils.logging.secret_scope import SecretLogFilter, remember_secret, secret_log_scope
    with secret_log_scope():
        remember_secret(FAKE)
        record = logging.LogRecord("AutoControlGUI", logging.INFO, __file__, 0, "%s %s", (FAKE,), None)
        record.exc_text = "cached " + FAKE
        record.stack_info = "stack " + FAKE
        assert SecretLogFilter().filter(record)
        assert record.getMessage() == "<unformattable application log record>"
        assert record.exc_text == "cached ***" and record.stack_info == "stack ***"


def test_an_unformattable_outcome_cannot_abort_execution(output, monkeypatch):
    class Unformattable:
        def __str__(self):
            raise RuntimeError("formatter failed: " + FAKE)
    value = Unformattable()
    monkeypatch.setitem(executor.event_dict, PROBE, lambda value: value)
    # Resolve first, then return an opaque outcome while the run's mask is active.
    monkeypatch.setitem(executor.event_dict, "AC_opaque_log_probe", lambda: value)
    result = executor.execute_action([
        [PROBE, {"value": "${secrets.LOGIN}"}], ["AC_opaque_log_probe"],
    ])
    assert list(result.values())[-1] is value
    assert FAKE not in output.getvalue()
    assert "<unformattable application log record>" in output.getvalue()
