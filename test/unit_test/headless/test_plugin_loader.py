"""Tests for the plugin loader."""
import pytest

from je_auto_control.utils.plugin_loader.plugin_loader import (
    discover_plugin_commands, load_plugin_directory, load_plugin_file,
    register_plugin_commands,
)


PLUGIN_SOURCE = """
from_ac_prefix = "not a callable"

def AC_hello(ctx=None):
    return "hello"

def AC_echo(args=None):
    return args

def not_exported():
    return "hidden"

AC_non_callable = 42
"""


def _write_plugin(tmp_path, name, body=PLUGIN_SOURCE):
    file_path = tmp_path / name
    file_path.write_text(body, encoding="utf-8")
    return str(file_path)


def test_load_plugin_file_returns_ac_callables(tmp_path):
    path = _write_plugin(tmp_path, "sample.py")
    commands = load_plugin_file(path)
    assert set(commands.keys()) == {"AC_hello", "AC_echo"}
    assert commands["AC_hello"]() == "hello"
    assert commands["AC_echo"]({"x": 1}) == {"x": 1}


def test_load_plugin_directory_merges_files_and_skips_underscore(tmp_path):
    _write_plugin(tmp_path, "a.py", "def AC_a():\n    return 'a'\n")
    _write_plugin(tmp_path, "b.py", "def AC_b():\n    return 'b'\n")
    _write_plugin(tmp_path, "_private.py", "def AC_hidden():\n    return 'x'\n")
    commands = load_plugin_directory(str(tmp_path))
    assert set(commands.keys()) == {"AC_a", "AC_b"}


def test_load_plugin_file_raises_for_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_plugin_file(str(tmp_path / "missing.py"))


def test_load_plugin_directory_raises_when_not_a_dir(tmp_path):
    path = tmp_path / "not_a_dir.py"
    path.write_text("", encoding="utf-8")
    with pytest.raises(NotADirectoryError):
        load_plugin_directory(str(path))


def test_register_plugin_commands_adds_and_removes_cleanly(tmp_path):
    from je_auto_control.utils.executor.action_executor import executor
    path = _write_plugin(tmp_path, "reg.py")
    commands = load_plugin_file(path)
    names = register_plugin_commands(commands)
    try:
        assert "AC_hello" in executor.event_dict
        assert "AC_echo" in executor.event_dict
        assert names == sorted(["AC_hello", "AC_echo"])
    finally:
        for name in names:
            executor.event_dict.pop(name, None)


def test_discover_ignores_non_callable_ac_attribute():
    class Module:
        AC_value = 42  # noqa: N815  # reason: AC_* is the plugin contract

        @staticmethod
        def AC_run():  # noqa: N802  # reason: AC_* is the plugin contract
            return 1

    found = discover_plugin_commands(Module)
    assert "AC_value" not in found
    assert "AC_run" in found
