from sys import stderr
from typing import Callable, Any

# utils cv2_utils
from je_auto_control.utils.cv2_utils.screenshot import pil_screenshot
from je_auto_control.utils.exception.exception_tags import get_bad_trigger_method_error_message, get_bad_trigger_function_error_message
from je_auto_control.utils.exception.exceptions import CallbackExecutorException
# executor
from je_auto_control.utils.executor.action_executor import execute_action, execute_files
# file process
from je_auto_control.utils.file_process.get_dir_file_list import get_dir_files_as_list
# html report
from je_auto_control.utils.generate_report.generate_html_report import generate_html, generate_html_report
# json report
from je_auto_control.utils.generate_report.generate_json_report import generate_json, generate_json_report
# xml report
from je_auto_control.utils.generate_report.generate_xml_report import generate_xml, generate_xml_report
# json file
from je_auto_control.utils.json.json_file import read_action_json, write_action_json
# package manager
from je_auto_control.utils.package_manager.package_manager_class import package_manager
# project
from je_auto_control.utils.project.create_project_structure import create_project_dir
# shell
from je_auto_control.utils.shell_process.shell_exec import ShellManager
# socket server
from je_auto_control.utils.socket_server.auto_control_socket_server import start_autocontrol_socket_server
# process
from je_auto_control.utils.start_exe.start_another_process import start_exe
# test record
from je_auto_control.utils.test_record.record_test_class import test_record_instance
# image wrapper
from je_auto_control.wrapper.auto_control_image import locate_all_image, locate_and_click, locate_image_center
# keyboard wrapper
from je_auto_control.wrapper.auto_control_keyboard import (
    check_key_is_press, get_special_table, get_keyboard_keys_table,
    hotkey, press_keyboard_key, release_keyboard_key,
    type_keyboard, write
)
# mouse wrapper
from je_auto_control.wrapper.auto_control_mouse import (
    click_mouse, get_mouse_table, get_mouse_position,
    mouse_scroll_error_message, press_mouse, release_mouse, set_mouse_position
)
# record wrapper
from je_auto_control.wrapper.auto_control_record import record, stop_record
# screen wrapper
from je_auto_control.wrapper.auto_control_screen import screen_size, screenshot


class CallbackFunctionExecutor:
    """
    CallbackFunctionExecutor
    回呼函式執行器
    - 提供統一的事件字典 event_dict
    - 可透過 trigger_function_name 執行對應功能
    - 執行後可呼叫 callback_function
    """

    def __init__(self):
        # 事件字典，對應字串名稱到實際函式
        self.event_dict: dict = {
            # mouse 滑鼠相關
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
            "AC_get_special_table": get_special_table,

            # keyboard 鍵盤相關
            "AC_get_keyboard_keys_table": get_keyboard_keys_table,
            "AC_type_keyboard": type_keyboard,
            "AC_press_keyboard_key": press_keyboard_key,
            "AC_release_keyboard_key": release_keyboard_key,
            "AC_check_key_is_press": check_key_is_press,
            "AC_write": write,
            "AC_hotkey": hotkey,

            # cv2_utils 影像辨識
            "AC_locate_all_image": locate_all_image,
            "AC_locate_image_center": locate_image_center,
            "AC_locate_and_click": locate_and_click,

            # screen 螢幕相關
            "AC_screen_size": screen_size,
            "AC_screenshot": screenshot,

            # test record 測試紀錄
            "AC_set_record_enable": test_record_instance.set_record_enable,

            # report 報告生成
            "AC_generate_html": generate_html,
            "AC_generate_json": generate_json,
            "AC_generate_xml": generate_xml,
            "AC_generate_html_report": generate_html_report,
            "AC_generate_json_report": generate_json_report,
            "AC_generate_xml_report": generate_xml_report,

            # record 錄製
            "AC_record": record,
            "AC_stop_record": stop_record,

            # executor 執行器
            "AC_execute_action": execute_action,
            "AC_execute_files": execute_files,

            # project 專案
            "create_template_dir": create_project_dir,
            "AC_create_project": create_project_dir,

            # file process 檔案處理
            "get_dir_files_as_list": get_dir_files_as_list,
            "read_action_json": read_action_json,
            "write_action_json": write_action_json,

            # screenshot 截圖
            "pil_screenshot": pil_screenshot,

            # socket server
            "start_autocontrol_socket_server": start_autocontrol_socket_server,

            # package manager
            "AC_add_package_to_executor": package_manager.add_package_to_executor,
            "AC_add_package_to_callback_executor": package_manager.add_package_to_callback_executor,

            # shell command
            "AC_shell_command": ShellManager().exec_shell,

            # process
            "AC_execute_process": start_exe,
        }

    def callback_function(
            self,
            trigger_function_name: str,
            callback_function: Callable,
            callback_function_param: dict | None = None,
            callback_param_method: str = "kwargs",
            **kwargs
    ) -> Any:
        """
        Execute a trigger function and then call a callback function
        執行指定的 trigger_function，並在完成後呼叫 callback_function

        :param trigger_function_name: 要觸發的函式名稱 (必須存在於 event_dict)
        :param callback_function: 要呼叫的回呼函式
        :param callback_function_param: 回呼函式的參數 (dict 或 list)
        :param callback_param_method: 回呼函式參數傳遞方式 ("kwargs" 或 "args")
        :param kwargs: 傳給 trigger_function 的參數
        :return: trigger_function 的回傳值
        """
        try:
            if trigger_function_name not in self.event_dict:
                raise CallbackExecutorException(get_bad_trigger_function_error_message)

            # 執行 trigger function
            execute_return_value = self.event_dict[trigger_function_name](**kwargs)

            # 呼叫 callback function
            if callback_function_param is not None:
                if callback_param_method not in ["kwargs", "args"]:
                    raise CallbackExecutorException(get_bad_trigger_method_error_message)
                if callback_param_method == "kwargs":
                    callback_function(**callback_function_param)
                else:
                    callback_function(*callback_function_param)
            else:
                callback_function()

            return execute_return_value

        except Exception as error:
            print(repr(error), file=stderr)


# === 全域 Callback Executor 實例 Global Instance ===
callback_executor = CallbackFunctionExecutor()
package_manager.callback_executor = callback_executor