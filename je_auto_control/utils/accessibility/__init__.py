"""Cross-platform accessibility-tree widget location + recording."""
from je_auto_control.utils.accessibility.accessibility_api import (
    AccessibilityElement, AccessibilityNotAvailableError, AXTreeNode,
    click_accessibility_element, dump_accessibility_tree,
    find_accessibility_element, list_accessibility_elements,
)
from je_auto_control.utils.accessibility.recorder import (
    AXRecorderEvent, AccessibilityRecorder,
)
from je_auto_control.utils.accessibility.tree import (
    AXTreeWalker, count_nodes, max_depth,
)


__all__ = [
    "AccessibilityElement", "AccessibilityNotAvailableError",
    "AccessibilityRecorder", "AXRecorderEvent", "AXTreeNode",
    "AXTreeWalker", "click_accessibility_element", "count_nodes",
    "dump_accessibility_tree", "find_accessibility_element",
    "list_accessibility_elements", "max_depth",
]
