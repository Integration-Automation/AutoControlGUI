import sys

from PySide6.QtWidgets import QMainWindow, QApplication
from qt_material import QtStyleTools

from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.gui.main_widget import AutoControlGUIWidget


class AutoControlGUIUI(QMainWindow, QtStyleTools):

    def __init__(self):
        super().__init__()
        self.id = language_wrapper.language_word_dict.get("application_name")
        if sys.platform in ["win32", "cygwin", "msys"]:
            from ctypes import windll
            windll.shell32.SetCurrentProcessExplicitAppUserModelID(self.id)
        self.setStyleSheet(
            f"font-size: 12pt;"
            f"font-family: 'Lato';"
        )
        self.apply_stylesheet(self, "dark_amber.xml")
        self.auto_control_gui_widget = AutoControlGUIWidget()
        self.setCentralWidget(self.auto_control_gui_widget)
