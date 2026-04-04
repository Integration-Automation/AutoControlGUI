import sys

from PySide6.QtWidgets import QMainWindow, QApplication, QComboBox, QLabel, QHBoxLayout, QWidget
from PySide6.QtGui import QAction
from qt_material import QtStyleTools

from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.gui.main_widget import AutoControlGUIWidget


class AutoControlGUIUI(QMainWindow, QtStyleTools):

    def __init__(self):
        super().__init__()

        # Application ID for Windows taskbar
        self.app_id = language_wrapper.language_word_dict.get("application_name")
        if sys.platform in ["win32", "cygwin", "msys"]:
            from ctypes import windll
            windll.shell32.SetCurrentProcessExplicitAppUserModelID(self.app_id)

        # Style
        self.setStyleSheet(
            "font-size: 12pt;"
            "font-family: 'Lato';"
        )
        self.apply_stylesheet(self, "dark_amber.xml")

        # Window title and size
        self.setWindowTitle(language_wrapper.language_word_dict.get("application_name", "AutoControlGUI"))
        self.resize(900, 700)

        # Central widget
        self.auto_control_gui_widget = AutoControlGUIWidget()
        self.setCentralWidget(self.auto_control_gui_widget)

        # Menu bar with language switcher
        self._build_menu_bar()

    def _build_menu_bar(self):
        menu_bar = self.menuBar()

        # Language selector in menu bar
        lang_widget = QWidget()
        lang_layout = QHBoxLayout(lang_widget)
        lang_layout.setContentsMargins(4, 0, 4, 0)

        lang_label = QLabel(language_wrapper.language_word_dict.get("language_label", "Language:"))
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["English", "Traditional_Chinese"])
        self.lang_combo.setCurrentText(language_wrapper.language)
        self.lang_combo.currentTextChanged.connect(self._on_language_changed)

        lang_layout.addWidget(lang_label)
        lang_layout.addWidget(self.lang_combo)

        menu_bar.setCornerWidget(lang_widget)

    def _on_language_changed(self, language: str):
        language_wrapper.reset_language(language)
        # Rebuild UI with new language
        self.setWindowTitle(language_wrapper.language_word_dict.get("application_name", "AutoControlGUI"))
        self.auto_control_gui_widget = AutoControlGUIWidget()
        self.setCentralWidget(self.auto_control_gui_widget)
        self._build_menu_bar()


if "__main__" == __name__:
    app = QApplication(sys.argv)
    window = AutoControlGUIUI()
    window.show()
    sys.exit(app.exec())