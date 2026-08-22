"""Windows UIAutomation backend via ``comtypes``.

Requires ``pip install comtypes``. If the module is absent, ``available`` is
``False`` and the facade falls back to the Null backend.

Flattens the UIAutomation tree into ``AccessibilityElement`` records one
level at a time starting from the root desktop, filtered by app if needed.
Only ``is_control_element=True`` nodes are surfaced to avoid millions of
decorative text children.
"""
import functools
import sys
from typing import Any, Dict, List, Optional

from je_auto_control.utils.accessibility.backends.base import (
    AccessibilityBackend,
)
from je_auto_control.utils.accessibility.element import (
    AccessibilityElement, AccessibilityNotAvailableError, element_matches,
)
from je_auto_control.utils.accessibility.backends.windows_query import (
    UIA_ERRORS, search_roots, walk_elements,
)
from je_auto_control.utils.accessibility.backends.windows_state import (
    is_password, read_state,
)
from je_auto_control.utils.logging.logging_instance import autocontrol_logger

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
# How much further to walk than we keep when an app_name filter is on: most
# elements in a window belong to that window's app, so a small factor is
# plenty, and an unbounded search would walk everything to return nothing.
_FILTER_OVERSCAN = 4
# How many elements a single-control search may examine before giving up.
# Unbounded, a target that is not there walks every window on the desktop and
# costs ~60 s to answer "no". The two bounds encode intent: naming a window
# says "it is in here, find it", so that search is allowed to go deep — a
# browser window holds thousands of nodes and a real target can sit well past
# any small cap. Not naming one says "look around", and stays cheap.
_FIND_SCAN_LIMIT = 1500
_FIND_SCAN_LIMIT_SCOPED = 20000
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


# ``CUIAutomation8`` is the only class that hands out ``IUIAutomation2``, which
# is the only way to bound how long UIA waits for an application's provider.
# It matters: a full-screen game that never answers UIA made a single
# ``ElementFromHandle`` block for **60 seconds** here, poisoning every
# desktop-wide search. With the connection timeout set, the same call is 1.0 s.
_CLSID_CUIAUTOMATION8 = "{e22ad333-b25f-460c-83d0-0581107395c9}"
_CLSID_CUIAUTOMATION = "{ff48dba4-60ef-4201-aa87-54103eef594e}"
# Only the connect step is tightened. A provider that cannot even connect within
# a second is not going to answer; how long a legitimate *query* may take is a
# different question, so ``TransactionTimeout`` keeps its default.
_CONNECTION_TIMEOUT_MS = 1000


def _create_automation(uia_module):
    """The UIAutomation object, with a bounded provider-connect wait if possible."""
    from comtypes import CoCreateInstance, GUID
    interface = getattr(uia_module, "IUIAutomation2", None)
    if interface is not None:
        try:
            automation = CoCreateInstance(GUID(_CLSID_CUIAUTOMATION8),
                                          interface=interface)
            automation.ConnectionTimeout = _CONNECTION_TIMEOUT_MS
            return automation
        except (OSError, AttributeError, ValueError) as error:
            autocontrol_logger.info(
                "UIAutomation2 unavailable, provider waits are unbounded: %r",
                error)
    return CoCreateInstance(GUID(_CLSID_CUIAUTOMATION),
                            interface=uia_module.IUIAutomation)


class WindowsAccessibilityBackend(AccessibilityBackend):
    """UIAutomation-based flat element listing."""

    name = "windows-uia"

    def __init__(self) -> None:
        import threading
        self.available = _is_available()
        self._automation: Any = None
        # The comtypes-generated UIAutomationClient module; `Any` because it
        # is generated at import time and has no declarations to check.
        self._uia_module: Any = None
        self._event_lock = threading.Lock()

    def _ensure_automation(self):
        if self._automation is not None:
            return self._automation
        if not self.available:
            raise AccessibilityNotAvailableError(
                "comtypes is required for Windows accessibility; "
                "install it with: pip install comtypes",
            )
        import comtypes.client  # noqa: F401
        try:
            uia_module = comtypes.client.GetModule("UIAutomationCore.dll")
        except OSError as error:
            raise AccessibilityNotAvailableError(
                f"UIAutomationCore.dll unavailable: {error!r}",
            ) from error
        automation = _create_automation(uia_module)
        self._automation = automation
        self._uia_module = uia_module
        return automation

    def _collect_from(self, automation, root, app_name, wanted,
                      results: List[AccessibilityElement]) -> None:
        """Append this root's elements to ``results``, stopping at ``wanted``.

        An ``app_name`` filter needs more elements walked than kept, so the walk
        gets room to keep looking — but still a bound, because an unmatched
        filter would otherwise walk an entire subtree to return nothing.
        """
        budget = wanted - len(results)
        if budget <= 0:
            return
        if app_name is not None:
            budget *= _FILTER_OVERSCAN
        try:
            for raw in walk_elements(automation, root, budget):
                if len(results) >= wanted:
                    return
                element = _convert_uia(raw, cached=True)
                if element is None:
                    continue
                if app_name is not None and element.app_name != app_name:
                    continue
                results.append(element)
        except UIA_ERRORS as error:
            # One unresponsive window must not lose the whole listing.
            autocontrol_logger.info("UIA walk skipped a root: %r", error)

    def list_elements(self, app_name: Optional[str] = None,
                      max_results: int = 200,
                      window_title: Optional[str] = None,
                      ) -> List[AccessibilityElement]:
        automation = self._ensure_automation()
        wanted = max(0, int(max_results))
        results: List[AccessibilityElement] = []
        # One window at a time, walked node by node, so the search stops as soon
        # as there are enough elements. Both halves matter: a desktop-rooted
        # FindAll cost ~61 s, and even per window a single FindAll is atomic —
        # one 34,507-element window took 10.3 s to answer a request for 200.
        #
        # The budget is checked *before* pulling the next window, not after:
        # obtaining a window's root element is itself a cross-process call, and
        # against a hung application it blocks for a minute. Fetching one more
        # root only to discover the results were already complete cost exactly
        # that.
        roots = search_roots(automation, window_title)
        while len(results) < wanted:
            try:
                root = next(roots)
            except StopIteration:
                break
            if window_title is None:
                # Searching a window's descendants does not include the window
                # element itself, which the desktop-rooted walk did return.
                window_element = _convert_uia(root)
                if window_element is not None and (
                        app_name is None or window_element.app_name == app_name):
                    results.append(window_element)
            self._collect_from(automation, root, app_name, wanted, results)
        return results

    def _raw_matches(self, raw, filters, cached: bool) -> bool:
        """Whether this element satisfies the caller's filters."""
        element = _convert_uia(raw, cached=cached)
        if element is None:
            return False
        automation_id = filters.get("automation_id")
        if automation_id is not None and element.native_id != automation_id:
            return False
        return element_matches(element, name=filters.get("name"),
                               role=filters.get("role"),
                               app_name=filters.get("app_name"),
                               contains=bool(filters.get("contains")))

    def _find_raw(self, name, role, app_name, automation_id,
                  window_title=None, contains=False):
        """Return the first matching raw UIA element, or ``None``.

        Every control-pattern call lands here, so this is the hot path for
        reading or acting on one control. It walks window by window and node by
        node and **stops at the first match**: a target in the front window is
        found in milliseconds. The obvious implementation — one
        ``FindAll(TreeScope_Descendants)`` from the desktop — cannot stop, and
        measured ~61 s on a busy desktop whether or not the target was the very
        first element.

        Naming ``window_title`` is still much better: it skips straight to that
        window instead of hoping the target is near the front.
        """
        automation = self._ensure_automation()
        filters = {"name": name, "role": role, "app_name": app_name,
                   "automation_id": automation_id, "contains": contains}
        budget = (_FIND_SCAN_LIMIT_SCOPED if window_title
                  else _FIND_SCAN_LIMIT)
        try:
            for root in search_roots(automation, window_title):
                if budget <= 0:
                    break
                # A window can itself be the target; the desktop-rooted walk
                # used to return window elements too.
                if window_title is None and self._raw_matches(root, filters,
                                                              cached=False):
                    return root
                for raw in walk_elements(automation, root, budget):
                    budget -= 1
                    if self._raw_matches(raw, filters, cached=True):
                        return raw
        except UIA_ERRORS as error:
            autocontrol_logger.error("UIA element search failed: %r", error)
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
                  automation_id=None, window_title=None,
                  contains=False) -> Optional[str]:
        raw = self._find_raw(name, role, app_name, automation_id,
                             window_title=window_title, contains=contains)
        if raw is not None and is_password(raw):
            # UIA is supposed to mask a password field's value, but a
            # custom-drawn control can put the plaintext in ValuePattern
            # anyway. Never hand that back — callers log and forward values.
            autocontrol_logger.info("get_value refused: password field")
            return None
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

    def get_state(self, name=None, role=None, app_name=None,
                  automation_id=None, window_title=None,
                  contains=False) -> Optional[Dict[str, Any]]:
        raw = self._find_raw(name, role, app_name, automation_id,
                             window_title=window_title, contains=contains)
        return None if not raw else read_state(raw)

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

    def _make_focus_handler(self, sink):
        """Build a COM focus-changed event handler that puts events on ``sink``."""
        try:
            import comtypes
            interface = self._uia_module.IUIAutomationFocusChangedEventHandler
        except (ImportError, AttributeError):
            return None

        class _FocusHandler(comtypes.COMObject):
            _com_interfaces_ = [interface]

            def IUIAutomationFocusChangedEventHandler_HandleFocusChangedEvent(
                    self, sender):  # noqa: N802  # reason: comtypes callback name
                element = _convert_uia(sender)
                sink.put(element.to_dict() if element else {"focused": True})
                return 0

        return _FocusHandler()

    def wait_for_focus_change(self, timeout=5.0) -> Optional[Dict[str, Any]]:
        import queue
        automation = self._ensure_automation()
        events: "queue.Queue" = queue.Queue()
        handler = self._make_focus_handler(events)
        if handler is None:
            return None
        try:
            with self._event_lock:
                automation.AddFocusChangedEventHandler(None, handler)
        except (OSError, AttributeError):
            return None
        try:
            return events.get(timeout=float(timeout))
        except queue.Empty:
            return None
        finally:
            with self._event_lock:
                try:
                    automation.RemoveFocusChangedEventHandler(handler)
                except (OSError, AttributeError):
                    pass

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


def _convert_uia(raw, cached: bool = False) -> Optional[AccessibilityElement]:
    """Convert one UIA element. ``cached`` reads the pre-fetched properties.

    Every ``Current*`` read is a cross-process call into the application that
    owns the window, so converting a few thousand elements one property at a
    time is the whole cost of a desktop-wide listing. Elements returned by
    ``FindAllBuildCache`` carry their properties already, and reading those
    costs nothing.
    """
    prefix = "Cached" if cached else "Current"
    try:
        name = str(getattr(raw, prefix + "Name") or "")
        control_type = int(getattr(raw, prefix + "ControlType") or 0)
        rect = getattr(raw, prefix + "BoundingRectangle")
        process_id = int(getattr(raw, prefix + "ProcessId") or 0)
        automation_id = str(getattr(raw, prefix + "AutomationId") or "")
        enabled = bool(getattr(raw, prefix + "IsEnabled"))
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
        enabled=enabled,
    )


@functools.lru_cache(maxsize=256)
def _process_name(process_id: int) -> str:
    """Executable name for a pid.

    Cached because a desktop listing asks for the same handful of pids
    thousands of times, and each miss is an ``OpenProcess`` /
    ``QueryFullProcessImageNameW`` / ``CloseHandle`` round trip. Windows does
    recycle pids, so a very long-lived session could in principle read a stale
    name here; it only labels ``app_name``, and the cache is bounded.
    """
    if process_id <= 0 or sys.platform != "win32":
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
