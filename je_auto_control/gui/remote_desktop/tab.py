"""``RemoteDesktopTab``: outer container holding the Remote Desktop sub-tabs.

The Quick Connect sub-tab is always present and is the default landing
view (AnyDesk-style). The legacy TCP host / viewer tabs are also always
present. The two WebRTC sub-tabs are loaded lazily and only added if the
optional ``av`` / ``aiortc`` extras are importable; otherwise a single
placeholder tab points the operator at the ``[webrtc]`` install extra so
the rest of the Remote Desktop UI stays usable on stock installs.
"""
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QLabel, QScrollArea, QTabWidget, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.remote_desktop._helpers import _t
from je_auto_control.gui.remote_desktop.connection_screen import (
    QuickConnectScreen,
)
from je_auto_control.gui.remote_desktop.host_panel import _HostPanel
from je_auto_control.gui.remote_desktop.viewer_panel import _ViewerPanel


def _wrap_in_scroll_area(panel: QWidget) -> QScrollArea:
    """Drop ``panel`` into a resizable scroll area so it adapts.

    ``setWidgetResizable(True)`` lets the inner panel grow horizontally
    with the tab and only scroll vertically when its natural height
    exceeds the viewport.
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


def _build_webrtc_placeholder() -> QWidget:
    """Stand-in shown when the optional ``av``/``aiortc`` extras are missing."""
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(24, 24, 24, 24)
    message = QLabel(_t("rd_webrtc_missing_extras"))
    message.setWordWrap(True)
    message.setAlignment(Qt.AlignmentFlag.AlignCenter)
    message.setStyleSheet("font-size: 11pt; color: #555;")
    layout.addWidget(message)
    layout.addStretch(1)
    return widget


def _load_webrtc_panels() -> Tuple[Optional[QWidget], Optional[QWidget]]:
    """Import the WebRTC panels lazily; ``(None, None)`` when extras absent."""
    try:
        from je_auto_control.gui.remote_desktop.webrtc_panel import (
            _WebRTCHostPanel, _WebRTCViewerPanel,
        )
    except ImportError:
        return None, None
    return _WebRTCHostPanel(), _WebRTCViewerPanel()


class RemoteDesktopTab(TranslatableMixin, QWidget):
    """Outer container holding the Remote Desktop sub-tabs."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._tabs = QTabWidget()
        self._quick_connect = QuickConnectScreen()
        self._host_panel = _HostPanel()
        self._viewer_panel = _ViewerPanel()
        # WebRTC sub-tab indices (-1 when extras are missing) are set
        # while building the sub-panel list below; the Quick Connect
        # screen routes 9-digit IDs and "publish via signaling" through
        # them via webrtc_handoff_requested / webrtc_host_handoff_requested.
        self._webrtc_viewer_index = -1
        self._webrtc_host_index = -1
        sub_panels = self._build_sub_panel_list()
        for panel, key in sub_panels:
            index = self._tabs.addTab(_wrap_in_scroll_area(panel), _t(key))
            self._tr_tab(self._tabs, index, key)
            if panel is self._webrtc_viewer_panel:
                self._webrtc_viewer_index = index
            elif panel is self._webrtc_host_panel:
                self._webrtc_host_index = index
        self._tabs.setCurrentIndex(0)
        layout.addWidget(self._tabs)
        self._quick_connect.webrtc_handoff_requested.connect(
            self._on_webrtc_handoff,
        )
        self._quick_connect.webrtc_host_handoff_requested.connect(
            self._on_webrtc_host_handoff,
        )
        # Only TranslatableMixin panels need retranslate(); the WebRTC
        # placeholder is a plain QWidget so we filter it out.
        self._sub_panels = [
            panel for panel, _key in sub_panels
            if isinstance(panel, TranslatableMixin)
        ]

    def _on_webrtc_handoff(self, host_id: str, token: str) -> None:
        """Pre-fill the WebRTC viewer panel and switch to its tab.

        When the optional WebRTC extras are absent the panel is a
        placeholder so the handoff degrades to switching to the
        placeholder tab; the user already sees the install hint there.
        """
        if (self._webrtc_viewer_panel is not None
                and hasattr(self._webrtc_viewer_panel, "prefill")):
            self._webrtc_viewer_panel.prefill(
                host_id=host_id, token=token,
            )
        if self._webrtc_viewer_index >= 0:
            self._tabs.setCurrentIndex(self._webrtc_viewer_index)

    def _on_webrtc_host_handoff(self, token: str, host_id: str) -> None:
        """Pre-fill the WebRTC Host panel so the operator can publish.

        Used when the Quick Connect operator clicks "Publish via
        signaling" — we forward the shared token (and the current
        TCP host's 9-digit ID, so viewers see the same number).
        """
        if (self._webrtc_host_panel is not None
                and hasattr(self._webrtc_host_panel, "prefill")):
            self._webrtc_host_panel.prefill(
                token=token, host_id=host_id,
            )
        if self._webrtc_host_index >= 0:
            self._tabs.setCurrentIndex(self._webrtc_host_index)

    def _build_sub_panel_list(self) -> List[Tuple[QWidget, str]]:
        sub_panels: List[Tuple[QWidget, str]] = [
            (self._quick_connect, "rd_quick_tab"),
            (self._host_panel, "rd_host_tab"),
            (self._viewer_panel, "rd_viewer_tab"),
        ]
        webrtc_host, webrtc_viewer = _load_webrtc_panels()
        if webrtc_host is not None and webrtc_viewer is not None:
            self._webrtc_host_panel = webrtc_host
            self._webrtc_viewer_panel = webrtc_viewer
            sub_panels.append((webrtc_host, "rd_webrtc_host_tab"))
            sub_panels.append((webrtc_viewer, "rd_webrtc_viewer_tab"))
        else:
            self._webrtc_host_panel = None
            self._webrtc_viewer_panel = None
            sub_panels.append(
                (_build_webrtc_placeholder(), "rd_webrtc_unavailable_tab"),
            )
        return sub_panels

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        for panel in self._sub_panels:
            panel.retranslate()
