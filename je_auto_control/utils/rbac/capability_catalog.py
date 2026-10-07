"""Reviewed remote capability names; unknown operations require host administration."""
from typing import Dict

from je_auto_control.utils.rbac.users import Capability

# Observation is an explicit allowlist, never inferred from a provider hint.
_SCREEN = '''screen_size get_screen_size get_mouse_position get_pixel screenshot
list_monitors list_windows find_window get_window_rect get_foreground_window
is_window_minimized window_exists a11y_list a11y_find known_commands
get_control_text control_expand_state control_range find_control_text
list_controls get_keyboard_layout keyboard_layout_info probe_capabilities discover_tools get_tool_schema'''.split()
_INPUT = '''click_mouse double_click_mouse press_mouse release_mouse set_mouse_position
move_mouse mouse_scroll scroll_mouse press_key release_key press_and_release_key
write write_secret type_unicode hotkey key_down key_up key_press
execute_action execute_actions execute_files execute_action_file execute_action_with_vars
set_var get_var inc_var append_var loop for_each while if_var if_image if_pixel if_window
try retry break continue sleep wait pause input_sequence focus_window show_window
minimize_window maximize_window restore_window set_foreground_window'''.split()
_AUDIT = '''history_list history_clear list_run_history clear_run_history
history_read audit_read audit_list audit_query logs_read log_read
read_action_journal list_journal_runs'''.split()
_USERS = '''user_add user_list user_remove user_set_role user_rotate_token'''.split()

CAPABILITY_CATALOG: Dict[str, str] = {
    'probe_mobile_devices': Capability.MANAGE_HOSTS,
    **dict.fromkeys(('mobile_capture', 'mobile_gesture', 'mobile_type_text',
                     'mobile_app', 'mobile_alert', 'mobile_extension', 'mobile_setup', 'mobile_surfaces',
                     'android_mobile_action', 'ios_mobile_action', 'mobile_run'), Capability.MANAGE_HOSTS),
    **dict.fromkeys(('start_physical_recording', 'stop_physical_recording', 'start_wayland_stop_shortcut',
                     'stop_wayland_stop_shortcut', 'wayland_input_status'), Capability.MANAGE_HOSTS),
    **dict.fromkeys(_SCREEN, Capability.READ_SCREEN),
    **dict.fromkeys(_INPUT, Capability.DRIVE_INPUT),
    **dict.fromkeys(_AUDIT, Capability.READ_AUDIT),
    **dict.fromkeys(_USERS, Capability.MANAGE_USERS),
}
