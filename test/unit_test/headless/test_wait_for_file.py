"""Headless tests for AC_wait_for_file / wait_until_file.

The file-size reader is injectable, so most cases are deterministic and
need no real filesystem; one case exercises the real default reader.
"""
import pytest

import je_auto_control as ac
from je_auto_control.utils.smart_waits.waits import wait_until_file


def _reader(values):
    """Return a stat_reader yielding ``values`` then repeating the last one."""
    seq = list(values)

    def read(_path):
        return seq.pop(0) if len(seq) > 1 else seq[0]
    return read


def test_succeeds_when_file_present():
    outcome = wait_until_file("f", stable_for_s=0, stat_reader=_reader([100]))
    assert outcome.succeeded is True
    assert outcome.reason == "file ready"


def test_succeeds_after_file_appears():
    outcome = wait_until_file(
        "f", stable_for_s=0, timeout_s=1.0, poll_interval_s=0.01,
        stat_reader=_reader([None, None, 50]))
    assert outcome.succeeded is True


def test_missing_file_times_out():
    outcome = wait_until_file(
        "f", timeout_s=0.2, poll_interval_s=0.02, stable_for_s=0,
        stat_reader=_reader([None]))
    assert outcome.succeeded is False
    assert "timeout" in outcome.reason


def test_min_size_gate_blocks_small_file():
    outcome = wait_until_file(
        "f", timeout_s=0.2, poll_interval_s=0.02, stable_for_s=0,
        min_size=10, stat_reader=_reader([3]))
    assert outcome.succeeded is False


def test_stability_requires_steady_size():
    outcome = wait_until_file(
        "f", timeout_s=1.0, poll_interval_s=0.02, stable_for_s=0.1,
        stat_reader=_reader([200]))
    assert outcome.succeeded is True
    assert outcome.elapsed_s >= 0.1


@pytest.mark.parametrize("kwargs", [
    {"timeout_s": 0}, {"poll_interval_s": 0}, {"stable_for_s": -1},
])
def test_validation_errors(kwargs):
    with pytest.raises(ValueError):
        wait_until_file("f", stat_reader=_reader([1]), **kwargs)


def test_default_reader_on_real_file(tmp_path):
    target = tmp_path / "download.bin"
    target.write_bytes(b"hello")
    outcome = wait_until_file(str(target), stable_for_s=0, timeout_s=1.0)
    assert outcome.succeeded is True


def test_facade_executor_and_mcp_wiring(tmp_path):
    target = tmp_path / "done.txt"
    target.write_text("ok", encoding="utf-8")
    assert ac.wait_until_file is wait_until_file
    assert "AC_wait_for_file" in ac.executor.known_commands()
    record = ac.execute_action(
        [["AC_wait_for_file", {"path": str(target), "stable_for_s": 0,
                               "timeout_s": 1.0}]])
    assert any("file ready" in str(value) for value in record.values())
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {tool.name for tool in build_default_tool_registry()}
    assert "ac_wait_for_file" in names
