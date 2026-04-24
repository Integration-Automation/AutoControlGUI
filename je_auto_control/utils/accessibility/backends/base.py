"""Abstract accessibility backend."""
from typing import List, Optional

from je_auto_control.utils.accessibility.element import AccessibilityElement


class AccessibilityBackend:
    """Each backend exposes the platform's accessibility tree as flat lists."""

    name: str = "abstract"
    available: bool = False

    def list_elements(self, app_name: Optional[str] = None,
                      max_results: int = 200,
                      ) -> List[AccessibilityElement]:
        raise NotImplementedError
