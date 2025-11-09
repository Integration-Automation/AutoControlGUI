# error tags
je_auto_control_error_message: str = "Auto-control error"
je_auto_control_critical_exit_error_message: str = "Auto-control critical exit error"

# os tags
linux_import_error_message: str = "Should only be loaded on Linux"
osx_import_error_message: str = "Should only be loaded on macOS"
windows_import_error_message: str = "Should only be loaded on Windows"
macos_record_error_message: str = "Cannot use recorder on macOS"

# keyboard tags
keyboard_error_message: str = "Auto-control keyboard error"
keyboard_press_key_error_message: str = "Keyboard key press error"
keyboard_release_key_error_message: str = "Keyboard key release error"
keyboard_type_key_error_message: str = "Keyboard key type error"
keyboard_write_error_message: str = "Keyboard write error"
keyboard_write_cant_find_error_message: str = "Keyboard write error: key not found"
keyboard_hotkey_error_message: str = "Keyboard hotkey error"

# mouse tags
mouse_error_message: str = "Auto-control mouse error"
mouse_get_position_error_message: str = "Mouse position retrieval error"
mouse_set_position_error_message: str = "Mouse position set error"
mouse_press_mouse_error_message: str = "Mouse press error"
mouse_release_mouse_error_message: str = "Mouse release error"
mouse_click_mouse_error_message: str = "Mouse click error"
mouse_scroll_error_message: str = "Mouse scroll error"
mouse_wrong_value_error_message: str = "Mouse value error"

# screen tags
screen_error_message: str = "Auto-control screen error"
screen_get_size_error_message: str = "Screen size retrieval error"
screen_screenshot_error_message: str = "Screen screenshot error"

# table tags
table_cant_find_key_error_message: str = "Cannot find key error"

# cv2_utils tags
cant_find_image_error_message: str = "Cannot find image"
find_image_error_variable_error_message: str = "Variable error"

# listener tags
listener_error_message: str = "Auto-control listener error"

# test_record tags
record_queue_error_message: str = "Cannot get test_record queue: it is None. Are you stopping test_record before running it?"
record_not_found_action_error_message: str = "test_record action not found"

# json tag
cant_execute_action_error_message: str = "Cannot execute action"
cant_generate_json_report_error_message: str = "Cannot generate JSON report"
cant_find_json_error_message: str = "Cannot find JSON file"
cant_save_json_error_message: str = "Cannot save JSON file"
action_is_null_error_message: str = "JSON action is null"

# HTML
html_generate_no_data_tag_error_message: str = "Record is None"

# add command
add_command_exception_error_message: str = "Command value must be a method or function"

# executor
executor_list_error_message: str = "Executor received invalid data: list is None or wrong type"

# argparse
argparse_get_wrong_data_error_message: str = "Argparse received invalid data"

# XML
cant_read_xml_error_message: str = "Cannot read XML"
xml_type_error_message: str = "XML type error"

# Callback executor
get_bad_trigger_method_error_message: str = "Invalid trigger method: only kwargs and args accepted"
get_bad_trigger_function_error_message: str = "Invalid trigger function: only functions in event_dict accepted"

# Can't find file
can_not_find_file_error_message: str = "Cannot find file"