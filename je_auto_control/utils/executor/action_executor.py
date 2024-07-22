import builtins
import types
from inspect import getmembers, isbuiltin
from typing import Any, Dict, List, Union

from je_auto_control.utils.exception.exception_tags import action_is_null_error, add_command_exception, \
    executor_list_error
from je_auto_control.utils.exception.exception_tags import cant_execute_action_error
from je_auto_control.utils.exception.exceptions import AutoControlActionException, AutoControlAddCommandException
from je_auto_control.utils.exception.exceptions import AutoControlActionNullException
from je_auto_control.utils.generate_report.generate_html_report import generate_html
from je_auto_control.utils.generate_report.generate_html_report import generate_html_report
from je_auto_control.utils.generate_report.generate_json_report import generate_json
from je_auto_control.utils.generate_report.generate_json_report import generate_json_report
from je_auto_control.utils.generate_report.generate_xml_report import generate_xml
from je_auto_control.utils.generate_report.generate_xml_report import generate_xml_report
from je_auto_control.utils.json.json_file import read_action_json
from je_auto_control.utils.logging.loggin_instance import auto_control_logger
from je_auto_control.utils.package_manager.package_manager_class import package_manager
from je_auto_control.utils.project.create_project_structure import create_project_dir
from je_auto_control.utils.scheduler.extend_apscheduler import scheduler_manager
from je_auto_control.utils.shell_process.shell_exec import ShellManager
from je_auto_control.utils.start_exe.start_another_process import start_exe
from je_auto_control.utils.test_record.record_test_class import record_action_to_list, test_record_instance
from je_auto_control.wrapper.auto_control_image import locate_all_image, locate_and_click, locate_image_center
from je_auto_control.wrapper.auto_control_keyboard import check_key_is_press
from je_auto_control.wrapper.auto_control_keyboard import get_special_table, get_keyboard_keys_table
from je_auto_control.wrapper.auto_control_keyboard import press_keyboard_key, release_keyboard_key, hotkey, \
    type_keyboard, write
from je_auto_control.wrapper.auto_control_mouse import get_mouse_position, press_mouse, release_mouse, click_mouse, \
    mouse_scroll
from je_auto_control.wrapper.auto_control_mouse import get_mouse_table
from je_auto_control.wrapper.auto_control_mouse import set_mouse_position
from je_auto_control.wrapper.auto_control_record import record, stop_record
from je_auto_control.wrapper.auto_control_screen import screenshot, screen_size


class Executor(object):

    def __init__(self):
        self.event_dict: dict = {
            # mouse
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
            "AC_get_special_table": get_special_table,
            # keyboard
            "AC_get_keyboard_keys_table": get_keyboard_keys_table,
            "AC_type_keyboard": type_keyboard,
            "AC_press_keyboard_key": press_keyboard_key,
            "AC_release_keyboard_key": release_keyboard_key,
            "AC_check_key_is_press": check_key_is_press,
            "AC_write": write,
            "AC_hotkey": hotkey,
            # cv2_utils
            "AC_locate_all_image": locate_all_image,
            "AC_locate_image_center": locate_image_center,
            "AC_locate_and_click": locate_and_click,
            # screen
            "AC_screen_size": screen_size,
            "AC_screenshot": screenshot,
            # test record
            "AC_set_record_enable": test_record_instance.set_record_enable,
            # only generate
            "AC_generate_html": generate_html,
            "AC_generate_json": generate_json,
            "AC_generate_xml": generate_xml,
            # generate report
            "AC_generate_html_report": generate_html_report,
            "AC_generate_json_report": generate_json_report,
            "AC_generate_xml_report": generate_xml_report,
            # record
            "AC_record": record,
            "AC_stop_record": stop_record,
            # execute
            "AC_execute_action": self.execute_action,
            "AC_execute_files": self.execute_files,
            "AC_add_package_to_executor": package_manager.add_package_to_executor,
            "AC_add_package_to_callback_executor": package_manager.add_package_to_callback_executor,
            # project
            "AC_create_project": create_project_dir,
            # Shell
            "AC_shell_command": ShellManager().exec_shell,
            # Another process
            "AC_execute_process": start_exe,
            # Scheduler
            "AC_scheduler_event_trigger": self.scheduler_event_trigger,
            "AC_remove_blocking_scheduler_job": scheduler_manager.remove_blocking_job,
            "AC_remove_nonblocking_scheduler_job": scheduler_manager.remove_nonblocking_job,
            "AC_start_blocking_scheduler": scheduler_manager.start_block_scheduler,
            "AC_start_nonblocking_scheduler": scheduler_manager.start_nonblocking_scheduler,
            "AC_start_all_scheduler": scheduler_manager.start_all_scheduler,
            "AC_shutdown_blocking_scheduler": scheduler_manager.shutdown_blocking_scheduler,
            "AC_shutdown_nonblocking_scheduler": scheduler_manager.shutdown_nonblocking_scheduler,
        }
        # get all builtin function and add to event dict
        for function in getmembers(builtins, isbuiltin):
            self.event_dict.update({str(function[0]): function[1]})

    def _execute_event(self, action: list) -> Any:
        event = self.event_dict.get(action[0])
        if len(action) == 2:
            if isinstance(action[1], dict):
                return event(**action[1])
            else:
                return event(*action[1])
        elif len(action) == 1:
            return event()
        else:
            raise AutoControlActionException(cant_execute_action_error + " " + str(action))

    def execute_action(self, action_list: [list, dict]) -> Dict[str, str]:
        """
        use to execute all action on action list(action file or program list)
        :param action_list the list include action
        for loop the list and execute action
        """
        auto_control_logger.info(f"execute_action, action_list: {action_list}")
        if isinstance(action_list, dict):
            action_list: list = action_list.get("auto_control")
            if action_list is None:
                raise AutoControlActionNullException(executor_list_error)
        execute_record_dict = dict()
        try:
            if len(action_list) < 0 or isinstance(action_list, list) is False:
                raise AutoControlActionNullException(action_is_null_error)
        except Exception as error:
            record_action_to_list("AC_execute_action", action_list, repr(error))
            auto_control_logger.info(
                f"execute_action, action_list: {action_list}, "
                f"failed: {repr(error)}")
        for action in action_list:
            try:
                event_response = self._execute_event(action)
                execute_record = "execute: " + str(action)
                execute_record_dict.update({execute_record: event_response})
            except Exception as error:
                auto_control_logger.info(
                    f"execute_action, action_list: {action_list}, "
                    f"action: {action}, failed: {repr(error)}")
                record_action_to_list("AC_execute_action", None, repr(error))
                execute_record = "execute: " + str(action)
                execute_record_dict.update({execute_record: repr(error)})
        for key, value in execute_record_dict.items():
            print(key, flush=True)
            print(value, flush=True)
        return execute_record_dict

    def execute_files(self, execute_files_list: list) -> List[Dict[str, str]]:
        """
        :param execute_files_list: list include execute files path
        :return: every execute detail as list
        """
        auto_control_logger.info(f"execute_files, execute_files_list: {execute_files_list}")
        execute_detail_list: list = list()
        for file in execute_files_list:
            execute_detail_list.append(self.execute_action(read_action_json(file)))
        return execute_detail_list

    def scheduler_event_trigger(
            self, function: str, scheduler_id: str = None, args: Union[list, tuple] = None,
            kwargs: dict = None, scheduler_type: str = "nonblocking", wait_type: str = "secondly",
            wait_value: int = 1, **trigger_args: Any) -> None:
        if scheduler_type == "nonblocking":
            scheduler_event = scheduler_manager.nonblocking_scheduler_event_dict.get(wait_type)
        else:
            scheduler_event = scheduler_manager.blocking_scheduler_event_dict.get(wait_type)
        scheduler_event(self.event_dict.get(function), scheduler_id, args, kwargs, wait_value, **trigger_args)


executor = Executor()
package_manager.executor = executor


def add_command_to_executor(command_dict: dict) -> None:
    """
    :param command_dict: dict include command we want to add to event_dict
    """
    for command_name, command in command_dict.items():
        if isinstance(command, (types.MethodType, types.FunctionType)):
            executor.event_dict.update({command_name: command})
        else:
            raise AutoControlAddCommandException(add_command_exception)


def execute_action(action_list: list) -> Dict[str, str]:
    return executor.execute_action(action_list)


def execute_files(execute_files_list: list) -> List[Dict[str, str]]:
    return executor.execute_files(execute_files_list)
