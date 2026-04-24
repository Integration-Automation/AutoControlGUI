"""Fallback backend used when no real backend can be loaded."""
from typing import List, Optional

from je_auto_control.utils.accessibility.backends.base import (
    AccessibilityBackend,
)
from je_auto_control.utils.accessibility.element import (
    AccessibilityElement, AccessibilityNotAvailableError,
)


class NullAccessibilityBackend(AccessibilityBackend):
    """Backend that always reports an unavailability error."""

    name = "null"
    available = False

    def __init__(self, reason: str = "no accessibility backend available"):
        self._reason = reason

    def list_elements(self, app_name: Optional[str] = None,
                      max_results: int = 200,
                      ) -> List[AccessibilityElement]:
        raise AccessibilityNotAvailableError(self._reason)
