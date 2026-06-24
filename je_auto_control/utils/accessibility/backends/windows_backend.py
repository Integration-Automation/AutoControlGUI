"""Windows UIAutomation backend via ``comtypes``.

Requires ``pip install comtypes``. If the module is absent, ``available`` is
``False`` and the facade falls back to the Null backend.

Flattens the UIAutomation tree into ``AccessibilityElement`` records one
level at a time starting from the root desktop, filtered by app if needed.
Only ``is_control_element=True`` nodes are surfaced to avoid millions of
decorative text children.
"""
from typing import Any, Dict, List, Optional

from je_auto_control.utils.accessibility.backends.base import (
    AccessibilityBackend,
)
from je_auto_control.utils.accessibility.element import (
    AccessibilityElement, AccessibilityNotAvailableError, element_matches,
)
from je_auto_control.utils.logging.logging_instance import autocontrol_logger

_TREE_SCOPE_DESCENDANTS = 4
_UIA_IS_CONTROL_ELEMENT_PROPERTY = 30016
_UIA_NAME_PROPERTY = 30005
_UIA_VALUE_PATTERN_ID = 10002
_UIA_INVOKE_PATTERN_ID = 10000
_UIA_TOGGLE_PATTERN_ID = 10015
_UIA_GRID_PATTERN_ID = 10006
_UIA_EXPANDCOLLAPSE_PATTERN_ID = 10005
_UIA_SELECTIONITEM_PATTERN_ID = 10010
_UIA_RANGEVALUE_PATTERN_ID = 10003
_UIA_SCROLLITEM_PATTERN_ID = 10017
_UIA_TEXT_PATTERN_ID = 10014
_UIA_ITEMCONTAINER_PATTERN_ID = 10019
_UIA_VIRTUALIZEDITEM_PATTERN_ID = 10020
_UIA_TABLE_PATTERN_ID = 10012
_UIA_GRIDITEM_PATTERN_ID = 10007
_UIA_TRANSFORM_PATTERN_ID = 10016
_UIA_WINDOW_PATTERN_ID = 10009
_UIA_LEGACYIACCESSIBLE_PATTERN_ID = 10018
_UIA_SELECTION_PATTERN_ID = 10001
_UIA_MULTIPLEVIEW_PATTERN_ID = 10008
_UIA_AUTOMATIONID_PROPERTY = 30011
_EXPAND_STATES = {0: "collapsed", 1: "expanded", 2: "partial", 3: "leaf"}
_WINDOW_VISUAL_STATES = {"normal": 0, "maximized": 1, "minimized": 2}
_WINDOW_INTERACTION_STATES = {
    0: "running", 1: "closing", 2: "ready", 3: "blocked_by_modal",
    4: "not_responding",
}


def _is_available() -> bool:
    try:
        import comtypes.client  # noqa: F401  # reason: probe import
        return True
    except ImportError:
        return False


class WindowsAccessibilityBackend(AccessibilityBackend):
    """UIAutomation-based flat element listing."""

    name = "windows-uia"

    def __init__(self) -> None:
        self.available = _is_available()
        self._automation = None
        self._uia_module = None

    def _ensure_automation(self):
        if self._automation is not None:
            return self._automation
        if not self.available:
            raise AccessibilityNotAvailableError(
                "comtypes is required for Windows accessibility; "
                "install it with: pip install comtypes",
            )
        import comtypes.client  # noqa: F401
        from comtypes import CoCreateInstance, GUID
        try:
            uia_module = comtypes.client.GetModule("UIAutomationCore.dll")
        except OSError as error:
            raise AccessibilityNotAvailableError(
                f"UIAutomationCore.dll unavailable: {error!r}",
            ) from error
        automation = CoCreateInstance(
            GUID("{ff48dba4-60ef-4201-aa87-54103eef594e}"),
            interface=uia_module.IUIAutomation,
        )
        self._automation = automation
        self._uia_module = uia_module
        return automation

    def list_elements(self, app_name: Optional[str] = None,
                      max_results: int = 200,
                      ) -> List[AccessibilityElement]:
        automation = self._ensure_automation()
        try:
            root = automation.GetRootElement()
            condition = automation.CreatePropertyCondition(
                _UIA_IS_CONTROL_ELEMENT_PROPERTY, True,
            )
            found = root.FindAll(_TREE_SCOPE_DESCENDANTS, condition)
        except (OSError, AttributeError) as error:
            autocontrol_logger.error("UIA FindAll failed: %r", error)
            return []
        results: List[AccessibilityElement] = []
        count = min(max(0, int(max_results)), int(found.Length or 0))
        for idx in range(count):
            element = _convert_uia(found.GetElement(idx))
            if element is None:
                continue
            if app_name is not None and element.app_name != app_name:
                continue
            results.append(element)
        return results

    def _find_raw(self, name, role, app_name, automation_id):
        """Re-walk the tree and return the first matching raw UIA element."""
        automation = self._ensure_automation()
        try:
            root = automation.GetRootElement()
            condition = automation.CreatePropertyCondition(
                _UIA_IS_CONTROL_ELEMENT_PROPERTY, True,
            )
            found = root.FindAll(_TREE_SCOPE_DESCENDANTS, condition)
        except (OSError, AttributeError) as error:
            autocontrol_logger.error("UIA FindAll failed: %r", error)
            return None
        for idx in range(int(found.Length or 0)):
            raw = found.GetElement(idx)
            element = _convert_uia(raw)
            if element is None:
                continue
            if automation_id is not None and element.native_id != automation_id:
                continue
            if element_matches(element, name=name, role=role, app_name=app_name):
                return raw
        return None

    def _pattern(self, raw, pattern_id, interface_name):
        """Return a queried control pattern interface, or None."""
        try:
            unknown = raw.GetCurrentPattern(pattern_id)
            if not unknown:
                return None
            interface = getattr(self._uia_module, interface_name)
            return unknown.QueryInterface(interface)
        except (OSError, AttributeError, ValueError):
            return None

    def get_value(self, name=None, role=None, app_name=None,
                  automation_id=None) -> Optional[str]:
        raw = self._find_raw(name, role, app_name, automation_id)
        pattern = self._pattern(raw, _UIA_VALUE_PATTERN_ID,
                                "IUIAutomationValuePattern") if raw else None
        if pattern is None:
            return None
        try:
            return str(pattern.CurrentValue or "")
        except (OSError, AttributeError):
            return None

    def set_value(self, value, name=None, role=None, app_name=None,
                  automation_id=None) -> bool:
        raw = self._find_raw(name, role, app_name, automation_id)
        pattern = self._pattern(raw, _UIA_VALUE_PATTERN_ID,
                                "IUIAutomationValuePattern") if raw else None
        if pattern is None:
            return False
        try:
            pattern.SetValue(str(value))
            return True
        except (OSError, AttributeError):
            return False

    def invoke(self, name=None, role=None, app_name=None,
               automation_id=None) -> bool:
        raw = self._find_raw(name, role, app_name, automation_id)
        pattern = self._pattern(raw, _UIA_INVOKE_PATTERN_ID,
                                "IUIAutomationInvokePattern") if raw else None
        if pattern is None:
            return False
        try:
            pattern.Invoke()
            return True
        except (OSError, AttributeError):
            return False

    def toggle(self, name=None, role=None, app_name=None,
               automation_id=None) -> bool:
        raw = self._find_raw(name, role, app_name, automation_id)
        pattern = self._pattern(raw, _UIA_TOGGLE_PATTERN_ID,
                                "IUIAutomationTogglePattern") if raw else None
        if pattern is None:
            return False
        try:
            pattern.Toggle()
            return True
        except (OSError, AttributeError):
            return False

    def read_table(self, name=None, role=None, app_name=None,
                   automation_id=None):
        raw = self._find_raw(name, role, app_name, automation_id)
        pattern = self._pattern(raw, _UIA_GRID_PATTERN_ID,
                                "IUIAutomationGridPattern") if raw else None
        if pattern is None:
            return []
        try:
            rows = int(pattern.CurrentRowCount or 0)
            cols = int(pattern.CurrentColumnCount or 0)
        except (OSError, AttributeError):
            return []
        return [self._read_row(pattern, r, cols) for r in range(rows)]

    def _invoke_pattern_method(self, name, role, app_name, automation_id,
                               pattern_id, interface_name, action):
        """Find a control, query a pattern, run ``action(pattern)`` → bool."""
        raw = self._find_raw(name, role, app_name, automation_id)
        pattern = self._pattern(raw, pattern_id, interface_name) if raw else None
        if pattern is None:
            return False
        try:
            action(pattern)
            return True
        except (OSError, AttributeError):
            return False

    def expand(self, name=None, role=None, app_name=None, automation_id=None):
        return self._invoke_pattern_method(
            name, role, app_name, automation_id, _UIA_EXPANDCOLLAPSE_PATTERN_ID,
            "IUIAutomationExpandCollapsePattern", lambda p: p.Expand())

    def collapse(self, name=None, role=None, app_name=None, automation_id=None):
        return self._invoke_pattern_method(
            name, role, app_name, automation_id, _UIA_EXPANDCOLLAPSE_PATTERN_ID,
            "IUIAutomationExpandCollapsePattern", lambda p: p.Collapse())

    def expand_state(self, name=None, role=None, app_name=None,
                     automation_id=None) -> Optional[str]:
        raw = self._find_raw(name, role, app_name, automation_id)
        pattern = self._pattern(raw, _UIA_EXPANDCOLLAPSE_PATTERN_ID,
                                "IUIAutomationExpandCollapsePattern") if raw else None
        if pattern is None:
            return None
        try:
            return _EXPAND_STATES.get(int(pattern.CurrentExpandCollapseState))
        except (OSError, AttributeError, ValueError, TypeError):
            return None

    def select_item(self, name=None, role=None, app_name=None, automation_id=None):
        return self._invoke_pattern_method(
            name, role, app_name, automation_id, _UIA_SELECTIONITEM_PATTERN_ID,
            "IUIAutomationSelectionItemPattern", lambda p: p.Select())

    def set_range_value(self, value, name=None, role=None, app_name=None,
                        automation_id=None):
        return self._invoke_pattern_method(
            name, role, app_name, automation_id, _UIA_RANGEVALUE_PATTERN_ID,
            "IUIAutomationRangeValuePattern", lambda p: p.SetValue(float(value)))

    def scroll_into_view(self, name=None, role=None, app_name=None,
                         automation_id=None):
        return self._invoke_pattern_method(
            name, role, app_name, automation_id, _UIA_SCROLLITEM_PATTERN_ID,
            "IUIAutomationScrollItemPattern", lambda p: p.ScrollIntoView())

    def get_range(self, name=None, role=None, app_name=None,
                  automation_id=None) -> Optional[Dict[str, Any]]:
        raw = self._find_raw(name, role, app_name, automation_id)
        pattern = self._pattern(raw, _UIA_RANGEVALUE_PATTERN_ID,
                                "IUIAutomationRangeValuePattern") if raw else None
        if pattern is None:
            return None
        try:
            return {"value": float(pattern.CurrentValue),
                    "minimum": float(pattern.CurrentMinimum),
                    "maximum": float(pattern.CurrentMaximum)}
        except (OSError, AttributeError, ValueError, TypeError):
            return None

    def _realize(self, raw) -> None:
        """Realize a virtualized element so it materializes (VirtualizedItemPattern)."""
        pattern = self._pattern(raw, _UIA_VIRTUALIZEDITEM_PATTERN_ID,
                                "IUIAutomationVirtualizedItemPattern")
        if pattern is None:
            return
        try:
            pattern.Realize()
        except (OSError, AttributeError):
            pass

    def find_virtual_item(self, item_name=None, by="name", container_name=None,
                          container_role=None, app_name=None, automation_id=None):
        container = self._find_raw(container_name, container_role, app_name,
                                   automation_id)
        pattern = self._pattern(container, _UIA_ITEMCONTAINER_PATTERN_ID,
                                "IUIAutomationItemContainerPattern"
                                ) if container else None
        if pattern is None:
            return None
        property_id = (_UIA_AUTOMATIONID_PROPERTY if by == "automation_id"
                       else _UIA_NAME_PROPERTY)
        try:
            found = pattern.FindItemByProperty(None, property_id, item_name)
        except (OSError, AttributeError, ValueError):
            return None
        if not found:
            return None
        self._realize(found)
        return _convert_uia(found)

    def get_properties(self, name=None, role=None, app_name=None,
                       automation_id=None) -> Optional[Dict[str, Any]]:
        raw = self._find_raw(name, role, app_name, automation_id)
        if not raw:
            return None
        return _read_properties(raw)

    def move_element(self, x=0.0, y=0.0, name=None, role=None, app_name=None,
                     automation_id=None):
        return self._invoke_pattern_method(
            name, role, app_name, automation_id, _UIA_TRANSFORM_PATTERN_ID,
            "IUIAutomationTransformPattern",
            lambda pattern: pattern.Move(float(x), float(y)))

    def resize_element(self, width=0.0, height=0.0, name=None, role=None,
                       app_name=None, automation_id=None):
        return self._invoke_pattern_method(
            name, role, app_name, automation_id, _UIA_TRANSFORM_PATTERN_ID,
            "IUIAutomationTransformPattern",
            lambda pattern: pattern.Resize(float(width), float(height)))

    def set_window_state(self, state="normal", name=None, role=None,
                         app_name=None, automation_id=None):
        visual = _WINDOW_VISUAL_STATES.get(str(state).lower())
        if visual is None:
            return False
        return self._invoke_pattern_method(
            name, role, app_name, automation_id, _UIA_WINDOW_PATTERN_ID,
            "IUIAutomationWindowPattern",
            lambda pattern: pattern.SetWindowVisualState(visual))

    def window_interaction_state(self, name=None, role=None, app_name=None,
                                 automation_id=None) -> Optional[str]:
        raw = self._find_raw(name, role, app_name, automation_id)
        pattern = self._pattern(raw, _UIA_WINDOW_PATTERN_ID,
                                "IUIAutomationWindowPattern") if raw else None
        if pattern is None:
            return None
        try:
            return _WINDOW_INTERACTION_STATES.get(
                int(pattern.CurrentWindowInteractionState))
        except (OSError, AttributeError, ValueError, TypeError):
            return None

    def legacy_info(self, name=None, role=None, app_name=None,
                    automation_id=None) -> Optional[Dict[str, Any]]:
        raw = self._find_raw(name, role, app_name, automation_id)
        pattern = self._pattern(raw, _UIA_LEGACYIACCESSIBLE_PATTERN_ID,
                                "IUIAutomationLegacyIAccessiblePattern"
                                ) if raw else None
        if pattern is None:
            return None
        return _read_legacy(pattern)

    def legacy_default_action(self, name=None, role=None, app_name=None,
                              automation_id=None):
        return self._invoke_pattern_method(
            name, role, app_name, automation_id,
            _UIA_LEGACYIACCESSIBLE_PATTERN_ID,
            "IUIAutomationLegacyIAccessiblePattern",
            lambda pattern: pattern.DoDefaultAction())

    def get_selection(self, name=None, role=None, app_name=None,
                      automation_id=None) -> Optional[Dict[str, Any]]:
        raw = self._find_raw(name, role, app_name, automation_id)
        pattern = self._pattern(raw, _UIA_SELECTION_PATTERN_ID,
                                "IUIAutomationSelectionPattern") if raw else None
        if pattern is None:
            return None
        try:
            items = _header_names(pattern.GetCurrentSelection())
            can_multiple = bool(pattern.CurrentCanSelectMultiple)
            required = bool(pattern.CurrentIsSelectionRequired)
        except (OSError, AttributeError):
            return None
        return {"items": items, "can_select_multiple": can_multiple,
                "is_required": required}

    def _multiple_view(self, name, role, app_name, automation_id):
        raw = self._find_raw(name, role, app_name, automation_id)
        return self._pattern(raw, _UIA_MULTIPLEVIEW_PATTERN_ID,
                             "IUIAutomationMultipleViewPattern") if raw else None

    def list_views(self, name=None, role=None, app_name=None,
                   automation_id=None) -> Optional[Dict[str, Any]]:
        pattern = self._multiple_view(name, role, app_name, automation_id)
        if pattern is None:
            return None
        try:
            view_ids = list(pattern.GetCurrentSupportedViews())
            current = int(pattern.CurrentCurrentView)
        except (OSError, AttributeError, ValueError, TypeError):
            return None
        return {"current": _view_name(pattern, current),
                "views": [_view_name(pattern, view_id) for view_id in view_ids]}

    def set_view(self, view="", name=None, role=None, app_name=None,
                 automation_id=None):
        pattern = self._multiple_view(name, role, app_name, automation_id)
        if pattern is None:
            return False
        try:
            for view_id in pattern.GetCurrentSupportedViews():
                if _view_name(pattern, view_id) == str(view):
                    pattern.SetCurrentView(int(view_id))
                    return True
        except (OSError, AttributeError, ValueError, TypeError):
            return False
        return False

    def get_table_headers(self, name=None, role=None, app_name=None,
                          automation_id=None) -> Optional[Dict[str, Any]]:
        raw = self._find_raw(name, role, app_name, automation_id)
        pattern = self._pattern(raw, _UIA_TABLE_PATTERN_ID,
                                "IUIAutomationTablePattern") if raw else None
        if pattern is None:
            return None
        try:
            columns = pattern.GetCurrentColumnHeaders()
            rows = pattern.GetCurrentRowHeaders()
        except (OSError, AttributeError):
            return None
        return {"columns": _header_names(columns), "rows": _header_names(rows)}

    def get_grid_cell(self, row=0, column=0, name=None, role=None,
                      app_name=None, automation_id=None) -> Optional[Dict[str, Any]]:
        raw = self._find_raw(name, role, app_name, automation_id)
        grid = self._pattern(raw, _UIA_GRID_PATTERN_ID,
                             "IUIAutomationGridPattern") if raw else None
        if grid is None:
            return None
        try:
            cell = grid.GetItem(int(row), int(column))
        except (OSError, AttributeError):
            return None
        if not cell:
            return None
        return _read_cell(self._pattern(cell, _UIA_GRIDITEM_PATTERN_ID,
                                        "IUIAutomationGridItemPattern"),
                          cell, int(row), int(column))

    def _text_pattern(self, name, role, app_name, automation_id):
        """Find a control and return its IUIAutomationTextPattern, or None."""
        raw = self._find_raw(name, role, app_name, automation_id)
        if not raw:
            return None
        return self._pattern(raw, _UIA_TEXT_PATTERN_ID,
                             "IUIAutomationTextPattern")

    def document_text(self, name=None, role=None, app_name=None,
                      automation_id=None) -> Optional[str]:
        pattern = self._text_pattern(name, role, app_name, automation_id)
        if pattern is None:
            return None
        try:
            return str(pattern.DocumentRange.GetText(-1) or "")
        except (OSError, AttributeError):
            return None

    def selected_text(self, name=None, role=None, app_name=None,
                      automation_id=None) -> Optional[str]:
        pattern = self._text_pattern(name, role, app_name, automation_id)
        if pattern is None:
            return None
        try:
            selection = pattern.GetSelection()
            if not selection or int(selection.Length or 0) == 0:
                return ""
            return str(selection.GetElement(0).GetText(-1) or "")
        except (OSError, AttributeError):
            return None

    def visible_text(self, name=None, role=None, app_name=None,
                     automation_id=None) -> Optional[str]:
        pattern = self._text_pattern(name, role, app_name, automation_id)
        if pattern is None:
            return None
        try:
            ranges = pattern.GetVisibleRanges()
            count = int(ranges.Length or 0)
            return "".join(str(ranges.GetElement(i).GetText(-1) or "")
                           for i in range(count))
        except (OSError, AttributeError):
            return None

    def _find_range(self, text, ignore_case, name, role, app_name, automation_id):
        """Find ``text`` in the control's document range (TextPattern.FindText)."""
        pattern = self._text_pattern(name, role, app_name, automation_id)
        if pattern is None:
            return None
        try:
            return pattern.DocumentRange.FindText(str(text), False,
                                                  bool(ignore_case))
        except (OSError, AttributeError):
            return None

    def find_text(self, text="", ignore_case=True, name=None, role=None,
                  app_name=None, automation_id=None) -> bool:
        return self._find_range(text, ignore_case, name, role, app_name,
                                automation_id) is not None

    def select_text(self, text="", ignore_case=True, name=None, role=None,
                    app_name=None, automation_id=None) -> bool:
        found = self._find_range(text, ignore_case, name, role, app_name,
                                 automation_id)
        if not found:
            return False
        try:
            found.Select()
            return True
        except (OSError, AttributeError):
            return False

    def text_attributes(self, name=None, role=None, app_name=None,
                        automation_id=None) -> Optional[Dict[str, Any]]:
        pattern = self._text_pattern(name, role, app_name, automation_id)
        if pattern is None:
            return None
        try:
            selection = pattern.GetSelection()
            text_range = (selection.GetElement(0)
                          if selection and int(selection.Length or 0) > 0
                          else pattern.DocumentRange)
        except (OSError, AttributeError):
            return None
        return _read_text_attributes(text_range)

    def set_focus(self, name=None, role=None, app_name=None,
                  automation_id=None) -> bool:
        raw = self._find_raw(name, role, app_name, automation_id)
        if not raw:
            return False
        try:
            raw.SetFocus()
            return True
        except (OSError, AttributeError):
            return False

    @staticmethod
    def _read_row(pattern, row: int, cols: int):
        """Read one grid row into a list of cell strings."""
        cells = []
        for col in range(cols):
            try:
                cell = pattern.GetItem(row, col)
                cells.append(str(cell.CurrentName or "") if cell else "")
            except (OSError, AttributeError):
                cells.append("")
        return cells


def _view_name(pattern, view_id) -> str:
    """Return a MultipleViewPattern view's name, or '' on failure."""
    try:
        return str(pattern.GetViewName(int(view_id)) or "")
    except (OSError, AttributeError, ValueError, TypeError):
        return ""


def _header_names(array) -> List[str]:
    """Read an IUIAutomationElementArray of header elements into name strings."""
    names: List[str] = []
    try:
        count = int(array.Length or 0)
    except (OSError, AttributeError):
        return names
    for index in range(count):
        try:
            names.append(str(array.GetElement(index).CurrentName or ""))
        except (OSError, AttributeError):
            names.append("")
    return names


def _read_cell(item_pattern, cell, row: int, column: int) -> Dict[str, Any]:
    """Build a cell record, enriching with GridItemPattern row/col/span if present."""
    info: Dict[str, Any] = {
        "value": _safe_name(cell), "row": row, "column": column,
        "row_span": 1, "column_span": 1,
    }
    if item_pattern is not None:
        for key, attr in (("row", "CurrentRow"), ("column", "CurrentColumn"),
                          ("row_span", "CurrentRowSpan"),
                          ("column_span", "CurrentColumnSpan")):
            try:
                info[key] = int(getattr(item_pattern, attr))
            except (OSError, AttributeError, ValueError, TypeError):
                pass
    return info


def _safe_name(raw) -> str:
    try:
        return str(raw.CurrentName or "")
    except (OSError, AttributeError):
        return ""


def _as_text(value) -> str:
    return str(value or "")


# UIA TextPattern attribute ids (UIAutomationClient AttributeId range).
_TEXT_ATTR_FONT_NAME = 40005
_TEXT_ATTR_FONT_SIZE = 40006
_TEXT_ATTR_FONT_WEIGHT = 40007
_TEXT_ATTR_FOREGROUND = 40008
_TEXT_ATTR_IS_ITALIC = 40014


def _attr(text_range, attribute_id, cast):
    try:
        return cast(text_range.GetAttributeValue(attribute_id))
    except (OSError, AttributeError, ValueError, TypeError):
        return None


def _read_text_attributes(text_range) -> Dict[str, Any]:
    """Read font / colour formatting of a TextRange into a plain dict."""
    weight = _attr(text_range, _TEXT_ATTR_FONT_WEIGHT, int)
    return {
        "font_name": _attr(text_range, _TEXT_ATTR_FONT_NAME, _as_text),
        "font_size": _attr(text_range, _TEXT_ATTR_FONT_SIZE, float),
        "bold": (weight >= 700) if isinstance(weight, int) else None,
        "italic": _attr(text_range, _TEXT_ATTR_IS_ITALIC, bool),
        "foreground_color": _attr(text_range, _TEXT_ATTR_FOREGROUND, int),
    }


# (key, LegacyIAccessiblePattern attribute, cast) for the MSAA bridge read.
_LEGACY_READS = (
    ("name", "CurrentName", _as_text),
    ("value", "CurrentValue", _as_text),
    ("description", "CurrentDescription", _as_text),
    ("default_action", "CurrentDefaultAction", _as_text),
    ("role", "CurrentRole", int),
    ("state", "CurrentState", int),
)


def _read_legacy(pattern) -> Dict[str, Any]:
    """Read a LegacyIAccessiblePattern's MSAA fields into a plain dict."""
    info: Dict[str, Any] = {}
    for key, attribute, cast in _LEGACY_READS:
        try:
            info[key] = cast(getattr(pattern, attribute))
        except (OSError, AttributeError, ValueError, TypeError):
            info[key] = None
    return info


# (key, UIA element attribute, cast) for the rich properties the flat list omits.
_PROPERTY_READS = (
    ("enabled", "CurrentIsEnabled", bool),
    ("offscreen", "CurrentIsOffscreen", bool),
    ("help_text", "CurrentHelpText", _as_text),
    ("item_status", "CurrentItemStatus", _as_text),
    ("accelerator_key", "CurrentAcceleratorKey", _as_text),
    ("access_key", "CurrentAccessKey", _as_text),
    ("orientation", "CurrentOrientation", int),
)


def _read_properties(raw) -> Dict[str, Any]:
    """Read the rich UIA properties of a raw element into a plain dict."""
    properties: Dict[str, Any] = {}
    for key, attribute, cast in _PROPERTY_READS:
        try:
            properties[key] = cast(getattr(raw, attribute))
        except (OSError, AttributeError, ValueError, TypeError):
            properties[key] = None
    return properties


def _convert_uia(raw) -> Optional[AccessibilityElement]:
    try:
        name = str(raw.CurrentName or "")
        control_type = int(raw.CurrentControlType or 0)
        rect = raw.CurrentBoundingRectangle
        process_id = int(raw.CurrentProcessId or 0)
        automation_id = str(raw.CurrentAutomationId or "")
    except (OSError, AttributeError):
        return None
    width = max(0, int(rect.right - rect.left))
    height = max(0, int(rect.bottom - rect.top))
    return AccessibilityElement(
        name=name, role=f"ControlType_{control_type}",
        bounds=(int(rect.left), int(rect.top), width, height),
        app_name=_process_name(process_id),
        process_id=process_id,
        native_id=automation_id,
    )


def _process_name(process_id: int) -> str:
    if process_id <= 0:
        return ""
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        process_query_information = 0x0400 | 0x0010
        handle = kernel32.OpenProcess(process_query_information, False, process_id)
        if not handle:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(260)
            size = wintypes.DWORD(len(buf))
            get_image = kernel32.QueryFullProcessImageNameW
            if not get_image(handle, 0, buf, ctypes.byref(size)):
                return ""
            return buf.value.rsplit("\\", 1)[-1]
        finally:
            kernel32.CloseHandle(handle)
    except OSError:
        return ""
