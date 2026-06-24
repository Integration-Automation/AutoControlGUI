"""Headless tests for WM_DROPFILES file drop (injected driver; no Win32)."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.clipboard_files import parse_dropfiles
from je_auto_control.utils.file_drop import drop_files, plan_file_drop

_WM_DROPFILES = 0x0233


def test_plan_file_drop_reuses_dropfiles_packing():
    plan = plan_file_drop(["C:\\a\\one.txt", "C:\\b\\two.png"], point=(12, 34))
    assert plan["message"] == _WM_DROPFILES
    assert plan["paths"] == ["C:\\a\\one.txt", "C:\\b\\two.png"]
    assert plan["point"] == [12, 34]
    assert plan["wide"] is True
    assert plan["blob_size"] > 20  # header + path list


def test_drop_files_dispatches_packed_blob_to_driver():
    captured = {}

    def fake_driver(hwnd, blob, point):
        captured["hwnd"] = hwnd
        captured["blob"] = blob
        captured["point"] = point
        return True

    ok = drop_files(0xABCD, ["C:\\docs\\report.pdf"], point=(5, 9),
                    driver=fake_driver)
    assert ok is True
    assert captured["hwnd"] == 0xABCD
    assert captured["point"] == (5, 9)
    # the blob the driver receives is a real DROPFILES the receiver could parse
    parsed = parse_dropfiles(captured["blob"])
    assert parsed["paths"] == ["C:\\docs\\report.pdf"]
    assert parsed["point"] == [5, 9]


def test_drop_files_returns_driver_result():
    assert drop_files(1, ["x"], driver=lambda *_: False) is False


def test_empty_paths_raise():
    with pytest.raises(ValueError):
        drop_files(1, [], driver=lambda *_: True)
    with pytest.raises(ValueError):
        plan_file_drop([])


# --- wiring (real Win32 PostMessage not executed in CI) --------------------

def test_executor_plan_path_is_pure():
    from je_auto_control.utils.executor.action_executor import _plan_file_drop
    plan = _plan_file_drop('["C:\\\\a\\\\one.txt"]', "[3, 4]")
    assert plan["point"] == [3, 4] and plan["paths"] == ["C:\\a\\one.txt"]


def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_drop_files", "AC_plan_file_drop"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_drop_files", "ac_plan_file_drop"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_drop_files", "AC_plan_file_drop"} <= specs


def test_facade_exports():
    for name in ("plan_file_drop", "drop_files"):
        assert hasattr(ac, name) and name in ac.__all__
