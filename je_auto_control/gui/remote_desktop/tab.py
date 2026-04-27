"""``RemoteDesktopTab``: outer container holding host + viewer sub-tabs."""
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QScrollArea, QTabWidget, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.remote_desktop._helpers import _t
from je_auto_control.gui.remote_desktop.host_panel import _HostPanel
from je_auto_control.gui.remote_desktop.viewer_panel import _ViewerPanel
from je_auto_control.gui.remote_desktop.webrtc_panel import (
    _WebRTCHostPanel, _WebRTCViewerPanel,
)


def _wrap_in_scroll_area(panel: QWidget) -> QScrollArea:
    """Drop ``panel`` into a resizable scroll area so it adapts.

    ``setWidgetResizable(True)`` lets the inner panel grow horizontally
    with the tab and only scroll vertically when its natural height
    exceeds the viewport. This is the responsive-sizing piece the
    panels were missing — a 4K user gets the panel filling the width,
    a laptop user gets a scrollbar instead of crushed widgets, and the
    middle ground "just works" without manual layout tweaks.
    """
    scroll = QScrollArea()
    scroll.setWidget(panel)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(
        Qt.ScrollBarPolicy.ScrollBarAsNeeded,
    )
    scroll.setVerticalScrollBarPolicy(
        Qt.ScrollBarPolicy.ScrollBarAsNeeded,
    )
    return scroll


class RemoteDesktopTab(TranslatableMixin, QWidget):
    """Outer container holding the host and viewer sub-tabs."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._tabs = QTabWidget()
        self._host_panel = _HostPanel()
        self._viewer_panel = _ViewerPanel()
        self._webrtc_host_panel = _WebRTCHostPanel()
        self._webrtc_viewer_panel = _WebRTCViewerPanel()
        sub_panels = [
            (self._host_panel, "rd_host_tab"),
            (self._viewer_panel, "rd_viewer_tab"),
            (self._webrtc_host_panel, "rd_webrtc_host_tab"),
            (self._webrtc_viewer_panel, "rd_webrtc_viewer_tab"),
        ]
        for panel, key in sub_panels:
            # Wrap each panel in a scroll area so the dense WebRTC tabs
            # remain usable on small screens and don't squash widgets
            # together on big monitors when the window is enlarged.
            index = self._tabs.addTab(_wrap_in_scroll_area(panel), _t(key))
            self._tr_tab(self._tabs, index, key)
        layout.addWidget(self._tabs)
        self._sub_panels = [panel for panel, _key in sub_panels]

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        for panel in self._sub_panels:
            panel.retranslate()
