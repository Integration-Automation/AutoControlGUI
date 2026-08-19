"""Tests for flow variable commands: read-file, http, transform, now,
random, assert-var."""
import datetime

import pytest

from je_auto_control.utils.exception.exceptions import (
    AutoControlAssertionException,
)
from je_auto_control.utils.executor import flow_data_commands
from je_auto_control.utils.executor.action_executor import Executor
from je_auto_control.utils.executor.flow_data_commands import (
    exec_assert_var, exec_http_to_var, exec_now_to_var, exec_random_to_var,
    exec_read_file_to_var, exec_transform_var,
)


def test_read_file_to_var(tmp_path):
    data = tmp_path / "data.txt"
    data.write_text("hello world", encoding="utf-8")
    executor = Executor()
    result = exec_read_file_to_var(executor, {"path": str(data), "var": "c"})
    assert result["length"] == 11
    assert executor.variables.get_value("c") == "hello world"


def test_http_to_var_stores_body(monkeypatch):
    import je_auto_control.utils.http_client.http_client as hc
    monkeypatch.setattr(hc, "http_request",
                        lambda *a, **k: {"status": 200, "text": "BODYTEXT"})
    executor = Executor()
    result = exec_http_to_var(executor, {"url": "https://x", "var": "resp"})
    assert result["status"] == 200
    assert executor.variables.get_value("resp") == "BODYTEXT"


def test_http_to_var_extracts_json_path(monkeypatch):
    import je_auto_control.utils.http_client.http_client as hc
    monkeypatch.setattr(
        hc, "http_request",
        lambda *a, **k: {"status": 200, "text": '{"data": [{"name": "Sam"}]}'})
    executor = Executor()
    exec_http_to_var(executor, {"url": "https://x", "var": "n",
                                "json_path": "data.0.name"})
    assert executor.variables.get_value("n") == "Sam"


def test_transform_var_upper_and_strip():
    executor = Executor()
    executor.variables.set("v", "  Hi There  ")
    exec_transform_var(executor, {"name": "v", "op": "strip"})
    assert executor.variables.get_value("v") == "Hi There"
    exec_transform_var(executor, {"name": "v", "op": "upper", "into": "u"})
    assert executor.variables.get_value("u") == "HI THERE"


def test_transform_var_regex_extract():
    executor = Executor()
    executor.variables.set("v", "Order #12345 confirmed")
    exec_transform_var(executor, {"name": "v", "op": "regex",
                                  "pattern": r"#(\d+)", "group": 1,
                                  "into": "id"})
    assert executor.variables.get_value("id") == "12345"


def test_transform_var_replace_and_slice():
    executor = Executor()
    executor.variables.set("v", "foo-bar-baz")
    exec_transform_var(executor, {"name": "v", "op": "replace",
                                  "find": "-", "replace_with": "_",
                                  "into": "r"})
    assert executor.variables.get_value("r") == "foo_bar_baz"
    exec_transform_var(executor, {"name": "v", "op": "slice",
                                  "start": 0, "end": 3, "into": "s"})
    assert executor.variables.get_value("s") == "foo"


def test_now_to_var_formats_injected_clock(monkeypatch):
    monkeypatch.setattr(flow_data_commands, "_now",
                        lambda: datetime.datetime(2026, 1, 2, 3, 4, 5))
    executor = Executor()
    result = exec_now_to_var(executor, {"format": "%Y-%m-%d", "var": "d"})
    assert result["value"] == "2026-01-02"
    assert executor.variables.get_value("d") == "2026-01-02"


def test_random_to_var_int_within_fixed_range():
    executor = Executor()
    exec_random_to_var(executor, {"kind": "int", "min": 1, "max": 1, "var": "r"})
    assert executor.variables.get_value("r") == 1


def test_random_to_var_choice():
    executor = Executor()
    exec_random_to_var(executor, {"kind": "choice", "choices": ["only"],
                                  "var": "c"})
    assert executor.variables.get_value("c") == "only"


def test_assert_var_passes_then_raises():
    executor = Executor()
    executor.variables.set("v", "Sam")
    result = exec_assert_var(executor, {"name": "v", "op": "eq",
                                        "value": "Sam"})
    assert result["passed"] is True
    with pytest.raises(AutoControlAssertionException):
        exec_assert_var(executor, {"name": "v", "op": "eq", "value": "Nope"})


def test_assert_var_regex_match():
    executor = Executor()
    executor.variables.set("v", "Order #12345")
    result = exec_assert_var(executor, {"name": "v", "op": "regex",
                                        "value": r"#\d+",
                                        "raise_on_fail": False})
    assert result["passed"] is True
