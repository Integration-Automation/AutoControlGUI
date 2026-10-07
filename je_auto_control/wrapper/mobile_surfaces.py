"""Code-backed mobile operation surfaces and explicit desktop-only alternatives."""
from __future__ import annotations

from typing import Any

# operation, API, AC command, default options: all execute through the same services.
_SURFACES = (
    ('device_setup', 'mobile_setup', 'AC_mobile_setup', {'connect': False}),
    ('capture', 'mobile_capture', 'AC_mobile_capture', {'file_path': 'phone.png'}),
    ('perform', 'mobile_gesture', 'AC_mobile_gesture', {'gesture': {'kind': 'tap', 'points': [[120, 200]]}}),
    ('type_text', 'mobile_type_text', 'AC_mobile_type_text', {'text': ''}),
    ('launch_app', 'mobile_app', 'AC_mobile_app', {'action': 'launch', 'app_id': 'com.example.demo'}),
    ('wait_for_app', 'mobile_app', 'AC_mobile_app', {'action': 'wait', 'app_id': 'com.example.demo', 'timeout_s': 5}),
    ('app_state', 'mobile_app', 'AC_mobile_app', {'action': 'state', 'app_id': 'com.example.demo'}),
    ('stop_app', 'mobile_app', 'AC_mobile_app', {'action': 'stop', 'app_id': 'com.example.demo'}),
    ('alert', 'mobile_alert', 'AC_mobile_alert', {'action': 'accept'}),
    ('install', 'mobile_extension_action', 'AC_mobile_extension',
     {'operation': 'install', 'options': {'file_path': ''}}),
    ('files', 'mobile_extension_action', 'AC_mobile_extension',
     {'operation': 'files', 'options': {'action': 'push', 'local_path': '', 'remote_path': '/sdcard/file'}}),
    ('clipboard', 'mobile_extension_action', 'AC_mobile_extension', {'operation': 'clipboard', 'options': {}}),
    ('recording', 'mobile_extension_action', 'AC_mobile_extension',
     {'operation': 'recording', 'options': {'file_path': 'phone.mp4', 'duration_s': 5}}),
)


def _operation_names() -> tuple[str, ...]:
    return tuple(row[0] for row in _SURFACES)


def mobile_surface_matrix(include_executor: bool = True) -> dict[str, Any]:
    """Return independent JSON rows; this metadata never imports Qt/SDKs or connects."""
    from copy import deepcopy  # pylint: disable=import-outside-toplevel  # reason: snapshot only when metadata requested
    matrix: dict[str, Any] = {'operations': [{'operation': operation, 'api': api, 'command': command,
                            'mcp': 'ac_' + command[3:], 'gui_action': 'mobile_run_operation',
                            'options': deepcopy(options)} for operation, api, command, options in _SURFACES],
            'desktop_limits': [
                {'operation': 'desktop_mouse', 'state': 'unsupported',
                 'alternative': 'Use native-point Gesture; mouse buttons/window coordinates do not apply.'},
                {'operation': 'desktop_windows', 'state': 'unsupported',
                 'alternative': 'Use app lifecycle and a device UI tree.'},
                {'operation': 'desktop_capture', 'state': 'unsupported',
                 'alternative': 'Use DeviceFrame capture/OCR/template/VLM and pixel_to_point.'},
            ]}
    if include_executor:
        matrix['executor_commands'] = _executor_rows()
    return matrix


def _executor_rows() -> list[dict[str, Any]]:
    # pylint: disable-next=import-outside-toplevel  # reason: live registry inventory only on explicit metadata query
    from je_auto_control.utils.executor.action_executor import executor
    rows = []
    for name in executor.known_commands():
        mobile = name.startswith(('AC_mobile_', 'AC_android_', 'AC_ios_'))
        rows.append({'command': name, 'device_scoped': mobile,
                     'state': 'device_capability_required' if mobile else 'outside_mobile_panel',
                     'reason': 'Check the selected owner capability and platform before native use.' if mobile else
                     'General host/flow/integration command; not accepted by the flat device-only panel.',
                     'alternative': name if mobile else _alternative(name)})
    return rows


def _alternative(name: str) -> str:
    if any(part in name for part in ('screenshot', 'screen', 'image', 'ocr', 'find')):
        return 'Use DeviceFrame capture and device-bound OCR/template/VLM localization.'
    if any(part in name for part in ('mouse', 'keyboard', 'write', 'key')):
        return 'Use mobile Gesture or type_text on the selected device.'
    if 'window' in name:
        return 'Use app_state, launch_app and stop_app; desktop window APIs do not apply.'
    return 'Use the general executor outside this panel; bind a device for explicit mobile steps.'


__all__ = ['mobile_surface_matrix']
