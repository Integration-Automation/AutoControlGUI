"""Schema definitions for AC_* commands used by the visual script editor.

Each entry describes:
- category (for grouping in the Add menu)
- display label
- parameter fields (name, type, optional, default, choices)
- optional nested-body keys (for flow control)
"""
from dataclasses import dataclass
from enum import Enum
from typing import List, Mapping, Optional, Sequence, Tuple


class FieldType(str, Enum):
    STRING = "string"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    ENUM = "enum"
    FILE_PATH = "file_path"
    RGB = "rgb"


@dataclass(frozen=True)
class FieldSpec:
    name: str
    field_type: FieldType
    optional: bool = False
    default: Optional[object] = None
    choices: Sequence[str] = ()
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    placeholder: str = ""


@dataclass(frozen=True)
class CommandSpec:
    command: str
    category: str
    label: str
    fields: Tuple[FieldSpec, ...] = ()
    body_keys: Tuple[str, ...] = ()
    description: str = ""


_MOUSE_BUTTONS = ("mouse_left", "mouse_right", "mouse_middle")


def _build_specs() -> List[CommandSpec]:
    specs: List[CommandSpec] = []
    _add_mouse_specs(specs)
    _add_keyboard_specs(specs)
    _add_screen_specs(specs)
    _add_image_specs(specs)
    _add_ocr_specs(specs)
    _add_window_specs(specs)
    _add_flow_specs(specs)
    _add_misc_specs(specs)
    return specs


def _add_mouse_specs(specs: List[CommandSpec]) -> None:
    specs.append(CommandSpec(
        "AC_click_mouse", "Mouse", "Click Mouse",
        fields=(
            FieldSpec("mouse_keycode", FieldType.ENUM, choices=_MOUSE_BUTTONS,
                      default="mouse_left"),
            FieldSpec("x", FieldType.INT, optional=True),
            FieldSpec("y", FieldType.INT, optional=True),
            FieldSpec("times", FieldType.INT, optional=True, default=1, min_value=1),
        ),
    ))
    specs.append(CommandSpec(
        "AC_set_mouse_position", "Mouse", "Move Mouse To",
        fields=(
            FieldSpec("x", FieldType.INT, default=0),
            FieldSpec("y", FieldType.INT, default=0),
        ),
    ))
    specs.append(CommandSpec(
        "AC_press_mouse", "Mouse", "Press Mouse Button",
        fields=(
            FieldSpec("mouse_keycode", FieldType.ENUM, choices=_MOUSE_BUTTONS,
                      default="mouse_left"),
            FieldSpec("x", FieldType.INT, optional=True),
            FieldSpec("y", FieldType.INT, optional=True),
        ),
    ))
    specs.append(CommandSpec(
        "AC_release_mouse", "Mouse", "Release Mouse Button",
        fields=(
            FieldSpec("mouse_keycode", FieldType.ENUM, choices=_MOUSE_BUTTONS,
                      default="mouse_left"),
            FieldSpec("x", FieldType.INT, optional=True),
            FieldSpec("y", FieldType.INT, optional=True),
        ),
    ))
    specs.append(CommandSpec(
        "AC_mouse_scroll", "Mouse", "Scroll Wheel",
        fields=(
            FieldSpec("scroll_value", FieldType.INT, default=1),
            FieldSpec("x", FieldType.INT, optional=True),
            FieldSpec("y", FieldType.INT, optional=True),
        ),
    ))
    specs.append(CommandSpec(
        "AC_get_mouse_position", "Mouse", "Get Mouse Position"
    ))


def _add_keyboard_specs(specs: List[CommandSpec]) -> None:
    specs.append(CommandSpec(
        "AC_type_keyboard", "Keyboard", "Type Key",
        fields=(
            FieldSpec("keycode", FieldType.STRING, placeholder="e.g. a, enter, 65"),
        ),
    ))
    specs.append(CommandSpec(
        "AC_press_keyboard_key", "Keyboard", "Press Key",
        fields=(
            FieldSpec("keycode", FieldType.STRING, placeholder="e.g. shift"),
        ),
    ))
    specs.append(CommandSpec(
        "AC_release_keyboard_key", "Keyboard", "Release Key",
        fields=(
            FieldSpec("keycode", FieldType.STRING, placeholder="e.g. shift"),
        ),
    ))
    specs.append(CommandSpec(
        "AC_write", "Keyboard", "Write Text",
        fields=(
            FieldSpec("write_string", FieldType.STRING, placeholder="Hello, world"),
        ),
    ))
    specs.append(CommandSpec(
        "AC_hotkey", "Keyboard", "Hotkey",
        fields=(
            FieldSpec("key_code_list", FieldType.STRING,
                      placeholder="ctrl, shift, s"),
        ),
    ))


def _add_screen_specs(specs: List[CommandSpec]) -> None:
    specs.append(CommandSpec(
        "AC_screenshot", "Screen", "Screenshot",
        fields=(
            FieldSpec("file_path", FieldType.FILE_PATH, optional=True),
            FieldSpec("screen_region", FieldType.STRING, optional=True,
                      placeholder="0,0,800,600"),
        ),
    ))
    specs.append(CommandSpec("AC_screen_size", "Screen", "Get Screen Size"))


def _add_image_specs(specs: List[CommandSpec]) -> None:
    specs.append(CommandSpec(
        "AC_locate_image_center", "Image", "Locate Image",
        fields=(
            FieldSpec("image", FieldType.FILE_PATH),
            FieldSpec("detect_threshold", FieldType.FLOAT, optional=True,
                      default=0.8, min_value=0.0, max_value=1.0),
            FieldSpec("draw_image", FieldType.BOOL, optional=True, default=False),
        ),
    ))
    specs.append(CommandSpec(
        "AC_locate_and_click", "Image", "Locate & Click",
        fields=(
            FieldSpec("image", FieldType.FILE_PATH),
            FieldSpec("mouse_keycode", FieldType.ENUM, choices=_MOUSE_BUTTONS,
                      default="mouse_left"),
            FieldSpec("detect_threshold", FieldType.FLOAT, optional=True,
                      default=0.8, min_value=0.0, max_value=1.0),
            FieldSpec("draw_image", FieldType.BOOL, optional=True, default=False),
        ),
    ))
    specs.append(CommandSpec(
        "AC_locate_all_image", "Image", "Locate All",
        fields=(
            FieldSpec("image", FieldType.FILE_PATH),
            FieldSpec("detect_threshold", FieldType.FLOAT, optional=True,
                      default=0.8, min_value=0.0, max_value=1.0),
        ),
    ))


def _add_ocr_specs(specs: List[CommandSpec]) -> None:
    specs.append(CommandSpec(
        "AC_locate_text", "OCR", "Locate Text",
        fields=(
            FieldSpec("target", FieldType.STRING),
            FieldSpec("lang", FieldType.STRING, optional=True, default="eng"),
            FieldSpec("min_confidence", FieldType.FLOAT, optional=True,
                      default=60.0, min_value=0.0, max_value=100.0),
        ),
    ))
    specs.append(CommandSpec(
        "AC_wait_text", "OCR", "Wait for Text",
        fields=(
            FieldSpec("target", FieldType.STRING),
            FieldSpec("lang", FieldType.STRING, optional=True, default="eng"),
            FieldSpec("timeout", FieldType.FLOAT, optional=True, default=10.0),
            FieldSpec("poll", FieldType.FLOAT, optional=True, default=0.5),
            FieldSpec("min_confidence", FieldType.FLOAT, optional=True,
                      default=60.0, min_value=0.0, max_value=100.0),
        ),
    ))
    specs.append(CommandSpec(
        "AC_click_text", "OCR", "Click Text",
        fields=(
            FieldSpec("target", FieldType.STRING),
            FieldSpec("mouse_keycode", FieldType.ENUM,
                      choices=_MOUSE_BUTTONS, default="mouse_left"),
            FieldSpec("lang", FieldType.STRING, optional=True, default="eng"),
            FieldSpec("min_confidence", FieldType.FLOAT, optional=True,
                      default=60.0, min_value=0.0, max_value=100.0),
        ),
    ))


def _add_window_specs(specs: List[CommandSpec]) -> None:
    specs.append(CommandSpec(
        "AC_focus_window", "Window", "Focus Window",
        fields=(
            FieldSpec("title_substring", FieldType.STRING),
            FieldSpec("case_sensitive", FieldType.BOOL, optional=True, default=False),
        ),
    ))
    specs.append(CommandSpec(
        "AC_wait_window", "Window", "Wait for Window",
        fields=(
            FieldSpec("title_substring", FieldType.STRING),
            FieldSpec("timeout", FieldType.FLOAT, optional=True, default=10.0),
            FieldSpec("poll", FieldType.FLOAT, optional=True, default=0.5),
        ),
    ))
    specs.append(CommandSpec(
        "AC_close_window", "Window", "Close Window",
        fields=(FieldSpec("title_substring", FieldType.STRING),),
    ))
    specs.append(CommandSpec("AC_list_windows", "Window", "List Windows"))


def _add_flow_specs(specs: List[CommandSpec]) -> None:
    specs.append(CommandSpec(
        "AC_sleep", "Flow", "Sleep",
        fields=(
            FieldSpec("seconds", FieldType.FLOAT, default=1.0, min_value=0.0),
        ),
    ))
    specs.append(CommandSpec(
        "AC_wait_image", "Flow", "Wait for Image",
        fields=(
            FieldSpec("image", FieldType.FILE_PATH),
            FieldSpec("threshold", FieldType.FLOAT, optional=True, default=0.8,
                      min_value=0.0, max_value=1.0),
            FieldSpec("timeout", FieldType.FLOAT, optional=True, default=10.0),
            FieldSpec("poll", FieldType.FLOAT, optional=True, default=0.2,
                      min_value=0.01),
        ),
    ))
    specs.append(CommandSpec(
        "AC_wait_pixel", "Flow", "Wait for Pixel",
        fields=(
            FieldSpec("x", FieldType.INT),
            FieldSpec("y", FieldType.INT),
            FieldSpec("rgb", FieldType.RGB, placeholder="255,255,255"),
            FieldSpec("tolerance", FieldType.INT, optional=True, default=0,
                      min_value=0, max_value=255),
            FieldSpec("timeout", FieldType.FLOAT, optional=True, default=10.0),
            FieldSpec("poll", FieldType.FLOAT, optional=True, default=0.2,
                      min_value=0.01),
        ),
    ))
    specs.append(CommandSpec(
        "AC_loop", "Flow", "Loop (N times)",
        fields=(
            FieldSpec("times", FieldType.INT, default=3, min_value=1),
        ),
        body_keys=("body",),
    ))
    specs.append(CommandSpec(
        "AC_while_image", "Flow", "While Image Visible",
        fields=(
            FieldSpec("image", FieldType.FILE_PATH),
            FieldSpec("threshold", FieldType.FLOAT, optional=True, default=0.8,
                      min_value=0.0, max_value=1.0),
            FieldSpec("max_iter", FieldType.INT, optional=True, default=100,
                      min_value=1),
        ),
        body_keys=("body",),
    ))
    specs.append(CommandSpec(
        "AC_if_image_found", "Flow", "If Image Found",
        fields=(
            FieldSpec("image", FieldType.FILE_PATH),
            FieldSpec("threshold", FieldType.FLOAT, optional=True, default=0.8,
                      min_value=0.0, max_value=1.0),
        ),
        body_keys=("then", "else"),
    ))
    specs.append(CommandSpec(
        "AC_if_pixel", "Flow", "If Pixel Matches",
        fields=(
            FieldSpec("x", FieldType.INT),
            FieldSpec("y", FieldType.INT),
            FieldSpec("rgb", FieldType.RGB, placeholder="255,255,255"),
            FieldSpec("tolerance", FieldType.INT, optional=True, default=0,
                      min_value=0, max_value=255),
        ),
        body_keys=("then", "else"),
    ))
    specs.append(CommandSpec(
        "AC_retry", "Flow", "Retry on Failure",
        fields=(
            FieldSpec("max_attempts", FieldType.INT, optional=True, default=3,
                      min_value=1),
            FieldSpec("backoff", FieldType.FLOAT, optional=True, default=0.5,
                      min_value=0.0),
        ),
        body_keys=("body",),
    ))
    specs.append(CommandSpec("AC_break", "Flow", "Break Loop"))
    specs.append(CommandSpec("AC_continue", "Flow", "Continue Loop"))


def _add_misc_specs(specs: List[CommandSpec]) -> None:
    specs.append(CommandSpec(
        "AC_shell_command", "Shell", "Shell Command",
        fields=(FieldSpec("shell_command", FieldType.STRING),),
    ))
    specs.append(CommandSpec(
        "AC_execute_process", "Shell", "Start Executable",
        fields=(FieldSpec("program_path", FieldType.FILE_PATH),),
    ))


_SPECS: Tuple[CommandSpec, ...] = tuple(_build_specs())
COMMAND_SPECS: Mapping[str, CommandSpec] = {spec.command: spec for spec in _SPECS}
CATEGORIES: Tuple[str, ...] = tuple(dict.fromkeys(spec.category for spec in _SPECS))


def specs_in_category(category: str) -> List[CommandSpec]:
    """Return all specs belonging to ``category`` in declaration order."""
    return [spec for spec in _SPECS if spec.category == category]
