"""Headless tests for AC_wait_for_process / wait_until_process.

The process lister is injectable, so the tests need neither psutil nor
real processes.
"""
import pytest

import je_auto_control as ac
from je_auto_control.utils.smart_waits.waits import wait_until_process


def _lister(values):
    """Return a lister yielding ``values`` then repeating the last one."""
    seq = list(values)

    def find(_name):
        return seq.pop(0) if len(seq) > 1 else seq[0]
    return find


def test_succeeds_when_process_present():
    outcome = wait_until_process("chrome", lister=_lister([["chrome.exe"]]))
    assert outcome.succeeded is True
    assert "appeared" in outcome.reason


def test_succeeds_after_process_appears():
    outcome = wait_until_process(
        "svc", timeout_s=1.0, poll_interval_s=0.01,
        lister=_lister([[], [], ["svc"]]))
    assert outcome.succeeded is True
    assert outcome.samples_taken >= 3


def test_succeeds_when_process_absent():
    outcome = wait_until_process("gone", present=False, lister=_lister([[]]))
    assert outcome.succeeded is True
    assert "exited" in outcome.reason


def test_times_out_when_never_present():
    outcome = wait_until_process(
        "missing", timeout_s=0.2, poll_interval_s=0.02, lister=_lister([[]]))
    assert outcome.succeeded is False
    assert "timeout" in outcome.reason


@pytest.mark.parametrize("kwargs", [{"timeout_s": 0}, {"poll_interval_s": 0}])
def test_validation_errors(kwargs):
    with pytest.raises(ValueError):
        wait_until_process("x", lister=_lister([["x"]]), **kwargs)


def test_facade_executor_and_mcp_wiring(monkeypatch):
    import je_auto_control.utils.smart_waits.waits as waits_module
    monkeypatch.setattr(waits_module, "_default_process_lister",
                        lambda _name: [])  # no real psutil / processes
    assert ac.wait_until_process is wait_until_process
    assert "AC_wait_for_process" in ac.executor.known_commands()
    record = ac.execute_action(
        [["AC_wait_for_process", {"name": "anything", "present": False,
                                  "timeout_s": 0.5, "poll_interval_s": 0.02}]])
    assert any("exited" in str(v) for v in record.values())
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {tool.name for tool in build_default_tool_registry()}
    assert "ac_wait_for_process" in names
