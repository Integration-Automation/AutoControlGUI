import types
from typing import Any, Callable, Dict, List, Optional, Union

from je_auto_control.utils.exception.exception_tags import (
    action_is_null_error_message, add_command_exception_error_message,
    executor_list_error_message, cant_execute_action_error_message
)
from je_auto_control.utils.exception.exceptions import (
    AutoControlActionException, AutoControlAddCommandException,
    AutoControlActionNullException
)
from je_auto_control.utils.accessibility.accessibility_api import (
    click_accessibility_element, find_accessibility_element,
)
from je_auto_control.utils.vision.vlm_api import (
    click_by_description, locate_by_description,
)
from je_auto_control.utils.clipboard.clipboard import (
    get_clipboard, set_clipboard,
)
from je_auto_control.utils.executor.action_schema import validate_actions
from je_auto_control.utils.executor.flow_control import (
    BLOCK_COMMANDS, LoopBreak, LoopContinue,
)
from je_auto_control.utils.ocr.ocr_engine import (
    click_text as ocr_click_text,
    locate_text_center as ocr_locate_text_center,
    wait_for_text as ocr_wait_for_text,
)
from je_auto_control.utils.run_history.history_store import default_history_store
from je_auto_control.utils.script_vars.interpolate import interpolate_actions
from je_auto_control.utils.generate_report.generate_html_report import generate_html, generate_html_report
from je_auto_control.utils.generate_report.generate_json_report import generate_json, generate_json_report
from je_auto_control.utils.generate_report.generate_xml_report import generate_xml, generate_xml_report
from je_auto_control.utils.json.json_file import read_action_json
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.mcp_server.server import start_mcp_stdio_server
from je_auto_control.utils.package_manager.package_manager_class import package_manager
from je_auto_control.utils.project.create_project_structure import create_project_dir
from je_auto_control.utils.shell_process.shell_exec import ShellManager
from je_auto_control.utils.start_exe.start_another_process import start_exe
from je_auto_control.utils.test_record.record_test_class import record_action_to_list, test_record_instance
from je_auto_control.wrapper.auto_control_image import locate_all_image, locate_and_click, locate_image_center
from je_auto_control.wrapper.auto_control_keyboard import (
    check_key_is_press, get_keyboard_keys_table,
    press_keyboard_key, release_keyboard_key, hotkey, type_keyboard, write
)
from je_auto_control.wrapper.auto_control_mouse import (
    get_mouse_position, press_mouse, release_mouse, click_mouse,
    mouse_scroll, get_mouse_table, set_mouse_position
)
from je_auto_control.wrapper.auto_control_record import record, stop_record
from je_auto_control.wrapper.auto_control_screen import screenshot, screen_size
from je_auto_control.wrapper.auto_control_window import (
    close_window_by_title, focus_window, list_windows, wait_for_window,
)


def _a11y_list_as_dicts(app_name: Optional[str] = None,
                        max_results: int = 200) -> List[dict]:
    """Executor adapter: list accessibility elements as plain dicts."""
    from je_auto_control.utils.accessibility.accessibility_api import (
        list_accessibility_elements,
    )
    return [
        element.to_dict()
        for element in list_accessibility_elements(
            app_name=app_name, max_results=int(max_results),
        )
    ]


def _a11y_find_as_dict(name: Optional[str] = None,
                       role: Optional[str] = None,
                       app_name: Optional[str] = None) -> Optional[dict]:
    """Executor adapter: find an accessibility element, return its dict."""
    element = find_accessibility_element(
        name=name, role=role, app_name=app_name,
    )
    return None if element is None else element.to_dict()


def _vlm_locate_as_list(description: str,
                        screen_region: Optional[List[int]] = None,
                        model: Optional[str] = None) -> Optional[List[int]]:
    """Executor adapter: return VLM-located coords as a JSON-safe list."""
    coords = locate_by_description(
        description, screen_region=screen_region, model=model,
    )
    return None if coords is None else [coords[0], coords[1]]


def _history_list_as_dicts(limit: int = 100,
                           source_type: Optional[str] = None) -> List[dict]:
    """Executor adapter: list run history as plain dicts (JSON-friendly)."""
    rows = default_history_store.list_runs(
        limit=int(limit), source_type=source_type,
    )
    return [
        {
            "id": r.id, "source_type": r.source_type,
            "source_id": r.source_id, "script_path": r.script_path,
            "started_at": r.started_at, "finished_at": r.finished_at,
            "status": r.status, "error_text": r.error_text,
            "duration_seconds": r.duration_seconds,
        }
        for r in rows
    ]


class Executor:
    """
    Executor
    指令執行器
    - 提供 event_dict 對應字串名稱到函式
    - 支援滑鼠、鍵盤、螢幕、影像辨識、報告生成等功能
    - 可執行 action list 或 action file
    - 支援流程控制指令 (AC_loop, AC_if_image_found 等)
    """

    def __init__(self):
        self._block_commands = BLOCK_COMMANDS
        # 事件字典，對應字串名稱到函式
        self.event_dict: dict = {
            # Mouse 滑鼠相關
            "AC_mouse_left": click_mouse,
            "AC_mouse_right": click_mouse,
            "AC_mouse_middle": click_mouse,
            "AC_click_mouse": click_mouse,
            "AC_get_mouse_table": get_mouse_table,
            "AC_get_mouse_position": get_mouse_position,
            "AC_press_mouse": press_mouse,
            "AC_release_mouse": release_mouse,
            "AC_mouse_scroll": mouse_scroll,
            "AC_set_mouse_position": set_mouse_position,

            # Keyboard 鍵盤相關
            "AC_get_keyboard_keys_table": get_keyboard_keys_table,
            "AC_type_keyboard": type_keyboard,
            "AC_press_keyboard_key": press_keyboard_key,
            "AC_release_keyboard_key": release_keyboard_key,
            "AC_check_key_is_press": check_key_is_press,
            "AC_write": write,
            "AC_hotkey": hotkey,

            # Image 影像辨識
            "AC_locate_all_image": locate_all_image,
            "AC_locate_image_center": locate_image_center,
            "AC_locate_and_click": locate_and_click,

            # Screen 螢幕相關
            "AC_screen_size": screen_size,
            "AC_screenshot": screenshot,

            # Test record 測試紀錄
            "AC_set_record_enable": test_record_instance.set_record_enable,

            # Report 報告生成
            "AC_generate_html": generate_html,
            "AC_generate_json": generate_json,
            "AC_generate_xml": generate_xml,
            "AC_generate_html_report": generate_html_report,
            "AC_generate_json_report": generate_json_report,
            "AC_generate_xml_report": generate_xml_report,

            # Record 錄製
            "AC_record": record,
            "AC_stop_record": stop_record,

            # Executor 執行器
            "AC_execute_action": self.execute_action,
            "AC_execute_files": self.execute_files,
            "AC_add_package_to_executor": package_manager.add_package_to_executor,
            "AC_add_package_to_callback_executor": package_manager.add_package_to_callback_executor,

            # Project 專案
            "AC_create_project": create_project_dir,

            # Shell
            "AC_shell_command": ShellManager().exec_shell,

            # Process
            "AC_execute_process": start_exe,

            # OCR
            "AC_locate_text": ocr_locate_text_center,
            "AC_wait_text": ocr_wait_for_text,
            "AC_click_text": ocr_click_text,

            # Window management
            "AC_list_windows": list_windows,
            "AC_focus_window": focus_window,
            "AC_wait_window": wait_for_window,
            "AC_close_window": close_window_by_title,

            # Clipboard
            "AC_clipboard_get": get_clipboard,
            "AC_clipboard_set": set_clipboard,

            # Run history
            "AC_history_list": _history_list_as_dicts,
            "AC_history_clear": default_history_store.clear,

            # Accessibility-tree widget location
            "AC_a11y_list": _a11y_list_as_dicts,
            "AC_a11y_find": _a11y_find_as_dict,
            "AC_a11y_click": click_accessibility_element,

            # VLM-based element locator
            "AC_vlm_locate": _vlm_locate_as_list,
            "AC_vlm_click": click_by_description,

            # MCP server (Model Context Protocol stdio bridge)
            "AC_start_mcp_server": start_mcp_stdio_server,
        }

    def known_commands(self) -> set:
        """Return the set of all command names the executor recognises."""
        return set(self.event_dict.keys()) | set(self._block_commands.keys())

    def _execute_event(self, action: list) -> Any:
        """
        執行單一事件
        Execute a single event
        """
        name = action[0]
        block_handler = self._block_commands.get(name)
        if block_handler is not None:
            args = action[1] if len(action) == 2 else {}
            if not isinstance(args, dict):
                raise AutoControlActionException(
                    f"{name} requires a dict of arguments"
                )
            return block_handler(self, args)

        event = self.event_dict.get(name)
        if event is None:
            raise AutoControlActionException(f"Unknown action: {name}")

        if len(action) == 2:
            if isinstance(action[1], dict):
                return event(**action[1])
            return event(*action[1])
        if len(action) == 1:
            return event()
        raise AutoControlActionException(cant_execute_action_error_message + " " + str(action))

    def execute_action(self, action_list: Union[list, dict],
                       raise_on_error: bool = False,
                       _validated: bool = False,
                       dry_run: bool = False,
                       step_callback: Optional[Callable[[list], None]] = None,
                       ) -> Dict[str, str]:
        """
        執行 action list
        Execute all actions in action list

        :param action_list: list 或 dict (包含 auto_control key)
        :param raise_on_error: 若為 True，遇到錯誤立即拋出 (流程控制用)
        :param _validated: 內部用；子呼叫已驗證過時避免重複驗證
        :param dry_run: 若為 True，只記錄將執行的動作，不實際呼叫。
        :param step_callback: 每個 action 開始前呼叫此 hook（偵錯用）。
        :return: 執行紀錄字典
        """
        autocontrol_logger.info(f"execute_action, action_list: {action_list}")
        action_list = self._unwrap_action_list(action_list)
        if not _validated:
            validate_actions(action_list, self.known_commands())

        execute_record_dict: Dict[str, Any] = {}
        for action in action_list:
            if step_callback is not None:
                step_callback(action)
            if dry_run:
                execute_record_dict["dry-run: " + str(action)] = "(not executed)"
                continue
            self._run_one_action(action, execute_record_dict, raise_on_error)

        for key, value in execute_record_dict.items():
            autocontrol_logger.info("%s -> %s", key, value)
        return execute_record_dict

    @staticmethod
    def _unwrap_action_list(action_list: Union[list, dict]) -> list:
        """Normalise the ``action_list`` argument or raise on invalid input."""
        if isinstance(action_list, dict):
            action_list = action_list.get("auto_control")
            if action_list is None:
                raise AutoControlActionNullException(executor_list_error_message)
        if not isinstance(action_list, list) or len(action_list) == 0:
            raise AutoControlActionNullException(action_is_null_error_message)
        return action_list

    def _run_one_action(self, action: list, record: Dict[str, Any],
                        raise_on_error: bool) -> None:
        """Execute a single action, recording the result or raising."""
        key = "execute: " + str(action)
        try:
            record[key] = self._execute_event(action)
        except (LoopBreak, LoopContinue):
            raise
        except (AutoControlActionException, OSError, RuntimeError,
                AttributeError, TypeError, ValueError) as error:
            if raise_on_error:
                raise
            autocontrol_logger.info(
                f"execute_action failed, action: {action}, error: {repr(error)}"
            )
            record_action_to_list("AC_execute_action", None, repr(error))
            record[key] = repr(error)

    def execute_files(self, execute_files_list: list) -> List[Dict[str, str]]:
        """
        執行 action files
        Execute actions from files

        :param execute_files_list: list of file paths
        :return: 每個檔案的執行結果
        """
        autocontrol_logger.info(f"execute_files, execute_files_list: {execute_files_list}")
        execute_detail_list = []
        for file in execute_files_list:
            execute_detail_list.append(self.execute_action(read_action_json(file)))
        return execute_detail_list


# === 全域 Executor 實例 Global Executor Instance ===
executor = Executor()
package_manager.executor = executor


def add_command_to_executor(command_dict: dict) -> None:
    """
    新增自訂指令到 Executor
    Add custom commands to Executor

    :param command_dict: dict {command_name: function}
    """
    for command_name, command in command_dict.items():
        if isinstance(command, (types.MethodType, types.FunctionType)):
            executor.event_dict[command_name] = command
        else:
            raise AutoControlAddCommandException(add_command_exception_error_message)


def execute_action(action_list: list) -> Dict[str, str]:
    return executor.execute_action(action_list)


def execute_files(execute_files_list: list) -> List[Dict[str, str]]:
    return executor.execute_files(execute_files_list)


def execute_action_with_vars(action_list: list, variables: dict
                             ) -> Dict[str, str]:
    """Interpolate ``${name}`` placeholders with ``variables`` and execute."""
    resolved = interpolate_actions(action_list, variables)
    return executor.execute_action(resolved)
