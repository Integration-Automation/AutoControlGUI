from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QWidget, QLineEdit, QComboBox, QPushButton, QVBoxLayout, QLabel,
    QGridLayout, QHBoxLayout, QRadioButton, QButtonGroup, QMessageBox,
    QGroupBox,
)

from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.wrapper.auto_control_keyboard import (
    type_keyboard, hotkey, write, get_keyboard_keys_table,
)
from je_auto_control.wrapper.auto_control_mouse import (
    click_mouse, get_mouse_position, mouse_scroll,
    mouse_keys_table, special_mouse_keys_table,
)


def _t(key: str) -> str:
    return language_wrapper.language_word_dict.get(key, key)


class AutoClickTabMixin:
    """
    Mixin that provides the auto-click tab UI and handlers.
    Requires the host widget to expose `self.timer`, `self.repeat_count`,
    `self.repeat_max` attributes set in its __init__.
    """

    def _build_auto_click_tab(self) -> QWidget:
        tab = QWidget()
        outer = QVBoxLayout()

        click_group = QGroupBox(_t("tab_auto_click"))
        grid = QGridLayout()
        row = 0

        grid.addWidget(QLabel(_t("input_method")), row, 0)
        self.mouse_radio = QRadioButton(_t("mouse_radio"))
        self.keyboard_radio = QRadioButton(_t("keyboard_radio"))
        self.mouse_radio.setChecked(True)
        self._input_group = QButtonGroup()
        self._input_group.addButton(self.mouse_radio)
        self._input_group.addButton(self.keyboard_radio)
        h = QHBoxLayout()
        h.addWidget(self.mouse_radio)
        h.addWidget(self.keyboard_radio)
        grid.addLayout(h, row, 1)

        row += 1
        grid.addWidget(QLabel(_t("interval_time")), row, 0)
        self.interval_input = QLineEdit("1000")
        self.interval_input.setValidator(QIntValidator(1, 999999999))
        grid.addWidget(self.interval_input, row, 1)

        row += 1
        grid.addWidget(QLabel(_t("cursor_x")), row, 0)
        self.cursor_x_input = QLineEdit()
        self.cursor_x_input.setValidator(QIntValidator())
        grid.addWidget(self.cursor_x_input, row, 1)

        row += 1
        grid.addWidget(QLabel(_t("cursor_y")), row, 0)
        self.cursor_y_input = QLineEdit()
        self.cursor_y_input.setValidator(QIntValidator())
        grid.addWidget(self.cursor_y_input, row, 1)

        row += 1
        grid.addWidget(QLabel(_t("mouse_button")), row, 0)
        self.mouse_button_combo = QComboBox()
        self.mouse_button_combo.addItems(
            list(mouse_keys_table.keys()) if isinstance(mouse_keys_table, dict) else list(mouse_keys_table)
        )
        grid.addWidget(self.mouse_button_combo, row, 1)

        row += 1
        grid.addWidget(QLabel(_t("keyboard_button")), row, 0)
        self.keyboard_button_combo = QComboBox()
        self.keyboard_button_combo.addItems(list(get_keyboard_keys_table().keys()))
        grid.addWidget(self.keyboard_button_combo, row, 1)

        row += 1
        grid.addWidget(QLabel(_t("click_type")), row, 0)
        self.click_type_combo = QComboBox()
        self.click_type_combo.addItems([_t("single_click"), _t("double_click")])
        grid.addWidget(self.click_type_combo, row, 1)

        row += 1
        self.repeat_until_stopped = QRadioButton(_t("repeat_until_stopped_radio"))
        self.repeat_count_times = QRadioButton(_t("repeat_radio"))
        self.repeat_count_input = QLineEdit()
        self.repeat_count_input.setValidator(QIntValidator(1, 999999999))
        self.repeat_count_input.setPlaceholderText(_t("times"))
        rg = QButtonGroup(tab)
        rg.addButton(self.repeat_until_stopped)
        rg.addButton(self.repeat_count_times)
        self.repeat_until_stopped.setChecked(True)
        rh = QHBoxLayout()
        rh.addWidget(self.repeat_until_stopped)
        rh.addWidget(self.repeat_count_times)
        rh.addWidget(self.repeat_count_input)
        grid.addLayout(rh, row, 0, 1, 2)

        row += 1
        btn_h = QHBoxLayout()
        self.start_button = QPushButton(_t("start"))
        self.start_button.clicked.connect(self._start_auto_click)
        self.stop_button = QPushButton(_t("stop"))
        self.stop_button.clicked.connect(self._stop_auto_click)
        btn_h.addWidget(self.start_button)
        btn_h.addWidget(self.stop_button)
        grid.addLayout(btn_h, row, 0, 1, 2)

        click_group.setLayout(grid)
        outer.addWidget(click_group)

        pos_group = QGroupBox(_t("get_position"))
        pos_layout = QHBoxLayout()
        self.pos_btn = QPushButton(_t("get_position"))
        self.pos_btn.clicked.connect(self._get_mouse_pos)
        self.pos_label = QLabel(_t("current_position") + " --")
        pos_layout.addWidget(self.pos_btn)
        pos_layout.addWidget(self.pos_label)
        pos_group.setLayout(pos_layout)
        outer.addWidget(pos_group)

        hotkey_group = QGroupBox(_t("hotkey_label"))
        hk_layout = QHBoxLayout()
        self.hotkey_input = QLineEdit()
        self.hotkey_input.setPlaceholderText("ctrl,a")
        self.hotkey_btn = QPushButton(_t("hotkey_send"))
        self.hotkey_btn.clicked.connect(self._send_hotkey)
        hk_layout.addWidget(self.hotkey_input)
        hk_layout.addWidget(self.hotkey_btn)
        hotkey_group.setLayout(hk_layout)
        outer.addWidget(hotkey_group)

        write_group = QGroupBox(_t("write_label"))
        wr_layout = QHBoxLayout()
        self.write_input = QLineEdit()
        self.write_btn = QPushButton(_t("write_send"))
        self.write_btn.clicked.connect(self._send_write)
        wr_layout.addWidget(self.write_input)
        wr_layout.addWidget(self.write_btn)
        write_group.setLayout(wr_layout)
        outer.addWidget(write_group)

        scroll_group = QGroupBox(_t("mouse_scroll_label"))
        sc_layout = QHBoxLayout()
        self.scroll_value_input = QLineEdit("3")
        self.scroll_value_input.setValidator(QIntValidator())
        sc_layout.addWidget(QLabel(_t("mouse_scroll_label")))
        sc_layout.addWidget(self.scroll_value_input)
        if special_mouse_keys_table:
            self.scroll_dir_combo = QComboBox()
            self.scroll_dir_combo.addItems(list(special_mouse_keys_table.keys()))
            sc_layout.addWidget(self.scroll_dir_combo)
        else:
            self.scroll_dir_combo = None
        self.scroll_btn = QPushButton(_t("scroll_send"))
        self.scroll_btn.clicked.connect(self._send_scroll)
        sc_layout.addWidget(self.scroll_btn)
        scroll_group.setLayout(sc_layout)
        outer.addWidget(scroll_group)

        outer.addStretch()

        self.mouse_radio.toggled.connect(self._update_click_mode)
        self._update_click_mode()

        tab.setLayout(outer)
        return tab

    def _update_click_mode(self):
        use_mouse = self.mouse_radio.isChecked()
        self.cursor_x_input.setEnabled(use_mouse)
        self.cursor_y_input.setEnabled(use_mouse)
        self.mouse_button_combo.setEnabled(use_mouse)
        self.keyboard_button_combo.setEnabled(not use_mouse)

    def _start_auto_click(self):
        try:
            interval = int(self.interval_input.text())
        except ValueError:
            QMessageBox.warning(self, "Warning", "Interval must be a number")
            return
        self.repeat_count = 0
        try:
            self.repeat_max = int(self.repeat_count_input.text())
        except ValueError:
            self.repeat_max = 0
        self.timer.setInterval(interval)
        try:
            self.timer.timeout.disconnect(self._timer_tick)
        except RuntimeError:
            pass
        self.timer.timeout.connect(self._timer_tick)
        self.timer.start()

    def _stop_auto_click(self):
        self.timer.stop()

    def _timer_tick(self):
        if self.repeat_until_stopped.isChecked():
            self._do_click()
        elif self.repeat_count_times.isChecked():
            self.repeat_count += 1
            if self.repeat_count <= self.repeat_max:
                self._do_click()
            else:
                self.repeat_count = 0
                self.timer.stop()

    def _do_click(self):
        try:
            is_double = self.click_type_combo.currentIndex() == 1
            if self.mouse_radio.isChecked():
                btn = self.mouse_button_combo.currentText()
                x = int(self.cursor_x_input.text() or "0")
                y = int(self.cursor_y_input.text() or "0")
                click_mouse(btn, x, y)
                if is_double:
                    click_mouse(btn, x, y)
            else:
                key = self.keyboard_button_combo.currentText()
                type_keyboard(key)
                if is_double:
                    type_keyboard(key)
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            self.timer.stop()
            QMessageBox.warning(self, "Error", str(error))

    def _get_mouse_pos(self):
        try:
            x, y = get_mouse_position()
            self.pos_label.setText(_t("current_position") + f" ({x}, {y})")
            self.cursor_x_input.setText(str(x))
            self.cursor_y_input.setText(str(y))
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            QMessageBox.warning(self, "Error", str(error))

    def _send_hotkey(self):
        try:
            keys = [k.strip() for k in self.hotkey_input.text().split(",") if k.strip()]
            if keys:
                hotkey(keys)
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            QMessageBox.warning(self, "Error", str(error))

    def _send_write(self):
        try:
            text = self.write_input.text()
            if text:
                write(text)
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            QMessageBox.warning(self, "Error", str(error))

    def _send_scroll(self):
        try:
            val = int(self.scroll_value_input.text() or "3")
            direction = self.scroll_dir_combo.currentText() if self.scroll_dir_combo else "scroll_down"
            mouse_scroll(val, scroll_direction=direction)
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            QMessageBox.warning(self, "Error", str(error))
