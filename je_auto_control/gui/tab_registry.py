"""Tab registry: what the workspace can open, and when each tab is built.

Every feature tab is described by a :class:`TabSpec` — key, title key,
category and where its widget class lives — and nothing more is loaded until
the tab is opened. :class:`TabEntry` holds one registered tab and builds the
widget on first access to ``widget``, so the window no longer imports and
constructs some fifty panels (with the timers and helper threads several of
them start) before it can show the three it opens on.
"""
from dataclasses import dataclass, field
from importlib import import_module
from typing import Any, Callable, Optional, Tuple

MenuActions = Tuple[Tuple[str, Callable[[], Any]], ...]
WidgetFactory = Callable[[], Any]


@dataclass(frozen=True)
class TabSpec:
    """A tab the workspace can open; ``module`` is imported on first use."""

    key: str
    title_key: str
    category: str
    module: str = ""
    class_name: str = ""
    default_visible: bool = False


def lazy_factory(module: str, class_name: str) -> WidgetFactory:
    """Return a factory that imports ``module`` and builds ``class_name``."""
    def build() -> Any:
        # reason: both names come from the TAB_SPECS table below, never from user input.
        return getattr(import_module(module), class_name)()  # nosemgrep: python.lang.security.audit.non-literal-import.non-literal-import
    return build


@dataclass
class TabEntry:
    """One registered tab; the widget is built the first time it is needed."""

    key: str
    title_key: str
    factory: WidgetFactory
    category: str = "core"
    default_visible: bool = False
    actions: MenuActions = ()
    on_build: Optional[Callable[[Any], None]] = None
    _widget: Any = field(default=None, repr=False)

    @property
    def built(self) -> bool:
        """Whether the widget exists yet."""
        return self._widget is not None

    @property
    def widget(self) -> Any:
        """The tab's widget, building it on first access."""
        if self._widget is None:
            self._widget = self.factory()
            if self.on_build is not None:
                self.on_build(self._widget)
        return self._widget


_GUI = "je_auto_control.gui"

# Registration order: it is the order of the View > Tabs menu, of the
# navigation panel inside each category, and of the tab bar. A spec without a
# module is one the main widget builds itself (its mixin tabs, and Remote
# Desktop, which needs an optional extra and falls back to a placeholder).
TAB_SPECS: Tuple[TabSpec, ...] = (
    TabSpec("auto_click", "tab_auto_click", "core"),
    TabSpec("screenshot", "tab_screenshot", "core"),
    TabSpec("image_detect", "tab_image_detect", "core"),
    TabSpec("record", "tab_record", "core", default_visible=True),
    TabSpec("script_builder", "tab_script_builder", "core",
            f"{_GUI}.script_builder", "ScriptBuilderTab", default_visible=True),
    TabSpec("flow_editor", "tab_flow_editor", "editing", f"{_GUI}.flow_editor", "FlowEditorTab"),
    TabSpec("script", "tab_script", "editing"),
    TabSpec("recording_editor", "tab_recording_editor", "editing",
            f"{_GUI}.recording_editor_tab", "RecordingEditorTab"),
    TabSpec("variables", "tab_variables", "editing", f"{_GUI}.variables_tab", "VariablesTab"),
    TabSpec("secrets", "tab_secrets", "editing", f"{_GUI}.secrets_tab", "SecretsTab"),
    TabSpec("vlm", "tab_vlm", "detection", f"{_GUI}.vlm_tab", "VLMTab"),
    TabSpec("self_healing", "tab_self_healing", "detection", f"{_GUI}.self_healing_tab", "SelfHealingTab"),
    TabSpec("ocr_reader", "tab_ocr_reader", "detection", f"{_GUI}.ocr_tab", "OCRReaderTab"),
    TabSpec("accessibility", "tab_accessibility", "detection", f"{_GUI}.accessibility_tab", "AccessibilityTab"),
    TabSpec("live_hud", "tab_live_hud", "detection", f"{_GUI}.live_hud_tab", "LiveHUDTab"),
    TabSpec("llm_planner", "tab_llm_planner", "detection", f"{_GUI}.llm_planner_tab", "LLMPlannerTab"),
    TabSpec("computer_use", "tab_computer_use", "detection", f"{_GUI}.computer_use_tab", "ComputerUseTab"),
    TabSpec("scheduler", "tab_scheduler", "automation", f"{_GUI}.scheduler_tab", "SchedulerTab"),
    TabSpec("hotkeys", "tab_hotkeys", "automation", f"{_GUI}.hotkeys_tab", "HotkeysTab"),
    TabSpec("triggers", "tab_triggers", "automation", f"{_GUI}.triggers_tab", "TriggersTab"),
    TabSpec("webhooks", "tab_webhooks", "automation", f"{_GUI}.webhooks_tab", "WebhooksTab"),
    TabSpec("email_triggers", "tab_email_triggers", "automation",
            f"{_GUI}.email_triggers_tab", "EmailTriggersTab"),
    TabSpec("test_suite", "tab_test_suite", "core", f"{_GUI}.test_suite_tab", "TestSuiteTab"),
    TabSpec("assertions", "tab_assertions", "core", f"{_GUI}.assertions_tab", "AssertionsTab"),
    TabSpec("data_source", "tab_data_source", "core", f"{_GUI}.data_source_tab", "DataSourceTab"),
    TabSpec("flakiness", "tab_flakiness", "system", f"{_GUI}.flakiness_tab", "FlakinessTab"),
    TabSpec("a11y_audit", "tab_a11y_audit", "core", f"{_GUI}.a11y_audit_tab", "A11yAuditTab"),
    TabSpec("device_matrix", "tab_device_matrix", "core", f"{_GUI}.device_matrix_tab", "DeviceMatrixTab"),
    TabSpec("media_checks", "tab_media_checks", "core", f"{_GUI}.media_checks_tab", "MediaChecksTab"),
    TabSpec("run_history", "tab_run_history", "automation", f"{_GUI}.run_history_tab", "RunHistoryTab"),
    TabSpec("profiler", "tab_profiler", "automation", f"{_GUI}.profiler_tab", "ProfilerTab"),
    TabSpec("window_manager", "tab_window_manager", "system", f"{_GUI}.window_tab", "WindowManagerTab"),
    TabSpec("plugins", "tab_plugins", "system", f"{_GUI}.plugins_tab", "PluginsTab"),
    TabSpec("webrunner", "tab_webrunner", "automation", f"{_GUI}.webrunner_tab", "WebRunnerTab"),
    TabSpec("dag_runner", "tab_dag_runner", "automation", f"{_GUI}.dag_tab", "DagTab"),
    TabSpec("chatops", "tab_chatops", "automation", f"{_GUI}.chatops_tab", "ChatOpsTab"),
    TabSpec("trace_replay", "tab_trace_replay", "automation", f"{_GUI}.trace_replay_tab", "TraceReplayTab"),
    TabSpec("remote_desktop", "tab_remote_desktop", "system", default_visible=True),
    TabSpec("presence", "tab_presence", "system", f"{_GUI}.presence_tab", "PresenceTab"),
    TabSpec("rest_api", "tab_rest_api", "system", f"{_GUI}.rest_api_tab", "RestApiTab"),
    TabSpec("admin_console", "tab_admin_console", "system", f"{_GUI}.admin_console_tab", "AdminConsoleTab"),
    TabSpec("audit_log", "tab_audit_log", "system", f"{_GUI}.audit_log_tab", "AuditLogTab"),
    TabSpec("inspector", "tab_inspector", "system", f"{_GUI}.inspector_tab", "InspectorTab"),
    TabSpec("usb_devices", "tab_usb_devices", "system", f"{_GUI}.usb_devices_tab", "UsbDevicesTab"),
    TabSpec("usb_browser", "tab_usb_browser", "system", f"{_GUI}.usb_browser_tab", "UsbBrowserTab"),
    TabSpec("usb_share", "tab_usb_share", "system", f"{_GUI}.usb_passthrough_panel", "UsbPassthroughPanel"),
    TabSpec("diagnostics", "tab_diagnostics", "system", f"{_GUI}.diagnostics_tab", "DiagnosticsTab"),
    TabSpec("report", "tab_report", "system"),
)
