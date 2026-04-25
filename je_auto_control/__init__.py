"""
import all wrapper function
"""

# callback
from je_auto_control.utils.callback.callback_function_executor import \
    callback_executor
# Critical
from je_auto_control.utils.critical_exit.critical_exit import CriticalExit
from je_auto_control.utils.cv2_utils.screen_record import ScreenRecorder
# utils cv2_utils
from je_auto_control.utils.cv2_utils.screenshot import pil_screenshot
# Recording
from je_auto_control.utils.cv2_utils.video_recording import RecordingThread
from je_auto_control.utils.exception.exceptions import \
    AutoControlActionException
from je_auto_control.utils.exception.exceptions import \
    AutoControlActionNullException
from je_auto_control.utils.exception.exceptions import \
    AutoControlCantFindKeyException
# Exception
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.exception.exceptions import \
    AutoControlJsonActionException
from je_auto_control.utils.exception.exceptions import \
    AutoControlKeyboardException
from je_auto_control.utils.exception.exceptions import \
    AutoControlMouseException
from je_auto_control.utils.exception.exceptions import \
    AutoControlRecordException
from je_auto_control.utils.exception.exceptions import \
    AutoControlScreenException
from je_auto_control.utils.exception.exceptions import ImageNotFoundException
from je_auto_control.utils.executor.action_executor import \
    add_command_to_executor
# executor
from je_auto_control.utils.executor.action_executor import execute_action
from je_auto_control.utils.executor.action_executor import \
    execute_action_with_vars
from je_auto_control.utils.executor.action_executor import execute_files
from je_auto_control.utils.executor.action_executor import executor
# Accessibility (headless)
from je_auto_control.utils.accessibility import (
    AccessibilityElement, AccessibilityNotAvailableError,
    click_accessibility_element, find_accessibility_element,
    list_accessibility_elements,
)
# VLM element locator (headless)
from je_auto_control.utils.vision import (
    VLMNotAvailableError, click_by_description, locate_by_description,
)
# Clipboard (headless)
from je_auto_control.utils.clipboard.clipboard import (
    get_clipboard, set_clipboard,
)
# Hotkey daemon (headless)
from je_auto_control.utils.hotkey.hotkey_daemon import (
    HotkeyBinding, HotkeyDaemon, default_hotkey_daemon,
)
# OCR (headless)
from je_auto_control.utils.ocr.ocr_engine import (
    TextMatch, click_text, find_text_matches, locate_text_center,
    set_tesseract_cmd, wait_for_text,
)
# MCP server (headless stdio bridge for Claude / other MCP clients)
from je_auto_control.utils.mcp_server import (
    MCPContent, MCPResource, MCPServer, MCPTool, MCPToolAnnotations,
    ResourceProvider, build_default_tool_registry,
    default_resource_provider, start_mcp_stdio_server,
)
# Plugin loader (headless)
from je_auto_control.utils.plugin_loader.plugin_loader import (
    discover_plugin_commands, load_plugin_directory, load_plugin_file,
    register_plugin_commands,
)
# REST API (headless)
from je_auto_control.utils.rest_api.rest_server import (
    RestApiServer, start_rest_api_server,
)
# Run history (headless)
from je_auto_control.utils.run_history.history_store import (
    HistoryStore, RunRecord, default_history_store,
)
# Triggers (headless)
from je_auto_control.utils.triggers.trigger_engine import (
    FilePathTrigger, ImageAppearsTrigger, PixelColorTrigger, TriggerEngine,
    WindowAppearsTrigger, default_trigger_engine,
)
# Recording editor (headless helpers)
from je_auto_control.utils.recording_edit.editor import (
    adjust_delays, filter_actions, insert_action, remove_action,
    scale_coordinates, trim_actions,
)
# Scheduler (headless)
from je_auto_control.utils.scheduler.scheduler import (
    ScheduledJob, Scheduler, default_scheduler,
)
# Script variables (headless)
from je_auto_control.utils.script_vars.interpolate import (
    interpolate_actions, interpolate_value, load_vars_from_json,
)
# Watchers (headless)
from je_auto_control.utils.watcher.watcher import (
    LogTail, MouseWatcher, PixelWatcher,
)
# file process
from je_auto_control.utils.file_process.get_dir_file_list import \
    get_dir_files_as_list
# html report
from je_auto_control.utils.generate_report.generate_html_report import \
    generate_html
from je_auto_control.utils.generate_report.generate_html_report import \
    generate_html_report
from je_auto_control.utils.generate_report.generate_json_report import \
    generate_json
from je_auto_control.utils.generate_report.generate_json_report import \
    generate_json_report
# xml
from je_auto_control.utils.generate_report.generate_xml_report import \
    generate_xml
from je_auto_control.utils.generate_report.generate_xml_report import \
    generate_xml_report
# json
from je_auto_control.utils.json.json_file import read_action_json
from je_auto_control.utils.json.json_file import write_action_json
# package manager
from je_auto_control.utils.package_manager.package_manager_class import \
    package_manager
from je_auto_control.utils.project.create_project_structure import \
    create_project_dir
# Shell command
from je_auto_control.utils.shell_process.shell_exec import ShellManager
from je_auto_control.utils.shell_process.shell_exec import default_shell_manager
# socket server
from je_auto_control.utils.socket_server.auto_control_socket_server import \
    start_autocontrol_socket_server
# Start exe
from je_auto_control.utils.start_exe.start_another_process import start_exe
# test record
from je_auto_control.utils.test_record.record_test_class import \
    test_record_instance
# Windows
from je_auto_control.windows.window import windows_window_manage
from je_auto_control.wrapper.auto_control_image import locate_all_image
from je_auto_control.wrapper.auto_control_image import locate_and_click
from je_auto_control.wrapper.auto_control_image import locate_image_center
# Keyboard wrappers
from je_auto_control.wrapper.auto_control_keyboard import check_key_is_press
from je_auto_control.wrapper.auto_control_keyboard import get_keyboard_keys_table
from je_auto_control.wrapper.auto_control_keyboard import hotkey
from je_auto_control.wrapper.auto_control_keyboard import keyboard_keys_table
from je_auto_control.wrapper.auto_control_keyboard import press_keyboard_key
from je_auto_control.wrapper.auto_control_keyboard import release_keyboard_key
from je_auto_control.wrapper.auto_control_keyboard import send_key_event_to_window
from je_auto_control.wrapper.auto_control_keyboard import type_keyboard
from je_auto_control.wrapper.auto_control_keyboard import write
# Mouse wrappers
from je_auto_control.wrapper.auto_control_mouse import click_mouse
from je_auto_control.wrapper.auto_control_mouse import get_mouse_position
from je_auto_control.wrapper.auto_control_mouse import mouse_keys_table
from je_auto_control.wrapper.auto_control_mouse import mouse_scroll
from je_auto_control.wrapper.auto_control_mouse import mouse_scroll_error_message
from je_auto_control.wrapper.auto_control_mouse import press_mouse
from je_auto_control.wrapper.auto_control_mouse import release_mouse
from je_auto_control.wrapper.auto_control_mouse import send_mouse_event_to_window
from je_auto_control.wrapper.auto_control_mouse import set_mouse_position
from je_auto_control.wrapper.auto_control_mouse import special_mouse_keys_table
# record
from je_auto_control.wrapper.auto_control_record import record
from je_auto_control.wrapper.auto_control_record import stop_record
# Screen wrappers
from je_auto_control.wrapper.auto_control_screen import screen_size
from je_auto_control.wrapper.auto_control_screen import screenshot
from je_auto_control.wrapper.auto_control_screen import get_pixel
# Cross-platform window manager (headless)
from je_auto_control.wrapper.auto_control_window import (
    close_window_by_title, find_window, focus_window, list_windows,
    show_window_by_title, wait_for_window,
)


def start_autocontrol_gui(*args, **kwargs):
    """Launch the GUI (imports PySide6 lazily so headless usage stays Qt-free)."""
    from je_auto_control.gui import start_autocontrol_gui as _impl
    return _impl(*args, **kwargs)

__all__ = [
    "click_mouse", "mouse_keys_table", "get_mouse_position", "press_mouse", "release_mouse",
    "mouse_scroll", "mouse_scroll_error_message", "set_mouse_position", "special_mouse_keys_table",
    "keyboard_keys_table", "press_keyboard_key", "release_keyboard_key", "type_keyboard", "check_key_is_press",
    "write", "hotkey", "start_exe", "get_keyboard_keys_table",
    "screen_size", "screenshot", "locate_all_image", "locate_image_center", "locate_and_click",
    "CriticalExit", "AutoControlException", "AutoControlKeyboardException",
    "AutoControlMouseException", "AutoControlCantFindKeyException",
    "AutoControlScreenException", "ImageNotFoundException", "AutoControlJsonActionException",
    "AutoControlRecordException", "AutoControlActionNullException", "AutoControlActionException", "record",
    "stop_record", "read_action_json", "write_action_json", "execute_action", "execute_files", "executor",
    "execute_action_with_vars",
    "add_command_to_executor", "test_record_instance", "pil_screenshot",
    # OCR
    "TextMatch", "find_text_matches", "locate_text_center", "wait_for_text",
    "click_text", "set_tesseract_cmd",
    # Recording editor
    "trim_actions", "insert_action", "remove_action", "filter_actions",
    "adjust_delays", "scale_coordinates",
    # Scheduler
    "Scheduler", "ScheduledJob", "default_scheduler",
    # Script variables
    "interpolate_actions", "interpolate_value", "load_vars_from_json",
    # Watchers
    "MouseWatcher", "PixelWatcher", "LogTail",
    # Window manager
    "list_windows", "find_window", "focus_window", "wait_for_window",
    "close_window_by_title", "show_window_by_title",
    # Clipboard
    "get_clipboard", "set_clipboard",
    # Hotkey daemon
    "HotkeyDaemon", "HotkeyBinding", "default_hotkey_daemon",
    # MCP server
    "MCPContent", "MCPResource", "MCPServer", "MCPTool",
    "MCPToolAnnotations", "ResourceProvider",
    "build_default_tool_registry", "default_resource_provider",
    "start_mcp_stdio_server",
    # Plugin loader
    "load_plugin_file", "load_plugin_directory", "discover_plugin_commands",
    "register_plugin_commands",
    # REST API
    "RestApiServer", "start_rest_api_server",
    # Triggers
    "TriggerEngine", "default_trigger_engine",
    "ImageAppearsTrigger", "WindowAppearsTrigger",
    "PixelColorTrigger", "FilePathTrigger",
    # Run history
    "HistoryStore", "RunRecord", "default_history_store",
    # Accessibility
    "AccessibilityElement", "AccessibilityNotAvailableError",
    "list_accessibility_elements", "find_accessibility_element",
    "click_accessibility_element",
    # VLM locator
    "VLMNotAvailableError", "locate_by_description", "click_by_description",
    "generate_html", "generate_html_report", "generate_json", "generate_json_report", "generate_xml",
    "generate_xml_report", "get_dir_files_as_list", "create_project_dir", "start_autocontrol_socket_server",
    "callback_executor", "package_manager", "ShellManager", "default_shell_manager",
    "RecordingThread", "send_key_event_to_window", "send_mouse_event_to_window", "windows_window_manage",
    "ScreenRecorder", "get_pixel",
    "start_autocontrol_gui"
]
