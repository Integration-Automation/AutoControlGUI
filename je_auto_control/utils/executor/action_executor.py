import builtins
import types
from inspect import getmembers, isbuiltin
from typing import Any, Dict, List, Union

from je_auto_control.utils.exception.exception_tags import (
    action_is_null_error_message, add_command_exception_error_message,
    executor_list_error_message, cant_execute_action_error_message
)
from je_auto_control.utils.exception.exceptions import (
    AutoControlActionException, AutoControlAddCommandException,
    AutoControlActionNullException
)
from je_auto_control.utils.generate_report.generate_html_report import generate_html, generate_html_report
from je_auto_control.utils.generate_report.generate_json_report import generate_json, generate_json_report
from je_auto_control.utils.generate_report.generate_xml_report import generate_xml, generate_xml_report
from je_auto_control.utils.json.json_file import read_action_json
from je_auto_control.utils.logging.loggin_instance import autocontrol_logger
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
    mouse_scroll_error_message, get_mouse_table, set_mouse_position
)
from je_auto_control.wrapper.auto_control_record import record, stop_record
from je_auto_control.wrapper.auto_control_screen import screenshot, screen_size


class Executor:
    """
    Executor
    指令執行器
    - 提供 event_dict 對應字串名稱到函式
    - 支援滑鼠、鍵盤、螢幕、影像辨識、報告生成等功能
    - 可執行 action list 或 action file
    """

    def __init__(self):
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
            "AC_mouse_scroll": mouse_scroll_error_message,
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
        }

        # 加入所有 Python 內建函式 Add all Python builtins
        for function in getmembers(builtins, isbuiltin):
            self.event_dict[str(function[0])] = function[1]

    def _execute_event(self, action: list) -> Any:
        """
        執行單一事件
        Execute a single event
        """
        event = self.event_dict.get(action[0])
        if event is None:
            raise AutoControlActionException(f"Unknown action: {action[0]}")

        if len(action) == 2:
            if isinstance(action[1], dict):
                return event(**action[1])
            else:
                return event(*action[1])
        elif len(action) == 1:
            return event()
        else:
            raise AutoControlActionException(cant_execute_action_error_message + " " + str(action))

    def execute_action(self, action_list: Union[list, dict]) -> Dict[str, str]:
        """
        執行 action list
        Execute all actions in action list

        :param action_list: list 或 dict (包含 auto_control key)
        :return: 執行紀錄字典
        """
        autocontrol_logger.info(f"execute_action, action_list: {action_list}")

        if isinstance(action_list, dict):
            action_list = action_list.get("auto_control")
            if action_list is None:
                raise AutoControlActionNullException(executor_list_error_message)

        if not isinstance(action_list, list) or len(action_list) == 0:
            raise AutoControlActionNullException(action_is_null_error_message)

        execute_record_dict = {}

        for action in action_list:
            try:
                event_response = self._execute_event(action)
                execute_record = "execute: " + str(action)
                execute_record_dict[execute_record] = event_response
            except Exception as error:
                autocontrol_logger.info(
                    f"execute_action failed, action: {action}, error: {repr(error)}"
                )
                record_action_to_list("AC_execute_action", None, repr(error))
                execute_record = "execute: " + str(action)
                execute_record_dict[execute_record] = repr(error)

        # 輸出執行結果 Print results
        for key, value in execute_record_dict.items():
            print(key, flush=True)
            print(value, flush=True)

        return execute_record_dict

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