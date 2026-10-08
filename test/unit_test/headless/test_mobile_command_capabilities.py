"""Every mobile command is filed under what it actually delivers.

``AC_android_list_devices``, ``AC_android_shell`` and the two ``device_info``
commands used to be listed under the ``input`` capability, which none of them
is: two describe devices and send nothing, one runs an arbitrary shell command.
"""
from collections import Counter

from je_auto_control.wrapper.device_context import CAPABILITY_NAMES
from je_auto_control.wrapper.mobile_commands import (
    COMMAND_PURPOSES, MOBILE_COMMANDS, mobile_capability_matrix,
)

_BY_NAME = {command.name: command for command in MOBILE_COMMANDS}


def test_the_three_commands_are_no_longer_input():
    assert _BY_NAME["AC_android_list_devices"].capability == "device_info"
    assert _BY_NAME["AC_android_device_info"].capability == "device_info"
    assert _BY_NAME["AC_ios_device_info"].capability == "device_info"
    assert _BY_NAME["AC_android_shell"].capability == "shell"
    assert _BY_NAME["AC_android_list_devices"].read_only is True
    assert _BY_NAME["AC_android_shell"].read_only is False


def test_what_is_left_under_input_sends_input():
    names = {command.name for command in MOBILE_COMMANDS if command.capability == "input"}
    assert names == {
        "AC_android_tap", "AC_android_swipe", "AC_android_key", "AC_android_long_press",
        "AC_android_drag", "AC_ios_tap", "AC_ios_swipe", "AC_ios_press_key",
        "AC_ios_long_press", "AC_ios_drag"}
    assert not any(_BY_NAME[name].read_only for name in names)


def test_every_command_has_a_known_capability_and_appears_once_in_the_matrix():
    known = set(CAPABILITY_NAMES) | set(COMMAND_PURPOSES)
    assert {command.capability for command in MOBILE_COMMANDS} <= known
    assert not set(CAPABILITY_NAMES) & set(COMMAND_PURPOSES)
    matrix = mobile_capability_matrix()
    listed = Counter(name for section in ("capabilities", "other_commands")
                     for row in matrix[section] for platform in ("android", "ios")
                     for name in row[platform])
    assert set(listed) == set(_BY_NAME)
    assert set(listed.values()) == {1}


def test_the_matrix_keeps_device_capabilities_apart_from_the_rest():
    matrix = mobile_capability_matrix()
    assert [row["capability"] for row in matrix["capabilities"]] == list(CAPABILITY_NAMES)
    other = {row["purpose"]: row for row in matrix["other_commands"]}
    assert other["device_info"]["android"] == [
        "AC_android_list_devices", "AC_android_device_info"]
    assert other["device_info"]["ios"] == ["AC_ios_device_info"]
    assert other["shell"] == {"purpose": "shell", "android": ["AC_android_shell"], "ios": []}
