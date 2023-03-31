# error tags
je_auto_control_error: str = "Auto control error"
je_auto_control_critical_exit_error: str = "Auto control critical exit error"
# os tags
linux_import_error: str = "should be only loaded on linux"
osx_import_error: str = "should be only loaded on MacOS"
windows_import_error: str = "should be only loaded on windows"
macos_record_error: str = "macos cant use recorder"
# keyboard tags
keyboard_error: str = "Auto control keyboard error"
keyboard_press_key: str = "keyboard press key error"
keyboard_release_key: str = "keyboard release key error"
keyboard_type_key: str = "keyboard type key error"
keyboard_write: str = "keyboard write error"
keyboard_write_cant_find: str = "keyboard write error cant find key"
keyboard_hotkey: str = "keyboard hotkey error"
# mouse tags
mouse_error: str = "Auto control mouse error"
mouse_get_position: str = "mouse get position error"
mouse_set_position: str = "mouse set position error"
mouse_press_mouse: str = "mouse press mouse error"
mouse_release_mouse: str = "mouse release key error"
mouse_click_mouse: str = "mouse click mouse error"
mouse_scroll: str = "mouse scroll error"
mouse_wrong_value: str = "mouse value error"
# screen tags
screen_error: str = "Auto control screen error"
screen_get_size: str = "screen get size error"
screen_screenshot: str = "screen screenshot error"
# table tags
table_cant_find_key: str = "cant find key error"
# image tags
cant_find_image: str = "cant find image"
find_image_error_variable: str = "variable error"
# listener tags
listener_error: str = "Auto control listener error"
# test_record tags
record_queue_error: str = "cant get test_record queue its none are you using stop test_record before test_record"
record_not_found_action_error: str = "test_record action not found"
# json tag
cant_execute_action_error: str = "cant execute action"
cant_generate_json_report: str = "can't generate json report"
cant_find_json_error: str = "cant find json file"
cant_save_json_error: str = "cant save json file"
action_is_null_error: str = "json action is null"
# timeout tag
timeout_need_on_main_error: str = "should put timeout function on main"
# HTML
html_generate_no_data_tag: str = "record is None"
# add command
add_command_exception_tag: str = "command value type should be as method or function"
# executor
executor_list_error: str = "executor receive wrong data list is none or wrong type"
# argparse
argparse_get_wrong_data: str = "argparse receive wrong data"
# XML
cant_read_xml_error: str = "can't read xml"
xml_type_error: str = "xml type error"
# Callback executor
get_bad_trigger_method: str = "get bad trigger method, only accept kwargs and args"
get_bad_trigger_function: str = "get bad trigger function only accept function in event_dict"
