"""Round-3 audit regressions: process launch, WM_DROPFILES, shell reaping.

Covers findings 8 (start_exe argv), 9 (file_drop ctypes signatures), and
12 (ShellManager.exit_program reaping). Headless: no real process is
launched and no real window message is posted.
"""
import subprocess

import pytest


# --- Finding 8: start_exe must not shlex-split a single spaced path -------

def test_start_exe_passes_argv_list_not_split_string(tmp_path, monkeypatch):
    from je_auto_control.utils.shell_process.shell_exec import ShellManager
    from je_auto_control.utils.start_exe.start_another_process import start_exe

    exe = tmp_path / "my program.exe"
    exe.write_text("stub")
    captured = {}

    def fake_exec(self, command):
        captured["command"] = command
        self.process = object()  # non-None → launch "succeeded"

    monkeypatch.setattr(ShellManager, "exec_shell", fake_exec)
    start_exe(str(exe))
    # The spaced path is handed over verbatim as a single argv element.
    assert captured["command"] == [str(exe)]


def test_start_exe_raises_when_launch_fails(tmp_path, monkeypatch):
    from je_auto_control.utils.shell_process.shell_exec import ShellManager
    from je_auto_control.utils.start_exe.start_another_process import start_exe
    from je_auto_control.utils.exception.exceptions import AutoControlException

    exe = tmp_path / "app.exe"
    exe.write_text("stub")

    def fake_exec(self, _command):
        self.process = None  # exec_shell swallowed the launch failure

    monkeypatch.setattr(ShellManager, "exec_shell", fake_exec)
    with pytest.raises(AutoControlException):
        start_exe(str(exe))


# --- Finding 9: file_drop ctypes signatures ------------------------------

class _FakeFn:
    """Stands in for a ctypes function pointer (accepts argtypes/restype)."""


class _FakeLib:
    def __init__(self, names):
        for name in names:
            setattr(self, name, _FakeFn())


def test_declare_win32_signatures_sets_all_argtypes():
    import ctypes
    from ctypes import wintypes
    from je_auto_control.utils.file_drop.file_drop import (
        _declare_win32_signatures,
    )
    kernel32 = _FakeLib(["GlobalAlloc", "GlobalLock", "GlobalUnlock"])
    user32 = _FakeLib(["PostMessageW"])

    _declare_win32_signatures(kernel32, user32)

    assert kernel32.GlobalAlloc.argtypes == [wintypes.UINT, ctypes.c_size_t]
    assert kernel32.GlobalAlloc.restype is wintypes.HGLOBAL
    # These three previously had NO argtypes → 64-bit handle truncation.
    assert kernel32.GlobalLock.argtypes == [wintypes.HGLOBAL]
    assert kernel32.GlobalLock.restype is ctypes.c_void_p
    assert kernel32.GlobalUnlock.argtypes == [wintypes.HGLOBAL]
    assert kernel32.GlobalUnlock.restype is wintypes.BOOL
    assert user32.PostMessageW.argtypes == [
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
    ]
    assert user32.PostMessageW.restype is wintypes.BOOL


# --- Finding 12: exit_program reaps and logs the real exit code ----------

class _FakeProc:
    def __init__(self):
        self.returncode = None
        self.terminated = False
        self.waited = False

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):  # noqa: ARG002  # reason: mirrors Popen.wait
        self.waited = True
        self.returncode = 0
        return 0

    def poll(self):
        return self.returncode


def test_exit_program_waits_and_logs_real_returncode(monkeypatch):
    from je_auto_control.utils.shell_process import shell_exec as shell_mod
    from je_auto_control.utils.shell_process.shell_exec import ShellManager

    manager = ShellManager()
    proc = _FakeProc()
    manager.process = proc
    messages = []
    monkeypatch.setattr(
        shell_mod.autocontrol_logger, "info",
        lambda msg, *a, **k: messages.append(str(msg)))
    monkeypatch.setattr(
        shell_mod.autocontrol_logger, "error", lambda *a, **k: None)

    manager.exit_program()

    assert proc.terminated is True
    assert proc.waited is True  # exit code was actually reaped, not read as None
    assert any("code 0" in message for message in messages)
    assert manager.process is None
    assert isinstance(subprocess.TimeoutExpired, type)  # import sanity


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
