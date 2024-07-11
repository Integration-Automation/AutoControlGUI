import os
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMainWindow, QApplication
from qt_material import apply_stylesheet

from je_auto_control.gui.main_widget import AutoControlWidget


class AutoControlGUI(QMainWindow):

    def __init__(self, debug_mode: bool = False):
        super().__init__()
        self.debug_mode = debug_mode
        self.central_widget = AutoControlWidget(self)
        self.setCentralWidget(self.central_widget)
        self.setWindowTitle("AutoControlGUI")
        # Set Icon
        self.icon_path = Path(os.getcwd() + "/je_driver_icon.ico")
        self.icon = QIcon(str(self.icon_path))
        if self.icon.isNull() is False:
            self.setWindowIcon(self.icon)
        if self.debug_mode:
            close_timer = QTimer(self)
            close_timer.setInterval(10000)
            close_timer.timeout.connect(self.debug_close)
            close_timer.start()

    @classmethod
    def debug_close(cls):
        sys.exit(0)


def start_autocontrol_gui(debug_mode: bool = False) -> None:
    autocontrol_gui = QCoreApplication.instance()
    if autocontrol_gui is None:
        autocontrol_gui = QApplication(sys.argv)
    window = AutoControlGUI(debug_mode)
    apply_stylesheet(autocontrol_gui, theme='dark_amber.xml')
    window.showMaximized()
    sys.exit(autocontrol_gui.exec())
