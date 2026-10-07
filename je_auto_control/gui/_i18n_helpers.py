"""Translation registries preserve child wrappers without retaining their GUI owner.

Widgets register their (widget, translation-key, setter-name) triples via
``self._tr(widget, key, setter)`` during UI construction. Calling
``self.retranslate()`` re-pulls every key from the language wrapper and
re-applies it through the recorded setter. Destroyed widgets are skipped
silently so removing a row never breaks a later language switch. Self entries
use a weak proxy: a self-cycle can otherwise postpone parentless widget
destruction until garbage collection on a non-GUI worker thread.
"""
import weakref
from typing import List, Tuple, TypeVar, cast

from PySide6.QtWidgets import (
    QAbstractButton,
    QGroupBox,
    QLabel,
    QLineEdit,
    QTabWidget,
    QWidget,
)

from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)

_Widget = TypeVar('_Widget', bound=QWidget)


def _registry_target(owner: object, widget: _Widget) -> _Widget:
    """Keep child wrappers alive while avoiding a strong owner-to-self cycle."""
    return cast(_Widget, weakref.proxy(widget)) if widget is owner else widget


def _default_setter(widget: QWidget) -> str:
    if isinstance(widget, QGroupBox):
        return "setTitle"
    if isinstance(widget, (QLabel, QAbstractButton)):
        return "setText"
    if isinstance(widget, QLineEdit):
        return "setPlaceholderText"
    return "setText"


class TranslatableMixin:  # pylint: disable=too-few-public-methods  # Mixin exposes one retranslate hook; registry helpers are private.
    """Provides ``_tr(...)`` / ``retranslate()`` for a widget-building class."""

    def _tr_init(self) -> None:
        self._tr_registry: List[Tuple[QWidget, str, str]] = []
        self._tr_tabs: List[Tuple[QTabWidget, int, str]] = []

    def _tr(self, widget: _Widget, key: str, setter: str = "") -> _Widget:
        """Set ``widget`` text from ``key`` now and on every retranslate."""
        if not hasattr(self, "_tr_registry"):
            self._tr_init()
        resolved = setter or _default_setter(widget)
        translated = language_wrapper.translate(key, key)
        getattr(widget, resolved)(translated)
        self._tr_registry.append((_registry_target(self, widget), key, resolved))
        return widget

    def _tr_tab(self, tab_widget: QTabWidget, index: int, key: str) -> None:
        """Register a tab title so it re-translates."""
        if not hasattr(self, "_tr_tabs"):
            self._tr_init()
        tab_widget.setTabText(index, language_wrapper.translate(key, key))
        self._tr_tabs.append((_registry_target(self, tab_widget), index, key))

    def retranslate(self) -> None:
        """Re-apply every registered translation key."""
        for widget, key, setter in getattr(self, "_tr_registry", []):
            try:
                getattr(widget, setter)(language_wrapper.translate(key, key))
            except RuntimeError:
                # Widget destroyed; leave it for a future cleanup pass.
                continue
        for tab_widget, index, key in getattr(self, "_tr_tabs", []):
            try:
                tab_widget.setTabText(index, language_wrapper.translate(key, key))
            except RuntimeError:
                continue
