"""Where a UIA search starts, and what a control is actually holding.

`windows_query.py` and `windows_state.py` are the two halves of the Windows
accessibility backend that were split out of it, and both sat near 20% on
every square -- including the Windows ones, because a test that reaches them
needs a UIAutomation provider and a desktop with windows on it.

Neither needs either. Both take the automation object as an argument, and
every COM import in them is lazy, so a recorder standing in for UIA drives
them from all nine squares.

The two files encode measurements, and the tests below are what stops those
being quietly undone:

* **A desktop-rooted `FindAll` is one call that cannot be stopped.** Measured
  at ~61 s for 2,085 elements, against 0.14 s starting from one window. So
  `search_roots` yields *windows*, front-most first, and `walk_elements`
  walks node by node -- asking for 200 elements has to cost 200 elements'
  worth of work no matter how large the window is.
* **Properties are cross-process reads.** They come back through a cache
  request built once per walk; reading them individually is thousands of
  round trips.
* **comtypes returns a wrapper around a NULL pointer, not `None`.** So
  `child is not None` is *true* at the end of a sibling list, and the walk
  collects a phantom element that raises the moment anything reads it.
  Truthiness is the check that works, and a stub that returned `None` would
  never catch the difference -- so the one here returns a false-y wrapper,
  exactly as comtypes does.
* **An unsupported pattern answers with a default**, not an error: an empty
  string for a control that has no value at all. Reading it without asking
  whether the pattern exists turns "no such concept" into "it is empty",
  which is the more misleading of the two because a caller acts on it.
* **A password field's contents never leave.** UIA is supposed to mask them,
  but that is a convention a custom-drawn control can ignore.
"""
from __future__ import annotations

import sys
import types

import pytest

from je_auto_control.utils.accessibility.backends import windows_query as query
from je_auto_control.utils.accessibility.backends.windows_query import (
    CACHED_PROPERTIES, _is_null, search_root, search_roots, walk_elements,
)
from je_auto_control.utils.accessibility.backends.windows_state import (
    TOGGLE_STATES, is_password, read_state,
)
from je_auto_control.utils.accessibility.element import (
    AccessibilityNotAvailableError,
)


class _NullPointer:
    """What comtypes hands back for "no such element": false-y, not None."""

    def __bool__(self) -> bool:
        return False


class _Element:
    """A UIA element: a name, some children, and scripted property reads."""

    def __init__(self, name: str = "", children=None, properties=None,
                 error=None) -> None:
        self.name = name
        self.children = list(children or [])
        self.properties = dict(properties or {})
        self.error = error
        self.reads = []

    def GetCurrentPropertyValue(self, property_id):  # noqa: N802  # UIA name
        self.reads.append(property_id)
        if self.error is not None:
            raise self.error
        return self.properties.get(property_id)

    def __repr__(self) -> str:      # pragma: no cover - debugging aid
        return f"<{self.name}>"


class _CacheRequest:
    def __init__(self) -> None:
        self.properties = []

    def AddProperty(self, property_id):     # noqa: N802  # reason: UIA name
        self.properties.append(property_id)


class _Walker:
    """The control-view walker, over `_Element.children`."""

    def __init__(self, world) -> None:
        self._world = world

    def GetFirstChildElementBuildCache(self, node, request):    # noqa: N802
        self._world.cache_requests.append(request)
        if node in self._world.first_child_errors:
            raise self._world.first_child_errors[node]
        return node.children[0] if node.children else _NullPointer()

    def GetNextSiblingElementBuildCache(self, node, request):   # noqa: N802
        if node in self._world.sibling_errors:
            raise self._world.sibling_errors[node]
        for parent in self._world.parents_of(node):
            index = parent.children.index(node)
            if index + 1 < len(parent.children):
                return parent.children[index + 1]
        return _NullPointer()


class _Automation:
    def __init__(self, root=None, handles=None) -> None:
        self.root = root or _Element("desktop")
        self.handles = dict(handles or {})   # hwnd -> element (or exception)
        self.cache_requests = []
        self.first_child_errors = {}
        self.sibling_errors = {}
        self.ControlViewWalker = _Walker(self)   # noqa: N815  # reason: UIA

    def GetRootElement(self):       # noqa: N802  # reason: the UIA name
        return self.root

    def CreateCacheRequest(self):   # noqa: N802  # reason: the UIA name
        return _CacheRequest()

    def ElementFromHandle(self, hwnd):  # noqa: N802  # reason: the UIA name
        found = self.handles.get(hwnd)
        if isinstance(found, Exception):
            raise found
        return found

    def parents_of(self, node):
        stack = [self.root, *[h for h in self.handles.values()
                              if isinstance(h, _Element)]]
        seen = set()
        while stack:
            current = stack.pop()
            if id(current) in seen:
                continue
            seen.add(id(current))
            if node in current.children:
                yield current
            stack.extend(current.children)


@pytest.fixture
def windows(monkeypatch):
    """Stand in for `get_all_window_hwnd`, on every platform."""
    listing = []

    def _get_all_window_hwnd():
        return list(listing)

    module = types.ModuleType(
        "je_auto_control.windows.window.windows_window_manage")
    module.get_all_window_hwnd = _get_all_window_hwnd
    package = types.ModuleType("je_auto_control.windows.window")
    package.windows_window_manage = module
    monkeypatch.setitem(sys.modules, "je_auto_control.windows.window", package)
    monkeypatch.setitem(
        sys.modules, "je_auto_control.windows.window.windows_window_manage",
        module)
    return listing


# --- choosing a root ----------------------------------------------------------

def test_an_unscoped_search_starts_at_the_desktop():
    automation = _Automation()
    assert search_root(automation, None) is automation.root


def test_a_window_title_is_matched_as_a_case_insensitive_substring(windows):
    target = _Element("notepad")
    automation = _Automation(handles={101: target})
    windows.extend([(100, "Calculator"), (101, "Untitled - Notepad")])
    assert search_root(automation, " notePAD ") is target


def test_the_first_window_whose_title_matches_wins(windows):
    first, second = _Element("first"), _Element("second")
    automation = _Automation(handles={1: first, 2: second})
    windows.extend([(1, "Report - Editor"), (2, "Notes - Editor")])
    assert search_root(automation, "Editor") is first


def test_a_title_that_matches_nothing_says_so(windows):
    windows.append((1, "Calculator"))
    with pytest.raises(AccessibilityNotAvailableError, match="Notepad"):
        search_root(_Automation(), "Notepad")


def test_a_window_with_no_title_is_not_a_match(windows):
    windows.append((1, None))
    with pytest.raises(AccessibilityNotAvailableError):
        search_root(_Automation(), "anything")


def test_a_window_uia_will_not_open_is_skipped(windows):
    later = _Element("later")
    automation = _Automation(handles={1: None, 2: later})
    windows.extend([(1, "Editor one"), (2, "Editor two")])
    assert search_root(automation, "Editor") is later


# --- iterating the roots ------------------------------------------------------

def test_an_unscoped_walk_yields_windows_rather_than_the_desktop(windows):
    # Same coverage as a desktop-rooted walk, but the caller can stop. That
    # is the 0.22 s / 61 s difference the module's docstring measured.
    first, second = _Element("one"), _Element("two")
    automation = _Automation(handles={1: first, 2: second})
    windows.extend([(1, "one"), (2, "two")])
    assert list(search_roots(automation, None)) == [first, second]


def test_the_roots_come_back_in_z_order(windows):
    # EnumWindows returns front-to-back, so the window the user is actually
    # looking at is searched first.
    front, back = _Element("front"), _Element("back")
    automation = _Automation(handles={9: front, 1: back})
    windows.extend([(9, "front"), (1, "back")])
    assert [e.name for e in search_roots(automation, None)] == ["front",
                                                                "back"]


def test_a_window_that_closes_between_enumerate_and_use_is_skipped(windows):
    survivor = _Element("survivor")
    automation = _Automation(handles={1: OSError("window closed"),
                                      2: survivor})
    windows.extend([(1, "gone"), (2, "survivor")])
    assert list(search_roots(automation, None)) == [survivor]


def test_a_null_pointer_root_is_skipped(windows):
    # comtypes answers with a wrapper around NULL, which is not None.
    survivor = _Element("survivor")
    automation = _Automation(handles={1: _NullPointer(), 2: survivor})
    windows.extend([(1, "phantom"), (2, "survivor")])
    assert list(search_roots(automation, None)) == [survivor]


def test_a_scoped_walk_yields_exactly_one_root(windows):
    target = _Element("notepad")
    automation = _Automation(handles={1: target})
    windows.append((1, "Untitled - Notepad"))
    assert list(search_roots(automation, "Notepad")) == [target]


@pytest.mark.parametrize("value,expected", [
    (None, True), (_NullPointer(), True), (_Element("real"), False),
])
def test_null_detection_uses_truthiness_not_identity(value, expected):
    assert _is_null(value) is expected


# --- walking ------------------------------------------------------------------

def _tree():
    leaf_a = _Element("a")
    leaf_b = _Element("b")
    group = _Element("group", children=[leaf_a, leaf_b])
    tail = _Element("tail")
    root = _Element("root", children=[group, tail])
    return root, [group, leaf_a, leaf_b, tail]


def test_the_walk_is_depth_first_in_reading_order():
    root, expected = _tree()
    automation = _Automation(root=root)
    walked = list(walk_elements(automation, root, 10))
    assert [e.name for e in walked] == [e.name for e in expected]


def test_the_walk_stops_at_the_limit():
    root, _expected = _tree()
    automation = _Automation(root=root)
    assert len(list(walk_elements(automation, root, 2))) == 2


@pytest.mark.parametrize("limit", [0, -1])
def test_a_walk_with_no_budget_asks_for_nothing(limit):
    root, _expected = _tree()
    automation = _Automation(root=root)
    assert list(walk_elements(automation, root, limit)) == []
    assert automation.cache_requests == [], "not one cross-process call"


def test_every_property_the_conversion_reads_is_cached_up_front():
    # Each `Current*` read is another cross-process call; the bulk request is
    # what makes converting 500 elements cost 0.02 s.
    root, _expected = _tree()
    automation = _Automation(root=root)
    list(walk_elements(automation, root, 10))
    assert automation.cache_requests
    assert automation.cache_requests[0].properties == list(CACHED_PROPERTIES)


def test_a_node_that_refuses_its_first_child_ends_that_branch():
    root, _expected = _tree()
    automation = _Automation(root=root)
    automation.first_child_errors[root.children[0]] = OSError("gone")
    walked = [e.name for e in walk_elements(automation, root, 10)]
    assert walked == ["group", "tail"], "the sibling after it still came back"


def test_a_node_that_refuses_a_sibling_keeps_what_it_already_had():
    root, _expected = _tree()
    automation = _Automation(root=root)
    automation.sibling_errors[root.children[0]] = OSError("gone")
    walked = [e.name for e in walk_elements(automation, root, 10)]
    assert walked == ["group", "a", "b"], "tail was never reached"


def test_a_node_with_more_children_than_the_budget_is_capped():
    children = [_Element(f"c{index}") for index in range(50)]
    root = _Element("root", children=children)
    automation = _Automation(root=root)
    assert len(list(walk_elements(automation, root, 3))) == 3


# --- reading a control's state ------------------------------------------------

_IS_PASSWORD = 30019
_IS_VALUE_AVAILABLE, _VALUE = 30029, 30045
_IS_TOGGLE_AVAILABLE, _TOGGLE = 30041, 30086
_IS_SELECTION_AVAILABLE, _SELECTED = 30036, 30079
_IS_RANGE_AVAILABLE, _RANGE = 30034, 30047
_READONLY = 30046
_LEGACY_VALUE = 30093


def _control(properties):
    """A UIA element whose property reads answer from a plain dict."""
    return _Element(properties=properties)


def test_a_password_field_reports_only_that_it_is_one():
    state = read_state(_control({_IS_PASSWORD: True,
                                   _IS_VALUE_AVAILABLE: True,
                                   _VALUE: "hunter2"}))
    assert state == {"password": True}
    assert "hunter2" not in str(state)


def test_an_element_whose_password_flag_cannot_be_read_counts_as_one():
    # Failing closed: the cost of being wrong the other way is a credential.
    element = _control({_IS_VALUE_AVAILABLE: True, _VALUE: "secret"})
    element.error = OSError("provider gone")
    assert is_password(element) is True
    assert read_state(element) == {"password": True}


def test_an_ordinary_field_is_not_a_password():
    assert is_password(_control({_IS_PASSWORD: False})) is False


def test_a_value_is_read_only_when_the_pattern_is_supported():
    # An unsupported pattern answers with the default -- an empty string --
    # which reads as "the value is empty" rather than "there is no value".
    absent = _control({_IS_PASSWORD: False, _VALUE: ""})
    assert "value" not in read_state(absent)


def test_a_supported_value_comes_back_as_text_with_its_read_only_flag():
    state = read_state(_control({_IS_PASSWORD: False,
                                    _IS_VALUE_AVAILABLE: True,
                                    _VALUE: 42, _READONLY: True}))
    assert state["value"] == "42"
    assert state["read_only"] is True


def test_an_empty_supported_value_is_still_a_value():
    state = read_state(_control({_IS_PASSWORD: False,
                                    _IS_VALUE_AVAILABLE: True, _VALUE: None}))
    assert state.get("value") is None, "None never reached the state at all"


def test_a_control_with_no_value_pattern_falls_back_to_the_legacy_one():
    # Win32 controls with no UIA provider still answer the legacy accessible
    # interface, and that is the only value they will ever report.
    state = read_state(_control({_IS_PASSWORD: False,
                                    _LEGACY_VALUE: "legacy text"}))
    assert state["value"] == "legacy text"
    assert "read_only" not in state


def test_an_empty_legacy_value_is_not_reported():
    state = read_state(_control({_IS_PASSWORD: False, _LEGACY_VALUE: ""}))
    assert "value" not in state


@pytest.mark.parametrize("code,expected", sorted(TOGGLE_STATES.items()))
def test_a_toggle_state_is_reported_by_name(code, expected):
    state = read_state(_control({_IS_PASSWORD: False,
                                    _IS_TOGGLE_AVAILABLE: True,
                                    _TOGGLE: code}))
    assert state["toggle"] == expected


def test_an_unknown_toggle_code_is_reported_as_itself():
    state = read_state(_control({_IS_PASSWORD: False,
                                    _IS_TOGGLE_AVAILABLE: True, _TOGGLE: 9}))
    assert state["toggle"] == "9"


def test_a_selection_state_is_reported_as_a_bool():
    state = read_state(_control({_IS_PASSWORD: False,
                                    _IS_SELECTION_AVAILABLE: True,
                                    _SELECTED: 1}))
    assert state["selected"] is True


def test_a_range_value_is_reported_as_a_float():
    state = read_state(_control({_IS_PASSWORD: False,
                                    _IS_RANGE_AVAILABLE: True, _RANGE: 3}))
    assert state["number"] == 3.0
    assert isinstance(state["number"], float)


def test_a_control_that_supports_nothing_reports_nothing():
    assert read_state(_control({_IS_PASSWORD: False})) == {}


def test_a_control_that_supports_several_patterns_reports_all_of_them():
    state = read_state(_control({
        _IS_PASSWORD: False,
        _IS_VALUE_AVAILABLE: True, _VALUE: "7", _READONLY: False,
        _IS_TOGGLE_AVAILABLE: True, _TOGGLE: 1,
        _IS_SELECTION_AVAILABLE: True, _SELECTED: True,
        _IS_RANGE_AVAILABLE: True, _RANGE: 7.5,
    }))
    assert state == {"value": "7", "read_only": False, "toggle": "on",
                     "selected": True, "number": 7.5}


def test_the_uia_error_tuple_contains_the_com_error_on_windows():
    # comtypes reports provider failures as COMError, which inherits from
    # Exception and from none of the usual suspects -- so an
    # `except (OSError, AttributeError)` around a UIA call does not contain
    # it, and a window closing mid-walk surfaces exactly that way.
    assert OSError in query.UIA_ERRORS
    if sys.platform == "win32":
        from _ctypes import COMError
        assert COMError in query.UIA_ERRORS
