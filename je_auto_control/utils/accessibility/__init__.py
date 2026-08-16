"""Cross-platform accessibility-tree widget location + recording."""
from je_auto_control.utils.accessibility.accessibility_api import (
    AccessibilityElement, accessibility_status, AccessibilityNotAvailableError, AXTreeNode,
    click_accessibility_element, control_get_state, control_get_value,
    control_invoke,
    control_set_value, control_toggle, dump_accessibility_tree,
    find_accessibility_element, find_accessibility_elements,
    list_accessibility_elements, read_control_table,
)
from je_auto_control.utils.accessibility.recorder import (
    AXRecorderEvent, AccessibilityRecorder,
)
from je_auto_control.utils.accessibility.tree import (
    AXTreeWalker, count_nodes, max_depth,
)


__all__ = [
    "AccessibilityElement", "accessibility_status", "AccessibilityNotAvailableError",
    "AccessibilityRecorder", "AXRecorderEvent", "AXTreeNode",
    "AXTreeWalker", "click_accessibility_element", "count_nodes",
    "dump_accessibility_tree", "find_accessibility_element",
    "find_accessibility_elements", "list_accessibility_elements",
    "max_depth",
    "control_get_state", "control_get_value", "control_set_value",
    "control_invoke",
    "control_toggle", "read_control_table",
]
