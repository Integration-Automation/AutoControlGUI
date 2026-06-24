"""Abstract accessibility backend."""
from typing import Any, Dict, List, Optional

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
                      ) -> List[AccessibilityElement]:
        raise NotImplementedError

    # --- control patterns (object-level actions) ---------------------------

    def get_value(self, name: Optional[str] = None, role: Optional[str] = None,
                  app_name: Optional[str] = None,
                  automation_id: Optional[str] = None) -> Optional[str]:
        """Return the matched control's value text, or None if not found."""
        self._unsupported("get_value")

    def set_value(self, value: str, name: Optional[str] = None,
                  role: Optional[str] = None, app_name: Optional[str] = None,
                  automation_id: Optional[str] = None) -> bool:
        """Set the matched control's value; return True on success."""
        self._unsupported("set_value")

    def invoke(self, name: Optional[str] = None, role: Optional[str] = None,
               app_name: Optional[str] = None,
               automation_id: Optional[str] = None) -> bool:
        """Invoke the matched control (e.g. press a button)."""
        self._unsupported("invoke")

    def toggle(self, name: Optional[str] = None, role: Optional[str] = None,
               app_name: Optional[str] = None,
               automation_id: Optional[str] = None) -> bool:
        """Toggle the matched control (e.g. a checkbox)."""
        self._unsupported("toggle")

    def read_table(self, name: Optional[str] = None, role: Optional[str] = None,
                   app_name: Optional[str] = None,
                   automation_id: Optional[str] = None,
                   ) -> List[List[str]]:
        """Read a grid/table/list control as rows of cell strings."""
        self._unsupported("read_table")

    # --- extended control patterns (Expand / Selection / Range / Scroll) ----

    def expand(self, name: Optional[str] = None, role: Optional[str] = None,
               app_name: Optional[str] = None,
               automation_id: Optional[str] = None) -> bool:
        """Expand the matched control (ExpandCollapsePattern); True on success."""
        self._unsupported("expand")

    def collapse(self, name: Optional[str] = None, role: Optional[str] = None,
                 app_name: Optional[str] = None,
                 automation_id: Optional[str] = None) -> bool:
        """Collapse the matched control (ExpandCollapsePattern); True on success."""
        self._unsupported("collapse")

    def expand_state(self, name: Optional[str] = None, role: Optional[str] = None,
                     app_name: Optional[str] = None,
                     automation_id: Optional[str] = None) -> Optional[str]:
        """Return ``expanded`` / ``collapsed`` / ``partial`` / ``leaf``, or None."""
        self._unsupported("expand_state")

    def select_item(self, name: Optional[str] = None, role: Optional[str] = None,
                    app_name: Optional[str] = None,
                    automation_id: Optional[str] = None) -> bool:
        """Select the matched item (SelectionItemPattern); True on success."""
        self._unsupported("select_item")

    def get_range(self, name: Optional[str] = None, role: Optional[str] = None,
                  app_name: Optional[str] = None,
                  automation_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Return ``{value, minimum, maximum}`` (RangeValuePattern), or None."""
        self._unsupported("get_range")

    def set_range_value(self, value: float, name: Optional[str] = None,
                        role: Optional[str] = None, app_name: Optional[str] = None,
                        automation_id: Optional[str] = None) -> bool:
        """Set a slider / progress value (RangeValuePattern); True on success."""
        self._unsupported("set_range_value")

    def scroll_into_view(self, name: Optional[str] = None,
                         role: Optional[str] = None, app_name: Optional[str] = None,
                         automation_id: Optional[str] = None) -> bool:
        """Scroll the matched control into view (ScrollItemPattern); True on success."""
        self._unsupported("scroll_into_view")

    # --- text patterns (TextPattern reads) ---------------------------------

    def document_text(self, name: Optional[str] = None, role: Optional[str] = None,
                      app_name: Optional[str] = None,
                      automation_id: Optional[str] = None) -> Optional[str]:
        """Return the matched control's full text (TextPattern), or None.

        Reads multiline / document controls where ValuePattern returns ``""``.
        """
        self._unsupported("document_text")

    def selected_text(self, name: Optional[str] = None, role: Optional[str] = None,
                      app_name: Optional[str] = None,
                      automation_id: Optional[str] = None) -> Optional[str]:
        """Return the control's currently selected text (TextPattern), or None."""
        self._unsupported("selected_text")

    def visible_text(self, name: Optional[str] = None, role: Optional[str] = None,
                     app_name: Optional[str] = None,
                     automation_id: Optional[str] = None) -> Optional[str]:
        """Return only the on-screen text of the control (TextPattern), or None."""
        self._unsupported("visible_text")

    # --- keyboard focus ----------------------------------------------------

    def set_focus(self, name: Optional[str] = None, role: Optional[str] = None,
                  app_name: Optional[str] = None,
                  automation_id: Optional[str] = None) -> bool:
        """Set keyboard focus on the matched control (SetFocus); True on success."""
        self._unsupported("set_focus")

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
        self._unsupported("find_virtual_item")

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
        self._unsupported("get_properties")

    def _unsupported(self, operation: str):
        """Raise a clear error for an action this backend can't perform."""
        raise AccessibilityNotAvailableError(
            f"{operation} is not supported by the {self.name} backend",
        )
