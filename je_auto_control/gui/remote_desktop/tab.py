"""``RemoteDesktopTab``: outer container holding host + viewer sub-tabs."""
from typing import Optional

from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.remote_desktop._helpers import _t
from je_auto_control.gui.remote_desktop.host_panel import _HostPanel
from je_auto_control.gui.remote_desktop.viewer_panel import _ViewerPanel


class RemoteDesktopTab(TranslatableMixin, QWidget):
    """Outer container holding the host and viewer sub-tabs."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        layout = QVBoxLayout(self)
        self._tabs = QTabWidget()
        self._host_panel = _HostPanel()
        self._viewer_panel = _ViewerPanel()
        host_index = self._tabs.addTab(self._host_panel, _t("rd_host_tab"))
        viewer_index = self._tabs.addTab(self._viewer_panel, _t("rd_viewer_tab"))
        self._tr_tab(self._tabs, host_index, "rd_host_tab")
        self._tr_tab(self._tabs, viewer_index, "rd_viewer_tab")
        layout.addWidget(self._tabs)

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        self._host_panel.retranslate()
        self._viewer_panel.retranslate()
