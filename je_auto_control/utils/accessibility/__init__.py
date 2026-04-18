"""Cross-platform accessibility-tree widget location."""
from je_auto_control.utils.accessibility.accessibility_api import (
    AccessibilityElement, AccessibilityNotAvailableError,
    click_accessibility_element, find_accessibility_element,
    list_accessibility_elements,
)

__all__ = [
    "AccessibilityElement", "AccessibilityNotAvailableError",
    "list_accessibility_elements", "find_accessibility_element",
    "click_accessibility_element",
]
