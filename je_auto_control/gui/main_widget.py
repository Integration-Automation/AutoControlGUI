from PySide6.QtCore import QTimer
from PySide6.QtGui import QIntValidator, QKeyEvent, Qt
from PySide6.QtWidgets import (
    QWidget, QLineEdit, QComboBox, QPushButton, QVBoxLayout, QLabel,
    QGridLayout, QHBoxLayout, QRadioButton, QButtonGroup, QMessageBox
)

from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.wrapper.auto_control_keyboard import type_keyboard
from je_auto_control.wrapper.auto_control_mouse import click_mouse
from je_auto_control.wrapper.platform_wrapper import keyboard_keys_table, mouse_keys_table


class AutoControlGUIWidget(QWidget):
    """
    AutoControl GUI Widget
    自動控制 GUI 元件
    提供滑鼠與鍵盤操作的自動化設定介面
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        main_layout = QVBoxLayout()

        # === Grid for input fields 輸入欄位區塊 ===
        grid = QGridLayout()

        # Interval time 間隔時間
        grid.addWidget(QLabel(language_wrapper.language_word_dict.get("interval_time")), 0, 0)
        self.interval_input = QLineEdit()
        self.interval_input.setValidator(QIntValidator())
        grid.addWidget(self.interval_input, 0, 1)

        # Cursor X/Y 滑鼠座標
        grid.addWidget(QLabel(language_wrapper.language_word_dict.get("cursor_x")), 2, 0)
        self.cursor_x_input = QLineEdit()
        self.cursor_x_input.setValidator(QIntValidator())
        grid.addWidget(self.cursor_x_input, 2, 1)

        grid.addWidget(QLabel(language_wrapper.language_word_dict.get("cursor_y")), 3, 0)
        self.cursor_y_input = QLineEdit()
        self.cursor_y_input.setValidator(QIntValidator())
        grid.addWidget(self.cursor_y_input, 3, 1)

        # Mouse button 滑鼠按鍵
        grid.addWidget(QLabel(language_wrapper.language_word_dict.get("mouse_button")), 4, 0)
        self.mouse_button_combo = QComboBox()
        self.mouse_button_combo.addItems(mouse_keys_table)
        grid.addWidget(self.mouse_button_combo, 4, 1)

        # Keyboard button 鍵盤按鍵
        grid.addWidget(QLabel(language_wrapper.language_word_dict.get("keyboard_button")), 5, 0)
        self.keyboard_button_combo = QComboBox()
        self.keyboard_button_combo.addItems(keyboard_keys_table.keys())
        grid.addWidget(self.keyboard_button_combo, 5, 1)

        # Click type 點擊類型
        grid.addWidget(QLabel(language_wrapper.language_word_dict.get("click_type")), 6, 0)
        self.click_type_combo = QComboBox()
        self.click_type_combo.addItems(["Single Click", "Double Click"])
        grid.addWidget(self.click_type_combo, 6, 1)

        # Input method selection 輸入方式選擇
        grid.addWidget(QLabel(language_wrapper.language_word_dict.get("input_method")), 7, 0)
        self.mouse_radio = QRadioButton(language_wrapper.language_word_dict.get("mouse_radio"))
        self.keyboard_radio = QRadioButton(language_wrapper.language_word_dict.get("keyboard_radio"))
        self.mouse_radio.setChecked(True)
        self.input_method_group = QButtonGroup()
        self.input_method_group.addButton(self.mouse_radio)
        self.input_method_group.addButton(self.keyboard_radio)
        grid.addWidget(self.mouse_radio, 7, 1)
        grid.addWidget(self.keyboard_radio, 7, 2)

        main_layout.addLayout(grid)

        # === Repeat options 重複執行選項 ===
        repeat_layout = QHBoxLayout()
        self.repeat_until_stopped = QRadioButton(language_wrapper.language_word_dict.get("repeat_until_stopped_radio"))
        self.repeat_count_times = QRadioButton(language_wrapper.language_word_dict.get("repeat_radio"))
        self.repeat_count_input = QLineEdit()
        self.repeat_count_input.setValidator(QIntValidator())
        self.repeat_count_input.setPlaceholderText(language_wrapper.language_word_dict.get("times"))
        repeat_group = QButtonGroup()
        repeat_group.addButton(self.repeat_until_stopped)
        repeat_group.addButton(self.repeat_count_times)
        self.repeat_until_stopped.setChecked(True)
        self.repeat_count = 0
        self.repeat_max = 0

        repeat_layout.addWidget(self.repeat_until_stopped)
        repeat_layout.addWidget(self.repeat_count_times)
        repeat_layout.addWidget(self.repeat_count_input)
        main_layout.addLayout(repeat_layout)

        # === Start/Stop buttons 開始/停止按鈕 ===
        button_layout = QHBoxLayout()
        self.start_button = QPushButton(language_wrapper.language_word_dict.get("start"))
        self.start_button.clicked.connect(self.start_autocontrol)
        self.stop_button = QPushButton(language_wrapper.language_word_dict.get("stop"))
        self.stop_button.clicked.connect(self.stop_autocontrol)
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        main_layout.addLayout(button_layout)

        # Timer 計時器
        self.start_autocontrol_timer = QTimer()

        # Connect input method toggle 輸入方式切換
        self.mouse_radio.toggled.connect(self.update_input_mode)
        self.keyboard_radio.toggled.connect(self.update_input_mode)
        self.update_input_mode()

        self.setLayout(main_layout)

    # === 更新輸入模式 ===
    def update_input_mode(self):
        """
        Enable/Disable input fields based on selected mode
        根據選擇的輸入方式啟用/停用相關欄位
        """
        use_mouse = self.mouse_radio.isChecked()
        self.cursor_x_input.setEnabled(use_mouse)
        self.cursor_y_input.setEnabled(use_mouse)
        self.mouse_button_combo.setEnabled(use_mouse)
        self.keyboard_button_combo.setEnabled(not use_mouse)

    # === 開始自動控制 ===
    def start_autocontrol(self):
        """
        Start auto control with timer
        啟動計時器開始自動控制
        """
        try:
            interval = int(self.interval_input.text())
        except ValueError:
            QMessageBox.warning(self, "Warning", "Interval must be a number\n間隔必須是數字")
            return

        self.start_autocontrol_timer.setInterval(interval)
        self.start_autocontrol_timer.timeout.connect(self.start_timer_function)
        self.start_autocontrol_timer.start()

        try:
            self.repeat_max = int(self.repeat_count_input.text())
        except ValueError:
            self.repeat_max = 0

    # === 計時器觸發函式 ===
    def start_timer_function(self):
        """
        Timer callback function
        計時器回呼函式
        """
        if self.repeat_until_stopped.isChecked():
            self.trigger_autocontrol_function()
        elif self.repeat_count_times.isChecked():
            self.repeat_count += 1
            if self.repeat_count < self.repeat_max:
                self.trigger_autocontrol_function()
            else:
                self.repeat_count = 0
                self.repeat_max = 0
                self.start_autocontrol_timer.stop()

    # === 執行自動控制動作 ===
    def trigger_autocontrol_function(self):
        """
        Execute mouse or keyboard action
        執行滑鼠或鍵盤操作
        """
        click_type = self.click_type_combo.currentText()

        if self.mouse_radio.isChecked():
            button = self.mouse_button_combo.currentText()
            try:
                x = int(self.cursor_x_input.text())
                y = int(self.cursor_y_input.text())
            except ValueError:
                QMessageBox.warning(self, "Warning", "Cursor position must be numbers\n座標必須是數字")
                return
            self._execute_click(click_mouse, click_type, button, x, y)

        elif self.keyboard_radio.isChecked():
            button = self.keyboard_button_combo.currentText()
            self._execute_click(type_keyboard, click_type, button)

    def _execute_click(self, func, click_type, *args, **kwargs):
        """
        Helper function to execute single/double click
        輔助函式：執行單擊或雙擊
        """
        func(*args, **kwargs)
        if click_type == "Double Click":
            func(*args, **kwargs)

    # === 停止自動控制 ===
    def stop_autocontrol(self):
        """
        Stop auto control
        停止自動控制
        """
        self.start_autocontrol_timer.stop()

    # === 鍵盤快捷鍵事件 ===
    def keyPressEvent(self, event: QKeyEvent):
        """
        Handle keyboard shortcut
        處理鍵盤快捷鍵事件
        Ctrl + 4 停止自動控制
        """
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_4:
            self.start_autocontrol_timer.stop()
        else:
            super().keyPressEvent(event)
