"""Immutable tab metadata and lazy owner-scoped factories; imports remain Qt-free."""
from __future__ import annotations

from dataclasses import dataclass
import weakref
from typing import Callable, Optional, Sequence, TYPE_CHECKING

from je_auto_control.utils.exception.exceptions import AutoControlException

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget


class TabRegistryError(AutoControlException, ValueError):
    """Invalid catalog identity or a registry whose GUI owner has been destroyed."""


@dataclass(frozen=True)
class TabSpec:
    """Freeze display/action metadata without importing a feature or constructing widgets."""

    key: str
    title_key: str
    category: str
    factory: Callable[[], QWidget]
    actions: tuple[tuple[str, str], ...] = ()
    default_visible: bool = False


class TabRegistry:
    """Create each tab once on demand; hide preserves it and explicit close releases it."""

    def __init__(self, specs: Sequence[TabSpec], *, parent: Optional[QWidget] = None) -> None:
        self._specs = {spec.key: spec for spec in specs}
        if len(self._specs) != len(specs) or any(not spec.key for spec in specs):
            raise TabRegistryError('tab keys must be unique and nonempty')
        self._instances: dict[str, QWidget] = {}
        self._parent: Optional[weakref.ReferenceType[QWidget]] = None
        self._disposed = False
        if parent is not None:
            self.bind_owner(parent)

    @property
    def owner(self) -> Optional[QWidget]:
        """Return the live owner for workspace embedding without opening a feature."""
        return self._parent() if self._parent is not None else None

    def bind_owner(self, parent: QWidget) -> None:
        """Attach an initially standalone registry to one GUI owner; never transfer ownership."""
        _require_gui_thread()
        if self._disposed or (self.owner is not None and self.owner is not parent):
            raise TabRegistryError('registry already belongs to another owner or has been destroyed')
        if self.owner is parent:
            return
        self._parent = weakref.ref(parent)
        parent.destroyed.connect(self._owner_destroyed)

    @property
    def specs(self) -> tuple[TabSpec, ...]:
        """Return ordered immutable metadata without running factories."""
        return tuple(self._specs.values())

    def instance(self, key: str) -> Optional[QWidget]:
        """Return an existing panel without implicitly constructing it."""
        return self._instances.get(key)

    def open(self, key: str) -> QWidget:
        """Construct only the selected feature on the caller's GUI thread."""
        if self._disposed or key not in self._specs:
            raise TabRegistryError('unknown tab or destroyed registry owner')
        _require_gui_thread()
        widget = self._instances.get(key)
        if widget is None:
            widget = self._specs[key].factory()
            if self._parent is not None:
                widget.setParent(self._parent())
            widget.setProperty('tab_key', key)
            widget.hide()
            self._instances[key] = widget
        return widget

    def close(self, key: str) -> None:
        """Close and defer Qt deletion so panel cleanup and subscriptions are released."""
        widget = self._instances.get(key)
        if widget is not None:
            _require_gui_thread()
            widget.close()
            widget.deleteLater()
            self._instances.pop(key, None)

    def close_all(self) -> None:
        """Release every constructed feature; unopened factories remain untouched."""
        for key in tuple(self._instances):
            self.close(key)

    def _owner_destroyed(self, _owner: object = None) -> None:
        self._disposed = True
        # Qt destroys owned children; do not call their methods while parent destruction runs.
        self._instances.clear()


__all__ = ['TabSpec', 'TabRegistry', 'TabRegistryError']


def _require_gui_thread() -> None:
    # pylint: disable-next=import-outside-toplevel  # reason: metadata queries stay Qt-free; explicit widget lifecycle is GUI-only
    from PySide6.QtCore import QThread
    # pylint: disable-next=import-outside-toplevel  # reason: widget factories require a GUI application rather than QCoreApplication
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if not isinstance(app, QApplication) or QThread.currentThread() != app.thread():
        raise TabRegistryError('widget factories and close must run on the GUI application thread')
