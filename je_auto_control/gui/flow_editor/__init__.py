"""Visual node-based flow editor for AutoControl scripts.

Mirrors the existing list-based ``script_builder`` view: both consume
the same :class:`Step` model + JSON action schema, so a script
authored in one view loads cleanly in the other.

The ``layout`` module is Qt-free and eager so headless tests can
import it without instantiating PySide6. The Qt-dependent names
(``FlowGraphScene``, ``FlowEditorTab`` …) load lazily via
:func:`__getattr__`; they are intentionally absent from ``__all__``
because Pylint's E0603 refuses to certify names that ``import *`` can
not resolve at module-load time. ``from je_auto_control.gui.flow_editor
import FlowEditorTab`` still works — Python falls through to
``__getattr__`` when the attribute is not pre-bound.
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
    target = _LAZY_SUBMODULES.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib
    # Argument is looked up from a hard-coded dict above, never user
    # input — safe to import dynamically.
    module = importlib.import_module(target)  # nosemgrep
    return getattr(module, name)


__all__ = [
    "FlowEdge", "FlowLayout", "FlowNodePosition", "layout_steps",
]
