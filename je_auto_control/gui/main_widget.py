import json
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QTimer, Signal, QObject
from PySide6.QtGui import QIntValidator, QDoubleValidator, QKeyEvent, Qt
from PySide6.QtWidgets import (
    QWidget, QLineEdit, QPushButton, QVBoxLayout, QLabel,
    QGridLayout, QHBoxLayout, QMessageBox,
    QTabWidget, QTextEdit, QFileDialog, QCheckBox, QGroupBox
)

from je_auto_control.gui._auto_click_tab import AutoClickTabMixin
from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.accessibility_tab import AccessibilityTab
from je_auto_control.gui._report_tab import ReportTabMixin
from je_auto_control.gui.hotkeys_tab import HotkeysTab
from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.gui.live_hud_tab import LiveHUDTab
from je_auto_control.gui.llm_planner_tab import LLMPlannerTab
from je_auto_control.gui.ocr_tab import OCRReaderTab
from je_auto_control.gui.plugins_tab import PluginsTab
from je_auto_control.gui.profiler_tab import ProfilerTab
from je_auto_control.gui.secrets_tab import SecretsTab
from je_auto_control.gui.admin_console_tab import AdminConsoleTab
from je_auto_control.gui.audit_log_tab import AuditLogTab
from je_auto_control.gui.diagnostics_tab import DiagnosticsTab
from je_auto_control.gui.inspector_tab import InspectorTab
from je_auto_control.gui.recording_editor_tab import RecordingEditorTab
from je_auto_control.gui.usb_browser_tab import UsbBrowserTab
from je_auto_control.gui.usb_devices_tab import UsbDevicesTab
# Remote desktop relies on the optional `webrtc` extra (aiortc + PyAV).
# Importing it eagerly would break embedders (e.g. PyBreeze) that install
# je_auto_control without the extra; fall back to a placeholder tab that
# tells the user how to enable it.
try:
    from je_auto_control.gui.remote_desktop_tab import RemoteDesktopTab
    _REMOTE_DESKTOP_IMPORT_ERROR: Optional[ImportError] = None
except ImportError as _remote_desktop_error:
    RemoteDesktopTab = None  # type: ignore[assignment]
    _REMOTE_DESKTOP_IMPORT_ERROR = _remote_desktop_error
from je_auto_control.gui.rest_api_tab import RestApiTab
from je_auto_control.gui.run_history_tab import RunHistoryTab
from je_auto_control.gui.scheduler_tab import SchedulerTab
from je_auto_control.gui.script_builder import ScriptBuilderTab
from je_auto_control.gui.selector import crop_template_to_file, open_region_selector
from je_auto_control.gui.triggers_tab import TriggersTab
from je_auto_control.gui.webhooks_tab import WebhooksTab
from je_auto_control.gui.email_triggers_tab import EmailTriggersTab
from je_auto_control.gui.variables_tab import VariablesTab
from je_auto_control.gui.vlm_tab import VLMTab
from je_auto_control.gui.window_tab import WindowManagerTab
from je_auto_control.wrapper.auto_control_screen import screen_size, screenshot, get_pixel
from je_auto_control.wrapper.auto_control_image import locate_all_image, locate_image_center, locate_and_click
from je_auto_control.wrapper.auto_control_record import record, stop_record
from je_auto_control.utils.executor.action_executor import execute_action, execute_files
from je_auto_control.utils.json.json_file import read_action_json, write_action_json
from je_auto_control.utils.file_process.get_dir_file_list import get_dir_files_as_list


_JSON_FILE_FILTER = "JSON (*.json)"


def _t(key: str) -> str:
    """language_wrapper shorthand"""
    return language_wrapper.translate(key, key)


class _WorkerSignals(QObject):
    finished = Signal(str)
    error = Signal(str)


@dataclass
class _TabEntry:
    key: str
    title_key: str
    widget: QWidget
    category: str = "core"
    default_visible: bool = False


# =============================================================================
# Main Widget
# =============================================================================
class AutoControlGUIWidget(
    TranslatableMixin, AutoClickTabMixin, ReportTabMixin, QWidget,
):
    """Owns the QTabWidget and exposes show/hide/list APIs for the menu bar."""

    tabs_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tr_init()
        layout = QVBoxLayout()

        self._tab_entries: list = []

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self._on_tab_close_requested)

        # Default UI keeps only the last three of the previously-visible
        # tabs (record / script_builder / remote_desktop) so the launcher
        # opens on a focused capture+script+remote workflow. The earlier
        # core tabs (auto_click / screenshot / image_detect) are still
        # registered and reachable from the View menu's "show tab" list.
        self._add_tab("auto_click", "tab_auto_click", self._build_auto_click_tab(),
                      category="core")
        self._add_tab("screenshot", "tab_screenshot", self._build_screenshot_tab(),
                      category="core")
        self._add_tab("image_detect", "tab_image_detect", self._build_image_detect_tab(),
                      category="core")
        self._add_tab("record", "tab_record", self._build_record_tab(),
                      category="core", default_visible=True)
        self._add_tab("script_builder", "tab_script_builder", ScriptBuilderTab(),
                      category="core", default_visible=True)
        self._add_tab("script", "tab_script", self._build_script_tab(),
                      category="editing")
        self._add_tab("recording_editor", "tab_recording_editor", RecordingEditorTab(),
                      category="editing")
        self._add_tab("variables", "tab_variables", VariablesTab(),
                      category="editing")
        self._add_tab("secrets", "tab_secrets", SecretsTab(),
                      category="editing")
        self._add_tab("vlm", "tab_vlm", VLMTab(),
                      category="detection")
        self._add_tab("ocr_reader", "tab_ocr_reader", OCRReaderTab(),
                      category="detection")
        self._add_tab("accessibility", "tab_accessibility", AccessibilityTab(),
                      category="detection")
        self._add_tab("live_hud", "tab_live_hud", LiveHUDTab(),
                      category="detection")
        self._add_tab("llm_planner", "tab_llm_planner", LLMPlannerTab(),
                      category="detection")
        self._add_tab("scheduler", "tab_scheduler", SchedulerTab(),
                      category="automation")
        self._add_tab("hotkeys", "tab_hotkeys", HotkeysTab(),
                      category="automation")
        self._add_tab("triggers", "tab_triggers", TriggersTab(),
                      category="automation")
        self._add_tab("webhooks", "tab_webhooks", WebhooksTab(),
                      category="automation")
        self._add_tab("email_triggers", "tab_email_triggers",
                      EmailTriggersTab(), category="automation")
        self._add_tab("run_history", "tab_run_history", RunHistoryTab(),
                      category="automation")
        self._add_tab("profiler", "tab_profiler", ProfilerTab(),
                      category="automation")
        self._add_tab("window_manager", "tab_window_manager", WindowManagerTab(),
                      category="system")
        self._add_tab("plugins", "tab_plugins", PluginsTab(),
                      category="system")
        self._add_tab(
            "remote_desktop", "tab_remote_desktop",
            self._build_remote_desktop_tab(),
            category="system", default_visible=True,
        )
        self._add_tab("rest_api", "tab_rest_api", RestApiTab(),
                      category="system")
        self._add_tab("admin_console", "tab_admin_console", AdminConsoleTab(),
                      category="system")
        self._add_tab("audit_log", "tab_audit_log", AuditLogTab(),
                      category="system")
        self._add_tab("inspector", "tab_inspector", InspectorTab(),
                      category="system")
        self._add_tab("usb_devices", "tab_usb_devices", UsbDevicesTab(),
                      category="system")
        self._add_tab("usb_browser", "tab_usb_browser", UsbBrowserTab(),
                      category="system")
        self._add_tab("diagnostics", "tab_diagnostics", DiagnosticsTab(),
                      category="system")
        self._add_tab("report", "tab_report", self._build_report_tab(),
                      category="system")
        layout.addWidget(self.tabs)

        self.setLayout(layout)

        self.timer = QTimer()
        self.repeat_count = 0
        self.repeat_max = 0
        self._record_data = []

    @staticmethod
    def _build_remote_desktop_tab() -> QWidget:
        """Return the real remote-desktop tab, or a placeholder if the
        ``webrtc`` extra is not installed."""
        if RemoteDesktopTab is not None:
            return RemoteDesktopTab()
        placeholder = QWidget()
        layout = QVBoxLayout(placeholder)
        message = QLabel(
            "Remote Desktop is unavailable: the optional 'webrtc' extra "
            "(aiortc + PyAV) is not installed.\n\n"
            "Install with:\n    pip install je_auto_control[webrtc]\n\n"
            f"Underlying error: {_REMOTE_DESKTOP_IMPORT_ERROR!r}",
        )
        message.setWordWrap(True)
        message.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(message)
        layout.addStretch()
        return placeholder

    # --- tab registry API ----------------------------------------------------

    def _add_tab(
            self, key: str, title_key: str, widget: QWidget,
            category: str = "core", default_visible: bool = False,
    ) -> None:
        self._tab_entries.append(_TabEntry(
            key=key, title_key=title_key, widget=widget,
            category=category, default_visible=default_visible,
        ))
        if default_visible:
            self.tabs.addTab(widget, language_wrapper.translate(title_key, title_key))

    def _find_entry(self, key: str):
        for entry in self._tab_entries:
            if entry.key == key:
                return entry
        return None

    def list_registered_tabs(self) -> list:
        """Return metadata for the View → Tabs menu."""
        return [
            {
                "key": entry.key,
                "title": language_wrapper.translate(entry.title_key, entry.title_key),
                "visible": self.tabs.indexOf(entry.widget) != -1,
                "category": entry.category,
            }
            for entry in self._tab_entries
        ]

    def show_tab(self, key: str) -> None:
        entry = self._find_entry(key)
        if entry is None or self.tabs.indexOf(entry.widget) != -1:
            return
        target_index = 0
        for candidate in self._tab_entries:
            if candidate.key == key:
                break
            if self.tabs.indexOf(candidate.widget) != -1:
                target_index += 1
        title = language_wrapper.translate(entry.title_key, entry.title_key)
        self.tabs.insertTab(target_index, entry.widget, title)
        self.tabs.setCurrentWidget(entry.widget)
        self.tabs_changed.emit()

    def hide_tab(self, key: str) -> None:
        entry = self._find_entry(key)
        if entry is None:
            return
        index = self.tabs.indexOf(entry.widget)
        if index != -1:
            self.tabs.removeTab(index)
            self.tabs_changed.emit()

    def _on_tab_close_requested(self, index: int) -> None:
        widget = self.tabs.widget(index)
        for entry in self._tab_entries:
            if entry.widget is widget:
                self.hide_tab(entry.key)
                return

    def _translate(self, key: str) -> str:
        return language_wrapper.translate(key, key)

    def retranslate(self) -> None:
        """Relabel tab titles and propagate into every child tab."""
        for entry in self._tab_entries:
            index = self.tabs.indexOf(entry.widget)
            if index != -1:
                self.tabs.setTabText(
                    index, language_wrapper.translate(entry.title_key, entry.title_key),
                )
        # Widgets registered via TranslatableMixin on this widget (screenshot,
        # image-detect, record, script, screen-record, shell, report tabs).
        TranslatableMixin.retranslate(self)
        if hasattr(self, "_auto_click_retranslate"):
            self._auto_click_retranslate()
        if hasattr(self, "_screenshot_retranslate"):
            self._screenshot_retranslate()
        if hasattr(self, "_record_retranslate"):
            self._record_retranslate()
        # Child class tabs get their own retranslate if they implement one.
        for entry in self._tab_entries:
            callback = getattr(entry.widget, "retranslate", None)
            if callable(callback) and entry.widget is not self:
                try:
                    callback()
                except (RuntimeError, AttributeError):
                    continue

    def open_script_file(self, path: str) -> None:
        """Load a JSON script into the Script Executor tab and focus it."""
        entry = self._find_entry("script")
        if entry is not None and self.tabs.indexOf(entry.widget) == -1:
            self.show_tab("script")
        self.script_path_input.setText(path)
        try:
            data = read_action_json(path)
            self.script_editor.setText(json.dumps(data, indent=2, ensure_ascii=False))
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            self.script_result_text.setText(f"Error loading: {error}")
            return
        if entry is not None:
            self.tabs.setCurrentWidget(entry.widget)

    # =========================================================================
    # Tab 2: Screenshot
    # =========================================================================
    def _build_screenshot_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout()

        # Screen size
        size_group = self._tr(QGroupBox(), "screen_size_label")
        sg = QHBoxLayout()
        self.screen_size_label = QLabel("--")
        self.screen_size_btn = self._tr(QPushButton(), "get_screen_size")
        self.screen_size_btn.clicked.connect(self._get_screen_size)
        sg.addWidget(self.screen_size_label)
        sg.addWidget(self.screen_size_btn)
        size_group.setLayout(sg)
        layout.addWidget(size_group)

        # Screenshot
        ss_group = self._tr(QGroupBox(), "take_screenshot")
        ss_grid = QGridLayout()
        ss_grid.addWidget(self._tr(QLabel(), "file_path_label"), 0, 0)
        self.ss_path_input = QLineEdit()
        ss_grid.addWidget(self.ss_path_input, 0, 1)
        self.ss_browse_btn = self._tr(QPushButton(), "browse")
        self.ss_browse_btn.clicked.connect(self._browse_ss_path)
        ss_grid.addWidget(self.ss_browse_btn, 0, 2)

        ss_grid.addWidget(self._tr(QLabel(), "region_label"), 1, 0)
        self.ss_region_input = QLineEdit()
        self.ss_region_input.setPlaceholderText("0, 0, 800, 600")
        ss_grid.addWidget(self.ss_region_input, 1, 1)
        self.ss_pick_region_btn = self._tr(QPushButton(), "pick_region")
        self.ss_pick_region_btn.clicked.connect(self._pick_ss_region)
        ss_grid.addWidget(self.ss_pick_region_btn, 1, 2)

        btn_h = QHBoxLayout()
        self.ss_take_btn = self._tr(QPushButton(), "take_screenshot")
        self.ss_take_btn.clicked.connect(self._take_screenshot)
        btn_h.addWidget(self.ss_take_btn)
        ss_grid.addLayout(btn_h, 2, 0, 1, 3)
        ss_group.setLayout(ss_grid)
        layout.addWidget(ss_group)

        # Get pixel
        px_group = self._tr(QGroupBox(), "get_pixel_label")
        px_grid = QGridLayout()
        px_grid.addWidget(self._tr(QLabel(), "pixel_x"), 0, 0)
        self.pixel_x_input = QLineEdit("0")
        self.pixel_x_input.setValidator(QIntValidator())
        px_grid.addWidget(self.pixel_x_input, 0, 1)
        px_grid.addWidget(self._tr(QLabel(), "pixel_y"), 0, 2)
        self.pixel_y_input = QLineEdit("0")
        self.pixel_y_input.setValidator(QIntValidator())
        px_grid.addWidget(self.pixel_y_input, 0, 3)
        self.pixel_btn = self._tr(QPushButton(), "get_pixel_label")
        self.pixel_btn.clicked.connect(self._get_pixel_color)
        px_grid.addWidget(self.pixel_btn, 1, 0, 1, 2)
        self.pixel_result_label = QLabel()
        self._pixel_result_suffix = " --"
        self.pixel_result_label.setText(
            self._translate("pixel_result") + self._pixel_result_suffix,
        )
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

    def _pick_ss_region(self):
        region = open_region_selector(self)
        if region is None:
            return
        x, y, w, h = region
        self.ss_region_input.setText(f"{x}, {y}, {x + w}, {y + h}")

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
            self._pixel_result_suffix = f" {color}"
            self.pixel_result_label.setText(
                self._translate("pixel_result") + self._pixel_result_suffix,
            )
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            self.pixel_result_label.setText(f"Error: {error}")

    def _screenshot_retranslate(self) -> None:
        if hasattr(self, "pixel_result_label"):
            self.pixel_result_label.setText(
                self._translate("pixel_result") + self._pixel_result_suffix,
            )

    # =========================================================================
    # Tab 3: Image Detection
    # =========================================================================
    def _build_image_detect_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout()

        grid = QGridLayout()
        grid.addWidget(self._tr(QLabel(), "template_image"), 0, 0)
        self.img_path_input = QLineEdit()
        grid.addWidget(self.img_path_input, 0, 1)
        self.img_browse_btn = self._tr(QPushButton(), "browse")
        self.img_browse_btn.clicked.connect(self._browse_img)
        grid.addWidget(self.img_browse_btn, 0, 2)
        self.img_crop_btn = self._tr(QPushButton(), "crop_template")
        self.img_crop_btn.clicked.connect(self._crop_template)
        grid.addWidget(self.img_crop_btn, 0, 3)

        grid.addWidget(self._tr(QLabel(), "threshold_label"), 1, 0)
        self.threshold_input = QLineEdit("0.8")
        self.threshold_input.setValidator(QDoubleValidator(0.0, 1.0, 2))
        grid.addWidget(self.threshold_input, 1, 1)
        self.draw_check = self._tr(QCheckBox(), "draw_image_check")
        grid.addWidget(self.draw_check, 1, 2)

        layout.addLayout(grid)

        btn_h = QHBoxLayout()
        self.locate_btn = self._tr(QPushButton(), "locate_image")
        self.locate_btn.clicked.connect(self._locate_image)
        self.locate_all_btn = self._tr(QPushButton(), "locate_all")
        self.locate_all_btn.clicked.connect(self._locate_all)
        self.locate_click_btn = self._tr(QPushButton(), "locate_click")
        self.locate_click_btn.clicked.connect(self._locate_click)
        btn_h.addWidget(self.locate_btn)
        btn_h.addWidget(self.locate_all_btn)
        btn_h.addWidget(self.locate_click_btn)
        layout.addLayout(btn_h)

        layout.addWidget(self._tr(QLabel(), "detection_result"))
        self.detect_result_text = QTextEdit()
        self.detect_result_text.setReadOnly(True)
        layout.addWidget(self.detect_result_text)
        tab.setLayout(layout)
        return tab

    def _browse_img(self):
        path, _ = QFileDialog.getOpenFileName(self, _t("template_image"), "", "Images (*.png *.jpg *.bmp);;All (*)")
        if path:
            self.img_path_input.setText(path)

    def _crop_template(self):
        save_path, _ = QFileDialog.getSaveFileName(
            self, _t("crop_template"), "", "PNG (*.png)"
        )
        if not save_path:
            return
        try:
            region = crop_template_to_file(save_path, self)
            if region is None:
                return
            self.img_path_input.setText(save_path)
            self.detect_result_text.setText(f"Template saved: {save_path} region={region}")
        except (OSError, ValueError, RuntimeError) as error:
            QMessageBox.warning(self, "Error", str(error))

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

        self._record_status_key = "record_idle"
        self.record_status_label = QLabel()
        self._apply_record_status_label()
        layout.addWidget(self.record_status_label)

        btn_h = QHBoxLayout()
        self.rec_start_btn = self._tr(QPushButton(), "start_record")
        self.rec_start_btn.clicked.connect(self._start_record)
        self.rec_stop_btn = self._tr(QPushButton(), "stop_record")
        self.rec_stop_btn.clicked.connect(self._stop_record)
        self.rec_play_btn = self._tr(QPushButton(), "playback")
        self.rec_play_btn.clicked.connect(self._playback_record)
        btn_h.addWidget(self.rec_start_btn)
        btn_h.addWidget(self.rec_stop_btn)
        btn_h.addWidget(self.rec_play_btn)
        layout.addLayout(btn_h)

        btn_h2 = QHBoxLayout()
        self.rec_save_btn = self._tr(QPushButton(), "save_record")
        self.rec_save_btn.clicked.connect(self._save_record)
        self.rec_load_btn = self._tr(QPushButton(), "load_record")
        self.rec_load_btn.clicked.connect(self._load_record)
        btn_h2.addWidget(self.rec_save_btn)
        btn_h2.addWidget(self.rec_load_btn)
        layout.addLayout(btn_h2)

        layout.addWidget(self._tr(QLabel(), "record_list_label"))
        self.record_list_text = QTextEdit()
        self.record_list_text.setReadOnly(True)
        layout.addWidget(self.record_list_text)
        tab.setLayout(layout)
        return tab

    def _apply_record_status_label(self) -> None:
        if hasattr(self, "record_status_label"):
            self.record_status_label.setText(
                self._translate("record_status") + " "
                + self._translate(self._record_status_key),
            )

    def _record_retranslate(self) -> None:
        self._apply_record_status_label()

    def _start_record(self):
        try:
            record()
            self._record_status_key = "record_recording"
            self._apply_record_status_label()
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            QMessageBox.warning(self, "Error", str(error))

    def _stop_record(self):
        try:
            self._record_data = stop_record() or []
            self._record_status_key = "record_idle"
            self._apply_record_status_label()
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
            path, _ = QFileDialog.getSaveFileName(self, _t("save_record"), "", _JSON_FILE_FILTER)
            if path:
                write_action_json(path, self._record_data)
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            QMessageBox.warning(self, "Error", str(error))

    def _load_record(self):
        try:
            path, _ = QFileDialog.getOpenFileName(self, _t("load_record"), "", _JSON_FILE_FILTER)
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

        file_h = QHBoxLayout()
        self.script_path_input = QLineEdit()
        self.script_browse_btn = self._tr(QPushButton(), "load_script")
        self.script_browse_btn.clicked.connect(self._browse_script)
        self.script_exec_btn = self._tr(QPushButton(), "execute_script")
        self.script_exec_btn.clicked.connect(self._execute_script)
        file_h.addWidget(self.script_path_input)
        file_h.addWidget(self.script_browse_btn)
        file_h.addWidget(self.script_exec_btn)
        layout.addLayout(file_h)

        dir_h = QHBoxLayout()
        self.script_dir_input = QLineEdit()
        self.script_dir_browse_btn = self._tr(QPushButton(), "execute_dir_label")
        self.script_dir_browse_btn.clicked.connect(self._browse_script_dir)
        self.script_dir_exec_btn = self._tr(QPushButton(), "execute_dir")
        self.script_dir_exec_btn.clicked.connect(self._execute_dir)
        dir_h.addWidget(self.script_dir_input)
        dir_h.addWidget(self.script_dir_browse_btn)
        dir_h.addWidget(self.script_dir_exec_btn)
        layout.addLayout(dir_h)

        layout.addWidget(self._tr(QLabel(), "script_content"))
        self.script_editor = QTextEdit()
        self.script_editor.setPlaceholderText('[["AC_type_keyboard", {"keycode": "a"}]]')
        layout.addWidget(self.script_editor)

        exec_btn = self._tr(QPushButton(), "execute_script")
        exec_btn.clicked.connect(self._execute_manual_script)
        layout.addWidget(exec_btn)

        layout.addWidget(self._tr(QLabel(), "execution_result"))
        self.script_result_text = QTextEdit()
        self.script_result_text.setReadOnly(True)
        layout.addWidget(self.script_result_text)
        tab.setLayout(layout)
        return tab

    def _browse_script(self):
        path, _ = QFileDialog.getOpenFileName(self, _t("load_script"), "", _JSON_FILE_FILTER)
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
    # Global keyboard shortcut: Ctrl+4 to stop
    # =========================================================================
    def keyPressEvent(self, event: QKeyEvent):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_4:
            self._stop_auto_click()
        else:
            super().keyPressEvent(event)
