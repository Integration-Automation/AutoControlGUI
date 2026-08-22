"""Abstract accessibility backend."""
from typing import Any, Dict, List, NoReturn, Optional

from je_auto_control.utils.accessibility.element import (
    AccessibilityElement, AccessibilityNotAvailableError,
)


class AccessibilityBackend:
    """Each backend exposes the platform's accessibility tree as flat lists.

    Beyond listing, a backend may *act* on a control via its native
    control patterns (read/set a value, invoke, toggle). Backends that
    don't implement these raise :class:`AccessibilityNotAvailableError`
    through :meth:`_unsupported`.
    """

    name: str = "abstract"
    available: bool = False

    def list_elements(self, app_name: Optional[str] = None,
                      max_results: int = 200,
                      window_title: Optional[str] = None,
                      ) -> List[AccessibilityElement]:
        """Flat list of elements, optionally scoped.

        ``window_title`` is a case-insensitive substring of a window's title.
        Scoping to one window is not just filtering: the desktop tree holds
        orders of magnitude more nodes, so searching a single window is both
        much faster and much less ambiguous. Backends that cannot scope may
        ignore it.
        """
        raise NotImplementedError

    # --- control patterns (object-level actions) ---------------------------

    def get_value(self, name: Optional[str] = None, role: Optional[str] = None,
                  app_name: Optional[str] = None,
                  automation_id: Optional[str] = None,
                  window_title: Optional[str] = None,
                  contains: bool = False) -> Optional[str]:
        """Return the matched control's value text, or None if not found.

        ``window_title`` / ``contains`` narrow which control is meant, the
        same way :meth:`get_state` does — the two reads stay a pair.
        """
        self._unsupported("get_value", name, role, app_name, automation_id)

    def set_value(self, value: str, name: Optional[str] = None,
                  role: Optional[str] = None, app_name: Optional[str] = None,
                  automation_id: Optional[str] = None) -> bool:
        """Set the matched control's value; return True on success."""
        self._unsupported("set_value", value, name, role, app_name, automation_id)

    def invoke(self, name: Optional[str] = None, role: Optional[str] = None,
               app_name: Optional[str] = None,
               automation_id: Optional[str] = None) -> bool:
        """Invoke the matched control (e.g. press a button)."""
        self._unsupported("invoke", name, role, app_name, automation_id)

    def toggle(self, name: Optional[str] = None, role: Optional[str] = None,
               app_name: Optional[str] = None,
               automation_id: Optional[str] = None) -> bool:
        """Toggle the matched control (e.g. a checkbox)."""
        self._unsupported("toggle", name, role, app_name, automation_id)

    def read_table(self, name: Optional[str] = None, role: Optional[str] = None,
                   app_name: Optional[str] = None,
                   automation_id: Optional[str] = None,
                   ) -> List[List[str]]:
        """Read a grid/table/list control as rows of cell strings."""
        self._unsupported("read_table", name, role, app_name, automation_id)

    # --- extended control patterns (Expand / Selection / Range / Scroll) ----

    def expand(self, name: Optional[str] = None, role: Optional[str] = None,
               app_name: Optional[str] = None,
               automation_id: Optional[str] = None) -> bool:
        """Expand the matched control (ExpandCollapsePattern); True on success."""
        self._unsupported("expand", name, role, app_name, automation_id)

    def collapse(self, name: Optional[str] = None, role: Optional[str] = None,
                 app_name: Optional[str] = None,
                 automation_id: Optional[str] = None) -> bool:
        """Collapse the matched control (ExpandCollapsePattern); True on success."""
        self._unsupported("collapse", name, role, app_name, automation_id)

    def expand_state(self, name: Optional[str] = None, role: Optional[str] = None,
                     app_name: Optional[str] = None,
                     automation_id: Optional[str] = None) -> Optional[str]:
        """Return ``expanded`` / ``collapsed`` / ``partial`` / ``leaf``, or None."""
        self._unsupported("expand_state", name, role, app_name, automation_id)

    def select_item(self, name: Optional[str] = None, role: Optional[str] = None,
                    app_name: Optional[str] = None,
                    automation_id: Optional[str] = None) -> bool:
        """Select the matched item (SelectionItemPattern); True on success."""
        self._unsupported("select_item", name, role, app_name, automation_id)

    def get_range(self, name: Optional[str] = None, role: Optional[str] = None,
                  app_name: Optional[str] = None,
                  automation_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Return ``{value, minimum, maximum}`` (RangeValuePattern), or None."""
        self._unsupported("get_range", name, role, app_name, automation_id)

    def set_range_value(self, value: float, name: Optional[str] = None,
                        role: Optional[str] = None, app_name: Optional[str] = None,
                        automation_id: Optional[str] = None) -> bool:
        """Set a slider / progress value (RangeValuePattern); True on success."""
        self._unsupported("set_range_value", value, name, role, app_name, automation_id)

    def scroll_into_view(self, name: Optional[str] = None,
                         role: Optional[str] = None, app_name: Optional[str] = None,
                         automation_id: Optional[str] = None) -> bool:
        """Scroll the matched control into view (ScrollItemPattern); True on success."""
        self._unsupported("scroll_into_view", name, role, app_name, automation_id)

    # --- text patterns (TextPattern reads) ---------------------------------

    def document_text(self, name: Optional[str] = None, role: Optional[str] = None,
                      app_name: Optional[str] = None,
                      automation_id: Optional[str] = None) -> Optional[str]:
        """Return the matched control's full text (TextPattern), or None.

        Reads multiline / document controls where ValuePattern returns ``""``.
        """
        self._unsupported("document_text", name, role, app_name, automation_id)

    def selected_text(self, name: Optional[str] = None, role: Optional[str] = None,
                      app_name: Optional[str] = None,
                      automation_id: Optional[str] = None) -> Optional[str]:
        """Return the control's currently selected text (TextPattern), or None."""
        self._unsupported("selected_text", name, role, app_name, automation_id)

    def visible_text(self, name: Optional[str] = None, role: Optional[str] = None,
                     app_name: Optional[str] = None,
                     automation_id: Optional[str] = None) -> Optional[str]:
        """Return only the on-screen text of the control (TextPattern), or None."""
        self._unsupported("visible_text", name, role, app_name, automation_id)

    def find_text(self, text: str = "", ignore_case: bool = True,
                  name: Optional[str] = None, role: Optional[str] = None,
                  app_name: Optional[str] = None,
                  automation_id: Optional[str] = None) -> bool:
        """Return whether ``text`` occurs in the control (TextPattern.FindText)."""
        self._unsupported("find_text", text, ignore_case, name, role, app_name, automation_id)

    def select_text(self, text: str = "", ignore_case: bool = True,
                    name: Optional[str] = None, role: Optional[str] = None,
                    app_name: Optional[str] = None,
                    automation_id: Optional[str] = None) -> bool:
        """Find ``text`` and select its range (TextPattern.FindText + Select)."""
        self._unsupported("select_text", text, ignore_case, name, role, app_name, automation_id)

    def text_attributes(self, name: Optional[str] = None,
                        role: Optional[str] = None, app_name: Optional[str] = None,
                        automation_id: Optional[str] = None,
                        ) -> Optional[Dict[str, Any]]:
        """Return formatting of the control's selection — ``{font_name, font_size,
        bold, italic, foreground_color}`` (TextPattern attributes), or None."""
        self._unsupported("text_attributes", name, role, app_name, automation_id)

    # --- keyboard focus ----------------------------------------------------

    def set_focus(self, name: Optional[str] = None, role: Optional[str] = None,
                  app_name: Optional[str] = None,
                  automation_id: Optional[str] = None) -> bool:
        """Set keyboard focus on the matched control (SetFocus); True on success."""
        self._unsupported("set_focus", name, role, app_name, automation_id)

    # --- virtualized items (realize off-screen list / grid items) -----------

    def find_virtual_item(self, item_name: Optional[str] = None, by: str = "name",
                          container_name: Optional[str] = None,
                          container_role: Optional[str] = None,
                          app_name: Optional[str] = None,
                          automation_id: Optional[str] = None,
                          ) -> Optional[AccessibilityElement]:
        """Find a (possibly virtualized) item inside a container and realize it.

        Long virtualized lists / grids only materialize visible rows; this locates
        the item by property (``ItemContainerPattern``) and realizes it
        (``VirtualizedItemPattern``) so it exists as a real element. Returns the
        realized element, or None if the container or item isn't found.
        """
        self._unsupported("find_virtual_item", item_name, by, container_name, container_role, app_name, automation_id)

    # --- rich element properties -------------------------------------------

    def get_properties(self, name: Optional[str] = None,
                       role: Optional[str] = None, app_name: Optional[str] = None,
                       automation_id: Optional[str] = None,
                       ) -> Optional[Dict[str, Any]]:
        """Return rich UIA properties of the matched control, or None.

        Surfaces the high-value properties the flat element list omits —
        ``enabled`` / ``offscreen`` / ``help_text`` / ``item_status`` /
        ``accelerator_key`` / ``access_key`` / ``orientation``.
        """
        self._unsupported("get_properties", name, role, app_name, automation_id)

    def get_state(self, name: Optional[str] = None,
                  role: Optional[str] = None, app_name: Optional[str] = None,
                  automation_id: Optional[str] = None,
                  window_title: Optional[str] = None,
                  contains: bool = False,
                  ) -> Optional[Dict[str, Any]]:
        """Return what the matched control currently holds, or None.

        The keys present depend on the control: ``value`` (+ ``read_only``),
        ``toggle`` (``on`` / ``off`` / ``mixed``), ``selected``, ``number``. A
        key is absent when the control does not support it — distinct from the
        value being empty. A password field reports only ``{"password": True}``.
        """
        self._unsupported("get_state", name, role, app_name, automation_id)

    # --- table headers + cell addressing (TablePattern / GridItemPattern) ---

    def get_table_headers(self, name: Optional[str] = None,
                          role: Optional[str] = None,
                          app_name: Optional[str] = None,
                          automation_id: Optional[str] = None,
                          ) -> Optional[Dict[str, Any]]:
        """Return a table's header labels as ``{columns: [...], rows: [...]}``."""
        self._unsupported("get_table_headers", name, role, app_name, automation_id)

    def get_grid_cell(self, row: int = 0, column: int = 0,
                      name: Optional[str] = None, role: Optional[str] = None,
                      app_name: Optional[str] = None,
                      automation_id: Optional[str] = None,
                      ) -> Optional[Dict[str, Any]]:
        """Return the cell at ``(row, column)`` as ``{value, row, column,
        row_span, column_span}`` (GridPattern.GetItem + GridItemPattern)."""
        self._unsupported("get_grid_cell", row, column, name, role, app_name, automation_id)

    # --- transform + window patterns (UIA-element-level) --------------------

    def move_element(self, x: float = 0.0, y: float = 0.0,
                     name: Optional[str] = None, role: Optional[str] = None,
                     app_name: Optional[str] = None,
                     automation_id: Optional[str] = None) -> bool:
        """Move the matched element to ``(x, y)`` (TransformPattern); True on success."""
        self._unsupported("move_element", x, y, name, role, app_name, automation_id)

    def resize_element(self, width: float = 0.0, height: float = 0.0,
                       name: Optional[str] = None, role: Optional[str] = None,
                       app_name: Optional[str] = None,
                       automation_id: Optional[str] = None) -> bool:
        """Resize the matched element (TransformPattern); True on success."""
        self._unsupported("resize_element", width, height, name, role, app_name, automation_id)

    def set_window_state(self, state: str = "normal",
                         name: Optional[str] = None, role: Optional[str] = None,
                         app_name: Optional[str] = None,
                         automation_id: Optional[str] = None) -> bool:
        """Set a window's visual state ``normal`` / ``maximized`` / ``minimized``."""
        self._unsupported("set_window_state", state, name, role, app_name, automation_id)

    def window_interaction_state(self, name: Optional[str] = None,
                                 role: Optional[str] = None,
                                 app_name: Optional[str] = None,
                                 automation_id: Optional[str] = None,
                                 ) -> Optional[str]:
        """Return a window's interaction state — ``ready`` / ``blocked_by_modal`` /
        ``not_responding`` / ``running`` / ``closing`` (WindowPattern), or None."""
        self._unsupported("window_interaction_state", name, role, app_name, automation_id)

    # --- MSAA bridge (LegacyIAccessiblePattern) ----------------------------

    def legacy_info(self, name: Optional[str] = None, role: Optional[str] = None,
                    app_name: Optional[str] = None,
                    automation_id: Optional[str] = None,
                    ) -> Optional[Dict[str, Any]]:
        """Return the MSAA ``IAccessible`` info of an old control, or None.

        ``{name, value, description, default_action, role, state}`` — the
        last-resort read for legacy Win32 controls that expose nothing useful via
        the modern UIA patterns.
        """
        self._unsupported("legacy_info", name, role, app_name, automation_id)

    def legacy_default_action(self, name: Optional[str] = None,
                              role: Optional[str] = None,
                              app_name: Optional[str] = None,
                              automation_id: Optional[str] = None) -> bool:
        """Fire an old control's MSAA default action (DoDefaultAction); True on
        success — the fallback when Value / Invoke / Toggle all do nothing."""
        self._unsupported("legacy_default_action", name, role, app_name, automation_id)

    # --- container selection + views (Selection / MultipleView patterns) ----

    def get_selection(self, name: Optional[str] = None, role: Optional[str] = None,
                      app_name: Optional[str] = None,
                      automation_id: Optional[str] = None,
                      ) -> Optional[Dict[str, Any]]:
        """Return a container's selection state — ``{items, can_select_multiple,
        is_required}`` (SelectionPattern), or None."""
        self._unsupported("get_selection", name, role, app_name, automation_id)

    def list_views(self, name: Optional[str] = None, role: Optional[str] = None,
                   app_name: Optional[str] = None,
                   automation_id: Optional[str] = None,
                   ) -> Optional[Dict[str, Any]]:
        """Return a control's selectable views — ``{current, views: [...]}``
        (MultipleViewPattern: list / details / tile / …), or None."""
        self._unsupported("list_views", name, role, app_name, automation_id)

    def set_view(self, view: str = "", name: Optional[str] = None,
                 role: Optional[str] = None, app_name: Optional[str] = None,
                 automation_id: Optional[str] = None) -> bool:
        """Switch a control to the named view (MultipleViewPattern); True on success."""
        self._unsupported("set_view", view, name, role, app_name, automation_id)

    # --- reactive events (UIA event subscription) --------------------------

    def wait_for_focus_change(self, timeout: float = 5.0,
                              ) -> Optional[Dict[str, Any]]:
        """Block until the keyboard focus moves, then return the newly-focused
        element ``{name, role, app_name, ...}`` (or None on ``timeout``).

        A zero-latency native wait (UIA AddFocusChangedEventHandler) — unlike the
        polling recorder, it can't miss a fast focus transition.
        """
        self._unsupported("wait_for_focus_change", timeout)

    def _unsupported(self, operation: str, *context: Any) -> NoReturn:
        """Raise a clear error for an action this backend can't perform."""
        raise AccessibilityNotAvailableError(
            f"{operation} is not supported by the {self.name} backend",
        )
