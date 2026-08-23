"""Reading structured content out of a Windows control.

Split from `test_accessibility_windows_patterns.py`, which covers acting on a
control; this half is the reads that come back as more than one value -- a
table, a selection, a set of views, the MSAA bridge's fields, a virtualized
row, and the text patterns.

What they have in common is a second layer of indirection. A grid hands back
a cell which carries its *own* pattern; a selection hands back an element
array which has to be walked by index; a text pattern hands back ranges. Each
of those is another cross-process object that can fail on its own, and the
answer for every one of them is the same: report what could be read, and say
"no" in the type the caller was promised rather than raising out of the
middle of a listing.

The virtualized-item path is the one worth reading twice. A row 500 places
down a list does not exist as an element until it is realized, so finding it
and realizing it are two calls and skipping the second hands the caller
something that is not there yet.
"""
from __future__ import annotations

import sys
import types

import pytest

from headless._uia_doubles import (
    Automation, ElementArray, Pattern, RawElement, Rect, UiaModule, Unknown,
    install_comtypes,
)
from je_auto_control.utils.accessibility.backends import (
    windows_backend as backend_module,
)
from je_auto_control.utils.accessibility.backends.windows_backend import (
    WindowsAccessibilityBackend, _header_names, _read_cell, _read_legacy,
    _read_text_attributes, _view_name,
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


# --- tables and grids ---------------------------------------------------------

def _grid(rows, cols, cells=None, item_error=None):
    lookup = dict(cells or {})

    def _get_item(row, column):
        if item_error is not None:
            raise item_error
        return lookup.get((row, column))

    pattern = Pattern(CurrentRowCount=rows, CurrentColumnCount=cols)
    pattern.GetItem = _get_item
    return pattern


def test_a_table_is_read_row_by_row(backend, found):
    cells = {(0, 0): types.SimpleNamespace(CurrentName="a"),
             (0, 1): types.SimpleNamespace(CurrentName="b"),
             (1, 0): types.SimpleNamespace(CurrentName="c"),
             (1, 1): types.SimpleNamespace(CurrentName="d")}
    _with(found, GRID, "IUIAutomationGridPattern", _grid(2, 2, cells))
    assert backend.read_table(name="Grid") == [["a", "b"], ["c", "d"]]


def test_a_cell_that_is_not_there_reads_as_empty(backend, found):
    _with(found, GRID, "IUIAutomationGridPattern", _grid(1, 2, {}))
    assert backend.read_table(name="Grid") == [["", ""]]


def test_a_cell_the_provider_refuses_reads_as_empty(backend, found):
    _with(found, GRID, "IUIAutomationGridPattern",
          _grid(1, 1, item_error=OSError("gone")))
    assert backend.read_table(name="Grid") == [[""]]


def test_a_table_whose_size_cannot_be_read_is_empty(backend, found):
    _with(found, GRID, "IUIAutomationGridPattern", Pattern())
    assert backend.read_table(name="Grid") == []


def test_a_control_that_is_not_a_grid_reads_as_no_table(backend, found):
    found["set"](_control())
    assert backend.read_table(name="Grid") == []


def test_a_control_that_is_not_there_reads_as_no_table(backend, found):
    assert backend.read_table(name="Grid") == []


def test_table_headers_are_read_from_both_axes(backend, found):
    columns = ElementArray([types.SimpleNamespace(CurrentName="Name"),
                            types.SimpleNamespace(CurrentName="Size")])
    rows = ElementArray([types.SimpleNamespace(CurrentName="1")])
    pattern = Pattern()
    pattern.GetCurrentColumnHeaders = lambda: columns
    pattern.GetCurrentRowHeaders = lambda: rows
    _with(found, TABLE, "IUIAutomationTablePattern", pattern)
    assert backend.get_table_headers(name="Grid") == {
        "columns": ["Name", "Size"], "rows": ["1"],
    }


def test_headers_the_provider_refuses_read_as_none(backend, found):
    pattern = Pattern()
    pattern.errors["GetCurrentColumnHeaders"] = OSError("gone")
    _with(found, TABLE, "IUIAutomationTablePattern", pattern)
    assert backend.get_table_headers(name="Grid") is None


def test_a_control_with_no_table_pattern_has_no_headers(backend, found):
    found["set"](_control())
    assert backend.get_table_headers(name="Grid") is None


def test_an_array_whose_length_cannot_be_read_is_empty():
    assert _header_names(ElementArray(length_error=OSError("gone"))) == []


def test_an_array_entry_that_cannot_be_read_reads_as_empty():
    array = ElementArray([types.SimpleNamespace(CurrentName="a")],
                         element_error=OSError("gone"))
    assert _header_names(array) == [""]


def test_a_grid_cell_carries_its_own_coordinates(backend, found):
    cell = types.SimpleNamespace(CurrentName="value")
    item = Unknown("IUIAutomationGridItemPattern",
                   Pattern(CurrentRow=3, CurrentColumn=4, CurrentRowSpan=2,
                           CurrentColumnSpan=1))
    cell_element = RawElement(patterns={GRID_ITEM: item})
    cell_element.CurrentName = "value"
    del cell
    _with(found, GRID, "IUIAutomationGridPattern",
          _grid(1, 1, {(0, 0): cell_element}))
    assert backend.get_grid_cell(0, 0, name="Grid") == {
        "value": "value", "row": 3, "column": 4,
        "row_span": 2, "column_span": 1,
    }


def test_a_grid_cell_without_an_item_pattern_reports_where_it_was_asked_for():
    cell = types.SimpleNamespace(CurrentName="value")
    assert _read_cell(None, cell, 1, 2) == {
        "value": "value", "row": 1, "column": 2,
        "row_span": 1, "column_span": 1,
    }


def test_a_grid_cell_whose_span_cannot_be_read_keeps_the_default():
    cell = types.SimpleNamespace(CurrentName="value")
    assert _read_cell(Pattern(CurrentRow=1), cell, 0, 0)["row_span"] == 1


def test_a_grid_cell_that_is_not_there_is_none(backend, found):
    _with(found, GRID, "IUIAutomationGridPattern", _grid(1, 1, {}))
    assert backend.get_grid_cell(0, 0, name="Grid") is None


def test_a_grid_cell_the_provider_refuses_is_none(backend, found):
    _with(found, GRID, "IUIAutomationGridPattern",
          _grid(1, 1, item_error=OSError("gone")))
    assert backend.get_grid_cell(0, 0, name="Grid") is None


def test_a_control_that_is_not_a_grid_has_no_cell(backend, found):
    found["set"](_control())
    assert backend.get_grid_cell(0, 0, name="Grid") is None


# --- selection and views ------------------------------------------------------

def test_a_selection_reports_its_items_and_its_rules(backend, found):
    pattern = Pattern(CurrentCanSelectMultiple=True,
                      CurrentIsSelectionRequired=False)
    pattern.GetCurrentSelection = lambda: ElementArray(
        [types.SimpleNamespace(CurrentName="one")])
    _with(found, SELECTION, "IUIAutomationSelectionPattern", pattern)
    assert backend.get_selection(name="List") == {
        "items": ["one"], "can_select_multiple": True, "is_required": False,
    }


def test_a_selection_the_provider_refuses_is_none(backend, found):
    pattern = Pattern()
    pattern.errors["GetCurrentSelection"] = OSError("gone")
    _with(found, SELECTION, "IUIAutomationSelectionPattern", pattern)
    assert backend.get_selection(name="List") is None


def test_a_control_with_no_selection_pattern_has_no_selection(backend, found):
    found["set"](_control())
    assert backend.get_selection(name="List") is None


def _views(names, current=0):
    pattern = Pattern(CurrentCurrentView=current)
    pattern.GetCurrentSupportedViews = lambda: list(range(len(names)))
    pattern.GetViewName = lambda view_id: names[int(view_id)]
    return pattern


def test_the_views_of_a_control_are_listed_by_name(backend, found):
    _with(found, MULTIPLE_VIEW, "IUIAutomationMultipleViewPattern",
          _views(["Icons", "Details"], current=1))
    assert backend.list_views(name="Files") == {
        "current": "Details", "views": ["Icons", "Details"],
    }


def test_views_the_provider_refuses_read_as_none(backend, found):
    pattern = Pattern(CurrentCurrentView=0)
    pattern.errors["GetCurrentSupportedViews"] = OSError("gone")
    _with(found, MULTIPLE_VIEW, "IUIAutomationMultipleViewPattern", pattern)
    assert backend.list_views(name="Files") is None


def test_a_control_with_no_views_has_none(backend, found):
    found["set"](_control())
    assert backend.list_views(name="Files") is None


def test_a_view_name_that_cannot_be_read_is_empty():
    assert _view_name(Pattern(), "not a number") == ""


def test_setting_a_view_matches_it_by_name(backend, found):
    pattern = _views(["Icons", "Details"])
    _with(found, MULTIPLE_VIEW, "IUIAutomationMultipleViewPattern", pattern)
    assert backend.set_view("Details", name="Files") is True
    assert ("SetCurrentView", (1,)) in pattern.calls


def test_setting_a_view_that_does_not_exist_fails(backend, found):
    _with(found, MULTIPLE_VIEW, "IUIAutomationMultipleViewPattern",
          _views(["Icons"]))
    assert backend.set_view("Details", name="Files") is False


def test_setting_a_view_the_provider_refuses_fails(backend, found):
    pattern = Pattern()
    pattern.errors["GetCurrentSupportedViews"] = OSError("gone")
    _with(found, MULTIPLE_VIEW, "IUIAutomationMultipleViewPattern", pattern)
    assert backend.set_view("Details", name="Files") is False


def test_setting_a_view_on_a_control_with_none_fails(backend, found):
    found["set"](_control())
    assert backend.set_view("Details", name="Files") is False


# --- the MSAA bridge ----------------------------------------------------------

def test_the_legacy_fields_are_read_into_plain_values(backend, found):
    _with(found, LEGACY, "IUIAutomationLegacyIAccessiblePattern",
          Pattern(CurrentName="OK", CurrentValue="", CurrentDescription="d",
                  CurrentDefaultAction="Press", CurrentRole=43,
                  CurrentState=1048576))
    assert backend.legacy_info(name="OK") == {
        "name": "OK", "value": "", "description": "d",
        "default_action": "Press", "role": 43, "state": 1048576,
    }


def test_a_legacy_field_the_provider_will_not_answer_reads_as_none():
    assert _read_legacy(Pattern())["name"] is None


def test_a_control_with_no_legacy_bridge_has_no_legacy_info(backend, found):
    found["set"](_control())
    assert backend.legacy_info(name="OK") is None


def test_the_legacy_default_action_is_performed(backend, found):
    pattern = _with(found, LEGACY, "IUIAutomationLegacyIAccessiblePattern")
    assert backend.legacy_default_action(name="OK") is True
    assert pattern.calls == [("DoDefaultAction", ())]


# --- virtualized items --------------------------------------------------------

def _container(item, by_property=None, find_error=None):
    pattern = Pattern()

    def _find(scope, property_id, value):
        if find_error is not None:
            raise find_error
        if by_property is not None and property_id != by_property:
            return None
        return item

    pattern.FindItemByProperty = _find
    return pattern


def test_a_virtual_item_is_found_realized_and_converted(backend, found):
    realize = Pattern()
    item = RawElement(name="Row 500", rect=Rect(0, 0, 10, 10),
                      patterns={VIRTUALIZED: Unknown(
                          "IUIAutomationVirtualizedItemPattern", realize)})
    _with(found, ITEM_CONTAINER, "IUIAutomationItemContainerPattern",
          _container(item))
    element = backend.find_virtual_item("Row 500", container_name="List")
    assert element.name == "Row 500"
    assert realize.calls == [("Realize", ())], (
        "a virtualized row is not a real element until it is realized"
    )


def test_a_virtual_item_can_be_looked_up_by_automation_id(backend, found):
    item = RawElement(name="Row", rect=Rect(0, 0, 1, 1))
    _with(found, ITEM_CONTAINER, "IUIAutomationItemContainerPattern",
          _container(item, by_property=backend_module._UIA_AUTOMATIONID_PROPERTY))
    assert backend.find_virtual_item("row-500", by="automation_id",
                                     container_name="List") is not None
    assert backend.find_virtual_item("row-500", container_name="List") is None


def test_a_virtual_item_that_is_not_in_the_container_is_none(backend, found):
    _with(found, ITEM_CONTAINER, "IUIAutomationItemContainerPattern",
          _container(None))
    assert backend.find_virtual_item("Row 500", container_name="List") is None


def test_a_container_that_refuses_the_lookup_answers_none(backend, found):
    _with(found, ITEM_CONTAINER, "IUIAutomationItemContainerPattern",
          _container(None, find_error=OSError("gone")))
    assert backend.find_virtual_item("Row 500", container_name="List") is None


def test_a_container_with_no_item_container_pattern_answers_none(backend,
                                                                 found):
    found["set"](_control())
    assert backend.find_virtual_item("Row 500", container_name="List") is None


def test_a_container_that_is_not_there_answers_none(backend, found):
    assert backend.find_virtual_item("Row 500", container_name="List") is None


def test_an_item_that_cannot_be_realized_is_still_returned(backend, found):
    realize = Pattern()
    realize.errors["Realize"] = OSError("already real")
    item = RawElement(name="Row", rect=Rect(0, 0, 1, 1),
                      patterns={VIRTUALIZED: Unknown(
                          "IUIAutomationVirtualizedItemPattern", realize)})
    _with(found, ITEM_CONTAINER, "IUIAutomationItemContainerPattern",
          _container(item))
    assert backend.find_virtual_item("Row", container_name="List") is not None


def test_an_item_with_no_virtualized_pattern_is_returned_as_is(backend,
                                                               found):
    item = RawElement(name="Row", rect=Rect(0, 0, 1, 1))
    _with(found, ITEM_CONTAINER, "IUIAutomationItemContainerPattern",
          _container(item))
    assert backend.find_virtual_item("Row", container_name="List").name == "Row"


# --- text ---------------------------------------------------------------------

class _TextRange:
    def __init__(self, text="", attributes=None) -> None:
        self._text = text
        self._attributes = dict(attributes or {})
        self.selected = 0
        self.attribute_error = None

    def GetText(self, length):      # noqa: N802  # reason: the UIA name
        return self._text

    def GetAttributeValue(self, attribute_id):  # noqa: N802  # UIA name
        if self.attribute_error is not None:
            raise self.attribute_error
        return self._attributes[attribute_id]

    def Select(self):               # noqa: N802  # reason: the UIA name
        self.selected += 1


def _text_pattern(document="", selection=None, visible=None,
                  find_result="missing"):
    pattern = Pattern(DocumentRange=_TextRange(document))
    if find_result != "missing":
        pattern.DocumentRange.FindText = lambda *args: find_result
    else:
        pattern.DocumentRange.FindText = lambda *args: None
    pattern.GetSelection = lambda: selection
    pattern.GetVisibleRanges = lambda: visible
    return pattern


def test_the_document_text_is_read_whole(backend, found):
    _with(found, TEXT, "IUIAutomationTextPattern",
          _text_pattern(document="the whole document"))
    assert backend.document_text(name="Editor") == "the whole document"


def test_a_control_with_no_text_pattern_has_no_document(backend, found):
    found["set"](_control())
    assert backend.document_text(name="Editor") is None


def test_a_control_that_is_not_there_has_no_document(backend, found):
    assert backend.document_text(name="Editor") is None


def test_a_document_the_provider_refuses_reads_as_none(backend, found):
    pattern = Pattern()
    _with(found, TEXT, "IUIAutomationTextPattern", pattern)
    assert backend.document_text(name="Editor") is None


def test_the_selected_text_comes_from_the_first_selected_range(backend,
                                                                found):
    selection = ElementArray([_TextRange("chosen")])
    _with(found, TEXT, "IUIAutomationTextPattern",
          _text_pattern(selection=selection))
    assert backend.selected_text(name="Editor") == "chosen"


def test_an_empty_selection_reads_as_the_empty_string(backend, found):
    # "" and None are different answers: nothing is selected, against there
    # being no text control at all.
    _with(found, TEXT, "IUIAutomationTextPattern",
          _text_pattern(selection=ElementArray([])))
    assert backend.selected_text(name="Editor") == ""


def test_a_selection_the_provider_refuses_reads_as_none(backend, found):
    _with(found, TEXT, "IUIAutomationTextPattern",
          _text_pattern(selection=ElementArray(length_error=OSError("gone"))))
    assert backend.selected_text(name="Editor") is None


@pytest.mark.parametrize("method", ["selected_text", "visible_text",
                                    "text_attributes"])
def test_a_control_with_no_text_pattern_has_no_text_of_any_kind(backend,
                                                                found,
                                                                method):
    found["set"](_control())
    assert getattr(backend, method)(name="Editor") is None


def test_the_visible_text_is_the_visible_ranges_joined(backend, found):
    visible = ElementArray([_TextRange("first "), _TextRange("second")])
    _with(found, TEXT, "IUIAutomationTextPattern",
          _text_pattern(visible=visible))
    assert backend.visible_text(name="Editor") == "first second"


def test_visible_text_the_provider_refuses_reads_as_none(backend, found):
    _with(found, TEXT, "IUIAutomationTextPattern",
          _text_pattern(visible=ElementArray(length_error=OSError("gone"))))
    assert backend.visible_text(name="Editor") is None


def test_finding_text_reports_whether_a_range_came_back(backend, found):
    _with(found, TEXT, "IUIAutomationTextPattern",
          _text_pattern(find_result=_TextRange("found")))
    assert backend.find_text("needle", name="Editor") is True


def test_finding_text_that_is_not_there_reports_false(backend, found):
    _with(found, TEXT, "IUIAutomationTextPattern", _text_pattern())
    assert backend.find_text("needle", name="Editor") is False


def test_finding_text_in_a_control_that_is_not_there_reports_false(backend,
                                                                   found):
    assert backend.find_text("needle", name="Editor") is False


def test_selecting_text_selects_the_range_it_found(backend, found):
    target = _TextRange("found")
    _with(found, TEXT, "IUIAutomationTextPattern",
          _text_pattern(find_result=target))
    assert backend.select_text("needle", name="Editor") is True
    assert target.selected == 1


def test_selecting_text_that_is_not_there_reports_false(backend, found):
    _with(found, TEXT, "IUIAutomationTextPattern", _text_pattern())
    assert backend.select_text("needle", name="Editor") is False


def test_a_selection_the_control_refuses_reports_false(backend, found):
    target = _TextRange("found")

    def _boom():
        raise OSError("read-only")

    target.Select = _boom
    _with(found, TEXT, "IUIAutomationTextPattern",
          _text_pattern(find_result=target))
    assert backend.select_text("needle", name="Editor") is False


def test_a_find_the_provider_refuses_reports_false(backend, found):
    pattern = Pattern(DocumentRange=_TextRange())

    def _boom(*_args):
        raise OSError("gone")

    pattern.DocumentRange.FindText = _boom
    _with(found, TEXT, "IUIAutomationTextPattern", pattern)
    assert backend.find_text("needle", name="Editor") is False


_ATTRS = {40005: "Consolas", 40006: 12.0, 40007: 700, 40008: 255, 40014: True}


def test_text_attributes_come_from_the_selection_when_there_is_one(backend,
                                                                    found):
    selected = _TextRange("chosen", attributes=_ATTRS)
    _with(found, TEXT, "IUIAutomationTextPattern",
          _text_pattern(selection=ElementArray([selected])))
    assert backend.text_attributes(name="Editor")["font_name"] == "Consolas"


def test_text_attributes_fall_back_to_the_whole_document(backend, found):
    pattern = _text_pattern(document="all of it",
                            selection=ElementArray([]))
    pattern.DocumentRange._attributes = dict(_ATTRS)
    _with(found, TEXT, "IUIAutomationTextPattern", pattern)
    assert backend.text_attributes(name="Editor")["font_size"] == 12.0


def test_a_font_weight_of_seven_hundred_is_bold():
    assert _read_text_attributes(_TextRange(attributes=_ATTRS))["bold"] is True


def test_a_lighter_font_weight_is_not_bold():
    attributes = {**_ATTRS, 40007: 400}
    assert _read_text_attributes(
        _TextRange(attributes=attributes))["bold"] is False


def test_an_unreadable_weight_leaves_boldness_unknown():
    # None is not False: "the control did not say" is a different answer from
    # "it is not bold", and a caller may want to ask again.
    text_range = _TextRange(attributes={})
    text_range.attribute_error = OSError("gone")
    assert _read_text_attributes(text_range)["bold"] is None


def test_a_selection_that_cannot_be_read_leaves_attributes_none(backend,
                                                                 found):
    _with(found, TEXT, "IUIAutomationTextPattern",
          _text_pattern(selection=ElementArray(length_error=OSError("gone"))))
    assert backend.text_attributes(name="Editor") is None


def test_a_control_with_no_text_pattern_has_no_attributes(backend, found):
    found["set"](_control())
    assert backend.text_attributes(name="Editor") is None


# --- focus --------------------------------------------------------------------

def test_focusing_a_control_calls_set_focus_on_it(backend, found):
    raw = found["set"](_control())
    assert backend.set_focus(name="Field") is True
    assert raw.focused == 1


def test_focusing_a_control_that_is_not_there_fails(backend, found):
    assert backend.set_focus(name="Field") is False


def test_a_focus_the_control_refuses_fails(backend, found):
    raw = found["set"](_control())
    raw.focus_error = OSError("cannot focus")
    assert backend.set_focus(name="Field") is False


def test_waiting_for_focus_registers_and_removes_its_handler(backend,
                                                             monkeypatch):
    install_comtypes(monkeypatch)
    automation = backend._automation
    result = backend.wait_for_focus_change(timeout=0.01)
    assert result is None, "nothing focused inside the timeout"
    assert automation.focus_handlers == [], "the handler was removed again"


def test_waiting_for_focus_reports_the_element_that_took_it(backend,
                                                            monkeypatch):
    install_comtypes(monkeypatch)
    captured = {}

    def _handler_factory(sink):
        captured["sink"] = sink
        sink.put({"name": "Field"})
        return object()

    monkeypatch.setattr(backend, "_make_focus_handler", _handler_factory)
    assert backend.wait_for_focus_change(timeout=1.0) == {"name": "Field"}


def test_waiting_for_focus_without_comtypes_answers_none(backend,
                                                         monkeypatch):
    monkeypatch.setattr(backend, "_make_focus_handler", lambda sink: None)
    assert backend.wait_for_focus_change(timeout=0.01) is None


def test_a_provider_that_refuses_the_subscription_answers_none(backend,
                                                               monkeypatch):
    install_comtypes(monkeypatch)
    backend._automation.add_error = OSError("cannot subscribe")
    assert backend.wait_for_focus_change(timeout=0.01) is None


def test_a_handler_that_cannot_be_removed_does_not_escape(backend,
                                                          monkeypatch):
    install_comtypes(monkeypatch)
    backend._automation.remove_error = OSError("already gone")
    assert backend.wait_for_focus_change(timeout=0.01) is None


def test_the_focus_handler_reports_the_element_that_was_focused(backend,
                                                                monkeypatch):
    import queue
    install_comtypes(monkeypatch)
    sink: "queue.Queue" = queue.Queue()
    handler = backend._make_focus_handler(sink)
    assert handler is not None
    raw = RawElement(name="Field", rect=Rect(0, 0, 1, 1))
    handler.IUIAutomationFocusChangedEventHandler_HandleFocusChangedEvent(raw)
    assert sink.get_nowait()["name"] == "Field"


def test_a_focus_event_whose_element_is_gone_still_reports_something(
        backend, monkeypatch):
    import queue
    install_comtypes(monkeypatch)
    sink: "queue.Queue" = queue.Queue()
    handler = backend._make_focus_handler(sink)
    broken = RawElement(rect=Rect(0, 0, 1, 1))
    del broken.CurrentName
    handler.IUIAutomationFocusChangedEventHandler_HandleFocusChangedEvent(
        broken)
    assert sink.get_nowait() == {"focused": True}


def test_no_comtypes_means_no_focus_handler(backend, monkeypatch):
    monkeypatch.setitem(sys.modules, "comtypes", None)
    assert backend._make_focus_handler(None) is None


def test_a_uia_module_without_the_event_interface_has_no_handler(backend,
                                                                 monkeypatch):
    install_comtypes(monkeypatch)
    backend._uia_module = types.SimpleNamespace()
    assert backend._make_focus_handler(None) is None


