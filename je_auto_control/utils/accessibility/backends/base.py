"""Abstract accessibility backend."""
from typing import List, Optional

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

    def _unsupported(self, operation: str):
        """Raise a clear error for an action this backend can't perform."""
        raise AccessibilityNotAvailableError(
            f"{operation} is not supported by the {self.name} backend",
        )
