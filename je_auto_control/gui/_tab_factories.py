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
    # pylint: disable-next=import-outside-toplevel  # reason: Qt is needed only when the selected factory lacks an extra
    from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget
    # pylint: disable-next=import-outside-toplevel  # reason: selected dependency recovery view uses native Qt text selection
    from PySide6.QtCore import Qt
    # pylint: disable-next=import-outside-toplevel  # reason: selected recovery view translates only when created
    from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
    widget = QWidget()
    layout = QVBoxLayout(widget)
    label = QLabel(language_wrapper.translate('feature_dependency_unavailable') + '\n' +
                   language_wrapper.translate('feature_dependency_recovery') + '\n' +
                   'Remote Desktop: python -m pip install je_auto_control[webrtc]\n' + reason)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    layout.addWidget(label)
    layout.addStretch()
    widget.setProperty('capability_reason', reason)
    return widget


def call_core_action(method: weakref.WeakMethod[Callable[[], object]]) -> None:
    """Invoke a legacy GUI handler without retaining its QObject through catalog callbacks."""
    handler = method()
    if handler is not None:
        handler()
