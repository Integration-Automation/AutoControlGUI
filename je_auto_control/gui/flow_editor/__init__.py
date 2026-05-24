"""Visual node-based flow editor for AutoControl scripts.

Mirrors the existing list-based ``script_builder`` view: both consume
the same :class:`Step` model + JSON action schema, so a script
authored in one view loads cleanly in the other.

Public surface::

    from je_auto_control.gui.flow_editor import (
        FlowEditorTab, FlowGraphScene, layout_steps,
    )
"""
from je_auto_control.gui.flow_editor.layout import (
    FlowEdge, FlowLayout, FlowNodePosition, layout_steps,
)
from je_auto_control.gui.flow_editor.scene import (
    FlowEdgeItem, FlowGraphScene, FlowNodeItem,
)
from je_auto_control.gui.flow_editor.tab import FlowEditorTab


__all__ = [
    "FlowEdge", "FlowEditorTab", "FlowEdgeItem", "FlowGraphScene",
    "FlowLayout", "FlowNodeItem", "FlowNodePosition", "layout_steps",
]
