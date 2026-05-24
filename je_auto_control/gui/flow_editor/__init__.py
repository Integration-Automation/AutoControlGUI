"""Visual node-based flow editor for AutoControl scripts.

Mirrors the existing list-based ``script_builder`` view: both consume
the same :class:`Step` model + JSON action schema, so a script
authored in one view loads cleanly in the other.

Public surface::

    from je_auto_control.gui.flow_editor import (
        FlowEditorTab, FlowGraphScene, layout_steps,
    )

The ``layout`` module is Qt-free and eager so headless tests can import
it without instantiating PySide6. ``scene`` and ``tab`` are loaded
lazily via :func:`__getattr__` because they pull in Qt.
"""
from je_auto_control.gui.flow_editor.layout import (
    FlowEdge, FlowLayout, FlowNodePosition, layout_steps,
)

_LAZY_SUBMODULES = {
    "FlowEdgeItem": "je_auto_control.gui.flow_editor.scene",
    "FlowGraphScene": "je_auto_control.gui.flow_editor.scene",
    "FlowNodeItem": "je_auto_control.gui.flow_editor.scene",
    "FlowEditorTab": "je_auto_control.gui.flow_editor.tab",
}


def __getattr__(name):
    if name in _LAZY_SUBMODULES:
        import importlib
        module = importlib.import_module(_LAZY_SUBMODULES[name])
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "FlowEdge", "FlowEditorTab", "FlowEdgeItem", "FlowGraphScene",
    "FlowLayout", "FlowNodeItem", "FlowNodePosition", "layout_steps",
]
