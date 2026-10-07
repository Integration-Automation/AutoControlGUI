"""Resolve one catalog factory only at first open, retaining optional dependency recovery."""
from __future__ import annotations

from importlib import import_module
from typing import Callable, TYPE_CHECKING
import weakref

from je_auto_control.gui.tab_registry import TabRegistryError

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget


def build_tab(host: weakref.ReferenceType[QWidget], module: str, target: str) -> QWidget:
    """Construct one known catalog target; missing extras have a selectable recovery view."""
    try:
        owner = host()
        if owner is None:
            raise TabRegistryError('tab factory owner no longer exists')
        if module:
            return getattr(import_module(module), target)()
        if target == '_build_remote_desktop_tab':
            return getattr(import_module('je_auto_control.gui.remote_desktop_tab'), 'RemoteDesktopTab')()
        return getattr(owner, target)()
    except ImportError as failure:
        return _dependency_view(str(failure))


def _dependency_view(reason: str) -> QWidget:
    # pylint: disable-next=import-outside-toplevel  # reason: Qt recovery panel is loaded only for a selected missing extra
    from je_auto_control.gui._dependency_panel import DependencyPanel
    return DependencyPanel(reason)


def call_core_action(method: weakref.WeakMethod[Callable[[], object]]) -> None:
    """Invoke a legacy GUI handler without retaining its QObject through catalog callbacks."""
    handler = method()
    if handler is not None:
        handler()
