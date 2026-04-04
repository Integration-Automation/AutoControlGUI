import sys

from PySide6.QtWidgets import QApplication

from je_auto_control.gui.main_window import AutoControlGUIUI


def start_autocontrol_gui():
    app = QApplication(sys.argv)
    window = AutoControlGUIUI()
    window.show()
    sys.exit(app.exec())
