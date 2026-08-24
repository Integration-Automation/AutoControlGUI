"""What the Windows backend does with a control once it has found one.

The search that finds it is covered in `test_accessibility_windows_uia.py`;
this file starts from "here is the element" and is about the thirty-odd
control patterns hanging off it -- the half of the backend that reads a
slider's number, presses a button, expands a tree node or pulls the text out
of a document.

They all go through one indirection, and it is where a mistake hides:

    unknown = raw.GetCurrentPattern(pattern_id)      # nothing if unsupported
    pattern = unknown.QueryInterface(getattr(uia_module, interface_name))

Two ids and one interface name per operation, none of them checked by
anything at runtime -- ask for the ValuePattern id and query the
RangeValuePattern interface and the failure is a `None` that reads exactly
like "no such control". The doubles here refuse a mismatched pair, so each
test below is also an assertion that the operation reaches for the pattern it
means.

The other thing worth stating is the answer shape. A control that does not
support a pattern is not an error and not an empty value -- it is "no", and
each method has to spell "no" in whatever type it promised: `None` for a
read, `False` for an action, `[]` for a table. A caller cannot recover from
`False` when it meant "there is no such control", so the distinction is the
whole contract.
"""
from __future__ import annotations

import sys

import pytest

from headless._uia_doubles import (
    Automation, Pattern, RawElement, Rect, UiaModule, Unknown,
)
from je_auto_control.utils.accessibility.backends import (
    windows_backend as backend_module,
)
from je_auto_control.utils.accessibility.backends.windows_backend import (
    WindowsAccessibilityBackend,
)

VALUE = backend_module._UIA_VALUE_PATTERN_ID
INVOKE = backend_module._UIA_INVOKE_PATTERN_ID
TOGGLE = backend_module._UIA_TOGGLE_PATTERN_ID
GRID = backend_module._UIA_GRID_PATTERN_ID
GRID_ITEM = backend_module._UIA_GRIDITEM_PATTERN_ID
EXPAND = backend_module._UIA_EXPANDCOLLAPSE_PATTERN_ID
SELECTION_ITEM = backend_module._UIA_SELECTIONITEM_PATTERN_ID
RANGE = backend_module._UIA_RANGEVALUE_PATTERN_ID
SCROLL_ITEM = backend_module._UIA_SCROLLITEM_PATTERN_ID
TEXT = backend_module._UIA_TEXT_PATTERN_ID
ITEM_CONTAINER = backend_module._UIA_ITEMCONTAINER_PATTERN_ID
VIRTUALIZED = backend_module._UIA_VIRTUALIZEDITEM_PATTERN_ID
TABLE = backend_module._UIA_TABLE_PATTERN_ID
TRANSFORM = backend_module._UIA_TRANSFORM_PATTERN_ID
WINDOW = backend_module._UIA_WINDOW_PATTERN_ID
LEGACY = backend_module._UIA_LEGACYIACCESSIBLE_PATTERN_ID
SELECTION = backend_module._UIA_SELECTION_PATTERN_ID
MULTIPLE_VIEW = backend_module._UIA_MULTIPLEVIEW_PATTERN_ID

_IS_PASSWORD = 30019


@pytest.fixture(autouse=True)
def named_processes(monkeypatch):
    monkeypatch.setattr(backend_module, "_process_name",
                        lambda pid: f"app{pid}.exe" if pid else "")


@pytest.fixture
def backend(monkeypatch):
    monkeypatch.setattr(backend_module, "_is_available", lambda: True)
    instance = WindowsAccessibilityBackend()
    instance._automation = Automation()
    instance._uia_module = UiaModule()
    return instance


@pytest.fixture
def found(backend, monkeypatch):
    """Answer every search with one raw element, and record what was asked."""
    state = {"raw": None, "filters": []}

    def _find_raw(name, role, app_name, automation_id, window_title=None,
                  contains=False):
        state["filters"].append({"name": name, "role": role,
                                 "app_name": app_name,
                                 "automation_id": automation_id,
                                 "window_title": window_title,
                                 "contains": contains})
        return state["raw"]

    monkeypatch.setattr(backend, "_find_raw", _find_raw)

    def _set(raw):
        state["raw"] = raw
        return raw

    state["set"] = _set
    return state


def _control(pattern_id=None, interface_name="", pattern=None, **kwargs):
    """A raw element carrying at most one pattern."""
    patterns = {}
    if pattern_id is not None:
        patterns[pattern_id] = Unknown(interface_name, pattern or Pattern())
    kwargs.setdefault("rect", Rect(0, 0, 1, 1))
    return RawElement(patterns=patterns, **kwargs)


def _with(found, pattern_id, interface_name, pattern=None, **kwargs):
    """Install a control carrying one pattern, and hand the pattern back."""
    pattern = pattern or Pattern()
    found["set"](_control(pattern_id, interface_name, pattern, **kwargs))
    return pattern


# --- the pattern indirection --------------------------------------------------

def test_a_control_that_does_not_support_a_pattern_yields_none(backend):
    assert backend._pattern(_control(), VALUE, "IUIAutomationValuePattern") is (
        None
    )


def test_asking_for_the_wrong_interface_yields_none_rather_than_a_pattern(
        backend):
    # The id and the interface name are two independent constants; a
    # mismatched pair is a silent `None` that reads like "no such control".
    raw = _control(VALUE, "IUIAutomationValuePattern")
    assert backend._pattern(raw, VALUE, "IUIAutomationRangeValuePattern") is (
        None
    )


def test_a_provider_that_fails_the_pattern_query_yields_none(backend):
    raw = _control(VALUE, "IUIAutomationValuePattern")
    raw.pattern_error = OSError("provider stopped responding")
    assert backend._pattern(raw, VALUE, "IUIAutomationValuePattern") is None


def test_the_uia_catch_tuple_covers_the_providers_own_error_type():
    # comtypes reports a provider failure as COMError, which derives straight
    # from Exception. Until 2026-08-24 the 37 guards in this module named
    # `(OSError, AttributeError, ...)` and therefore contained none of them,
    # while the two walk guards in the same file already used UIA_ERRORS.
    assert TypeError in backend_module._UIA_ERRORS
    if sys.platform == "win32":
        from _ctypes import COMError
        assert COMError in backend_module._UIA_ERRORS
        assert not issubclass(
            COMError, (OSError, AttributeError, ValueError, TypeError))


@pytest.mark.skipif(sys.platform != "win32",
                    reason="COMError only exists where comtypes can")
def test_a_window_that_closes_between_the_search_and_the_read_is_contained(
        backend, found):
    # The race the guard is for: the element was found, and the application
    # owning it went away before its value could be read. The answer is "no
    # value", not an exception past the executor's containment boundary.
    from _ctypes import COMError
    raw = _control(VALUE, "IUIAutomationValuePattern",
                   properties={_IS_PASSWORD: False})
    raw.pattern_error = COMError(-2147220991, "the window closed", None)
    found["set"](raw)
    assert backend.get_value(name="Field") is None


# --- value --------------------------------------------------------------------

def test_a_value_is_read_from_the_value_pattern(backend, found):
    _with(found, VALUE, "IUIAutomationValuePattern",
          Pattern(CurrentValue="typed"), properties={_IS_PASSWORD: False})
    assert backend.get_value(name="Field") == "typed"


def test_a_password_fields_value_is_never_handed_back(backend, found):
    # UIA is supposed to mask it, but that is a convention a custom-drawn
    # control can ignore -- and callers log and forward what they read.
    _with(found, VALUE, "IUIAutomationValuePattern",
          Pattern(CurrentValue="hunter2"), properties={_IS_PASSWORD: True})
    assert backend.get_value(name="Password") is None


def test_a_value_read_forwards_the_scope_it_was_given(backend, found):
    _with(found, VALUE, "IUIAutomationValuePattern",
          Pattern(CurrentValue="typed"), properties={_IS_PASSWORD: False})
    backend.get_value(name="Field", window_title="Editor", contains=True)
    assert found["filters"][-1]["window_title"] == "Editor"
    assert found["filters"][-1]["contains"] is True


def test_a_control_with_no_value_pattern_has_no_value(backend, found):
    found["set"](_control(properties={_IS_PASSWORD: False}))
    assert backend.get_value(name="Field") is None


def test_a_value_the_provider_will_not_answer_reads_as_none(backend, found):
    _with(found, VALUE, "IUIAutomationValuePattern", Pattern(),
          properties={_IS_PASSWORD: False})
    assert backend.get_value(name="Field") is None


def test_an_empty_value_reads_as_the_empty_string(backend, found):
    _with(found, VALUE, "IUIAutomationValuePattern",
          Pattern(CurrentValue=None), properties={_IS_PASSWORD: False})
    assert backend.get_value(name="Field") == ""


def test_a_control_that_is_not_there_has_no_value(backend, found):
    assert backend.get_value(name="Nothing") is None


def test_setting_a_value_writes_it_as_text(backend, found):
    pattern = _with(found, VALUE, "IUIAutomationValuePattern")
    assert backend.set_value(42, name="Field") is True
    assert pattern.calls == [("SetValue", ("42",))]


def test_setting_a_value_on_a_control_that_is_not_there_fails(backend, found):
    assert backend.set_value("x", name="Nothing") is False


def test_setting_a_value_the_control_refuses_fails(backend, found):
    pattern = _with(found, VALUE, "IUIAutomationValuePattern")
    pattern.errors["SetValue"] = OSError("read-only")
    assert backend.set_value("x", name="Field") is False


# --- invoke and toggle --------------------------------------------------------

def test_invoking_presses_the_control(backend, found):
    pattern = _with(found, INVOKE, "IUIAutomationInvokePattern")
    assert backend.invoke(name="OK") is True
    assert pattern.calls == [("Invoke", ())]


def test_invoking_a_control_with_no_invoke_pattern_fails(backend, found):
    found["set"](_control())
    assert backend.invoke(name="OK") is False


def test_invoking_a_control_that_is_not_there_fails(backend, found):
    assert backend.invoke(name="OK") is False


def test_an_invoke_the_control_refuses_fails(backend, found):
    pattern = _with(found, INVOKE, "IUIAutomationInvokePattern")
    pattern.errors["Invoke"] = OSError("disabled")
    assert backend.invoke(name="OK") is False


def test_toggling_flips_the_control(backend, found):
    pattern = _with(found, TOGGLE, "IUIAutomationTogglePattern")
    assert backend.toggle(name="Enabled") is True
    assert pattern.calls == [("Toggle", ())]


def test_toggling_a_control_that_cannot_be_toggled_fails(backend, found):
    found["set"](_control())
    assert backend.toggle(name="Enabled") is False


def test_a_toggle_the_control_refuses_fails(backend, found):
    pattern = _with(found, TOGGLE, "IUIAutomationTogglePattern")
    pattern.errors["Toggle"] = OSError("disabled")
    assert backend.toggle(name="Enabled") is False


# --- expand / collapse / select / scroll --------------------------------------

@pytest.mark.parametrize("method,expected", [
    ("expand", "Expand"), ("collapse", "Collapse"),
])
def test_expanding_and_collapsing_reach_the_same_pattern(backend, found,
                                                          method, expected):
    pattern = _with(found, EXPAND, "IUIAutomationExpandCollapsePattern")
    assert getattr(backend, method)(name="Node") is True
    assert pattern.calls == [(expected, ())]


def test_an_action_on_a_control_without_that_pattern_fails(backend, found):
    # `expand`, `select_item`, `scroll_into_view`, `move_element`,
    # `resize_element`, `set_range_value`, `set_window_state` and
    # `legacy_default_action` all funnel through one helper; this is that
    # helper's "the control cannot do it" answer.
    found["set"](_control())
    assert backend.expand(name="Node") is False


def test_an_action_the_control_refuses_fails(backend, found):
    pattern = _with(found, EXPAND, "IUIAutomationExpandCollapsePattern")
    pattern.errors["Expand"] = OSError("already expanded")
    assert backend.expand(name="Node") is False


def test_an_action_on_a_control_that_is_not_there_fails(backend, found):
    assert backend.expand(name="Node") is False


@pytest.mark.parametrize("code,expected", [
    (0, "collapsed"), (1, "expanded"), (2, "partial"), (3, "leaf"),
])
def test_an_expand_state_is_reported_by_name(backend, found, code, expected):
    _with(found, EXPAND, "IUIAutomationExpandCollapsePattern",
          Pattern(CurrentExpandCollapseState=code))
    assert backend.expand_state(name="Node") == expected


def test_an_unknown_expand_state_reads_as_none(backend, found):
    _with(found, EXPAND, "IUIAutomationExpandCollapsePattern",
          Pattern(CurrentExpandCollapseState=9))
    assert backend.expand_state(name="Node") is None


def test_an_unreadable_expand_state_reads_as_none(backend, found):
    _with(found, EXPAND, "IUIAutomationExpandCollapsePattern",
          Pattern(CurrentExpandCollapseState="sideways"))
    assert backend.expand_state(name="Node") is None


def test_a_control_that_does_not_expand_has_no_expand_state(backend, found):
    found["set"](_control())
    assert backend.expand_state(name="Node") is None


def test_a_control_that_is_not_there_has_no_expand_state(backend, found):
    assert backend.expand_state(name="Node") is None


def test_selecting_an_item_reaches_the_selection_item_pattern(backend, found):
    pattern = _with(found, SELECTION_ITEM,
                    "IUIAutomationSelectionItemPattern")
    assert backend.select_item(name="Row") is True
    assert pattern.calls == [("Select", ())]


def test_scrolling_into_view_reaches_the_scroll_item_pattern(backend, found):
    pattern = _with(found, SCROLL_ITEM, "IUIAutomationScrollItemPattern")
    assert backend.scroll_into_view(name="Row") is True
    assert pattern.calls == [("ScrollIntoView", ())]


# --- range --------------------------------------------------------------------

def test_a_range_is_read_as_three_floats(backend, found):
    _with(found, RANGE, "IUIAutomationRangeValuePattern",
          Pattern(CurrentValue=3, CurrentMinimum=0, CurrentMaximum=10))
    assert backend.get_range(name="Volume") == {
        "value": 3.0, "minimum": 0.0, "maximum": 10.0,
    }


def test_a_range_that_cannot_be_read_is_none(backend, found):
    _with(found, RANGE, "IUIAutomationRangeValuePattern",
          Pattern(CurrentValue="loud", CurrentMinimum=0, CurrentMaximum=10))
    assert backend.get_range(name="Volume") is None


def test_a_control_with_no_range_has_none(backend, found):
    found["set"](_control())
    assert backend.get_range(name="Volume") is None


def test_a_control_that_is_not_there_has_no_range(backend, found):
    assert backend.get_range(name="Volume") is None


def test_setting_a_range_value_writes_it_as_a_float(backend, found):
    pattern = _with(found, RANGE, "IUIAutomationRangeValuePattern")
    assert backend.set_range_value(7, name="Volume") is True
    assert pattern.calls == [("SetValue", (7.0,))]


# --- transform and window state -----------------------------------------------

def test_moving_a_control_writes_floats(backend, found):
    pattern = _with(found, TRANSFORM, "IUIAutomationTransformPattern")
    assert backend.move_element(10, 20, name="Panel") is True
    assert pattern.calls == [("Move", (10.0, 20.0))]


def test_resizing_a_control_writes_floats(backend, found):
    pattern = _with(found, TRANSFORM, "IUIAutomationTransformPattern")
    assert backend.resize_element(300, 400, name="Panel") is True
    assert pattern.calls == [("Resize", (300.0, 400.0))]


@pytest.mark.parametrize("state,code", [
    ("normal", 0), ("maximized", 1), ("minimized", 2), ("MAXIMIZED", 1),
])
def test_a_window_state_is_written_as_its_visual_state_code(backend, found,
                                                             state, code):
    pattern = _with(found, WINDOW, "IUIAutomationWindowPattern")
    assert backend.set_window_state(state, name="Editor") is True
    assert pattern.calls == [("SetWindowVisualState", (code,))]


def test_an_unknown_window_state_is_refused_before_any_search(backend, found):
    assert backend.set_window_state("shaded", name="Editor") is False
    assert found["filters"] == [], "it never went looking"


@pytest.mark.parametrize("code,expected", [
    (0, "running"), (1, "closing"), (2, "ready"), (3, "blocked_by_modal"),
    (4, "not_responding"),
])
def test_a_window_interaction_state_is_reported_by_name(backend, found, code,
                                                         expected):
    _with(found, WINDOW, "IUIAutomationWindowPattern",
          Pattern(CurrentWindowInteractionState=code))
    assert backend.window_interaction_state(name="Editor") == expected


def test_an_unknown_interaction_state_reads_as_none(backend, found):
    _with(found, WINDOW, "IUIAutomationWindowPattern",
          Pattern(CurrentWindowInteractionState=99))
    assert backend.window_interaction_state(name="Editor") is None


def test_an_unreadable_interaction_state_reads_as_none(backend, found):
    _with(found, WINDOW, "IUIAutomationWindowPattern", Pattern())
    assert backend.window_interaction_state(name="Editor") is None


def test_a_control_that_is_not_a_window_has_no_interaction_state(backend,
                                                                  found):
    found["set"](_control())
    assert backend.window_interaction_state(name="Editor") is None


def test_a_control_that_is_not_there_has_no_interaction_state(backend, found):
    assert backend.window_interaction_state(name="Editor") is None


# --- state --------------------------------------------------------------------

def test_the_state_of_a_control_is_read_from_it(backend, found):
    found["set"](_control(properties={_IS_PASSWORD: False,
                                       30029: True, 30045: "typed",
                                       30046: False}))
    assert backend.get_state(name="Field")["value"] == "typed"


def test_the_state_of_a_control_that_is_not_there_is_none(backend, found):
    assert backend.get_state(name="Field") is None
