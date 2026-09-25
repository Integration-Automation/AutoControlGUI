"""Accessibility and OCR at the edges the audit found (fakes only; nothing is clicked).

A closed window's COMError escaped the UIA state read; FindText's NULL range
read as "found"; macOS bounds were always zero; elements with no rectangle
ranked first and were clicked at (0, 0); audits ignored Windows role names;
one framework error stopped the recorder; the Linux search had no node budget;
mixed text formatting read as a value; every Tesseract failure was "binary not
found"; anchor locate hid backends that are not set up; integer roles crashed.
"""
import threading
import types

import pytest

from je_auto_control.utils.accessibility.element import (
    AccessibilityElement, element_matches, rank_by_name,
)
from je_auto_control.utils.exception.exceptions import AutoControlException


def _element(name, bounds, role="button"):
    return AccessibilityElement(name=name, role=role, bounds=bounds)


class _FakeCOMError(Exception):
    pass


def test_a_closed_windows_property_read_is_unreadable_not_an_escape(monkeypatch):
    from je_auto_control.utils.accessibility.backends import windows_query, windows_state
    monkeypatch.setattr(windows_query, "UIA_ERRORS", (OSError, _FakeCOMError))

    class _Raw:
        @staticmethod
        def GetCurrentPropertyValue(property_id):  # noqa: N802  # reason: UIA's name
            raise _FakeCOMError("element not available")

    assert windows_state._prop(_Raw(), 30019) is None  # noqa: SLF001
    assert windows_state.is_password(_Raw()) is True


def test_find_text_reads_a_null_range_as_not_found():
    import ctypes

    from je_auto_control.utils.accessibility.backends.windows_backend import WindowsAccessibilityBackend
    backend = object.__new__(WindowsAccessibilityBackend)
    backend._find_range = lambda *args: ctypes.POINTER(ctypes.c_long)()  # noqa: SLF001
    assert backend.find_text("definitely absent") is False


def test_macos_bounds_are_unwrapped_from_ax_values():
    from je_auto_control.utils.accessibility.backends.macos_backend import _extract_bounds
    values = {"pos": types.SimpleNamespace(x=10.6, y=20.2), "size": types.SimpleNamespace(width=30.0, height=40.9)}

    def ax_value_get_value(value, kind, _out):
        return True, values[value.key]

    ax = types.SimpleNamespace(AXValueGetValue=ax_value_get_value,
                               kAXValueCGPointType=1, kAXValueCGSizeType=2)
    bounds = _extract_bounds(types.SimpleNamespace(key="pos"), types.SimpleNamespace(key="size"), ax)
    assert bounds == (10, 20, 30, 40)


def test_an_element_with_no_rectangle_ranks_last_and_is_not_clicked(monkeypatch):
    hidden, visible = _element("Save", (0, 0, 0, 0)), _element("Save", (600, 400, 80, 24))
    assert rank_by_name([hidden, visible], "save")[0] is visible
    from je_auto_control.utils.accessibility import accessibility_api
    monkeypatch.setattr(accessibility_api, "list_accessibility_elements",
                        lambda **kwargs: [hidden, visible])
    assert accessibility_api.find_accessibility_element(name="Save") is visible
    monkeypatch.setattr(accessibility_api, "list_accessibility_elements", lambda **kwargs: [hidden])
    from je_auto_control.wrapper import auto_control_mouse
    clicks = []
    monkeypatch.setattr(auto_control_mouse, "set_mouse_position", lambda *a: clicks.append(a))
    monkeypatch.setattr(auto_control_mouse, "click_mouse", lambda *a: clicks.append(a))
    assert accessibility_api.click_accessibility_element(name="Save") is False and clicks == []


def test_audits_read_windows_role_names():
    from je_auto_control.utils.a11y_audit.audit import audit_missing_labels
    from je_auto_control.utils.screen_state.screen_state import describe_screen
    unnamed = _element("", (0, 0, 16, 16), role="ControlType_50000")
    assert len(audit_missing_labels([unnamed])) == 1
    named = {"name": "User name", "role": "ControlType_50004", "bounds": [0, 0, 100, 20]}
    assert describe_screen([named])["controls"] == ["User name"]


def test_one_framework_error_does_not_stop_the_recorder():
    from je_auto_control.utils.accessibility.recorder import AccessibilityRecorder
    stop, calls = threading.Event(), []

    def fetcher(_app_name):
        calls.append(1)
        if len(calls) == 1:
            raise AutoControlException("the session bus did not answer in time")
        stop.set()

    recorder = AccessibilityRecorder(poll_interval_s=0.01, fetcher=fetcher)
    recorder._run(stop)  # noqa: SLF001
    assert len(calls) == 2


class _WideTree:
    """A root with one application whose window holds 20,000 cells."""

    def __init__(self):
        self.calls = 0

    def children(self, reference):
        self.calls += 1
        if reference == ("bus", "app"):
            return [("bus", "window")]
        if reference == ("bus", "window"):
            return [("bus", f"cell{i}") for i in range(20000)]
        return []

    def property(self, reference, _name):
        self.calls += 1
        return reference[1]

    def role_name(self, _reference):
        self.calls += 1
        return "table cell"

    def extents(self, _reference):
        return (0, 0, 10, 10)

    def state(self, _reference):
        return 0


def test_the_linux_search_stops_at_its_node_budget():
    from je_auto_control.utils.accessibility.backends import linux_backend
    backend = object.__new__(linux_backend.LinuxAccessibilityBackend)
    tree = _WideTree()
    found = backend._search(tree, ("bus", "app"), "app", "Missing", None, False)  # noqa: SLF001
    assert found is None and tree.calls < 3 * (linux_backend._SEARCH_BUDGET + 10)  # noqa: SLF001


def test_mixed_text_formatting_reads_as_unknown():
    from je_auto_control.utils.accessibility.backends import windows_reads
    sentinel_range = types.SimpleNamespace(GetAttributeValue=lambda attribute_id: object())
    attributes = windows_reads._read_text_attributes(sentinel_range)  # noqa: SLF001
    assert attributes["font_name"] is None and attributes["italic"] is None


def test_a_tesseract_failure_other_than_a_missing_binary_says_what_failed(monkeypatch):
    from je_auto_control.utils.ocr.backends import tesseract_backend
    from je_auto_control.utils.ocr.backends.base import OCRBackendNotAvailableError

    class TesseractError(RuntimeError):
        pass

    def fail(*args, **kwargs):
        raise TesseractError("Failed loading language 'chi_tra'")

    fake = types.SimpleNamespace(image_to_data=fail, Output=types.SimpleNamespace(DICT="dict"))
    monkeypatch.setattr(tesseract_backend, "_load", lambda: fake)
    backend = object.__new__(tesseract_backend.TesseractBackend)
    with pytest.raises(OCRBackendNotAvailableError, match="chi_tra"):
        backend.image_to_matches(object(), "chi_tra", 60.0)


def test_anchor_locate_reports_a_backend_that_is_not_set_up(monkeypatch):
    from je_auto_control.utils.anchor_locator import locator
    from je_auto_control.utils.ocr import ocr_engine
    from je_auto_control.utils.ocr.backends.base import OCRBackendNotAvailableError

    def no_engine(*args, **kwargs):
        raise OCRBackendNotAvailableError("no OCR backend ready")

    monkeypatch.setattr(ocr_engine, "find_text_matches", no_engine)
    with pytest.raises(OCRBackendNotAvailableError):
        locator._ocr_candidates(locator.ocr_locator("Name"))  # noqa: SLF001


def test_an_integer_role_is_matched_not_crashed():
    element = _element("OK", (1, 1, 10, 10), role="ControlType_50000")
    assert element_matches(element, role=50000) is True
