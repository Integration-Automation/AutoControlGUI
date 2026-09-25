"""Headless tests for WM_DROPFILES file drop (injected driver; no Win32)."""
import sys

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


class _Fn:
    def __init__(self, result, calls, name):
        self.result, self.calls, self.name = result, calls, name

    def __call__(self, *args):
        self.calls.append((self.name, args))
        return self.result


class _Lib:
    def __init__(self, calls, **results):
        for name, result in results.items():
            setattr(self, name, _Fn(result, calls, name))


def _fake_api(monkeypatch, *, is_window=1, post=1):
    from je_auto_control.utils.clipboard import win32_clipboard_api
    calls = []
    user32 = _Lib(calls, IsWindow=is_window, PostMessageW=post)
    kernel32 = _Lib(calls, GlobalAlloc=0x1234, GlobalFree=0)
    monkeypatch.setattr(win32_clipboard_api, "clipboard_api", lambda: (user32, kernel32))
    monkeypatch.setattr(win32_clipboard_api, "fill_global", lambda *_args: None)
    return calls


def test_a_failed_post_frees_the_block(monkeypatch):
    # Until PostMessage succeeds the HGLOBAL is still the sender's; it leaked.
    from je_auto_control.utils.file_drop.file_drop import FileDropError, _default_driver
    calls = _fake_api(monkeypatch, post=0)
    with pytest.raises(FileDropError):
        _default_driver(0x77, b"blob", (0, 0))
    assert ("GlobalFree", (0x1234,)) in calls


def test_a_delivered_drop_leaves_the_block_to_the_receiver(monkeypatch):
    from je_auto_control.utils.file_drop.file_drop import _default_driver
    calls = _fake_api(monkeypatch)
    assert _default_driver(0x77, b"blob", (0, 0)) is True
    assert "GlobalFree" not in [name for name, _args in calls]


def test_a_non_window_is_refused_before_allocating(monkeypatch):
    # PostMessage(NULL, ...) posts to the caller's own queue and "succeeds".
    from je_auto_control.utils.exception.exceptions import AutoControlException
    from je_auto_control.utils.file_drop.file_drop import _default_driver
    calls = _fake_api(monkeypatch, is_window=0)
    with pytest.raises(AutoControlException):
        _default_driver(0, b"blob", (0, 0))
    assert "GlobalAlloc" not in [name for name, _args in calls]


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Win32")
def test_the_real_driver_refuses_hwnd_zero_and_keeps_windll_clean():
    import ctypes
    from je_auto_control.utils.file_drop.file_drop import FileDropError, _default_driver
    shared = ctypes.windll.user32.IsWindow
    before = shared.argtypes
    shared.argtypes = None
    try:
        with pytest.raises(FileDropError):
            _default_driver(0, b"blob", (0, 0))
        # Prototypes live on the private handles, not the process-wide windll.
        assert shared.argtypes is None
    finally:
        shared.argtypes = before


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
