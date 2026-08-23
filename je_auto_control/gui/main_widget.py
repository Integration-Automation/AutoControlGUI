import json
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QTimer, Signal, QObject
from PySide6.QtGui import QKeyEvent, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTabWidget,
)

from je_auto_control.gui._auto_click_tab import AutoClickTabMixin
from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui._image_detect_tab import ImageDetectTabMixin
from je_auto_control.gui._record_tab import RecordTabMixin
from je_auto_control.gui._screenshot_tab import ScreenshotTabMixin
from je_auto_control.gui._script_tab import ScriptTabMixin
from je_auto_control.gui.accessibility_tab import AccessibilityTab
from je_auto_control.gui.assertions_tab import AssertionsTab
from je_auto_control.gui.data_source_tab import DataSourceTab
from je_auto_control.gui.flakiness_tab import FlakinessTab
from je_auto_control.gui.test_suite_tab import TestSuiteTab
from je_auto_control.gui.a11y_audit_tab import A11yAuditTab
from je_auto_control.gui.device_matrix_tab import DeviceMatrixTab
from je_auto_control.gui.media_checks_tab import MediaChecksTab
from je_auto_control.gui.computer_use_tab import ComputerUseTab
from je_auto_control.gui.chatops_tab import ChatOpsTab
from je_auto_control.gui.dag_tab import DagTab
from je_auto_control.gui.trace_replay_tab import TraceReplayTab
from je_auto_control.gui._report_tab import ReportTabMixin
from je_auto_control.gui.hotkeys_tab import HotkeysTab
from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.gui.live_hud_tab import LiveHUDTab
from je_auto_control.gui.llm_planner_tab import LLMPlannerTab
from je_auto_control.gui.ocr_tab import OCRReaderTab
from je_auto_control.gui.plugins_tab import PluginsTab
from je_auto_control.gui.presence_tab import PresenceTab
from je_auto_control.gui.profiler_tab import ProfilerTab
from je_auto_control.gui.secrets_tab import SecretsTab
from je_auto_control.gui.admin_console_tab import AdminConsoleTab
from je_auto_control.gui.audit_log_tab import AuditLogTab
from je_auto_control.gui.diagnostics_tab import DiagnosticsTab
from je_auto_control.gui.inspector_tab import InspectorTab
from je_auto_control.gui.recording_editor_tab import RecordingEditorTab
from je_auto_control.gui.usb_browser_tab import UsbBrowserTab
from je_auto_control.gui.usb_devices_tab import UsbDevicesTab
from je_auto_control.gui.usb_passthrough_panel import UsbPassthroughPanel
# Remote desktop relies on the optional `webrtc` extra (aiortc + PyAV).
# Importing it eagerly would break embedders (e.g. PyBreeze) that install
# je_auto_control without the extra; fall back to a placeholder tab that
# tells the user how to enable it.
try:
    from je_auto_control.gui.remote_desktop_tab import RemoteDesktopTab
    _REMOTE_DESKTOP_IMPORT_ERROR: Optional[ImportError] = None
except ImportError as _remote_desktop_error:
    RemoteDesktopTab = None  # type: ignore[assignment,misc]  # reason: name is a class or None
    _REMOTE_DESKTOP_IMPORT_ERROR = _remote_desktop_error
from je_auto_control.gui.rest_api_tab import RestApiTab
from je_auto_control.gui.run_history_tab import RunHistoryTab
from je_auto_control.gui.scheduler_tab import SchedulerTab
from je_auto_control.gui.flow_editor import FlowEditorTab
from je_auto_control.gui.script_builder import ScriptBuilderTab
from je_auto_control.gui.self_healing_tab import SelfHealingTab
from je_auto_control.gui.triggers_tab import TriggersTab
from je_auto_control.gui.webhooks_tab import WebhooksTab
from je_auto_control.gui.email_triggers_tab import EmailTriggersTab
from je_auto_control.gui.variables_tab import VariablesTab
from je_auto_control.gui.vlm_tab import VLMTab
from je_auto_control.gui.webrunner_tab import WebRunnerTab
from je_auto_control.gui.window_tab import WindowManagerTab
from je_auto_control.utils.json.json_file import read_action_json


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
    actions: tuple = ()


# =============================================================================
# Main Widget
# =============================================================================
class AutoControlGUIWidget(
    TranslatableMixin, AutoClickTabMixin, ScreenshotTabMixin,
    ImageDetectTabMixin, RecordTabMixin, ScriptTabMixin, ReportTabMixin,
    QWidget,
):
    """Owns the QTabWidget and exposes show/hide/list APIs for the menu bar."""

    tabs_changed = Signal()
    current_tab_changed = Signal()

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
                      category="core", actions=(
                          ("start", self._start_auto_click),
                          ("stop", self._stop_auto_click),
                          ("get_position", self._get_mouse_pos),
                          ("hotkey_send", self._send_hotkey),
                          ("write_send", self._send_write),
                          ("scroll_send", self._send_scroll),
                      ))
        self._add_tab("screenshot", "tab_screenshot", self._build_screenshot_tab(),
                      category="core", actions=(
                          ("take_screenshot", self._take_screenshot),
                          ("browse", self._browse_ss_path),
                          ("pick_region", self._pick_ss_region),
                          ("get_screen_size", self._get_screen_size),
                          ("get_pixel_label", self._get_pixel_color),
                      ))
        self._add_tab("image_detect", "tab_image_detect", self._build_image_detect_tab(),
                      category="core", actions=(
                          ("browse", self._browse_img),
                          ("crop_template", self._crop_template),
                          ("locate_image", self._locate_image),
                          ("locate_all", self._locate_all),
                          ("locate_click", self._locate_click),
                      ))
        self._add_tab("record", "tab_record", self._build_record_tab(),
                      category="core", default_visible=True, actions=(
                          ("start_record", self._start_record),
                          ("stop_record", self._stop_record),
                          ("playback", self._playback_record),
                          ("save_record", self._save_record),
                          ("load_record", self._load_record),
                      ))
        self._add_tab("script_builder", "tab_script_builder", ScriptBuilderTab(),
                      category="core", default_visible=True)
        self._add_tab("flow_editor", "tab_flow_editor", FlowEditorTab(),
                      category="editing")
        self._add_tab("script", "tab_script", self._build_script_tab(),
                      category="editing", actions=(
                          ("load_script", self._browse_script),
                          ("execute_script", self._execute_script),
                          ("menu_choose_script_dir", self._browse_script_dir),
                          ("execute_dir", self._execute_dir),
                          ("execute_editor_script", self._execute_manual_script),
                      ))
        self._add_tab("recording_editor", "tab_recording_editor", RecordingEditorTab(),
                      category="editing")
        self._add_tab("variables", "tab_variables", VariablesTab(),
                      category="editing")
        self._add_tab("secrets", "tab_secrets", SecretsTab(),
                      category="editing")
        self._add_tab("vlm", "tab_vlm", VLMTab(),
                      category="detection")
        self._add_tab("self_healing", "tab_self_healing", SelfHealingTab(),
                      category="detection")
        self._add_tab("ocr_reader", "tab_ocr_reader", OCRReaderTab(),
                      category="detection")
        self._add_tab("accessibility", "tab_accessibility", AccessibilityTab(),
                      category="detection")
        self._add_tab("live_hud", "tab_live_hud", LiveHUDTab(),
                      category="detection")
        self._add_tab("llm_planner", "tab_llm_planner", LLMPlannerTab(),
                      category="detection")
        self._add_tab("computer_use", "tab_computer_use", ComputerUseTab(),
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
        self._add_tab("test_suite", "tab_test_suite", TestSuiteTab(),
                      category="core")
        self._add_tab("assertions", "tab_assertions", AssertionsTab(),
                      category="core")
        self._add_tab("data_source", "tab_data_source", DataSourceTab(),
                      category="core")
        self._add_tab("flakiness", "tab_flakiness", FlakinessTab(),
                      category="system")
        self._add_tab("a11y_audit", "tab_a11y_audit", A11yAuditTab(),
                      category="core")
        self._add_tab("device_matrix", "tab_device_matrix", DeviceMatrixTab(),
                      category="core")
        self._add_tab("media_checks", "tab_media_checks", MediaChecksTab(),
                      category="core")
        self._add_tab("run_history", "tab_run_history", RunHistoryTab(),
                      category="automation")
        self._add_tab("profiler", "tab_profiler", ProfilerTab(),
                      category="automation")
        self._add_tab("window_manager", "tab_window_manager", WindowManagerTab(),
                      category="system")
        self._add_tab("plugins", "tab_plugins", PluginsTab(),
                      category="system")
        self._add_tab("webrunner", "tab_webrunner", WebRunnerTab(),
                      category="automation")
        self._add_tab("dag_runner", "tab_dag_runner", DagTab(),
                      category="automation")
        self._add_tab("chatops", "tab_chatops", ChatOpsTab(),
                      category="automation")
        self._add_tab("trace_replay", "tab_trace_replay", TraceReplayTab(),
                      category="automation")
        self._add_tab(
            "remote_desktop", "tab_remote_desktop",
            self._build_remote_desktop_tab(),
            category="system", default_visible=True,
        )
        self._add_tab("presence", "tab_presence", PresenceTab(),
                      category="system")
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
        self._add_tab("usb_share", "tab_usb_share", UsbPassthroughPanel(),
                      category="system")
        self._add_tab("diagnostics", "tab_diagnostics", DiagnosticsTab(),
                      category="system")
        self._add_tab("report", "tab_report", self._build_report_tab(),
                      category="system", actions=(
                          ("enable_test_record", self._enable_test_record),
                          ("disable_test_record", self._disable_test_record),
                          ("generate_html_report", self._gen_html),
                          ("generate_json_report", self._gen_json),
                          ("generate_xml_report", self._gen_xml),
                      ))
        layout.addWidget(self.tabs)

        self.setLayout(layout)

        self.tabs.currentChanged.connect(self._on_current_tab_changed)

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
            actions: tuple = (),
    ) -> None:
        self._tab_entries.append(_TabEntry(
            key=key, title_key=title_key, widget=widget,
            category=category, default_visible=default_visible,
            actions=actions,
        ))
        if default_visible:
            self.tabs.addTab(widget, language_wrapper.translate(title_key, title_key))

    def _on_current_tab_changed(self, _index: int) -> None:
        self.current_tab_changed.emit()

    def current_tab_menu_actions(self) -> list:
        """Return ``[(label_key, callable), ...]`` for the active tab.

        Core tabs declare their actions at registration time; feature tabs
        may instead expose a ``menu_actions()`` method returning the same
        shape. The menu bar renders these under the Actions menu so tabs
        stay button-free.
        """
        widget = self.tabs.currentWidget()
        if widget is None:
            return []
        for entry in self._tab_entries:
            if entry.widget is widget:
                if entry.actions:
                    return list(entry.actions)
                provider = getattr(widget, "menu_actions", None)
                if callable(provider):
                    return list(provider())
                return []
        return []

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
    # Global keyboard shortcut: Ctrl+4 to stop
    # =========================================================================
    def keyPressEvent(self, event: QKeyEvent):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_4:
            self._stop_auto_click()
        else:
            super().keyPressEvent(event)
