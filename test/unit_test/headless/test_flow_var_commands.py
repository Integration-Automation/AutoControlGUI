"""Tests for flow variable commands: read-file, http, transform."""
from je_auto_control.utils.executor import flow_control
from je_auto_control.utils.executor.action_executor import Executor
from je_auto_control.utils.executor.flow_control import (
    exec_http_to_var, exec_read_file_to_var, exec_transform_var,
)


def test_read_file_to_var(tmp_path):
    data = tmp_path / "data.txt"
    data.write_text("hello world", encoding="utf-8")
    executor = Executor()
    result = exec_read_file_to_var(executor, {"path": str(data), "var": "c"})
    assert result["length"] == 11
    assert executor.variables.get_value("c") == "hello world"


def test_http_to_var_stores_body(monkeypatch):
    monkeypatch.setattr(flow_control, "_http_get",
                        lambda url, method, timeout: (200, "BODYTEXT"))
    executor = Executor()
    result = exec_http_to_var(executor, {"url": "https://x", "var": "resp"})
    assert result["status"] == 200
    assert executor.variables.get_value("resp") == "BODYTEXT"


def test_http_to_var_extracts_json_path(monkeypatch):
    monkeypatch.setattr(
        flow_control, "_http_get",
        lambda url, method, timeout: (200, '{"data": [{"name": "Sam"}]}'))
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
