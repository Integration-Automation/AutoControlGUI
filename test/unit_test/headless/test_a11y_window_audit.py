"""Regression tests for the accessibility / OCR / window defects of the 2026-09-23 audit.

A blank ``name`` with ``contains=True`` matched every element and an empty
window title every window (``close_window_by_title('')`` closed one). Saving a
layout read geometry by title substring and restoring it moved the same first
window for every duplicate title. A scoped UIA search died on a raw COMError,
``show_window`` foregrounded windows it was asked not to activate, waits with
``timeout=0`` never looked, and OCR matching ignored Unicode normalisation.
All of it runs against fakes.
"""
import sys
import types
import unicodedata

import pytest

from je_auto_control.utils.accessibility.element import AccessibilityElement, element_matches
from je_auto_control.utils.exception.exceptions import AutoControlActionException, AutoControlException
from je_auto_control.utils.ocr.text_span import normalize
from je_auto_control.utils.window_capture import window_capture
from je_auto_control.wrapper import auto_control_window


def _element(name):
    return AccessibilityElement(name=name, role="button", app_name="app",
                                bounds=(0, 0, 10, 10), process_id=1)


@pytest.mark.parametrize("name", ["", "   "])
def test_a_blank_contains_search_matches_nothing(name):
    assert not element_matches(_element("Delete everything"), name=name, contains=True)


@pytest.mark.parametrize("title", ["", "   ", None])
def test_a_blank_window_title_is_refused(monkeypatch, title):
    monkeypatch.setattr(auto_control_window, "list_windows", lambda titled_only=False: [(101, "")])
    with pytest.raises(AutoControlActionException, match="non-empty"):
        auto_control_window.find_window(title)


def test_wait_for_window_with_no_timeout_still_looks(monkeypatch):
    monkeypatch.setattr(auto_control_window, "list_windows", lambda titled_only=False: [(7, "Calc")])
    assert auto_control_window.wait_for_window("Calc", timeout=0) == 7


def test_wait_for_text_with_no_timeout_still_looks(monkeypatch):
    from je_auto_control.utils.ocr import ocr_engine
    monkeypatch.setattr(ocr_engine, "locate_text_center", lambda *args, **kwargs: (65, 20))
    assert ocr_engine.wait_for_text("Save As", timeout=0) == (65, 20)


def test_ocr_matching_normalises_unicode():
    composed, decomposed = "Café", unicodedata.normalize("NFD", "Café")
    assert normalize(composed) == normalize(decomposed)
    assert normalize("STRASSE") == normalize("straße")
    assert normalize("ＡＢ") == normalize("AB"), "full-width forms fold too"


def test_a_saved_layout_reads_each_window_by_its_handle(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    real = {1: (0, 0, 800, 600), 2: (900, 50, 400, 300)}
    monkeypatch.setattr(window_capture, "_win32_geometry", lambda hwnd: real[hwnd])
    layout = window_capture.save_window_layout(lister=lambda: [(1, "Editor - a"), (2, "Editor")])
    assert [(entry["title"], entry["x"]) for entry in layout] == [("Editor - a", 0), ("Editor", 900)]


def test_restoring_duplicate_titles_moves_each_window_once(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    import je_auto_control.wrapper.auto_control_window as window_module
    monkeypatch.setattr(window_module, "list_windows",
                        lambda titled_only=False: [(1, "Editor - a"), (2, "Editor"), (3, "Editor")])
    moved = []
    fake_wm = types.SimpleNamespace(move_window=lambda hwnd, *rect: moved.append(hwnd) or True)
    monkeypatch.setitem(sys.modules, "je_auto_control.windows.window.windows_window_manage", fake_wm)
    monkeypatch.setattr(sys.modules["je_auto_control.windows.window"], "windows_window_manage",
                        fake_wm, raising=False)
    count = window_capture.restore_window_layout([
        {"title": "Editor", "x": 0, "y": 0, "width": 1, "height": 1},
        {"title": "Editor", "x": 5, "y": 5, "width": 1, "height": 1},
    ])
    assert count == 2 and moved == [2, 3]


@pytest.mark.skipif(sys.platform != "win32", reason="the UIA query module loads on Windows only")
def test_a_scoped_uia_search_skips_a_window_that_errors(monkeypatch):
    from je_auto_control.utils.accessibility.backends import windows_query
    from je_auto_control.windows.window import windows_window_manage
    monkeypatch.setattr(windows_window_manage, "get_all_window_hwnd",
                        lambda: [(1, "Chrome - hung"), (2, "Chrome - fine")])
    error_type = windows_query.UIA_ERRORS[0] if windows_query.UIA_ERRORS else OSError

    class _Automation:
        def ElementFromHandle(self, hwnd):  # noqa: N802 - COM name
            if hwnd == 1:
                raise error_type("provider not responding")
            return "root-2"

    monkeypatch.setattr(windows_query, "_is_null", lambda element: element is None)
    assert windows_query.search_root(_Automation(), "Chrome") == "root-2"


@pytest.mark.skipif(sys.platform != "win32", reason="the Win32 window manager loads on Windows only")
@pytest.mark.parametrize("command, foreground", [(1, True), (5, True), (9, True),
                                                 (2, False), (4, False), (7, False), (0, False)])
def test_show_window_foregrounds_only_for_activating_commands(monkeypatch, command, foreground):
    from je_auto_control.windows.window import windows_window_manage
    calls = []
    fake = types.SimpleNamespace(ShowWindow=lambda hwnd, cmd: calls.append("show"),
                                 SetForegroundWindow=lambda hwnd: calls.append("foreground"))
    monkeypatch.setattr(windows_window_manage, "_user32", fake)
    windows_window_manage.show_window(1, command)
    assert ("foreground" in calls) is foreground


def test_unavailable_errors_are_in_the_framework_family():
    from je_auto_control.utils.accessibility.element import AccessibilityNotAvailableError
    from je_auto_control.utils.ocr.backends.base import OCRBackendNotAvailableError
    for error in (AccessibilityNotAvailableError, OCRBackendNotAvailableError):
        assert issubclass(error, AutoControlException) and issubclass(error, RuntimeError)
