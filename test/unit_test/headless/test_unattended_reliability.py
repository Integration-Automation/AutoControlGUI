"""Headless tests for the unattended-reliability features:
OTP/TOTP generation, native file-dialog handling, and the session guard.
All external steps are deterministic or injected — no real GUI/2FA."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.exception.exceptions import AutoControlException


# --- OTP / TOTP ------------------------------------------------------------

def test_generate_totp_deterministic_and_verifies():
    secret = ac.generate_secret()
    code = ac.generate_totp(secret, at=0)
    assert code.isdigit() and len(code) == 6
    assert ac.verify_totp(secret, code, at=0) is True
    # same 30-second step -> same code
    assert ac.generate_totp(secret, at=0) == ac.generate_totp(secret, at=15)
    # a code from a far-away step does not verify (near-epoch counters safe)
    assert ac.verify_totp(secret, ac.generate_totp(secret, at=99999),
                          at=0) is False


def test_otp_to_var_command():
    from je_auto_control.utils.executor.action_executor import Executor
    from je_auto_control.utils.executor.flow_control import exec_otp_to_var
    executor = Executor()
    result = exec_otp_to_var(
        executor, {"secret": ac.generate_secret(), "var": "code"})
    assert result["var"] == "code"
    assert executor.variables.get_value("code").isdigit()


# --- native file dialog ----------------------------------------------------

class _FakeDriver:
    def __init__(self, found=True):
        self.found = found
        self.calls = {}

    def wait_window(self, title, timeout_s):
        self.calls["wait"] = (title, timeout_s)
        return self.found

    def type_path(self, path):
        self.calls["typed"] = path

    def confirm(self, key):
        self.calls["confirm"] = key


def test_handle_file_dialog_types_and_confirms():
    from je_auto_control.utils.file_dialog import handle_file_dialog
    drv = _FakeDriver()
    result = handle_file_dialog("C:/out.txt", action="save", driver=drv)
    assert result == {"handled": True, "title": "Save As"}
    assert drv.calls["typed"] == "C:/out.txt"
    assert drv.calls["confirm"] == "enter"


def test_handle_file_dialog_missing_dialog():
    from je_auto_control.utils.file_dialog import handle_file_dialog
    drv = _FakeDriver(found=False)
    result = handle_file_dialog("x", driver=drv)
    assert result["handled"] is False
    assert "typed" not in drv.calls


# --- session guard ---------------------------------------------------------

def test_session_locked_raises():
    assert ac.is_session_locked(probe=lambda: True) is True
    with pytest.raises(AutoControlException):
        ac.ensure_interactive_session(probe=lambda: True)


def test_session_active_passes():
    assert ac.is_session_locked(probe=lambda: False) is False
    assert ac.ensure_interactive_session(probe=lambda: False) is True


# --- wiring ----------------------------------------------------------------

def test_executor_and_mcp_and_builder_wiring():
    known = ac.executor.known_commands()
    assert {"AC_otp_to_var", "AC_handle_file_dialog",
            "AC_assert_session_active"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_generate_otp", "ac_handle_file_dialog",
            "ac_assert_session_active"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_otp_to_var", "AC_handle_file_dialog",
            "AC_assert_session_active"} <= cmds
