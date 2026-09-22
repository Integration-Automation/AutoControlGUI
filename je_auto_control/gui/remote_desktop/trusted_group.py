"""The 'trusted viewers' group the WebRTC host panel builds.

Split out of ``webrtc_panel`` for the same reason as
:mod:`je_auto_control.gui.remote_desktop.advanced_group`: it is a widget
builder that *writes* onto the panel it is given (``_trusted_list``), and that
contract has to be written down somewhere other than inside a file already at
its line-count cap.

The panel argument is therefore a :class:`TrustedGroupHost`: what the builder
reads (``_tr`` and the four slots it connects) and what it sets. Imports
``PySide6`` — it is GUI-only by construction.
"""
from __future__ import annotations

from typing import Any, Protocol

from PySide6.QtWidgets import (
    QGroupBox, QHBoxLayout, QPushButton, QVBoxLayout, QWidget,
)

from je_auto_control.gui.remote_desktop.webrtc_dialogs import TrustedViewersList


class TrustedGroupHost(Protocol):
    """A WebRTC host panel, seen from the trusted-viewers group it hosts."""

    _trusted_list: Any

    def _tr(self, widget: QWidget, key: str, setter: str = "") -> QWidget:
        """Register ``widget`` for live re-translation and return it."""

    def _on_remove_trust(self, viewer_id: str) -> None:
        """Forget the viewer the list emitted."""

    def _on_remove_trust_button(self) -> None:
        """Forget the viewer selected in the list."""

    def _on_clear_trust(self) -> None:
        """Forget every trusted viewer."""

    def _on_import_trust(self) -> None:
        """Merge a trust list from a file."""

    def _on_export_trust(self) -> None:
        """Write the trust list to a file."""


def build_trusted_group(panel: TrustedGroupHost) -> QGroupBox:
    """The trusted-viewers list plus its remove / clear / import / export row."""
    group = panel._tr(QGroupBox(), "rd_webrtc_trusted_group")
    layout = QVBoxLayout()
    panel._trusted_list = TrustedViewersList()
    panel._trusted_list.removed.connect(panel._on_remove_trust)
    layout.addWidget(panel._trusted_list)
    button_row = QHBoxLayout()
    for key, slot in (
        ("rd_webrtc_remove_trusted", panel._on_remove_trust_button),
        ("rd_webrtc_clear_trusted", panel._on_clear_trust),
        ("rd_webrtc_trust_import", panel._on_import_trust),
        ("rd_webrtc_trust_export", panel._on_export_trust),
    ):
        button = panel._tr(QPushButton(), key)
        button.clicked.connect(slot)
        button_row.addWidget(button)
    layout.addLayout(button_row)
    group.setLayout(layout)
    return group


__all__ = ["TrustedGroupHost", "build_trusted_group"]
