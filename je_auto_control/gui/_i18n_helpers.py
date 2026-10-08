"""Translation-registry mixin shared by tabs that need live language switching.

Widgets register their (widget, translation-key, setter-name) triples via
``self._tr(widget, key, setter)`` during UI construction. Calling
``self.retranslate()`` re-pulls every key from the language wrapper and
re-applies it through the recorded setter. Destroyed widgets are skipped
silently so removing a row never breaks a later language switch.

A widget that registers *itself* (``self._tr(self, "title_key",
setter="setWindowTitle")``) is recorded as ``None``, not as a reference. Holding
it made the widget a reference cycle, so dropping one never freed it: it stayed
a live window until the cycle collector ran, and the collector destroyed the
C++ object wherever it happened to be — on Python 3.10/3.11 that can be in the
middle of a PySide call that is still walking a list of widgets.
"""
from typing import List, Optional, Tuple

from PySide6.QtWidgets import (
    QAbstractButton, QGroupBox, QLabel, QLineEdit, QTabWidget, QWidget,
)

from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)


def _default_setter(widget: QWidget) -> str:
    if isinstance(widget, QGroupBox):
        return "setTitle"
    if isinstance(widget, (QLabel, QAbstractButton)):
        return "setText"
    if isinstance(widget, QLineEdit):
        return "setPlaceholderText"
    return "setText"


class TranslatableMixin:
    """Provides ``_tr(...)`` / ``retranslate()`` for a widget-building class."""

    def _tr_init(self) -> None:
        self._tr_registry: List[Tuple[Optional[QWidget], str, str]] = []
        self._tr_tabs: List[Tuple[QTabWidget, int, str]] = []

    def _tr(self, widget: QWidget, key: str, setter: str = "") -> QWidget:
        """Set ``widget`` text from ``key`` now and on every retranslate."""
        if not hasattr(self, "_tr_registry"):
            self._tr_init()
        resolved = setter or _default_setter(widget)
        translated = language_wrapper.translate(key, key)
        getattr(widget, resolved)(translated)
        # None stands for ``self``: see the module docstring.
        self._tr_registry.append((None if widget is self else widget, key, resolved))
        return widget

    def _tr_tab(self, tab_widget: QTabWidget, index: int, key: str) -> None:
        """Register a tab title so it re-translates."""
        if not hasattr(self, "_tr_tabs"):
            self._tr_init()
        tab_widget.setTabText(index, language_wrapper.translate(key, key))
        self._tr_tabs.append((tab_widget, index, key))

    def retranslate(self) -> None:
        """Re-apply every registered translation key."""
        for widget, key, setter in getattr(self, "_tr_registry", []):
            target = self if widget is None else widget
            try:
                getattr(target, setter)(language_wrapper.translate(key, key))
            except RuntimeError:
                # Widget destroyed; leave it for a future cleanup pass.
                continue
        for tab_widget, index, key in getattr(self, "_tr_tabs", []):
            try:
                tab_widget.setTabText(index, language_wrapper.translate(key, key))
            except RuntimeError:
                continue
