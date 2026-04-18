import json

from PySide6.QtCore import QTimer, Signal, QObject
from PySide6.QtGui import QIntValidator, QDoubleValidator, QKeyEvent, Qt
from PySide6.QtWidgets import (
    QWidget, QLineEdit, QComboBox, QPushButton, QVBoxLayout, QLabel,
    QGridLayout, QHBoxLayout, QRadioButton, QButtonGroup, QMessageBox,
    QTabWidget, QTextEdit, QFileDialog, QCheckBox, QGroupBox
)

from je_auto_control.gui._auto_click_tab import AutoClickTabMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.wrapper.auto_control_screen import screen_size, screenshot, get_pixel
from je_auto_control.wrapper.auto_control_image import locate_all_image, locate_image_center, locate_and_click
from je_auto_control.wrapper.auto_control_record import record, stop_record
from je_auto_control.utils.executor.action_executor import execute_action, execute_files
from je_auto_control.utils.json.json_file import read_action_json, write_action_json
from je_auto_control.utils.file_process.get_dir_file_list import get_dir_files_as_list
from je_auto_control.utils.cv2_utils.screen_record import ScreenRecorder
from je_auto_control.utils.shell_process.shell_exec import ShellManager
from je_auto_control.utils.start_exe.start_another_process import start_exe
from je_auto_control.utils.generate_report.generate_html_report import generate_html_report
from je_auto_control.utils.generate_report.generate_json_report import generate_json_report
from je_auto_control.utils.generate_report.generate_xml_report import generate_xml_report
from je_auto_control.utils.test_record.record_test_class import test_record_instance


def _t(key: str) -> str:
    """language_wrapper shorthand"""
    return language_wrapper.language_word_dict.get(key, key)


class _WorkerSignals(QObject):
    finished = Signal(str)
    error = Signal(str)


# =============================================================================
# Main Widget
# =============================================================================
class AutoControlGUIWidget(AutoClickTabMixin, QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout()

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_auto_click_tab(), _t("tab_auto_click"))
        self.tabs.addTab(self._build_screenshot_tab(), _t("tab_screenshot"))
        self.tabs.addTab(self._build_image_detect_tab(), _t("tab_image_detect"))
        self.tabs.addTab(self._build_record_tab(), _t("tab_record"))
        self.tabs.addTab(self._build_script_tab(), _t("tab_script"))
        self.tabs.addTab(self._build_screen_record_tab(), _t("tab_screen_record"))
        self.tabs.addTab(self._build_shell_tab(), _t("tab_shell"))
        self.tabs.addTab(self._build_report_tab(), _t("tab_report"))
        layout.addWidget(self.tabs)

        self.setLayout(layout)

        # shared state
        self.timer = QTimer()
        self.repeat_count = 0
        self.repeat_max = 0
        self.screen_recorder = ScreenRecorder()
        self._record_data = []

    # =========================================================================
    # Tab 1: Auto Click
    # =========================================================================
    def _build_auto_click_tab(self) -> QWidget:
        tab = QWidget()
        outer = QVBoxLayout()

        # --- Mouse / Keyboard click group ---
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
        self.mouse_button_combo.addItems(list(mouse_keys_table.keys()) if isinstance(mouse_keys_table, dict) else list(mouse_keys_table))
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

        # --- Mouse position ---
        pos_group = QGroupBox(_t("get_position"))
        pos_layout = QHBoxLayout()
        self.pos_btn = QPushButton(_t("get_position"))
        self.pos_btn.clicked.connect(self._get_mouse_pos)
        self.pos_label = QLabel(_t("current_position") + " --")
        pos_layout.addWidget(self.pos_btn)
        pos_layout.addWidget(self.pos_label)
        pos_group.setLayout(pos_layout)
        outer.addWidget(pos_group)

        # --- Hotkey ---
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

        # --- Write text ---
        write_group = QGroupBox(_t("write_label"))
        wr_layout = QHBoxLayout()
        self.write_input = QLineEdit()
        self.write_btn = QPushButton(_t("write_send"))
        self.write_btn.clicked.connect(self._send_write)
        wr_layout.addWidget(self.write_input)
        wr_layout.addWidget(self.write_btn)
        write_group.setLayout(wr_layout)
        outer.addWidget(write_group)

        # --- Scroll ---
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

        # toggle handler
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

    # =========================================================================
    # Tab 2: Screenshot
    # =========================================================================
    def _build_screenshot_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout()

        # Screen size
        size_group = QGroupBox(_t("screen_size_label"))
        sg = QHBoxLayout()
        self.screen_size_label = QLabel("--")
        self.screen_size_btn = QPushButton(_t("get_screen_size"))
        self.screen_size_btn.clicked.connect(self._get_screen_size)
        sg.addWidget(self.screen_size_label)
        sg.addWidget(self.screen_size_btn)
        size_group.setLayout(sg)
        layout.addWidget(size_group)

        # Screenshot
        ss_group = QGroupBox(_t("take_screenshot"))
        ss_grid = QGridLayout()
        ss_grid.addWidget(QLabel(_t("file_path_label")), 0, 0)
        self.ss_path_input = QLineEdit()
        ss_grid.addWidget(self.ss_path_input, 0, 1)
        self.ss_browse_btn = QPushButton(_t("browse"))
        self.ss_browse_btn.clicked.connect(self._browse_ss_path)
        ss_grid.addWidget(self.ss_browse_btn, 0, 2)

        ss_grid.addWidget(QLabel(_t("region_label")), 1, 0)
        self.ss_region_input = QLineEdit()
        self.ss_region_input.setPlaceholderText("0, 0, 800, 600")
        ss_grid.addWidget(self.ss_region_input, 1, 1, 1, 2)

        btn_h = QHBoxLayout()
        self.ss_take_btn = QPushButton(_t("take_screenshot"))
        self.ss_take_btn.clicked.connect(self._take_screenshot)
        btn_h.addWidget(self.ss_take_btn)
        ss_grid.addLayout(btn_h, 2, 0, 1, 3)
        ss_group.setLayout(ss_grid)
        layout.addWidget(ss_group)

        # Get pixel
        px_group = QGroupBox(_t("get_pixel_label"))
        px_grid = QGridLayout()
        px_grid.addWidget(QLabel(_t("pixel_x")), 0, 0)
        self.pixel_x_input = QLineEdit("0")
        self.pixel_x_input.setValidator(QIntValidator())
        px_grid.addWidget(self.pixel_x_input, 0, 1)
        px_grid.addWidget(QLabel(_t("pixel_y")), 0, 2)
        self.pixel_y_input = QLineEdit("0")
        self.pixel_y_input.setValidator(QIntValidator())
        px_grid.addWidget(self.pixel_y_input, 0, 3)
        self.pixel_btn = QPushButton(_t("get_pixel_label"))
        self.pixel_btn.clicked.connect(self._get_pixel_color)
        px_grid.addWidget(self.pixel_btn, 1, 0, 1, 2)
        self.pixel_result_label = QLabel(_t("pixel_result") + " --")
        px_grid.addWidget(self.pixel_result_label, 1, 2, 1, 2)
        px_group.setLayout(px_grid)
        layout.addWidget(px_group)

        self.ss_result_text = QTextEdit()
        self.ss_result_text.setReadOnly(True)
        self.ss_result_text.setMaximumHeight(100)
        layout.addWidget(self.ss_result_text)
        layout.addStretch()
        tab.setLayout(layout)
        return tab

    def _get_screen_size(self):
        try:
            w, h = screen_size()
            self.screen_size_label.setText(f"{w} x {h}")
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            QMessageBox.warning(self, "Error", str(error))

    def _browse_ss_path(self):
        path, _ = QFileDialog.getSaveFileName(self, _t("save_screenshot"), "", "PNG (*.png);;All (*)")
        if path:
            self.ss_path_input.setText(path)

    def _take_screenshot(self):
        try:
            path = self.ss_path_input.text() or None
            region_text = self.ss_region_input.text().strip()
            region = None
            if region_text:
                region = [int(x.strip()) for x in region_text.split(",")]
            screenshot(file_path=path, screen_region=region)
            self.ss_result_text.setText(f"Screenshot saved: {path or '(not saved)'}")
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            self.ss_result_text.setText(f"Error: {error}")

    def _get_pixel_color(self):
        try:
            x = int(self.pixel_x_input.text())
            y = int(self.pixel_y_input.text())
            color = get_pixel(x, y)
            self.pixel_result_label.setText(_t("pixel_result") + f" {color}")
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            self.pixel_result_label.setText(f"Error: {error}")

    # =========================================================================
    # Tab 3: Image Detection
    # =========================================================================
    def _build_image_detect_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout()

        grid = QGridLayout()
        grid.addWidget(QLabel(_t("template_image")), 0, 0)
        self.img_path_input = QLineEdit()
        grid.addWidget(self.img_path_input, 0, 1)
        self.img_browse_btn = QPushButton(_t("browse"))
        self.img_browse_btn.clicked.connect(self._browse_img)
        grid.addWidget(self.img_browse_btn, 0, 2)

        grid.addWidget(QLabel(_t("threshold_label")), 1, 0)
        self.threshold_input = QLineEdit("0.8")
        self.threshold_input.setValidator(QDoubleValidator(0.0, 1.0, 2))
        grid.addWidget(self.threshold_input, 1, 1)
        self.draw_check = QCheckBox(_t("draw_image_check"))
        grid.addWidget(self.draw_check, 1, 2)

        layout.addLayout(grid)

        btn_h = QHBoxLayout()
        self.locate_btn = QPushButton(_t("locate_image"))
        self.locate_btn.clicked.connect(self._locate_image)
        self.locate_all_btn = QPushButton(_t("locate_all"))
        self.locate_all_btn.clicked.connect(self._locate_all)
        self.locate_click_btn = QPushButton(_t("locate_click"))
        self.locate_click_btn.clicked.connect(self._locate_click)
        btn_h.addWidget(self.locate_btn)
        btn_h.addWidget(self.locate_all_btn)
        btn_h.addWidget(self.locate_click_btn)
        layout.addLayout(btn_h)

        layout.addWidget(QLabel(_t("detection_result")))
        self.detect_result_text = QTextEdit()
        self.detect_result_text.setReadOnly(True)
        layout.addWidget(self.detect_result_text)
        tab.setLayout(layout)
        return tab

    def _browse_img(self):
        path, _ = QFileDialog.getOpenFileName(self, _t("template_image"), "", "Images (*.png *.jpg *.bmp);;All (*)")
        if path:
            self.img_path_input.setText(path)

    def _get_detect_params(self):
        path = self.img_path_input.text()
        if not path:
            raise ValueError("Template image path is empty")
        threshold = float(self.threshold_input.text() or "0.8")
        draw = self.draw_check.isChecked()
        return path, threshold, draw

    def _locate_image(self):
        try:
            path, th, draw = self._get_detect_params()
            result = locate_image_center(path, th, draw)
            self.detect_result_text.setText(f"Center: {result}")
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            self.detect_result_text.setText(f"Error: {error}")

    def _locate_all(self):
        try:
            path, th, draw = self._get_detect_params()
            result = locate_all_image(path, th, draw)
            self.detect_result_text.setText(f"Found {len(result)} matches:\n{result}")
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            self.detect_result_text.setText(f"Error: {error}")

    def _locate_click(self):
        try:
            path, th, draw = self._get_detect_params()
            btn = self.mouse_button_combo.currentText() if hasattr(self, "mouse_button_combo") else "mouse_left"
            result = locate_and_click(path, btn, th, draw)
            self.detect_result_text.setText(f"Clicked at: {result}")
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            self.detect_result_text.setText(f"Error: {error}")

    # =========================================================================
    # Tab 4: Record / Playback
    # =========================================================================
    def _build_record_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout()

        self.record_status_label = QLabel(_t("record_status") + " " + _t("record_idle"))
        layout.addWidget(self.record_status_label)

        btn_h = QHBoxLayout()
        self.rec_start_btn = QPushButton(_t("start_record"))
        self.rec_start_btn.clicked.connect(self._start_record)
        self.rec_stop_btn = QPushButton(_t("stop_record"))
        self.rec_stop_btn.clicked.connect(self._stop_record)
        self.rec_play_btn = QPushButton(_t("playback"))
        self.rec_play_btn.clicked.connect(self._playback_record)
        btn_h.addWidget(self.rec_start_btn)
        btn_h.addWidget(self.rec_stop_btn)
        btn_h.addWidget(self.rec_play_btn)
        layout.addLayout(btn_h)

        btn_h2 = QHBoxLayout()
        self.rec_save_btn = QPushButton(_t("save_record"))
        self.rec_save_btn.clicked.connect(self._save_record)
        self.rec_load_btn = QPushButton(_t("load_record"))
        self.rec_load_btn.clicked.connect(self._load_record)
        btn_h2.addWidget(self.rec_save_btn)
        btn_h2.addWidget(self.rec_load_btn)
        layout.addLayout(btn_h2)

        layout.addWidget(QLabel(_t("record_list_label")))
        self.record_list_text = QTextEdit()
        self.record_list_text.setReadOnly(True)
        layout.addWidget(self.record_list_text)
        tab.setLayout(layout)
        return tab

    def _start_record(self):
        try:
            record()
            self.record_status_label.setText(_t("record_status") + " " + _t("record_recording"))
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            QMessageBox.warning(self, "Error", str(error))

    def _stop_record(self):
        try:
            self._record_data = stop_record() or []
            self.record_status_label.setText(_t("record_status") + " " + _t("record_idle"))
            self.record_list_text.setText(json.dumps(self._record_data, indent=2, ensure_ascii=False))
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            QMessageBox.warning(self, "Error", str(error))

    def _playback_record(self):
        try:
            if not self._record_data:
                QMessageBox.warning(self, "Warning", "No recorded data")
                return
            execute_action(self._record_data)
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            QMessageBox.warning(self, "Error", str(error))

    def _save_record(self):
        try:
            if not self._record_data:
                QMessageBox.warning(self, "Warning", "No recorded data")
                return
            path, _ = QFileDialog.getSaveFileName(self, _t("save_record"), "", "JSON (*.json)")
            if path:
                write_action_json(path, self._record_data)
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            QMessageBox.warning(self, "Error", str(error))

    def _load_record(self):
        try:
            path, _ = QFileDialog.getOpenFileName(self, _t("load_record"), "", "JSON (*.json)")
            if path:
                self._record_data = read_action_json(path)
                self.record_list_text.setText(json.dumps(self._record_data, indent=2, ensure_ascii=False))
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            QMessageBox.warning(self, "Error", str(error))

    # =========================================================================
    # Tab 5: Script Executor
    # =========================================================================
    def _build_script_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout()

        # Load / execute single file
        file_h = QHBoxLayout()
        self.script_path_input = QLineEdit()
        self.script_browse_btn = QPushButton(_t("load_script"))
        self.script_browse_btn.clicked.connect(self._browse_script)
        self.script_exec_btn = QPushButton(_t("execute_script"))
        self.script_exec_btn.clicked.connect(self._execute_script)
        file_h.addWidget(self.script_path_input)
        file_h.addWidget(self.script_browse_btn)
        file_h.addWidget(self.script_exec_btn)
        layout.addLayout(file_h)

        # Execute directory
        dir_h = QHBoxLayout()
        self.script_dir_input = QLineEdit()
        self.script_dir_browse_btn = QPushButton(_t("execute_dir_label"))
        self.script_dir_browse_btn.clicked.connect(self._browse_script_dir)
        self.script_dir_exec_btn = QPushButton(_t("execute_dir"))
        self.script_dir_exec_btn.clicked.connect(self._execute_dir)
        dir_h.addWidget(self.script_dir_input)
        dir_h.addWidget(self.script_dir_browse_btn)
        dir_h.addWidget(self.script_dir_exec_btn)
        layout.addLayout(dir_h)

        # Manual JSON input
        layout.addWidget(QLabel(_t("script_content")))
        self.script_editor = QTextEdit()
        self.script_editor.setPlaceholderText('[["AC_type_keyboard", {"keycode": "a"}]]')
        layout.addWidget(self.script_editor)

        exec_btn = QPushButton(_t("execute_script"))
        exec_btn.clicked.connect(self._execute_manual_script)
        layout.addWidget(exec_btn)

        layout.addWidget(QLabel(_t("execution_result")))
        self.script_result_text = QTextEdit()
        self.script_result_text.setReadOnly(True)
        layout.addWidget(self.script_result_text)
        tab.setLayout(layout)
        return tab

    def _browse_script(self):
        path, _ = QFileDialog.getOpenFileName(self, _t("load_script"), "", "JSON (*.json)")
        if path:
            self.script_path_input.setText(path)
            try:
                data = read_action_json(path)
                self.script_editor.setText(json.dumps(data, indent=2, ensure_ascii=False))
            except (OSError, ValueError, TypeError, RuntimeError) as error:
                self.script_result_text.setText(f"Error loading: {error}")

    def _execute_script(self):
        try:
            path = self.script_path_input.text()
            if not path:
                return
            data = read_action_json(path)
            result = execute_action(data)
            self.script_result_text.setText(json.dumps(result, indent=2, default=str, ensure_ascii=False))
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            self.script_result_text.setText(f"Error: {error}")

    def _browse_script_dir(self):
        path = QFileDialog.getExistingDirectory(self, _t("execute_dir_label"))
        if path:
            self.script_dir_input.setText(path)

    def _execute_dir(self):
        try:
            path = self.script_dir_input.text()
            if not path:
                return
            files = get_dir_files_as_list(path)
            result = execute_files(files)
            self.script_result_text.setText(json.dumps(result, indent=2, default=str, ensure_ascii=False))
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            self.script_result_text.setText(f"Error: {error}")

    def _execute_manual_script(self):
        try:
            text = self.script_editor.toPlainText().strip()
            if not text:
                return
            data = json.loads(text)
            result = execute_action(data)
            self.script_result_text.setText(json.dumps(result, indent=2, default=str, ensure_ascii=False))
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            self.script_result_text.setText(f"Error: {error}")

    # =========================================================================
    # Tab 6: Screen Recording
    # =========================================================================
    def _build_screen_record_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout()

        grid = QGridLayout()
        row = 0

        grid.addWidget(QLabel(_t("recorder_name")), row, 0)
        self.sr_name_input = QLineEdit("default")
        grid.addWidget(self.sr_name_input, row, 1)

        row += 1
        grid.addWidget(QLabel(_t("output_file")), row, 0)
        self.sr_file_input = QLineEdit("output.avi")
        grid.addWidget(self.sr_file_input, row, 1)
        self.sr_file_browse_btn = QPushButton(_t("browse"))
        self.sr_file_browse_btn.clicked.connect(self._browse_sr_file)
        grid.addWidget(self.sr_file_browse_btn, row, 2)

        row += 1
        grid.addWidget(QLabel(_t("codec_label")), row, 0)
        self.sr_codec_input = QLineEdit("XVID")
        grid.addWidget(self.sr_codec_input, row, 1)

        row += 1
        grid.addWidget(QLabel(_t("fps_label")), row, 0)
        self.sr_fps_input = QLineEdit("30")
        self.sr_fps_input.setValidator(QIntValidator(1, 120))
        grid.addWidget(self.sr_fps_input, row, 1)

        row += 1
        grid.addWidget(QLabel(_t("resolution_label")), row, 0)
        self.sr_res_input = QLineEdit("1920x1080")
        grid.addWidget(self.sr_res_input, row, 1)

        layout.addLayout(grid)

        btn_h = QHBoxLayout()
        self.sr_start_btn = QPushButton(_t("start_screen_record"))
        self.sr_start_btn.clicked.connect(self._start_screen_record)
        self.sr_stop_btn = QPushButton(_t("stop_screen_record"))
        self.sr_stop_btn.clicked.connect(self._stop_screen_record)
        btn_h.addWidget(self.sr_start_btn)
        btn_h.addWidget(self.sr_stop_btn)
        layout.addLayout(btn_h)

        self.sr_status_label = QLabel(_t("screen_record_status") + " " + _t("record_idle"))
        layout.addWidget(self.sr_status_label)

        layout.addStretch()
        tab.setLayout(layout)
        return tab

    def _browse_sr_file(self):
        path, _ = QFileDialog.getSaveFileName(self, _t("output_file"), "", "AVI (*.avi);;MP4 (*.mp4);;All (*)")
        if path:
            self.sr_file_input.setText(path)

    def _start_screen_record(self):
        try:
            name = self.sr_name_input.text() or "default"
            output = self.sr_file_input.text() or "output.avi"
            codec = self.sr_codec_input.text() or "XVID"
            fps = int(self.sr_fps_input.text() or "30")
            res_text = self.sr_res_input.text() or "1920x1080"
            w, h = res_text.lower().split("x")
            resolution = (int(w), int(h))
            self.screen_recorder.start_new_record(name, output, codec, fps, resolution)
            self.sr_status_label.setText(_t("screen_record_status") + " " + _t("record_recording"))
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            QMessageBox.warning(self, "Error", str(error))

    def _stop_screen_record(self):
        try:
            name = self.sr_name_input.text() or "default"
            self.screen_recorder.stop_record(name)
            self.sr_status_label.setText(_t("screen_record_status") + " " + _t("record_idle"))
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            QMessageBox.warning(self, "Error", str(error))

    # =========================================================================
    # Tab 7: Shell Command
    # =========================================================================
    def _build_shell_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout()

        # Shell command
        shell_group = QGroupBox(_t("shell_command_label"))
        sg = QVBoxLayout()
        self.shell_input = QLineEdit()
        self.shell_input.setPlaceholderText("echo hello")
        self.shell_exec_btn = QPushButton(_t("execute_shell"))
        self.shell_exec_btn.clicked.connect(self._execute_shell)
        sh = QHBoxLayout()
        sh.addWidget(self.shell_input)
        sh.addWidget(self.shell_exec_btn)
        sg.addLayout(sh)
        shell_group.setLayout(sg)
        layout.addWidget(shell_group)

        # Start exe
        exe_group = QGroupBox(_t("start_exe_label"))
        eg = QHBoxLayout()
        self.exe_path_input = QLineEdit()
        self.exe_browse_btn = QPushButton(_t("browse"))
        self.exe_browse_btn.clicked.connect(self._browse_exe)
        self.exe_start_btn = QPushButton(_t("start_exe"))
        self.exe_start_btn.clicked.connect(self._start_exe)
        eg.addWidget(self.exe_path_input)
        eg.addWidget(self.exe_browse_btn)
        eg.addWidget(self.exe_start_btn)
        exe_group.setLayout(eg)
        layout.addWidget(exe_group)

        layout.addWidget(QLabel(_t("shell_output")))
        self.shell_output_text = QTextEdit()
        self.shell_output_text.setReadOnly(True)
        layout.addWidget(self.shell_output_text)
        tab.setLayout(layout)
        return tab

    def _execute_shell(self):
        try:
            cmd = self.shell_input.text()
            if not cmd:
                return
            mgr = ShellManager()
            mgr.exec_shell(cmd)
            self.shell_output_text.setText(f"Executed: {cmd}\n(Check console for output)")
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            self.shell_output_text.setText(f"Error: {error}")

    def _browse_exe(self):
        path, _ = QFileDialog.getOpenFileName(self, _t("start_exe_label"), "", "Executable (*.exe);;All (*)")
        if path:
            self.exe_path_input.setText(path)

    def _start_exe(self):
        try:
            path = self.exe_path_input.text()
            if not path:
                return
            start_exe(path)
            self.shell_output_text.setText(f"Started: {path}")
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            self.shell_output_text.setText(f"Error: {error}")

    # =========================================================================
    # Tab 8: Report
    # =========================================================================
    def _build_report_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout()

        # Test record toggle
        tr_group = QGroupBox(_t("test_record_status"))
        tr_h = QHBoxLayout()
        self.tr_enable_btn = QPushButton(_t("enable_test_record"))
        self.tr_enable_btn.clicked.connect(lambda: self._set_test_record(True))
        self.tr_disable_btn = QPushButton(_t("disable_test_record"))
        self.tr_disable_btn.clicked.connect(lambda: self._set_test_record(False))
        self.tr_status_label = QLabel("OFF")
        tr_h.addWidget(self.tr_enable_btn)
        tr_h.addWidget(self.tr_disable_btn)
        tr_h.addWidget(self.tr_status_label)
        tr_group.setLayout(tr_h)
        layout.addWidget(tr_group)

        # Report name
        name_h = QHBoxLayout()
        name_h.addWidget(QLabel(_t("report_name")))
        self.report_name_input = QLineEdit("autocontrol_report")
        name_h.addWidget(self.report_name_input)
        layout.addLayout(name_h)

        # Generate buttons
        btn_h = QHBoxLayout()
        self.html_report_btn = QPushButton(_t("generate_html_report"))
        self.html_report_btn.clicked.connect(self._gen_html)
        self.json_report_btn = QPushButton(_t("generate_json_report"))
        self.json_report_btn.clicked.connect(self._gen_json)
        self.xml_report_btn = QPushButton(_t("generate_xml_report"))
        self.xml_report_btn.clicked.connect(self._gen_xml)
        btn_h.addWidget(self.html_report_btn)
        btn_h.addWidget(self.json_report_btn)
        btn_h.addWidget(self.xml_report_btn)
        layout.addLayout(btn_h)

        layout.addWidget(QLabel(_t("report_result")))
        self.report_result_text = QTextEdit()
        self.report_result_text.setReadOnly(True)
        layout.addWidget(self.report_result_text)
        layout.addStretch()
        tab.setLayout(layout)
        return tab

    def _set_test_record(self, enable: bool):
        test_record_instance.set_record_enable(enable)
        self.tr_status_label.setText("ON" if enable else "OFF")

    def _gen_html(self):
        try:
            name = self.report_name_input.text() or "autocontrol_report"
            generate_html_report(name)
            self.report_result_text.setText(f"HTML report generated: {name}")
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            self.report_result_text.setText(f"Error: {error}")

    def _gen_json(self):
        try:
            name = self.report_name_input.text() or "autocontrol_report"
            generate_json_report(name)
            self.report_result_text.setText(f"JSON report generated: {name}")
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            self.report_result_text.setText(f"Error: {error}")

    def _gen_xml(self):
        try:
            name = self.report_name_input.text() or "autocontrol_report"
            generate_xml_report(name)
            self.report_result_text.setText(f"XML report generated: {name}")
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            self.report_result_text.setText(f"Error: {error}")

    # =========================================================================
    # Global keyboard shortcut: Ctrl+4 to stop
    # =========================================================================
    def keyPressEvent(self, event: QKeyEvent):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_4:
            self._stop_auto_click()
        else:
            super().keyPressEvent(event)
