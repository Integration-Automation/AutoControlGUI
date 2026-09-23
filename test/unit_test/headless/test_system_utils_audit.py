"""Regression tests for the system-utility defects of the 2026-09-23 audit.

On Windows, ``AC_shell_command`` / ``ac_shell`` split command strings with
non-POSIX ``shlex``, which kept quote characters in argv; the documented
``command`` keyword was refused. A second ``keep_awake_on`` cancelled itself,
and a nested ``keep_awake`` reset the outer one. The clipboard setters leaked
their memory handle on every failure. ``FilePathTrigger`` never fired on
creation, ``wait_until_file`` accepted directories and NaN, a missing psutil
aborted scripts as a failed assertion, killing a process that exits mid-kill
raised, and ``.env`` values containing U+2028 were cut. Every OS call here is
faked except child processes the tests start themselves.
"""
import os
import sys

import pytest

from je_auto_control.utils.dotenv.dotenv import dump_dotenv, parse_dotenv
from je_auto_control.utils.exception.exceptions import (
    AutoControlAssertionException, AutoControlException,
)
from je_auto_control.utils.idle_keepawake import idle_keepawake
from je_auto_control.utils.shell_process.shell_exec import command_args
from je_auto_control.utils.smart_waits.waits import wait_until_file
from je_auto_control.utils.triggers.trigger_engine import FilePathTrigger


@pytest.mark.skipif(sys.platform != "win32", reason="Windows command-line handling")
def test_a_windows_command_line_is_passed_whole():
    line = '"C:\\Program Files\\app.exe" "a b"'
    assert command_args(line) == line


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX splitting")
def test_a_posix_command_line_is_split():
    assert command_args('prog "a b" c') == ["prog", "a b", "c"]


def test_quoted_arguments_reach_the_child_unquoted():
    import subprocess  # nosec B404  # reason: runs this interpreter only
    script = "import sys; print('|'.join(sys.argv[1:]))"
    line = f'"{sys.executable}" -c "{script}" "a b" c'
    argv = command_args(line)
    out = subprocess.run(argv, capture_output=True, text=True, check=True, timeout=30)  # nosec B603  # nosemgrep
    assert out.stdout.strip() == "a b|c"


def test_shell_command_accepts_the_command_keyword(monkeypatch):
    from je_auto_control.utils.shell_process import shell_exec
    started = []
    monkeypatch.setattr(shell_exec.subprocess, "Popen",
                        lambda args, **kwargs: started.append(args) or _FakeProcess())
    manager = shell_exec.ShellManager()
    manager.exec_shell(command=["prog", "x"])
    assert started == [["prog", "x"]]


class _FakeProcess:
    stdout = stderr = None
    returncode = 0

    def poll(self):
        return 0

    def terminate(self):
        pass

    def wait(self, timeout=None):
        return 0


class _Kernel32:
    """SetThreadExecutionState that returns the previous state, like the real one."""

    def __init__(self):
        self.state, self.calls = 0x80000000, []

    def SetThreadExecutionState(self, flags):  # noqa: N802 - Win32 name
        previous, self.state = self.state, int(getattr(flags, "value", flags))
        self.calls.append(self.state)
        return previous


@pytest.fixture
def kernel32(monkeypatch):
    fake = _Kernel32()
    monkeypatch.setattr(idle_keepawake, "ctypes",
                        type("C", (), {"windll": type("W", (), {"kernel32": fake}),
                                       "c_uint": staticmethod(lambda v: v)}))
    monkeypatch.setattr(idle_keepawake, "_keepawake_backend", lambda: "SetThreadExecutionState")
    monkeypatch.setattr(idle_keepawake, "_ACTIVE", [])
    return fake


def test_a_second_keep_awake_on_stays_in_force(kernel32):
    idle_keepawake.keep_awake_on(display=False)
    idle_keepawake.keep_awake_on(display=True)
    assert kernel32.state & 0x3 == 0x3


def test_a_nested_keep_awake_restores_the_outer_state(kernel32):
    with idle_keepawake.keep_awake(display=True):
        with idle_keepawake.keep_awake(display=False):
            pass
        assert kernel32.state & 0x3 == 0x3
    assert kernel32.state == 0x80000000


@pytest.mark.skipif(sys.platform != "win32", reason="the Win32 clipboard API loads on Windows only")
def test_the_clipboard_handle_is_freed_when_setting_fails(monkeypatch):
    from je_auto_control.utils.clipboard import win32_clipboard_api as api
    freed = []

    class _User32:
        def OpenClipboard(self, _hwnd):  # noqa: N802 - Win32 name
            return True

        def CloseClipboard(self):  # noqa: N802
            return True

        def EmptyClipboard(self):  # noqa: N802
            return True

        def SetClipboardData(self, _fmt, _handle):  # noqa: N802
            return 0

    import ctypes
    buffer = ctypes.create_string_buffer(64)

    class _Kernel:
        def GlobalAlloc(self, _flags, _size):  # noqa: N802
            return 1234

        def GlobalLock(self, _handle):  # noqa: N802
            return ctypes.addressof(buffer)

        def GlobalUnlock(self, _handle):  # noqa: N802
            return True

        def GlobalFree(self, handle):  # noqa: N802
            freed.append(handle)

    monkeypatch.setattr(api, "clipboard_api", lambda: (_User32(), _Kernel()))
    with pytest.raises(RuntimeError):
        api.set_clipboard_format(49999, b"x")
    assert freed == [1234]


def test_a_created_file_fires_the_trigger(tmp_path):
    path = tmp_path / "drop.txt"
    trigger = FilePathTrigger(trigger_id="t", script_path="s.json", watch_path=str(path))
    assert trigger.is_fired() is False
    path.write_text("x", encoding="utf-8")
    assert trigger.is_fired() is True
    assert trigger.is_fired() is False


def test_a_replacement_with_an_older_mtime_fires(tmp_path):
    path = tmp_path / "drop.txt"
    path.write_text("x", encoding="utf-8")
    trigger = FilePathTrigger(trigger_id="t", script_path="s.json", watch_path=str(path))
    trigger.is_fired()
    os.utime(path, (1_000_000, 1_000_000))
    assert trigger.is_fired() is True


def test_waiting_for_a_file_does_not_accept_a_directory(tmp_path):
    result = wait_until_file(str(tmp_path), timeout_s=0.3, poll_interval_s=0.05,
                             stable_for_s=0.0, min_size=0)
    assert result.succeeded is False


def test_a_nan_timeout_is_refused():
    with pytest.raises(ValueError):
        wait_until_file("nope", timeout_s=float("nan"))


def test_a_missing_psutil_is_not_an_assertion_failure(monkeypatch):
    from je_auto_control.utils.assertion import assertions
    monkeypatch.setitem(sys.modules, "psutil", None)
    with pytest.raises(AutoControlException) as caught:
        assertions._running_process_names("x")
    assert not isinstance(caught.value, AutoControlAssertionException)


@pytest.mark.parametrize("value", ["a\u2028b", "a\x0bb", "a\x85b"])
def test_dotenv_values_with_unicode_line_separators_round_trip(value):
    assert parse_dotenv(dump_dotenv({"K": value, "NEXT": "1"})) == {"K": value, "NEXT": "1"}


def test_a_process_that_exits_mid_kill_is_reported_not_raised(monkeypatch):
    psutil = pytest.importorskip("psutil")
    from je_auto_control.utils.mcp_server.tools import _handlers_system

    class _Gone:
        def __init__(self, pid):
            self.pid = pid

        def terminate(self):
            raise psutil.NoSuchProcess(self.pid)

    monkeypatch.setattr(psutil, "Process", _Gone)
    assert _handlers_system.kill_process(4242) == "terminated"
