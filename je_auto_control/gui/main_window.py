import sys

from PySide6.QtWidgets import QMainWindow, QApplication
from qt_material import QtStyleTools

from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.gui.main_widget import AutoControlGUIWidget


class AutoControlGUIUI(QMainWindow, QtStyleTools):
    """
    AutoControl GUI Main Window
    自動控制 GUI 主視窗
    - 提供應用程式主要介面
    - 套用 Qt Material 樣式
    """

    def __init__(self):
        super().__init__()

        # === Application ID 應用程式 ID ===
        # 用於 Windows 工作列顯示正確的應用程式名稱
        self.app_id = language_wrapper.language_word_dict.get("application_name")

        if sys.platform in ["win32", "cygwin", "msys"]:
            from ctypes import windll
            windll.shell32.SetCurrentProcessExplicitAppUserModelID(self.app_id)

        # === Style 設定字型與樣式 ===
        self.setStyleSheet(
            "font-size: 12pt;"
            "font-family: 'Lato';"
        )

        # 套用 Qt Material 樣式 (可替換不同主題檔案)
        self.apply_stylesheet(self, "dark_amber.xml")

        # === Central Widget 主控元件 ===
        # 將 AutoControlGUIWidget 作為主視窗中央元件
        self.auto_control_gui_widget = AutoControlGUIWidget()
        self.setCentralWidget(self.auto_control_gui_widget)