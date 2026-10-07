"""Compatible import path for the lazy AutoControl GUI widget."""
from je_auto_control.gui._lazy_widget import AutoControlGUIWidget as _LazyAutoControlGUIWidget


class AutoControlGUIWidget(_LazyAutoControlGUIWidget):
    """Retain the original class/import identity for GUI embedders and downstream audits."""

__all__ = ["AutoControlGUIWidget"]
