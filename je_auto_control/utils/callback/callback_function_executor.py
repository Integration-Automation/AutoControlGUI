import typing
from sys import stderr

from je_auto_control.utils.exception.exception_tags import get_bad_trigger_method, get_bad_trigger_function
from je_auto_control.utils.exception.exceptions import CallbackExecutorException
# executor
from je_auto_control.utils.executor.action_executor import execute_action
from je_auto_control.utils.executor.action_executor import execute_files
from je_auto_control.utils.file_process.create_project_structure import create_template_dir
# file process
from je_auto_control.utils.file_process.get_dir_file_list import get_dir_files_as_list
# html report
from je_auto_control.utils.generate_report.generate_html_report import generate_html
from je_auto_control.utils.generate_report.generate_html_report import generate_html_report
from je_auto_control.utils.generate_report.generate_json_report import generate_json
from je_auto_control.utils.generate_report.generate_json_report import generate_json_report
# xml
from je_auto_control.utils.generate_report.generate_xml_report import generate_xml
from je_auto_control.utils.generate_report.generate_xml_report import generate_xml_report
# utils image
from je_auto_control.utils.image.screenshot import pil_screenshot
# json
from je_auto_control.utils.json.json_file import read_action_json
from je_auto_control.utils.json.json_file import write_action_json
# socket server
from je_auto_control.utils.socket_server.auto_control_socket_server import start_autocontrol_socket_server
# test record
from je_auto_control.utils.test_record.record_test_class import test_record_instance
# import image
from je_auto_control.wrapper.auto_control_image import locate_all_image
from je_auto_control.wrapper.auto_control_image import locate_and_click
from je_auto_control.wrapper.auto_control_image import locate_image_center
from je_auto_control.wrapper.auto_control_keyboard import check_key_is_press
from je_auto_control.wrapper.auto_control_keyboard import hotkey
# import keyboard
from je_auto_control.wrapper.auto_control_keyboard import keys_table
from je_auto_control.wrapper.auto_control_keyboard import press_key
from je_auto_control.wrapper.auto_control_keyboard import release_key
from je_auto_control.wrapper.auto_control_keyboard import type_key
from je_auto_control.wrapper.auto_control_keyboard import write
# import mouse
from je_auto_control.wrapper.auto_control_mouse import click_mouse
from je_auto_control.wrapper.auto_control_mouse import mouse_table
from je_auto_control.wrapper.auto_control_mouse import position
from je_auto_control.wrapper.auto_control_mouse import press_mouse
from je_auto_control.wrapper.auto_control_mouse import release_mouse
from je_auto_control.wrapper.auto_control_mouse import scroll
from je_auto_control.wrapper.auto_control_mouse import set_position
from je_auto_control.wrapper.auto_control_mouse import special_table
# test_record
from je_auto_control.wrapper.auto_control_record import record
from je_auto_control.wrapper.auto_control_record import stop_record
from je_auto_control.wrapper.auto_control_screen import screenshot
# import screen
from je_auto_control.wrapper.auto_control_screen import size


class CallbackFunctionExecutor(object):

    def __init__(self):
        self.event_dict: dict = {
            # mouse
            "mouse_left": click_mouse,
            "mouse_right": click_mouse,
            "mouse_middle": click_mouse,
            "click_mouse": click_mouse,
            "mouse_table": mouse_table,
            "position": position,
            "press_mouse": press_mouse,
            "release_mouse": release_mouse,
            "scroll": scroll,
            "set_position": set_position,
            "special_table": special_table,
            # keyboard
            "keys_table": keys_table,
            "type_key": type_key,
            "press_key": press_key,
            "release_key": release_key,
            "check_key_is_press": check_key_is_press,
            "write": write,
            "hotkey": hotkey,
            # image
            "locate_all_image": locate_all_image,
            "locate_image_center": locate_image_center,
            "locate_and_click": locate_and_click,
            # screen
            "size": size,
            "screenshot": screenshot,
            # test record
            "set_record_enable": test_record_instance.set_record_enable,
            # only generate
            "generate_html": generate_html,
            "generate_json": generate_json,
            "generate_xml": generate_xml,
            # generate report
            "generate_html_report": generate_html_report,
            "generate_json_report": generate_json_report,
            "generate_xml_report": generate_xml_report,
            # record
            "record": record,
            "stop_record": stop_record,
            "execute_action": execute_action,
            "execute_files": execute_files,
            "create_template_dir": create_template_dir,
            "get_dir_files_as_list": get_dir_files_as_list,
            "pil_screenshot": pil_screenshot,
            "read_action_json": read_action_json,
            "write_action_json": write_action_json,
            "start_autocontrol_socket_server": start_autocontrol_socket_server,

        }

    def callback_function(
            self,
            trigger_function_name: str,
            callback_function: typing.Callable,
            callback_function_param: [dict, None] = None,
            callback_param_method: str = "kwargs",
            **kwargs
    ):
        """
        :param trigger_function_name: what function we want to trigger only accept function in event_dict
        :param callback_function: what function we want to callback
        :param callback_function_param: callback function's param only accept dict 
        :param callback_param_method: what type param will use on callback function only accept kwargs and args
        :param kwargs: trigger_function's param
        :return: 
        """
        try:
            if trigger_function_name not in self.event_dict.keys():
                raise CallbackExecutorException(get_bad_trigger_function)
            execute_return_value = self.event_dict.get(trigger_function_name)(**kwargs)
            if callback_function_param is not None:
                if callback_param_method not in ["kwargs", "args"]:
                    raise CallbackExecutorException(get_bad_trigger_method)
                if callback_param_method == "kwargs":
                    callback_function(**callback_function_param)
                else:
                    callback_function(*callback_function_param.values())
            else:
                callback_function()
            return execute_return_value
        except Exception as error:
            print(repr(error), file=stderr)


callback_executor = CallbackFunctionExecutor()


