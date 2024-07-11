from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from je_auto_control.gui.main_window import AutoControlGUI

from PySide6.QtWidgets import QWidget, QGridLayout


class AutoControlWidget(QWidget):

    def __init__(self, main_ui: AutoControlGUI):
        super().__init__()
        # Variable
        self.main_ui = main_ui
        # UI component
        # Grid layout
        self.grid_layout = QGridLayout()
        self.setLayout(self.grid_layout)
