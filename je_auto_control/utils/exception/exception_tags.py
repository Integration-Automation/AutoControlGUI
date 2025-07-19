# error tags
je_auto_control_error: str = "Auto-control error"
je_auto_control_critical_exit_error: str = "Auto-control critical exit error"

# os tags
linux_import_error: str = "Should only be loaded on Linux"
osx_import_error: str = "Should only be loaded on macOS"
windows_import_error: str = "Should only be loaded on Windows"
macos_record_error: str = "Cannot use recorder on macOS"

# keyboard tags
keyboard_error: str = "Auto-control keyboard error"
keyboard_press_key: str = "Keyboard key press error"
keyboard_release_key: str = "Keyboard key release error"
keyboard_type_key: str = "Keyboard key type error"
keyboard_write: str = "Keyboard write error"
keyboard_write_cant_find: str = "Keyboard write error: key not found"
keyboard_hotkey: str = "Keyboard hotkey error"

# mouse tags
mouse_error: str = "Auto-control mouse error"
mouse_get_position: str = "Mouse position retrieval error"
mouse_set_position: str = "Mouse position set error"
mouse_press_mouse: str = "Mouse press error"
mouse_release_mouse: str = "Mouse release error"
mouse_click_mouse: str = "Mouse click error"
mouse_scroll: str = "Mouse scroll error"
mouse_wrong_value: str = "Mouse value error"

# screen tags
screen_error: str = "Auto-control screen error"
screen_get_size: str = "Screen size retrieval error"
screen_screenshot: str = "Screen screenshot error"

# table tags
table_cant_find_key: str = "Cannot find key error"

# cv2_utils tags
cant_find_image: str = "Cannot find image"
find_image_error_variable: str = "Variable error"

# listener tags
listener_error: str = "Auto-control listener error"

# test_record tags
record_queue_error: str = "Cannot get test_record queue: it is None. Are you stopping test_record before running it?"
record_not_found_action_error: str = "test_record action not found"

# json tag
cant_execute_action_error: str = "Cannot execute action"
cant_generate_json_report: str = "Cannot generate JSON report"
cant_find_json_error: str = "Cannot find JSON file"
cant_save_json_error: str = "Cannot save JSON file"
action_is_null_error: str = "JSON action is null"

# timeout tag
timeout_need_on_main_error: str = "Timeout function must be in main"

# HTML
html_generate_no_data_tag: str = "Record is None"

# add command
add_command_exception: str = "Command value must be a method or function"

# executor
executor_list_error: str = "Executor received invalid data: list is None or wrong type"

# argparse
argparse_get_wrong_data: str = "Argparse received invalid data"

# XML
cant_read_xml_error: str = "Cannot read XML"
xml_type_error: str = "XML type error"

# Callback executor
get_bad_trigger_method: str = "Invalid trigger method: only kwargs and args accepted"
get_bad_trigger_function: str = "Invalid trigger function: only functions in event_dict accepted"

# Can't find file
can_not_find_file: str = "Cannot find file"