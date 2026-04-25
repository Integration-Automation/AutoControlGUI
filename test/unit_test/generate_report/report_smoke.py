"""Shared smoke-test driver for the html / json / xml report generators.

Each report-format script (``html_report_test.py``, ``json_report.py``,
``xml_report_test.py``) drives the same mouse + keyboard sequence,
intentionally throws one parameter error so the report exercises both
success and failure paths, and then invokes the format-specific
``AC_generate_*_report`` command. Hosting the sequence here keeps the
three smoke scripts down to a single line of intent each.
"""
import sys

from je_auto_control import execute_action, test_record_instance

_TYPE_KEYCODE_BY_PLATFORM = {
    "win32": 65, "cygwin": 65, "msys": 65,
    "linux": 38, "linux2": 38,
    "darwin": 0x00,
}


def run_report_smoke(report_command: str) -> None:
    """Run the canonical action sequence then call ``report_command``."""
    test_record_instance.init_record = True
    keycode = _TYPE_KEYCODE_BY_PLATFORM.get(sys.platform, 65)
    test_list = [
        ["AC_set_record_enable", {"set_enable": True}],
        ["AC_type_keyboard", {"keycode": keycode}],
        ["AC_mouse_left", {"x": 500, "y": 500}],
        ["AC_get_mouse_position"],
        ["AC_press_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
        ["AC_release_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
        ["AC_type_keyboard", {"mouse_keycode": "dwadwawda", "dwadwad": 500, "wdawddwawad": 500}],
        [report_command],
    ]
    print("\n\n")
    execute_action(test_list)
