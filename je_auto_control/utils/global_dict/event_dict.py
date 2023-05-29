from je_auto_control.utils.socket_server.auto_control_socket_server import start_autocontrol_socket_server

from je_auto_control.utils.image.screenshot import pil_screenshot

from je_auto_control.utils.file_process.get_dir_file_list import get_dir_files_as_list

from je_auto_control.utils.executor.action_executor import execute_action, execute_files

from je_auto_control.utils.generate_report.generate_html_report import generate_html
from je_auto_control.utils.generate_report.generate_html_report import generate_html_report
from je_auto_control.utils.generate_report.generate_json_report import generate_json
from je_auto_control.utils.generate_report.generate_json_report import generate_json_report
from je_auto_control.utils.generate_report.generate_xml_report import generate_xml
from je_auto_control.utils.generate_report.generate_xml_report import generate_xml_report
from je_auto_control.utils.json.json_file import read_action_json, write_action_json
from je_auto_control.utils.package_manager.package_manager_class import package_manager
from je_auto_control.utils.project.create_project_structure import create_project_dir
from je_auto_control.utils.shell_process.shell_exec import ShellManager
from je_auto_control.utils.start_exe.start_another_process import start_exe
from je_auto_control.utils.test_record.record_test_class import test_record_instance
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

event_dict: dict = {
    # mouse
    "mouse_left": click_mouse,
    "mouse_right": click_mouse,
    "mouse_middle": click_mouse,
    "click_mouse": click_mouse,
    "get_mouse_table": get_mouse_table,
    "get_mouse_position": get_mouse_position,
    "press_mouse": press_mouse,
    "release_mouse": release_mouse,
    "mouse_scroll": mouse_scroll,
    "set_mouse_position": set_mouse_position,
    "get_special_table": get_special_table,
    # keyboard
    "get_keyboard_keys_table": get_keyboard_keys_table,
    "type_keyboard": type_keyboard,
    "press_keyboard_key": press_keyboard_key,
    "release_keyboard_key": release_keyboard_key,
    "check_key_is_press": check_key_is_press,
    "write": write,
    "hotkey": hotkey,
    # image
    "locate_all_image": locate_all_image,
    "locate_image_center": locate_image_center,
    "locate_and_click": locate_and_click,
    # screen
    "screen_size": screen_size,
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
    # execute
    "execute_action": execute_action,
    "execute_files": execute_files,
    "create_template_dir": create_project_dir,
    "get_dir_files_as_list": get_dir_files_as_list,
    "pil_screenshot": pil_screenshot,
    "read_action_json": read_action_json,
    "write_action_json": write_action_json,
    "start_autocontrol_socket_server": start_autocontrol_socket_server,
    "add_package_to_executor": package_manager.add_package_to_executor,
    "add_package_to_callback_executor": package_manager.add_package_to_callback_executor,
    # project
    "create_project": create_project_dir,
    # Shell
    "shell_command": ShellManager().exec_shell,
    # Another process
    "execute_process": start_exe,
}
