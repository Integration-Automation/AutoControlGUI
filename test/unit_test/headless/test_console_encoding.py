"""Console output is decoded in the code page it is written in, on Python 3.15 too.

Python 3.15 turns UTF-8 mode on by default (PEP 686), and in UTF-8 mode
``locale.getpreferredencoding(False)`` answers ``utf-8`` while ``cmd`` and
``sc`` keep writing the ANSI code page. The tests simulate that mode on any
interpreter: the preferred encoding says UTF-8, the locale says cp950.
No subprocess is started.
"""
import locale
import subprocess  # nosec B404  # reason: only CompletedProcess is built, nothing runs
import sys
import types

import pytest

from je_auto_control.utils.shell_process import shell_exec

_VOLUME = "磁碟區"


@pytest.fixture()
def utf8_mode_on_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(locale, "getpreferredencoding", lambda do_setlocale=True: "utf-8")
    monkeypatch.setattr(locale, "getencoding", lambda: "cp950", raising=False)


def _console_writes(monkeypatch, module):
    def run_captured(argv, timeout_s):
        return subprocess.CompletedProcess(argv, 0, _VOLUME.encode("cp950"), b"")  # nosemgrep  # reason: builds a result, runs nothing
    monkeypatch.setattr(module, "run_captured", run_captured)


def test_windows_reads_the_code_page_in_utf8_mode(utf8_mode_on_windows):
    assert shell_exec.console_encoding() == "cp950"


def test_other_platforms_keep_the_preferred_encoding(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(locale, "getpreferredencoding", lambda do_setlocale=True: "utf-8")
    monkeypatch.setattr(locale, "getencoding", lambda: "ANSI_X3.4-1968", raising=False)
    assert shell_exec.console_encoding() == "utf-8"


def test_shell_to_var_decodes_the_code_page(utf8_mode_on_windows, monkeypatch):
    from je_auto_control.utils.executor.flow_data_commands import exec_shell_to_var
    _console_writes(monkeypatch, shell_exec)
    executor = types.SimpleNamespace(variables=types.SimpleNamespace(set=lambda name, value: None))
    assert exec_shell_to_var(executor, {"command": ["vol"]})["output"] == _VOLUME


def test_the_mcp_shell_tool_decodes_the_code_page(utf8_mode_on_windows, monkeypatch):
    from je_auto_control.utils.mcp_server.tools._handlers_system import shell_command
    _console_writes(monkeypatch, shell_exec)
    assert shell_command("vol")["stdout"] == _VOLUME


def test_shell_manager_defaults_to_the_code_page(utf8_mode_on_windows):
    assert shell_exec.ShellManager().program_encoding == "cp950"
