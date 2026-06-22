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
        "AC_human_move", "Mouse", "Human-like Move To",
        fields=(
            FieldSpec("x", FieldType.INT, default=0),
            FieldSpec("y", FieldType.INT, default=0),
            FieldSpec("duration_s", FieldType.FLOAT, optional=True,
                      default=0.4, min_value=0.0),
            FieldSpec("curve", FieldType.FLOAT, optional=True, default=0.2),
            FieldSpec("overshoot", FieldType.FLOAT, optional=True,
                      default=0.0),
            FieldSpec("jitter", FieldType.FLOAT, optional=True, default=1.0),
            FieldSpec("seed", FieldType.INT, optional=True),
        ),
        description="Move the cursor along a curved, human-like path.",
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
        "AC_human_type", "Keyboard", "Human-like Type",
        fields=(
            FieldSpec("text", FieldType.STRING, placeholder="Hello, world"),
            FieldSpec("base_delay", FieldType.FLOAT, optional=True,
                      default=0.05, min_value=0.0),
            FieldSpec("jitter", FieldType.FLOAT, optional=True, default=0.04,
                      min_value=0.0),
            FieldSpec("pause_chance", FieldType.FLOAT, optional=True,
                      default=0.0, min_value=0.0, max_value=1.0),
            FieldSpec("seed", FieldType.INT, optional=True),
        ),
        description="Type text with randomized per-key delays.",
    ))
    specs.append(CommandSpec(
        "AC_set_field_text", "Keyboard", "Set Field Text",
        fields=(
            FieldSpec("text", FieldType.STRING, placeholder="new value"),
            FieldSpec("clear", FieldType.ENUM, choices=("select_all", "none"),
                      optional=True, default="select_all"),
            FieldSpec("paste", FieldType.BOOL, optional=True, default=False),
            FieldSpec("modifier", FieldType.STRING, optional=True,
                      default="ctrl", placeholder="ctrl | command"),
        ),
        description="Clear the focused field then enter text (paste for Unicode).",
    ))
    specs.append(CommandSpec(
        "AC_hold_key", "Keyboard", "Hold Key",
        fields=(
            FieldSpec("key", FieldType.STRING, placeholder="e.g. key_d, space"),
            FieldSpec("duration_s", FieldType.FLOAT, default=1.0,
                      min_value=0.01),
            FieldSpec("rate_hz", FieldType.FLOAT, optional=True,
                      placeholder="auto-repeat presses/sec (blank = hold)"),
        ),
        description="Hold a key for a duration, or auto-repeat it at rate_hz.",
    ))
    specs.append(CommandSpec(
        "AC_type_unicode", "Keyboard", "Type Unicode (emoji / CJK)",
        fields=(
            FieldSpec("text", FieldType.STRING, placeholder="café 🚀 値"),
            FieldSpec("modifier", FieldType.STRING, optional=True,
                      default="ctrl", placeholder="ctrl | command"),
        ),
        description="Enter any Unicode text via clipboard paste (write can't).",
    ))
    specs.append(CommandSpec(
        "AC_with_modifiers", "Keyboard", "With Modifiers Held",
        fields=(
            FieldSpec("modifiers", FieldType.STRING, placeholder="ctrl+shift"),
            FieldSpec("actions", FieldType.STRING,
                      placeholder='[["AC_click_mouse", {...}], ...]'),
        ),
        description="Run nested actions while modifiers are held (release-safe).",
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
        "AC_read_qr", "OCR", "Read QR Codes",
        fields=(
            FieldSpec("region", FieldType.STRING, optional=True,
                      placeholder="[0, 0, 400, 400]"),
        ),
        description="Decode QR codes in a screen region (OpenCV).",
    ))
    specs.append(CommandSpec(
        "AC_scroll_to_find", "OCR", "Scroll Until Visible",
        fields=(
            FieldSpec("target", FieldType.STRING),
            FieldSpec("kind", FieldType.ENUM, choices=("image", "text"),
                      default="image"),
            FieldSpec("direction", FieldType.ENUM,
                      choices=("down", "up", "left", "right"), default="down"),
            FieldSpec("max_scrolls", FieldType.INT, optional=True, default=10,
                      min_value=1),
            FieldSpec("scroll_amount", FieldType.INT, optional=True, default=3,
                      min_value=1),
        ),
        description="Scroll until a template image or OCR text appears.",
    ))
    specs.append(CommandSpec(
        "AC_ocr_to_var", "OCR", "Read Text into Variable",
        fields=(
            FieldSpec("var", FieldType.STRING, default="ocr_text"),
            FieldSpec("region", FieldType.STRING, optional=True,
                      placeholder="[0, 0, 400, 80]"),
            FieldSpec("lang", FieldType.STRING, optional=True, default="eng"),
            FieldSpec("min_confidence", FieldType.FLOAT, optional=True,
                      default=60.0, min_value=0.0, max_value=100.0),
        ),
        description="OCR a region and store the text in a flow variable.",
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
    specs.append(CommandSpec(
        "AC_snap_window", "Window", "Snap / Tile Window",
        fields=(
            FieldSpec("title", FieldType.STRING),
            FieldSpec("position", FieldType.ENUM,
                      choices=("left", "right", "top", "bottom",
                               "top-left", "top-right", "bottom-left",
                               "bottom-right", "max"),
                      default="left"),
        ),
        description="Move a window to a screen half / quarter / maximize.",
    ))
    specs.append(CommandSpec(
        "AC_wait_window_closed", "Window", "Wait for Window to Close",
        fields=(
            FieldSpec("title", FieldType.STRING),
            FieldSpec("timeout_s", FieldType.FLOAT, optional=True,
                      default=10.0),
            FieldSpec("poll_interval_s", FieldType.FLOAT, optional=True,
                      default=0.2, min_value=0.01),
        ),
        description="Wait until a window matching the title disappears.",
    ))
    specs.append(CommandSpec(
        "AC_wait_for_file", "Flow", "Wait for File",
        fields=(
            FieldSpec("path", FieldType.FILE_PATH),
            FieldSpec("timeout_s", FieldType.FLOAT, optional=True,
                      default=30.0),
            FieldSpec("stable_for_s", FieldType.FLOAT, optional=True,
                      default=1.0, min_value=0.0),
            FieldSpec("min_size", FieldType.INT, optional=True, default=1,
                      min_value=0),
            FieldSpec("poll_interval_s", FieldType.FLOAT, optional=True,
                      default=0.25, min_value=0.01),
        ),
        description="Wait until a file appears and stops growing (download done).",
    ))
    specs.append(CommandSpec(
        "AC_wait_for_port", "Flow", "Wait for TCP Port",
        fields=(
            FieldSpec("host", FieldType.STRING, default="127.0.0.1"),
            FieldSpec("port", FieldType.INT, min_value=1, max_value=65535),
            FieldSpec("timeout_s", FieldType.FLOAT, optional=True,
                      default=30.0),
            FieldSpec("connect_timeout_s", FieldType.FLOAT, optional=True,
                      default=1.0, min_value=0.01),
            FieldSpec("poll_interval_s", FieldType.FLOAT, optional=True,
                      default=0.25, min_value=0.01),
        ),
        description="Wait until a TCP host:port accepts connections.",
    ))
    specs.append(CommandSpec(
        "AC_wait_for_process", "Flow", "Wait for Process",
        fields=(
            FieldSpec("name", FieldType.STRING),
            FieldSpec("present", FieldType.BOOL, optional=True, default=True),
            FieldSpec("timeout_s", FieldType.FLOAT, optional=True,
                      default=30.0),
            FieldSpec("poll_interval_s", FieldType.FLOAT, optional=True,
                      default=0.25, min_value=0.01),
        ),
        description="Wait until a process appears (or exits). Requires psutil.",
    ))
    specs.append(CommandSpec("AC_list_windows", "Window", "List Windows"))
    specs.append(CommandSpec(
        "AC_capture_window", "Window", "Capture Window",
        fields=(
            FieldSpec("title", FieldType.STRING),
            FieldSpec("output_path", FieldType.STRING),
        ),
        description="Screenshot the window matching title to a PNG.",
    ))
    specs.append(CommandSpec(
        "AC_save_window_layout", "Window", "Save Window Layout",
        fields=(FieldSpec("path", FieldType.STRING, optional=True),),
        description="Snapshot every window's position (optionally to a file).",
    ))
    specs.append(CommandSpec(
        "AC_restore_window_layout", "Window", "Restore Window Layout",
        fields=(FieldSpec("layout", FieldType.FILE_PATH),),
        description="Move windows back to a saved layout file.",
    ))


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
        "AC_wait_clipboard_change", "Flow", "Wait for Clipboard Change",
        fields=(
            FieldSpec("target", FieldType.STRING, optional=True),
            FieldSpec("contains", FieldType.BOOL, optional=True, default=False),
            FieldSpec("timeout_s", FieldType.FLOAT, optional=True,
                      default=10.0),
            FieldSpec("poll_interval_s", FieldType.FLOAT, optional=True,
                      default=0.2, min_value=0.01),
        ),
        description="Wait until the clipboard changes or matches target.",
    ))
    specs.append(CommandSpec(
        "AC_wait_image_gone", "Flow", "Wait for Image to Vanish",
        fields=(
            FieldSpec("image", FieldType.STRING, placeholder="path/to/spinner.png"),
            FieldSpec("detect_threshold", FieldType.FLOAT, optional=True,
                      default=1.0),
            FieldSpec("timeout_s", FieldType.FLOAT, optional=True, default=10.0),
            FieldSpec("poll_interval_s", FieldType.FLOAT, optional=True,
                      default=0.2, min_value=0.01),
            FieldSpec("gone_for_s", FieldType.FLOAT, optional=True, default=0.0),
        ),
        description="Block until an image (spinner/toast) leaves the screen.",
    ))
    specs.append(CommandSpec(
        "AC_wait_text_gone", "Flow", "Wait for Text to Vanish",
        fields=(
            FieldSpec("text", FieldType.STRING, placeholder="Loading..."),
            FieldSpec("timeout_s", FieldType.FLOAT, optional=True, default=10.0),
            FieldSpec("poll_interval_s", FieldType.FLOAT, optional=True,
                      default=0.2, min_value=0.01),
            FieldSpec("gone_for_s", FieldType.FLOAT, optional=True, default=0.0),
        ),
        description="Block until on-screen text (OCR) disappears.",
    ))
    specs.append(CommandSpec(
        "AC_wait_color", "Flow", "Wait for Region Colour",
        fields=(
            FieldSpec("target_rgb", FieldType.STRING, placeholder="[0, 200, 0]"),
            FieldSpec("region", FieldType.STRING, optional=True,
                      placeholder="[left, top, right, bottom]"),
            FieldSpec("tolerance", FieldType.INT, optional=True, default=10),
            FieldSpec("min_fraction", FieldType.FLOAT, optional=True,
                      default=0.5, min_value=0.0, max_value=1.0),
            FieldSpec("present", FieldType.BOOL, optional=True, default=True),
            FieldSpec("timeout_s", FieldType.FLOAT, optional=True, default=10.0),
            FieldSpec("poll_interval_s", FieldType.FLOAT, optional=True,
                      default=0.2, min_value=0.01),
        ),
        description="Block until a colour fills (or leaves) a screen region.",
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
    specs.append(CommandSpec(
        "AC_transform_var", "Flow", "Transform Variable",
        fields=(
            FieldSpec("name", FieldType.STRING),
            FieldSpec("op", FieldType.ENUM,
                      choices=("upper", "lower", "strip", "title",
                               "lstrip", "rstrip", "replace", "regex",
                               "slice"),
                      default="strip"),
            FieldSpec("into", FieldType.STRING, optional=True),
            FieldSpec("find", FieldType.STRING, optional=True),
            FieldSpec("replace_with", FieldType.STRING, optional=True),
            FieldSpec("pattern", FieldType.STRING, optional=True),
        ),
        description="String-transform a variable (upper/strip/replace/regex/...).",
    ))
    specs.append(CommandSpec(
        "AC_now_to_var", "Flow", "Timestamp into Variable",
        fields=(
            FieldSpec("var", FieldType.STRING, default="now"),
            FieldSpec("format", FieldType.STRING, optional=True,
                      default="%Y-%m-%d %H:%M:%S"),
        ),
        description="Store the current time (strftime format) in a variable.",
    ))
    specs.append(CommandSpec(
        "AC_random_to_var", "Flow", "Random into Variable",
        fields=(
            FieldSpec("var", FieldType.STRING, default="random"),
            FieldSpec("kind", FieldType.ENUM,
                      choices=("int", "float", "choice"), default="int"),
            FieldSpec("min", FieldType.FLOAT, optional=True, default=0.0),
            FieldSpec("max", FieldType.FLOAT, optional=True, default=100.0),
            FieldSpec("seed", FieldType.INT, optional=True),
        ),
        description="Store a random int / float / choice in a variable.",
    ))
    specs.append(CommandSpec(
        "AC_assert_var", "Flow", "Assert Variable",
        fields=(
            FieldSpec("name", FieldType.STRING),
            FieldSpec("op", FieldType.ENUM,
                      choices=("eq", "ne", "lt", "le", "gt", "ge",
                               "contains", "startswith", "endswith",
                               "regex"), default="eq"),
            FieldSpec("value", FieldType.STRING, optional=True),
        ),
        description="Fail if a flow variable doesn't satisfy the condition.",
    ))
    specs.append(CommandSpec(
        "AC_assert_duration", "Flow", "Assert Duration (perf budget)",
        fields=(
            FieldSpec("max_ms", FieldType.FLOAT, default=1000.0, min_value=0.0),
            FieldSpec("min_ms", FieldType.FLOAT, optional=True, default=0.0,
                      min_value=0.0),
        ),
        body_keys=("body",),
        description="Fail if the body takes longer than max_ms.",
    ))
    specs.append(CommandSpec(
        "AC_parallel", "Flow", "Parallel Branches",
        fields=(
            FieldSpec("branches", FieldType.STRING,
                      placeholder='[[["AC_sleep",{"seconds":1}]]]'),
        ),
        description="Run each branch action list concurrently (JSON list).",
    ))
    specs.append(CommandSpec(
        "AC_define_macro", "Flow", "Define Macro",
        fields=(
            FieldSpec("name", FieldType.STRING),
            FieldSpec("params", FieldType.STRING, optional=True,
                      placeholder="x, y"),
        ),
        body_keys=("body",),
        description="Register a named, parameterised action sub-routine.",
    ))
    specs.append(CommandSpec(
        "AC_call_macro", "Flow", "Call Macro",
        fields=(
            FieldSpec("name", FieldType.STRING),
            FieldSpec("args", FieldType.STRING, optional=True,
                      placeholder='{"x": 10, "y": 20}'),
        ),
        description="Invoke a macro defined by AC_define_macro.",
    ))


def _add_native_control_specs(specs: List[CommandSpec]) -> None:
    fields = (
        FieldSpec("name", FieldType.STRING, optional=True),
        FieldSpec("role", FieldType.STRING, optional=True),
        FieldSpec("app_name", FieldType.STRING, optional=True),
        FieldSpec("automation_id", FieldType.STRING, optional=True),
    )
    specs.append(CommandSpec(
        "AC_control_get_value", "Native UI", "Get Control Value",
        fields=fields,
        description="Read a native control's value via the accessibility API.",
    ))
    specs.append(CommandSpec(
        "AC_control_set_value", "Native UI", "Set Control Value",
        fields=(FieldSpec("value", FieldType.STRING),) + fields,
        description="Set a native control's value directly (no per-key typing).",
    ))
    specs.append(CommandSpec(
        "AC_control_invoke", "Native UI", "Invoke Control",
        fields=fields,
        description="Invoke a native control (e.g. press a button).",
    ))
    specs.append(CommandSpec(
        "AC_control_toggle", "Native UI", "Toggle Control",
        fields=fields,
        description="Toggle a native control (e.g. a checkbox).",
    ))
    specs.append(CommandSpec(
        "AC_read_table", "Native UI", "Read Table / Grid",
        fields=fields,
        description="Read a grid/table/list control as rows of cell strings.",
    ))


def _add_misc_specs(specs: List[CommandSpec]) -> None:
    _add_native_control_specs(specs)
    specs.append(CommandSpec(
        "AC_watchdog_add", "Flow", "Watchdog: Add Popup Rule",
        fields=(
            FieldSpec("title", FieldType.STRING),
            FieldSpec("action", FieldType.STRING, optional=True,
                      default="close", placeholder="close / enter / esc"),
            FieldSpec("case_sensitive", FieldType.BOOL, optional=True,
                      default=False),
            FieldSpec("name", FieldType.STRING, optional=True),
        ),
        description="Auto-dismiss an unexpected window when it appears.",
    ))
    specs.append(CommandSpec(
        "AC_watchdog_start", "Flow", "Watchdog: Start"))
    specs.append(CommandSpec(
        "AC_watchdog_stop", "Flow", "Watchdog: Stop"))
    specs.append(CommandSpec(
        "AC_watchdog_list", "Flow", "Watchdog: List Rules / Hits"))
    specs.append(CommandSpec(
        "AC_otp_to_var", "Flow", "OTP (TOTP) into Variable",
        fields=(
            FieldSpec("secret", FieldType.STRING),
            FieldSpec("var", FieldType.STRING, default="otp"),
            FieldSpec("digits", FieldType.INT, optional=True, default=6),
            FieldSpec("step", FieldType.INT, optional=True, default=30),
        ),
        description="Generate a TOTP 2FA code from a base32 secret.",
    ))
    specs.append(CommandSpec(
        "AC_handle_file_dialog", "Native UI", "Handle File Dialog",
        fields=(
            FieldSpec("path", FieldType.STRING),
            FieldSpec("action", FieldType.ENUM,
                      choices=("open", "save", "folder"),
                      optional=True, default="open"),
            FieldSpec("window_title", FieldType.STRING, optional=True),
            FieldSpec("timeout_s", FieldType.FLOAT, optional=True,
                      default=10.0),
            FieldSpec("confirm_key", FieldType.STRING, optional=True,
                      default="enter"),
        ),
        description="Wait for a native file dialog, type a path, confirm.",
    ))
    specs.append(CommandSpec(
        "AC_assert_session_active", "Flow", "Assert Session Active",
        description="Fail if the session is locked / non-interactive.",
    ))
    _add_work_queue_specs(specs)
    _add_tooling_specs(specs)
    _add_authoring_specs(specs)
    _add_agent_specs(specs)
    _add_office_specs(specs)
    _add_memory_specs(specs)
    _add_data_quality_specs(specs)
    _add_i18n_specs(specs)
    _add_checkpoint_specs(specs)
    _add_set_of_marks_specs(specs)
    _add_screen_state_specs(specs)
    _add_input_macro_specs(specs)
    _add_resilience_specs(specs)
    _add_devex_specs(specs)
    _add_audit_specs(specs)
    specs.append(CommandSpec(
        "AC_tween_drag", "Mouse", "Tweened Drag",
        fields=(
            FieldSpec("steps", FieldType.INT, optional=True, default=30),
            FieldSpec("easing", FieldType.ENUM,
                      choices=("linear", "ease_in_out_quad", "ease_out_cubic",
                               "ease_in_cubic"),
                      optional=True, default="ease_in_out_quad"),
            FieldSpec("button", FieldType.ENUM, choices=_MOUSE_BUTTONS,
                      optional=True, default="mouse_left"),
        ),
        description="Drag along an eased path; 'start'/'end' [x,y] via JSON "
                    "view.",
    ))
    specs.append(CommandSpec(
        "AC_move_along_path", "Mouse", "Move Along Path",
        fields=(
            FieldSpec("waypoints", FieldType.STRING,
                      placeholder="[[100,100],[400,150],[400,500]]"),
            FieldSpec("easing", FieldType.ENUM,
                      choices=("linear", "ease_in_out_quad", "ease_out_cubic",
                               "ease_in_cubic"),
                      optional=True, default="linear"),
            FieldSpec("per_segment_steps", FieldType.INT, optional=True,
                      default=20),
        ),
        description="Move the pointer through a polyline of waypoints.",
    ))
    specs.append(CommandSpec(
        "AC_drag_path", "Mouse", "Drag Along Path",
        fields=(
            FieldSpec("waypoints", FieldType.STRING,
                      placeholder="[[50,50],[300,50],[300,300]]"),
            FieldSpec("button", FieldType.ENUM, choices=_MOUSE_BUTTONS,
                      optional=True, default="mouse_left"),
            FieldSpec("easing", FieldType.ENUM,
                      choices=("linear", "ease_in_out_quad", "ease_out_cubic",
                               "ease_in_cubic"),
                      optional=True, default="linear"),
            FieldSpec("per_segment_steps", FieldType.INT, optional=True,
                      default=20),
        ),
        description="Press, drag through a polyline of waypoints, release.",
    ))
    specs.append(CommandSpec(
        "AC_move_mouse_relative", "Mouse", "Move Relative",
        fields=(
            FieldSpec("dx", FieldType.INT, placeholder="-40"),
            FieldSpec("dy", FieldType.INT, placeholder="12"),
        ),
        description="Move the pointer by (dx, dy) from its current position.",
    ))
    specs.append(CommandSpec(
        "AC_list_plugins", "Tools", "List Plugin Commands",
        fields=(FieldSpec("group", FieldType.STRING, optional=True,
                          default="je_auto_control.commands"),),
        description="Discover third-party AC_* commands from entry points.",
    ))
    specs.append(CommandSpec(
        "AC_load_plugins", "Tools", "Load Plugin Commands",
        fields=(FieldSpec("group", FieldType.STRING, optional=True,
                          default="je_auto_control.commands"),),
        description="Discover + register third-party plugin commands.",
    ))
    specs.append(CommandSpec(
        "AC_approval_request", "Tools", "Approval: Request",
        fields=(
            FieldSpec("action", FieldType.STRING),
            FieldSpec("requester", FieldType.STRING, optional=True),
            FieldSpec("db", FieldType.STRING, optional=True),
        ),
        description="Maker-checker: file a high-risk action for approval.",
    ))
    specs.append(CommandSpec(
        "AC_approval_approve", "Tools", "Approval: Approve",
        fields=(
            FieldSpec("token", FieldType.STRING),
            FieldSpec("approver", FieldType.STRING),
            FieldSpec("db", FieldType.STRING, optional=True),
        ),
        description="Approve a request (approver must differ from requester).",
    ))
    specs.append(CommandSpec(
        "AC_approval_reject", "Tools", "Approval: Reject",
        fields=(
            FieldSpec("token", FieldType.STRING),
            FieldSpec("approver", FieldType.STRING),
            FieldSpec("db", FieldType.STRING, optional=True),
        ),
        description="Reject a request (approver must differ from requester).",
    ))
    specs.append(CommandSpec(
        "AC_approval_status", "Tools", "Approval: Status",
        fields=(
            FieldSpec("token", FieldType.STRING),
            FieldSpec("db", FieldType.STRING, optional=True),
        ),
        description="Report a request's status and approved flag.",
    ))
    specs.append(CommandSpec(
        "AC_lease_secret", "Tools", "Lease: Issue",
        fields=(
            FieldSpec("name", FieldType.STRING),
            FieldSpec("ttl", FieldType.FLOAT, optional=True, default=300.0),
        ),
        description="Issue a short-lived JIT lease for a secret (no value).",
    ))
    specs.append(CommandSpec(
        "AC_lease_valid", "Tools", "Lease: Valid?",
        fields=(FieldSpec("token", FieldType.STRING),),
        description="Report whether a lease token is still valid.",
    ))
    specs.append(CommandSpec(
        "AC_revoke_lease", "Tools", "Lease: Revoke",
        fields=(FieldSpec("token", FieldType.STRING),),
        description="Revoke a lease token immediately.",
    ))
    specs.append(CommandSpec(
        "AC_lease_active", "Tools", "Lease: List Active",
        fields=(),
        description="List active leases (token, name, ttl_remaining).",
    ))
    specs.append(CommandSpec(
        "AC_egress_allow", "Tools", "Egress: Set Allowlist",
        fields=(
            FieldSpec("allow", FieldType.STRING, optional=True,
                      placeholder="*.example.com, api.foo.com"),
            FieldSpec("deny", FieldType.STRING, optional=True,
                      placeholder="bad.example.com"),
        ),
        description="Lock the HTTP client to an egress allow/deny policy.",
    ))
    specs.append(CommandSpec(
        "AC_egress_check", "Tools", "Egress: Check URL",
        fields=(FieldSpec("url", FieldType.STRING,
                          placeholder="https://api.example.com"),),
        description="Report whether a URL is permitted by the egress policy.",
    ))
    specs.append(CommandSpec(
        "AC_egress_reset", "Tools", "Egress: Reset (allow-all)",
        fields=(),
        description="Clear the egress policy back to allow-all.",
    ))
    specs.append(CommandSpec(
        "AC_verify_artifact", "Testing", "Approval: Verify Artifact",
        fields=(
            FieldSpec("name", FieldType.STRING, placeholder="login_screen"),
            FieldSpec("content", FieldType.STRING),
            FieldSpec("approvals_dir", FieldType.STRING, optional=True,
                      default=".approvals"),
            FieldSpec("extension", FieldType.STRING, optional=True,
                      default="txt"),
        ),
        description="Compare content to its approved baseline (snapshot test).",
    ))
    specs.append(CommandSpec(
        "AC_approve_artifact", "Testing", "Approval: Promote Received",
        fields=(
            FieldSpec("name", FieldType.STRING),
            FieldSpec("approvals_dir", FieldType.STRING, optional=True,
                      default=".approvals"),
            FieldSpec("extension", FieldType.STRING, optional=True,
                      default="txt"),
        ),
        description="Promote a received artifact to the approved baseline.",
    ))
    specs.append(CommandSpec(
        "AC_pending_artifacts", "Testing", "Approval: List Pending",
        fields=(FieldSpec("approvals_dir", FieldType.STRING, optional=True,
                          default=".approvals"),),
        description="List artifacts awaiting approval.",
    ))
    specs.append(CommandSpec(
        "AC_evaluate_trajectory", "Agent", "Evaluate Trajectory",
        fields=(
            FieldSpec("trajectory", FieldType.STRING,
                      placeholder='[{"action": "AC_click_mouse"}]'),
            FieldSpec("rubric", FieldType.STRING,
                      placeholder='{"required_actions": ["AC_type_text"]}'),
        ),
        description="Score an agent trajectory against a rubric (JSON).",
    ))
    specs.append(CommandSpec(
        "AC_compliance_report", "Report", "Compliance Control Report",
        fields=(
            FieldSpec("evidence", FieldType.STRING,
                      placeholder='{"egress_allowlist_enforced": true}'),
            FieldSpec("frameworks", FieldType.STRING, optional=True,
                      placeholder="SOC2, ISO27001"),
            FieldSpec("path", FieldType.STRING, optional=True),
            FieldSpec("fmt", FieldType.ENUM, optional=True, default="json",
                      choices=("json", "html")),
        ),
        description="Map governance evidence to SOC2/ISO 27001 controls.",
    ))
    specs.append(CommandSpec(
        "AC_trace_record", "Agent", "Trace: Record Span",
        fields=(
            FieldSpec("operation", FieldType.STRING, placeholder="chat"),
            FieldSpec("model", FieldType.STRING, optional=True),
            FieldSpec("system", FieldType.STRING, optional=True),
            FieldSpec("input_tokens", FieldType.INT, optional=True),
            FieldSpec("output_tokens", FieldType.INT, optional=True),
            FieldSpec("tool_name", FieldType.STRING, optional=True),
            FieldSpec("duration_s", FieldType.FLOAT, optional=True,
                      default=0.0),
            FieldSpec("status", FieldType.ENUM, optional=True, default="ok",
                      choices=("ok", "error")),
        ),
        description="Record a GenAI-convention span on the default trace.",
    ))
    specs.append(CommandSpec(
        "AC_trace_summary", "Agent", "Trace: Summary",
        fields=(),
        description="Roll up the default agent trace (count/tokens/duration).",
    ))
    specs.append(CommandSpec(
        "AC_trace_export", "Agent", "Trace: Export (OTLP)",
        fields=(),
        description="Export the default agent trace as OTLP-friendly spans.",
    ))
    specs.append(CommandSpec(
        "AC_trace_reset", "Agent", "Trace: Reset",
        fields=(),
        description="Clear the default agent trace.",
    ))
    specs.append(CommandSpec(
        "AC_write_step_video", "Report", "Step-Overlay Video",
        fields=(
            FieldSpec("steps", FieldType.STRING,
                      placeholder='[{"image": "s1.png", "caption": "Step 1"}]'),
            FieldSpec("output", FieldType.STRING, default="walkthrough.mp4"),
            FieldSpec("fps", FieldType.INT, optional=True, default=10),
            FieldSpec("seconds_per_step", FieldType.FLOAT, optional=True,
                      default=2.0),
        ),
        description="Render captioned screenshots into a walkthrough video.",
    ))
    specs.append(CommandSpec(
        "AC_fuzzy_ratio", "Data", "Fuzzy: Similarity Ratio",
        fields=(
            FieldSpec("left", FieldType.STRING),
            FieldSpec("right", FieldType.STRING),
            FieldSpec("ignore_case", FieldType.BOOL, optional=True,
                      default=True),
        ),
        description="Similarity score (0..1) between two strings.",
    ))
    specs.append(CommandSpec(
        "AC_fuzzy_best_match", "Data", "Fuzzy: Best Match",
        fields=(
            FieldSpec("query", FieldType.STRING),
            FieldSpec("choices", FieldType.STRING,
                      placeholder='["Save", "Cancel", "Submit"]'),
            FieldSpec("score_cutoff", FieldType.FLOAT, optional=True,
                      default=0.0),
            FieldSpec("ignore_case", FieldType.BOOL, optional=True,
                      default=True),
        ),
        description="Best fuzzy match of query within choices (JSON list).",
    ))
    specs.append(CommandSpec(
        "AC_fuzzy_dedupe", "Data", "Fuzzy: Dedupe",
        fields=(
            FieldSpec("items", FieldType.STRING,
                      placeholder='["foo", "foo ", "bar"]'),
            FieldSpec("threshold", FieldType.FLOAT, optional=True,
                      default=0.9),
            FieldSpec("ignore_case", FieldType.BOOL, optional=True,
                      default=True),
        ),
        description="Collapse near-duplicate strings (JSON list).",
    ))
    specs.append(CommandSpec(
        "AC_s3_upload", "Tools", "S3: Upload Artifact",
        fields=(
            FieldSpec("local_path", FieldType.FILE_PATH),
            FieldSpec("key", FieldType.STRING, optional=True),
        ),
        description="Upload a file to the configured default S3 store.",
    ))
    specs.append(CommandSpec(
        "AC_s3_download", "Tools", "S3: Download Artifact",
        fields=(
            FieldSpec("key", FieldType.STRING),
            FieldSpec("local_path", FieldType.STRING),
        ),
        description="Download an object from the default S3 store.",
    ))
    specs.append(CommandSpec(
        "AC_s3_list", "Tools", "S3: List Artifacts",
        fields=(FieldSpec("prefix", FieldType.STRING, optional=True),),
        description="List object keys in the default S3 store.",
    ))
    specs.append(CommandSpec(
        "AC_s3_delete", "Tools", "S3: Delete Artifact",
        fields=(FieldSpec("key", FieldType.STRING),),
        description="Delete an object from the default S3 store.",
    ))
    specs.append(CommandSpec(
        "AC_image_hash", "Image", "Perceptual Hash",
        fields=(
            FieldSpec("path", FieldType.FILE_PATH),
            FieldSpec("algo", FieldType.ENUM, optional=True, default="average",
                      choices=("average", "dhash")),
        ),
        description="Perceptual hash of an image (average or dhash).",
    ))
    specs.append(CommandSpec(
        "AC_dedupe_images", "Image", "Dedupe Near-Identical Images",
        fields=(
            FieldSpec("paths", FieldType.STRING,
                      placeholder='["a.png", "b.png"]'),
            FieldSpec("max_distance", FieldType.INT, optional=True, default=5),
        ),
        description="Collapse near-duplicate images by perceptual hash.",
    ))
    specs.append(CommandSpec(
        "AC_parse_decimal", "Data", "Locale: Parse Decimal",
        fields=(
            FieldSpec("text", FieldType.STRING, placeholder="1.234,56"),
            FieldSpec("locale", FieldType.STRING, optional=True,
                      default="en_US"),
        ),
        description="Parse a locale-formatted decimal string to a float.",
    ))
    specs.append(CommandSpec(
        "AC_parse_number", "Data", "Locale: Parse Number",
        fields=(
            FieldSpec("text", FieldType.STRING, placeholder="1,234"),
            FieldSpec("locale", FieldType.STRING, optional=True,
                      default="en_US"),
        ),
        description="Parse a locale-formatted integer string to an int.",
    ))
    specs.append(CommandSpec(
        "AC_format_decimal", "Data", "Locale: Format Decimal",
        fields=(
            FieldSpec("value", FieldType.FLOAT),
            FieldSpec("locale", FieldType.STRING, optional=True,
                      default="en_US"),
        ),
        description="Format a number for a locale.",
    ))
    specs.append(CommandSpec(
        "AC_format_currency", "Data", "Locale: Format Currency",
        fields=(
            FieldSpec("value", FieldType.FLOAT),
            FieldSpec("currency", FieldType.STRING, placeholder="USD"),
            FieldSpec("locale", FieldType.STRING, optional=True,
                      default="en_US"),
        ),
        description="Format a value as currency (ISO 4217) for a locale.",
    ))
    specs.append(CommandSpec(
        "AC_format_date", "Data", "Locale: Format Date",
        fields=(
            FieldSpec("value", FieldType.STRING, placeholder="2026-06-20"),
            FieldSpec("locale", FieldType.STRING, optional=True,
                      default="en_US"),
            FieldSpec("fmt", FieldType.ENUM, optional=True, default="medium",
                      choices=("short", "medium", "long", "full")),
        ),
        description="Format an ISO date string for a locale.",
    ))
    specs.append(CommandSpec(
        "AC_voice_register", "Agent", "Voice: Register Command",
        fields=(
            FieldSpec("phrase", FieldType.STRING, placeholder="save file"),
            FieldSpec("actions", FieldType.STRING,
                      placeholder='[["AC_hotkey", {"keys": ["ctrl", "s"]}]]'),
        ),
        description="Map a spoken phrase to an action list (JSON).",
    ))
    specs.append(CommandSpec(
        "AC_voice_dispatch", "Agent", "Voice: Dispatch Text",
        fields=(FieldSpec("text", FieldType.STRING,
                          placeholder="save the file"),),
        description="Run the command best matching recognized text.",
    ))
    specs.append(CommandSpec(
        "AC_voice_list", "Agent", "Voice: List Commands",
        fields=(),
        description="List registered voice-command phrases.",
    ))
    specs.append(CommandSpec(
        "AC_voice_clear", "Agent", "Voice: Clear Commands",
        fields=(),
        description="Remove all registered voice commands.",
    ))
    specs.append(CommandSpec(
        "AC_to_physical", "Agent", "Coords: Model -> Physical",
        fields=(
            FieldSpec("x", FieldType.FLOAT), FieldSpec("y", FieldType.FLOAT),
            FieldSpec("physical_w", FieldType.INT),
            FieldSpec("physical_h", FieldType.INT),
            FieldSpec("model_w", FieldType.INT),
            FieldSpec("model_h", FieldType.INT),
        ),
        description="Map a model-grid coordinate to physical pixels.",
    ))
    specs.append(CommandSpec(
        "AC_to_model", "Agent", "Coords: Physical -> Model",
        fields=(
            FieldSpec("x", FieldType.INT), FieldSpec("y", FieldType.INT),
            FieldSpec("physical_w", FieldType.INT),
            FieldSpec("physical_h", FieldType.INT),
            FieldSpec("model_w", FieldType.INT),
            FieldSpec("model_h", FieldType.INT),
        ),
        description="Map a physical-pixel coordinate to a model grid.",
    ))
    specs.append(CommandSpec(
        "AC_loop_guard_observe", "Agent", "Loop Guard: Observe Step",
        fields=(
            FieldSpec("tool", FieldType.STRING, placeholder="AC_click_mouse"),
            FieldSpec("args", FieldType.STRING, optional=True,
                      placeholder='{"x": 10, "y": 20}'),
            FieldSpec("result_digest", FieldType.STRING, optional=True),
        ),
        description="Detect repeat/ping-pong/no-op stuck-loop patterns.",
    ))
    specs.append(CommandSpec(
        "AC_loop_guard_reset", "Agent", "Loop Guard: Reset",
        fields=(),
        description="Clear the default loop guard's history.",
    ))
    specs.append(CommandSpec(
        "AC_mine_actions", "Report", "Mine Action Log",
        fields=(
            FieldSpec("actions", FieldType.STRING,
                      placeholder='[["AC_click_mouse", {}], ...]'),
            FieldSpec("min_len", FieldType.INT, optional=True, default=2),
            FieldSpec("max_len", FieldType.INT, optional=True, default=5),
            FieldSpec("min_count", FieldType.INT, optional=True, default=3),
        ),
        description="Find repeated sequences + rank automation candidates.",
    ))
    specs.append(CommandSpec(
        "AC_set_asset", "Data", "Asset: Set",
        fields=(
            FieldSpec("name", FieldType.STRING),
            FieldSpec("value", FieldType.STRING),
            FieldSpec("asset_type", FieldType.ENUM, optional=True,
                      default="text",
                      choices=("text", "int", "bool", "credential")),
            FieldSpec("environment", FieldType.STRING, optional=True,
                      default="default"),
            FieldSpec("db", FieldType.STRING, optional=True),
        ),
        description="Store a typed, environment-scoped asset.",
    ))
    specs.append(CommandSpec(
        "AC_get_asset", "Data", "Asset: Get",
        fields=(
            FieldSpec("name", FieldType.STRING),
            FieldSpec("environment", FieldType.STRING, optional=True,
                      default="default"),
            FieldSpec("db", FieldType.STRING, optional=True),
        ),
        description="Read a typed asset (credential stays a reference).",
    ))
    specs.append(CommandSpec(
        "AC_list_assets", "Data", "Asset: List",
        fields=(
            FieldSpec("environment", FieldType.STRING, optional=True),
            FieldSpec("db", FieldType.STRING, optional=True),
        ),
        description="List assets (name/type/environment, no values).",
    ))
    specs.append(CommandSpec(
        "AC_emit_event", "Tools", "Emit CloudEvent",
        fields=(
            FieldSpec("event_type", FieldType.STRING,
                      placeholder="com.example.run.finished"),
            FieldSpec("data", FieldType.STRING, optional=True,
                      placeholder='{"run_id": "42"}'),
            FieldSpec("source", FieldType.STRING, optional=True,
                      default="je_auto_control"),
            FieldSpec("subject", FieldType.STRING, optional=True),
            FieldSpec("url", FieldType.STRING, optional=True,
                      placeholder="https://hooks.example.com/ce"),
        ),
        description="Wrap data in a CloudEvents envelope; optionally POST it.",
    ))
    specs.append(CommandSpec(
        "AC_notify_webhook", "Tools", "Notify: Webhook/Chat",
        fields=(
            FieldSpec("url", FieldType.STRING,
                      placeholder="https://hooks.example.com/..."),
            FieldSpec("text", FieldType.STRING),
            FieldSpec("transport", FieldType.ENUM, optional=True,
                      default="raw",
                      choices=("raw", "slack", "discord", "teams")),
            FieldSpec("title", FieldType.STRING, optional=True),
        ),
        description="Send a Slack/Discord/Teams/raw webhook notification.",
    ))
    specs.append(CommandSpec(
        "AC_json_query", "Data", "JSONPath: Query",
        fields=(
            FieldSpec("data", FieldType.STRING,
                      placeholder='{"a": [1, 2]}'),
            FieldSpec("path", FieldType.STRING, placeholder="$.a[*]"),
        ),
        description="Query parsed JSON with a JSONPath subset (all matches).",
    ))
    specs.append(CommandSpec(
        "AC_json_extract", "Data", "JSONPath: Extract Mapping",
        fields=(
            FieldSpec("data", FieldType.STRING),
            FieldSpec("mapping", FieldType.STRING,
                      placeholder='{"name": "$.user.name"}'),
        ),
        description="Extract a {key: jsonpath} mapping into a flat object.",
    ))
    specs.append(CommandSpec(
        "AC_validate_json", "Data", "JSON Schema: Validate",
        fields=(
            FieldSpec("data", FieldType.STRING,
                      placeholder='{"name": "Jo", "age": 30}'),
            FieldSpec("schema", FieldType.STRING,
                      placeholder='{"type": "object", "required": ["name"]}'),
        ),
        description="Validate JSON against a JSON Schema; returns {ok, errors}.",
    ))
    specs.append(CommandSpec(
        "AC_match_json", "Data", "JSON Contract: Match",
        fields=(
            FieldSpec("actual", FieldType.STRING,
                      placeholder='{"id": 1, "name": "Ada"}'),
            FieldSpec("expected", FieldType.STRING,
                      placeholder='{"id": 1, "name": "Ada"}'),
            FieldSpec("partial", FieldType.BOOL, optional=True, default=False),
            FieldSpec("match_type", FieldType.BOOL, optional=True,
                      default=False),
        ),
        description="Match JSON against expected (partial/type); {ok, mismatches}.",
    ))
    specs.append(CommandSpec(
        "AC_diff_json", "Data", "JSON Contract: Diff",
        fields=(
            FieldSpec("actual", FieldType.STRING, placeholder='[1, 2, 3]'),
            FieldSpec("expected", FieldType.STRING, placeholder='[1, 2]'),
        ),
        description="Path-tagged diff between two JSON payloads; {diffs}.",
    ))
    specs.append(CommandSpec(
        "AC_evaluate_flag", "Flow", "Feature Flag: Evaluate",
        fields=(
            FieldSpec("flags", FieldType.STRING,
                      placeholder='{"flags": {"f": {"variants": {...}}}}'),
            FieldSpec("key", FieldType.STRING, placeholder="new-checkout"),
            FieldSpec("context", FieldType.STRING, optional=True,
                      placeholder='{"targeting_key": "user1", "country": "US"}'),
        ),
        description="Evaluate a feature flag; returns {value, variant, reason}.",
    ))
    specs.append(CommandSpec(
        "AC_flag_enabled", "Flow", "Feature Flag: Enabled?",
        fields=(
            FieldSpec("flags", FieldType.STRING),
            FieldSpec("key", FieldType.STRING, placeholder="new-checkout"),
            FieldSpec("context", FieldType.STRING, optional=True),
        ),
        description="Boolean feature-flag check; returns {enabled}.",
    ))
    specs.append(CommandSpec(
        "AC_unified_diff", "Data", "Text: Unified Diff",
        fields=(
            FieldSpec("a", FieldType.STRING, placeholder="original text"),
            FieldSpec("b", FieldType.STRING, placeholder="changed text"),
        ),
        description="Unified diff transforming a into b; returns {diff}.",
    ))
    specs.append(CommandSpec(
        "AC_apply_unified", "Data", "Text: Apply Diff",
        fields=(
            FieldSpec("text", FieldType.STRING, placeholder="original text"),
            FieldSpec("diff", FieldType.STRING, placeholder="@@ -1 +1 @@ ..."),
        ),
        description="Apply a unified diff to text; returns {result}.",
    ))
    specs.append(CommandSpec(
        "AC_three_way_merge", "Data", "Text: Three-Way Merge",
        fields=(
            FieldSpec("base", FieldType.STRING, placeholder="base text"),
            FieldSpec("ours", FieldType.STRING, placeholder="our text"),
            FieldSpec("theirs", FieldType.STRING, placeholder="their text"),
        ),
        description="Merge ours/theirs against base; returns {text, clean, conflicts}.",
    ))
    specs.append(CommandSpec(
        "AC_rrule_occurrences", "Flow", "Recurrence: Expand (RRULE)",
        fields=(
            FieldSpec("rule", FieldType.STRING,
                      placeholder="FREQ=MONTHLY;BYDAY=2TU"),
            FieldSpec("dtstart", FieldType.STRING,
                      placeholder="2026-01-01T09:00:00"),
            FieldSpec("count", FieldType.INT, optional=True, default=10),
        ),
        description="Expand an RFC 5545 RRULE into ISO datetimes.",
    ))
    specs.append(CommandSpec(
        "AC_rrule_next", "Flow", "Recurrence: Next Occurrence",
        fields=(
            FieldSpec("rule", FieldType.STRING,
                      placeholder="FREQ=WEEKLY;BYDAY=MO,WE,FR"),
            FieldSpec("dtstart", FieldType.STRING,
                      placeholder="2026-01-01T09:00:00"),
            FieldSpec("now", FieldType.STRING, optional=True,
                      placeholder="2026-03-15T00:00:00"),
        ),
        description="Next RRULE occurrence at/after now; returns {next}.",
    ))
    specs.append(CommandSpec(
        "AC_describe_stats", "Data", "Describe Statistics",
        fields=(
            FieldSpec("values", FieldType.STRING,
                      placeholder="[12.0, 9.5, 14.2, 11.1]"),
        ),
        description="Summary stats + percentiles of a numeric list.",
    ))
    specs.append(CommandSpec(
        "AC_ab_significance", "Data", "A/B Significance (z-test)",
        fields=(
            FieldSpec("a_conv", FieldType.INT, placeholder="90"),
            FieldSpec("a_n", FieldType.INT, placeholder="200"),
            FieldSpec("b_conv", FieldType.INT, placeholder="110"),
            FieldSpec("b_n", FieldType.INT, placeholder="200"),
        ),
        description="Two-proportion z-test; returns {z, p_value, significant, ci}.",
    ))
    specs.append(CommandSpec(
        "AC_search_documents", "Data", "Full-Text Search (BM25)",
        fields=(
            FieldSpec("docs", FieldType.STRING,
                      placeholder='{"d1": "quick brown fox", "d2": "lazy dog"}'),
            FieldSpec("query", FieldType.STRING, placeholder="quick fox"),
            FieldSpec("top_k", FieldType.INT, optional=True, default=10),
            FieldSpec("mode", FieldType.STRING, optional=True,
                      placeholder="bm25", choices=("bm25", "tfidf")),
        ),
        description="Rank a {id: text} corpus for a query; returns {hits}.",
    ))
    specs.append(CommandSpec(
        "AC_resolve_pointer", "Data", "JSON Pointer: Resolve",
        fields=(
            FieldSpec("doc", FieldType.STRING, placeholder='{"a": {"b": [1, 2]}}'),
            FieldSpec("pointer", FieldType.STRING, placeholder="/a/b/0"),
        ),
        description="Resolve an RFC 6901 JSON Pointer; returns {value}.",
    ))
    specs.append(CommandSpec(
        "AC_apply_json_patch", "Data", "JSON Patch: Apply",
        fields=(
            FieldSpec("doc", FieldType.STRING, placeholder='{"a": 1}'),
            FieldSpec("patch", FieldType.STRING,
                      placeholder='[{"op": "add", "path": "/b", "value": 2}]'),
        ),
        description="Apply an RFC 6902 JSON Patch; returns {result}.",
    ))
    specs.append(CommandSpec(
        "AC_make_json_patch", "Data", "JSON Patch: Diff",
        fields=(
            FieldSpec("old", FieldType.STRING, placeholder='{"a": 1}'),
            FieldSpec("new", FieldType.STRING, placeholder='{"a": 2}'),
        ),
        description="Compute an RFC 6902 patch from old to new; returns {patch}.",
    ))
    specs.append(CommandSpec(
        "AC_merge_patch", "Data", "JSON Merge Patch: Apply",
        fields=(
            FieldSpec("doc", FieldType.STRING, placeholder='{"a": 1, "b": 2}'),
            FieldSpec("patch", FieldType.STRING,
                      placeholder='{"b": null, "c": 3}'),
        ),
        description="Apply an RFC 7386 merge patch (null deletes); returns {result}.",
    ))
    specs.append(CommandSpec(
        "AC_scan_vulns", "Security", "Scan Dependencies for Vulnerabilities",
        fields=(
            FieldSpec("components", FieldType.STRING,
                      placeholder='{"components": [{"name": "foo", '
                                  '"version": "1.0", "purl": "pkg:pypi/foo@1.0"}]}'),
            FieldSpec("advisories", FieldType.STRING,
                      placeholder='[{"id": "GHSA-...", "affected": [...]}]'),
            FieldSpec("sarif_path", FieldType.STRING, optional=True,
                      placeholder="vulns.sarif"),
        ),
        description="Match SBOM components against an OSV advisory database.",
    ))
    specs.append(CommandSpec(
        "AC_apply_vex", "Security", "Apply VEX Triage to Findings",
        fields=(
            FieldSpec("findings", FieldType.STRING,
                      placeholder='[{"id": "GHSA-...", "package": "foo"}]'),
            FieldSpec("vex", FieldType.STRING,
                      placeholder='{"statements": [{"vulnerability": '
                                  '{"name": "CVE-..."}, "status": "not_affected"}]}'),
        ),
        description="Suppress not_affected/fixed vulns via an OpenVEX document.",
    ))
    specs.append(CommandSpec(
        "AC_check_licenses", "Security", "Check Dependency Licenses",
        fields=(
            FieldSpec("components", FieldType.STRING,
                      placeholder='{"components": [{"name": "x", '
                                  '"licenses": [{"license": {"name": "MIT"}}]}]}'),
            FieldSpec("allow", FieldType.STRING, optional=True,
                      placeholder='["MIT", "Apache-2.0", "BSD-3-Clause"]'),
            FieldSpec("deny", FieldType.STRING, optional=True,
                      placeholder='["GPL-3.0-only", "AGPL-3.0-only"]'),
        ),
        description="Evaluate SBOM licenses against allow/deny SPDX lists.",
    ))
    specs.append(CommandSpec(
        "AC_build_provenance", "Security", "Provenance: Build (SLSA)",
        fields=(
            FieldSpec("paths", FieldType.STRING,
                      placeholder='["dist/app.whl", "sbom.cdx.json"]'),
            FieldSpec("builder_id", FieldType.STRING, optional=True,
                      placeholder="je_auto_control"),
        ),
        description="Build a SLSA in-toto provenance statement over files.",
    ))
    specs.append(CommandSpec(
        "AC_verify_provenance", "Security", "Provenance: Verify",
        fields=(
            FieldSpec("statement", FieldType.STRING,
                      placeholder='{"subject": [...], "predicate": {...}}'),
            FieldSpec("files", FieldType.STRING,
                      placeholder='{"app.whl": "dist/app.whl"}'),
        ),
        description="Re-hash files against a provenance statement; {ok, mismatches}.",
    ))
    specs.append(CommandSpec(
        "AC_jwt_encode", "Security", "JWT: Sign Token",
        fields=(
            FieldSpec("claims", FieldType.STRING,
                      placeholder='{"sub": "user1", "exp": 1893456000}'),
            FieldSpec("key", FieldType.STRING, placeholder="shared secret"),
            FieldSpec("alg", FieldType.STRING, optional=True,
                      placeholder="HS256",
                      choices=("HS256", "HS384", "HS512")),
        ),
        description="Sign a compact JWT (HMAC) from claims; returns {token}.",
    ))
    specs.append(CommandSpec(
        "AC_jwt_decode", "Security", "JWT: Verify Token",
        fields=(
            FieldSpec("token", FieldType.STRING, placeholder="eyJhbGci..."),
            FieldSpec("key", FieldType.STRING, placeholder="shared secret"),
            FieldSpec("algorithms", FieldType.STRING, optional=True,
                      placeholder='["HS256"]'),
            FieldSpec("audience", FieldType.STRING, optional=True),
        ),
        description="Verify a JWT (alg allowlist + exp/nbf/aud); returns {ok, claims}.",
    ))
    specs.append(CommandSpec(
        "AC_percentiles", "Report", "Percentiles",
        fields=(
            FieldSpec("samples", FieldType.STRING,
                      placeholder="[12.0, 9.5, 14.2, 11.1]"),
            FieldSpec("qs", FieldType.STRING, optional=True,
                      placeholder="[50, 90, 99]"),
        ),
        description="Exact percentiles of a numeric sample list.",
    ))
    specs.append(CommandSpec(
        "AC_evaluate_slo", "Report", "SLO: Evaluate (SLI + Error Budget)",
        fields=(
            FieldSpec("records", FieldType.STRING,
                      placeholder='[{"timestamp": 1700000000, "ok": true}]'),
            FieldSpec("target", FieldType.FLOAT, placeholder="0.99"),
            FieldSpec("window_s", FieldType.FLOAT, optional=True),
        ),
        description="SLI + error budget for outcome records vs a target.",
    ))
    specs.append(CommandSpec(
        "AC_burn_alerts", "Report", "SLO: Burn-Rate Alerts",
        fields=(
            FieldSpec("records", FieldType.STRING,
                      placeholder='[{"timestamp": 1700000000, "ok": false}]'),
            FieldSpec("target", FieldType.FLOAT, placeholder="0.99"),
        ),
        description="Multi-window burn-rate alerts (Google SRE tiers).",
    ))
    specs.append(CommandSpec(
        "AC_run_chaos", "Flow", "Run Chaos Experiment",
        fields=(
            FieldSpec("spec", FieldType.STRING,
                      placeholder='{"title": "...", "probes": [{"name": "p", '
                                  '"action": [...]}], "method": [{"name": "f", '
                                  '"action": [...]}], "rollbacks": [[...]]}'),
        ),
        description="Verify steady state, inject faults, re-verify, roll back.",
    ))
    specs.append(CommandSpec(
        "AC_run_saga", "Flow", "Run Saga (Compensating Rollback)",
        fields=(
            FieldSpec("steps", FieldType.STRING,
                      placeholder='[{"name": "s1", "action": [...], '
                                  '"compensation": [...]}]'),
        ),
        description="Run steps; on failure undo completed steps LIFO.",
    ))
    specs.append(CommandSpec(
        "AC_decision_table", "Flow", "Decision Table (DMN)",
        fields=(
            FieldSpec("spec", FieldType.STRING,
                      placeholder='{"inputs": ["age"], "hit_policy": "FIRST", '
                                  '"rules": [...]}'),
            FieldSpec("context", FieldType.STRING,
                      placeholder='{"age": 30}'),
        ),
        description="Evaluate inputs against a rule table (hit policy).",
    ))
    specs.append(CommandSpec(
        "AC_repair_record", "Tools", "Locator Repair: Record",
        fields=(
            FieldSpec("key", FieldType.STRING),
            FieldSpec("method", FieldType.STRING, placeholder="vlm/image"),
            FieldSpec("coordinates", FieldType.STRING, optional=True,
                      placeholder="[10, 20]"),
            FieldSpec("description", FieldType.STRING, optional=True),
            FieldSpec("confidence", FieldType.FLOAT, optional=True,
                      default=1.0),
            FieldSpec("auto_threshold", FieldType.FLOAT, optional=True,
                      default=0.9),
            FieldSpec("db", FieldType.STRING, optional=True),
        ),
        description="Persist a corrected locator from a heal (auto/queue).",
    ))
    specs.append(CommandSpec(
        "AC_repair_resolved", "Tools", "Locator Repair: Resolved",
        fields=(
            FieldSpec("key", FieldType.STRING),
            FieldSpec("db", FieldType.STRING, optional=True),
        ),
        description="Get the learned corrected locator for a key.",
    ))
    specs.append(CommandSpec(
        "AC_repair_pending", "Tools", "Locator Repair: Pending",
        fields=(FieldSpec("db", FieldType.STRING, optional=True),),
        description="List locator-repair suggestions awaiting review.",
    ))
    specs.append(CommandSpec(
        "AC_repair_approve", "Tools", "Locator Repair: Approve",
        fields=(
            FieldSpec("suggestion_id", FieldType.STRING),
            FieldSpec("db", FieldType.STRING, optional=True),
        ),
        description="Approve a pending locator-repair suggestion.",
    ))
    specs.append(CommandSpec(
        "AC_detect_pii", "Data", "PII: Detect",
        fields=(
            FieldSpec("text", FieldType.STRING),
            FieldSpec("kinds", FieldType.STRING, optional=True,
                      placeholder='["email", "phone"]'),
        ),
        description="Detect PII spans (email/phone/ssn/card/ip/iban) in text.",
    ))
    specs.append(CommandSpec(
        "AC_redact_pii", "Data", "PII: Redact",
        fields=(
            FieldSpec("text", FieldType.STRING),
            FieldSpec("kinds", FieldType.STRING, optional=True,
                      placeholder='["email"]'),
            FieldSpec("mode", FieldType.ENUM, optional=True, default="label",
                      choices=("label", "mask", "partial", "hash")),
            FieldSpec("mask_char", FieldType.STRING, optional=True,
                      default="*"),
        ),
        description="Redact PII in text (label/mask/partial/hash).",
    ))
    specs.append(CommandSpec(
        "AC_export_sarif", "Report", "Export SARIF (Code Scanning)",
        fields=(
            FieldSpec("findings", FieldType.STRING,
                      placeholder='[{"rule_id": "AC1", "message": "...", '
                                  '"level": "error"}]'),
            FieldSpec("path", FieldType.STRING, optional=True,
                      placeholder="results.sarif"),
            FieldSpec("tool_name", FieldType.STRING, optional=True,
                      default="AutoControl"),
        ),
        description="Unify findings into a SARIF 2.1.0 document.",
    ))
    specs.append(CommandSpec(
        "AC_generate_sop", "Report", "Generate SOP Document",
        fields=(
            FieldSpec("title", FieldType.STRING, optional=True,
                      default="Automation Procedure"),
            FieldSpec("path", FieldType.FILE_PATH, optional=True),
        ),
        description="Build a step-by-step SOP (HTML) from 'actions' (JSON "
                    "view).",
    ))


def _add_audit_specs(specs: List[CommandSpec]) -> None:
    specs.append(CommandSpec(
        "AC_heal_stats", "Testing", "Self-Heal Analytics",
        fields=(FieldSpec("limit", FieldType.INT, optional=True,
                          default=200),),
        description="Aggregate the self-heal log (heal rate, brittle "
                    "locators).",
    ))
    specs.append(CommandSpec(
        "AC_scan_secrets", "Tools", "Scan for Hardcoded Secrets",
        description="Scan 'data' (JSON view) for hardcoded secrets that "
                    "should use ${secrets.*}.",
    ))


def _add_devex_specs(specs: List[CommandSpec]) -> None:
    specs.append(CommandSpec(
        "AC_ci_annotations", "Tools", "Emit CI Annotations",
        description="Emit GitHub Actions annotations from 'annotations' "
                    "(JSON view).",
    ))
    specs.append(CommandSpec(
        "AC_clip_history_capture", "Misc", "Clipboard History: Capture"))
    specs.append(CommandSpec(
        "AC_clip_history_list", "Misc", "Clipboard History: List"))
    specs.append(CommandSpec(
        "AC_clip_history_search", "Misc", "Clipboard History: Search",
        fields=(FieldSpec("query", FieldType.STRING),)))
    specs.append(CommandSpec(
        "AC_clip_history_start", "Misc", "Clipboard History: Start"))
    specs.append(CommandSpec(
        "AC_clip_history_stop", "Misc", "Clipboard History: Stop"))


def _add_resilience_specs(specs: List[CommandSpec]) -> None:
    specs.append(CommandSpec(
        "AC_circuit_call", "Flow", "Circuit Breaker Call",
        fields=(
            FieldSpec("name", FieldType.STRING),
            FieldSpec("threshold", FieldType.INT, optional=True, default=5),
            FieldSpec("reset_s", FieldType.FLOAT, optional=True, default=30.0),
        ),
        description="Run 'actions' (JSON view) via a named circuit breaker.",
    ))
    specs.append(CommandSpec(
        "AC_bulkhead_run", "Flow", "Bulkhead (Bounded Concurrency)",
        fields=(
            FieldSpec("name", FieldType.STRING),
            FieldSpec("max_concurrent", FieldType.INT, default=4),
            FieldSpec("actions", FieldType.STRING,
                      placeholder="[[\"AC_click_mouse\", {...}]]"),
        ),
        description="Run 'actions' (JSON view) under a named bulkhead permit.",
    ))
    specs.append(CommandSpec(
        "AC_retry_after", "Flow", "Parse Retry-After / RateLimit",
        fields=(
            FieldSpec("response", FieldType.STRING,
                      placeholder='{"status": 429, "headers": {"Retry-After": "30"}}'),
        ),
        description="Server-advised wait (seconds) from an HTTP response; {delay}.",
    ))
    specs.append(CommandSpec(
        "AC_http_replay", "Data", "HTTP Cassette: Replay",
        fields=(
            FieldSpec("cassette", FieldType.STRING,
                      placeholder='{"interactions": [{"request": {...}, '
                                  '"response": {...}}]}'),
            FieldSpec("url", FieldType.STRING,
                      placeholder="https://api.example.com/users/1"),
            FieldSpec("method", FieldType.STRING, optional=True,
                      placeholder="GET"),
        ),
        description="Replay a recorded HTTP response from a cassette (no network).",
    ))
    specs.append(CommandSpec(
        "AC_trace_inject", "Data", "Trace Context: Inject",
        fields=(
            FieldSpec("headers", FieldType.STRING, optional=True,
                      placeholder='{"accept": "application/json"}'),
            FieldSpec("traceparent", FieldType.STRING, optional=True,
                      placeholder="00-<32 hex>-<16 hex>-01 (parent; omit for root)"),
        ),
        description="Set a W3C traceparent on outgoing headers (root or child).",
    ))
    specs.append(CommandSpec(
        "AC_trace_extract", "Data", "Trace Context: Extract",
        fields=(
            FieldSpec("headers", FieldType.STRING,
                      placeholder='{"traceparent": "00-...-...-01"}'),
        ),
        description="Extract the W3C trace context from request headers.",
    ))
    specs.append(CommandSpec(
        "AC_baggage_parse", "Data", "Baggage: Parse Header",
        fields=(
            FieldSpec("header", FieldType.STRING,
                      placeholder="tenant=acme,run=42"),
        ),
        description="Parse a W3C baggage header into key-value items.",
    ))
    specs.append(CommandSpec(
        "AC_baggage_format", "Data", "Baggage: Format Header",
        fields=(
            FieldSpec("items", FieldType.STRING,
                      placeholder='{"tenant": "acme", "run": "42"}'),
        ),
        description="Serialise items into a percent-encoded baggage header.",
    ))
    specs.append(CommandSpec(
        "AC_canonical_log", "Report", "Canonical Log: Build Line",
        fields=(
            FieldSpec("fields", FieldType.STRING,
                      placeholder='{"event": "run", "ok": true, "ms": 42}'),
        ),
        description="Build a canonical wide-event log line (rendered as JSON).",
    ))
    specs.append(CommandSpec(
        "AC_normalize_text", "Data", "Text: Normalize (Unicode)",
        fields=(
            FieldSpec("text", FieldType.STRING, placeholder="Café  Menu"),
            FieldSpec("form", FieldType.STRING, optional=True,
                      placeholder="NFKC"),
            FieldSpec("casefold", FieldType.BOOL, optional=True, default=True),
            FieldSpec("collapse_ws", FieldType.BOOL, optional=True,
                      default=True),
        ),
        description="Unicode-normalise text (form + casefold + ws fold).",
    ))
    specs.append(CommandSpec(
        "AC_slugify", "Data", "Text: Slugify",
        fields=(
            FieldSpec("text", FieldType.STRING, placeholder="Café Menu!"),
            FieldSpec("sep", FieldType.STRING, optional=True, placeholder="-"),
        ),
        description="Produce an ASCII slug (de-accent, lowercase, join).",
    ))
    specs.append(CommandSpec(
        "AC_text_similarity", "Data", "Text: Similarity",
        fields=(
            FieldSpec("a", FieldType.STRING, placeholder="login"),
            FieldSpec("b", FieldType.STRING, placeholder="lgoin"),
            FieldSpec("metric", FieldType.STRING, optional=True,
                      placeholder="jaro_winkler | levenshtein | jaccard | dice"),
        ),
        description="Normalised string similarity (Jaro-Winkler / edit / Jaccard).",
    ))
    specs.append(CommandSpec(
        "AC_simhash", "Data", "Near-Dup: SimHash",
        fields=(
            FieldSpec("text", FieldType.STRING, placeholder="some text"),
            FieldSpec("bits", FieldType.INT, optional=True, default=64),
        ),
        description="SimHash fingerprint (int) of text.",
    ))
    specs.append(CommandSpec(
        "AC_near_duplicates", "Data", "Near-Dup: Cluster Texts",
        fields=(
            FieldSpec("texts", FieldType.STRING,
                      placeholder='["the cat sat", "the cat sat down", "dog"]'),
            FieldSpec("max_distance", FieldType.INT, optional=True, default=3),
        ),
        description="Cluster near-duplicate texts by SimHash distance.",
    ))
    specs.append(CommandSpec(
        "AC_spans_to_otlp", "Report", "OTLP: Export Spans",
        fields=(
            FieldSpec("spans", FieldType.STRING,
                      placeholder='[{"trace_id": "...", "span_id": "...", '
                                  '"name": "step", "start_unix_nano": 1, '
                                  '"end_unix_nano": 2}]'),
            FieldSpec("resource_attrs", FieldType.STRING, optional=True,
                      placeholder='{"service.name": "autocontrol"}'),
        ),
        description="Wrap spans in an OTLP/JSON resourceSpans envelope.",
    ))
    specs.append(CommandSpec(
        "AC_resolve_ref", "Security", "Secret Ref: Resolve",
        fields=(
            FieldSpec("ref", FieldType.STRING,
                      placeholder="env://TOKEN  |  file://./token  |  secret://api-key"),
        ),
        description="Resolve an env:// / file:// / secret:// value reference.",
    ))
    specs.append(CommandSpec(
        "AC_resolve_refs", "Security", "Secret Ref: Resolve In Structure",
        fields=(
            FieldSpec("obj", FieldType.STRING,
                      placeholder='{"token": "env://TOKEN", "url": "..."}'),
        ),
        description="Recursively resolve references inside a JSON structure.",
    ))
    specs.append(CommandSpec(
        "AC_validate_config", "Data", "Config Schema: Validate",
        fields=(
            FieldSpec("schema", FieldType.STRING,
                      placeholder='{"port": {"type": "int", "required": true}}'),
            FieldSpec("config", FieldType.STRING,
                      placeholder='{"port": "8080"}'),
        ),
        description="Validate a config mapping against a typed schema spec.",
    ))
    specs.append(CommandSpec(
        "AC_redact_config", "Security", "Redaction: Redact Config",
        fields=(
            FieldSpec("obj", FieldType.STRING,
                      placeholder='{"db": {"password": "hunter2longvalue"}}'),
            FieldSpec("mask", FieldType.STRING, optional=True, default="***"),
        ),
        description="Mask secret-looking values in a JSON config structure.",
    ))
    specs.append(CommandSpec(
        "AC_redact_secret_text", "Security", "Redaction: Redact Secret Text",
        fields=(
            FieldSpec("text", FieldType.STRING,
                      placeholder="log line with AKIA... or a bearer token"),
            FieldSpec("mask", FieldType.STRING, optional=True, default="***"),
        ),
        description="Mask secret-looking tokens within a free-text string.",
    ))
    specs.append(CommandSpec(
        "AC_profile_rows", "Data", "Data Profile: Profile Rows",
        fields=(
            FieldSpec("rows", FieldType.STRING,
                      placeholder='[{"id": 1, "name": "a"}, {"id": 2}]'),
            FieldSpec("columns", FieldType.STRING, optional=True,
                      placeholder='["id", "name"] (omit for all)'),
        ),
        description="Per-column stats: null fraction, cardinality, type, ranges.",
    ))
    specs.append(CommandSpec(
        "AC_infer_schema", "Data", "Data Profile: Infer Schema",
        fields=(
            FieldSpec("rows", FieldType.STRING,
                      placeholder='[{"id": 1, "name": "a"}, {"id": 2}]'),
            FieldSpec("columns", FieldType.STRING, optional=True,
                      placeholder='["id", "name"] (omit for all)'),
        ),
        description="Infer a validate_rows-compatible schema from observed rows.",
    ))
    specs.append(CommandSpec(
        "AC_parse_problem", "Data", "HTTP Problem (RFC 9457): Parse",
        fields=(
            FieldSpec("response", FieldType.STRING,
                      placeholder='{"status": 400, "headers": '
                                  '{"Content-Type": "application/problem+json"}, '
                                  '"json": {"title": "Bad Request"}}'),
        ),
        description="Parse an application/problem+json error response.",
    ))
    specs.append(CommandSpec(
        "AC_parse_dotenv", "Data", "Dotenv: Parse Text",
        fields=(
            FieldSpec("text", FieldType.STRING,
                      placeholder='KEY=value\nexport TOKEN="abc"  # comment'),
        ),
        description="Parse .env text (KEY=VALUE, quotes, escapes) into values.",
    ))
    specs.append(CommandSpec(
        "AC_load_dotenv", "Data", "Dotenv: Load File",
        fields=(
            FieldSpec("path", FieldType.STRING, placeholder=".env"),
            FieldSpec("override", FieldType.BOOL, optional=True, default=False),
        ),
        description="Load a .env file into a values dict.",
    ))
    specs.append(CommandSpec(
        "AC_parse_sse", "Data", "SSE: Parse Event Stream",
        fields=(
            FieldSpec("text", FieldType.STRING,
                      placeholder='event: ping\ndata: {"x": 1}\n\n'),
        ),
        description="Parse a text/event-stream blob into events.",
    ))
    specs.append(CommandSpec(
        "AC_parse_link_header", "Data", "Link Header: Parse",
        fields=(
            FieldSpec("value", FieldType.STRING,
                      placeholder='<https://api/x?page=2>; rel="next"'),
        ),
        description="Parse an RFC 8288 Link header into links.",
    ))
    specs.append(CommandSpec(
        "AC_next_url", "Data", "Link Header: Next URL",
        fields=(
            FieldSpec("value", FieldType.STRING,
                      placeholder='<https://api/x?page=2>; rel="next"'),
        ),
        description="Return the rel=next URL from a Link header.",
    ))
    specs.append(CommandSpec(
        "AC_build_multipart", "Data", "Multipart: Build Body",
        fields=(
            FieldSpec("fields", FieldType.STRING, optional=True,
                      placeholder='{"name": "report", "tag": "v1"}'),
            FieldSpec("files", FieldType.STRING, optional=True,
                      placeholder='[{"name": "f", "filename": "a.txt", '
                                  '"content": "hi"}]'),
            FieldSpec("boundary", FieldType.STRING, optional=True),
        ),
        description="Build a multipart/form-data body (base64) for upload.",
    ))
    specs.append(CommandSpec(
        "AC_parse_multipart", "Data", "Multipart: Parse Body",
        fields=(
            FieldSpec("content_type", FieldType.STRING,
                      placeholder="multipart/form-data; boundary=..."),
            FieldSpec("body_base64", FieldType.STRING,
                      placeholder="<base64 body>"),
        ),
        description="Parse a base64 multipart body into fields and files.",
    ))
    specs.append(CommandSpec(
        "AC_decode_body", "Data", "HTTP Content: Decode Body",
        fields=(
            FieldSpec("headers", FieldType.STRING,
                      placeholder='{"Content-Encoding": "gzip"}'),
            FieldSpec("body_base64", FieldType.STRING,
                      placeholder="<base64 compressed body>"),
        ),
        description="Decode a gzip/deflate response body by Content-Encoding.",
    ))
    specs.append(CommandSpec(
        "AC_parse_quality_values", "Data", "HTTP Content: Quality Values",
        fields=(
            FieldSpec("header", FieldType.STRING,
                      placeholder="text/html;q=0.8, application/json"),
        ),
        description="Parse an Accept/Accept-Encoding header by q-value.",
    ))
    specs.append(CommandSpec(
        "AC_cookie_header", "Data", "Cookie Jar: Build Cookie Header",
        fields=(
            FieldSpec("set_cookies", FieldType.STRING,
                      placeholder='sid=abc; Path=/   (or ["a=1", "b=2"])'),
        ),
        description="Build a Cookie request header from Set-Cookie value(s).",
    ))
    specs.append(CommandSpec(
        "AC_parse_set_cookie", "Data", "Cookie Jar: Parse Set-Cookie",
        fields=(
            FieldSpec("header", FieldType.STRING,
                      placeholder="sid=abc; Path=/; Max-Age=3600"),
        ),
        description="Parse one Set-Cookie header into name/value/attributes.",
    ))
    specs.append(CommandSpec(
        "AC_parse_cache_control", "Data", "HTTP Conditional: Cache-Control",
        fields=(
            FieldSpec("headers", FieldType.STRING,
                      placeholder='{"Cache-Control": "max-age=60, public"}'),
        ),
        description="Parse a Cache-Control header into directives.",
    ))
    specs.append(CommandSpec(
        "AC_store_validators", "Data", "HTTP Conditional: Store Validators",
        fields=(
            FieldSpec("response", FieldType.STRING,
                      placeholder='{"headers": {"ETag": "\\"abc\\""}}'),
        ),
        description="Extract ETag / Last-Modified / Cache-Control validators.",
    ))
    specs.append(CommandSpec(
        "AC_resolve_config", "Data", "Layered Config: Resolve",
        fields=(
            FieldSpec("layers", FieldType.STRING,
                      placeholder='[{"name": "defaults", "mapping": {}}, '
                                  '{"name": "env", "mapping": {}, '
                                  '"priority": 10}]'),
        ),
        description="Deep-merge ordered config layers into one config.",
    ))
    specs.append(CommandSpec(
        "AC_explain_config", "Data", "Layered Config: Explain Key",
        fields=(
            FieldSpec("layers", FieldType.STRING,
                      placeholder='[{"name": "defaults", "mapping": {}}]'),
            FieldSpec("key", FieldType.STRING, placeholder="db.host"),
        ),
        description="Show the value and winning layer for a dotted config key.",
    ))
    specs.append(CommandSpec(
        "AC_detect_drift", "Data", "Data Drift: Detect (PSI + KS)",
        fields=(
            FieldSpec("reference", FieldType.STRING,
                      placeholder="[1.0, 2.0, 3.0, ...]"),
            FieldSpec("current", FieldType.STRING,
                      placeholder="[1.1, 2.2, 9.9, ...]"),
            FieldSpec("threshold", FieldType.FLOAT, optional=True,
                      default=0.25),
            FieldSpec("bins", FieldType.INT, optional=True, default=10),
        ),
        description="Numeric drift: Population Stability Index + KS two-sample.",
    ))
    specs.append(CommandSpec(
        "AC_categorical_drift", "Data", "Data Drift: Categorical",
        fields=(
            FieldSpec("reference", FieldType.STRING,
                      placeholder='["a", "b", "a", ...]'),
            FieldSpec("current", FieldType.STRING,
                      placeholder='["a", "c", "c", ...]'),
        ),
        description="Categorical drift: chi-square + total-variation distance.",
    ))
    specs.append(CommandSpec(
        "AC_check_compatibility", "Data", "Schema Compat: Check",
        fields=(
            FieldSpec("old", FieldType.STRING,
                      placeholder='{"properties": {"id": {"type": "integer"}}}'),
            FieldSpec("new", FieldType.STRING,
                      placeholder='{"properties": {"id": {"type": "integer"}}, '
                                  '"required": ["id"]}'),
            FieldSpec("mode", FieldType.STRING, optional=True,
                      placeholder="backward | forward | full"),
        ),
        description="Classify JSON-Schema changes as backward/forward/full.",
    ))
    specs.append(CommandSpec(
        "AC_ts_rate", "Data", "Time-Series: Counter Rate",
        fields=(
            FieldSpec("series", FieldType.STRING,
                      placeholder="[[0, 0], [10, 50], [20, 120]]"),
            FieldSpec("window_s", FieldType.FLOAT, optional=True),
        ),
        description="Per-second counter rate (reset-aware) over a series.",
    ))
    specs.append(CommandSpec(
        "AC_ts_downsample", "Data", "Time-Series: Downsample",
        fields=(
            FieldSpec("series", FieldType.STRING,
                      placeholder="[[0, 1], [5, 3], [12, 9]]"),
            FieldSpec("bucket_s", FieldType.FLOAT, placeholder="10"),
            FieldSpec("agg", FieldType.STRING, optional=True,
                      placeholder="avg|sum|min|max|first|last|count"),
        ),
        description="Roll a series into tumbling buckets by aggregate.",
    ))
    specs.append(CommandSpec(
        "AC_detect_anomalies", "Data", "Anomaly: Detect in Series",
        fields=(
            FieldSpec("values", FieldType.STRING,
                      placeholder="[10, 11, 9, 10, 95, 10]"),
            FieldSpec("method", FieldType.STRING, optional=True,
                      placeholder="mad | zscore"),
            FieldSpec("threshold", FieldType.FLOAT, optional=True),
        ),
        description="Flag outliers in a numeric series (MAD / z-score).",
    ))
    specs.append(CommandSpec(
        "AC_sma", "Data", "Smoothing: Simple Moving Average",
        fields=(
            FieldSpec("values", FieldType.STRING, placeholder="[1, 2, 3, 4, 5]"),
            FieldSpec("window", FieldType.INT, placeholder="3"),
        ),
        description="Trailing simple moving average over a window.",
    ))
    specs.append(CommandSpec(
        "AC_ewma", "Data", "Smoothing: EWMA",
        fields=(
            FieldSpec("values", FieldType.STRING, placeholder="[1, 2, 3, 4, 5]"),
            FieldSpec("alpha", FieldType.FLOAT, optional=True, default=0.3),
        ),
        description="Exponentially-weighted moving average of a series.",
    ))
    specs.append(CommandSpec(
        "AC_idempotency_begin", "Flow", "Idempotency: Begin",
        fields=(
            FieldSpec("name", FieldType.STRING, placeholder="payments"),
            FieldSpec("key", FieldType.STRING, placeholder="order-42"),
            FieldSpec("request", FieldType.STRING, optional=True,
                      placeholder='{"amount": 100}'),
        ),
        description="Register/look up an idempotency key (new/in_progress/done).",
    ))
    specs.append(CommandSpec(
        "AC_idempotency_complete", "Flow", "Idempotency: Complete",
        fields=(
            FieldSpec("name", FieldType.STRING, placeholder="payments"),
            FieldSpec("key", FieldType.STRING, placeholder="order-42"),
            FieldSpec("response", FieldType.STRING, placeholder='{"ok": true}'),
        ),
        description="Store the completed response for an idempotency key.",
    ))
    specs.append(CommandSpec(
        "AC_dedup_check", "Flow", "Dedup Window: Check",
        fields=(
            FieldSpec("name", FieldType.STRING, placeholder="webhooks"),
            FieldSpec("message_id", FieldType.STRING, placeholder="evt-123"),
            FieldSpec("ttl_s", FieldType.FLOAT, optional=True, default=3600),
        ),
        description="Check-and-mark a message id; first_seen false on duplicate.",
    ))
    specs.append(CommandSpec(
        "AC_sequence_observe", "Flow", "Sequence: Observe",
        fields=(
            FieldSpec("name", FieldType.STRING, placeholder="ingest"),
            FieldSpec("stream_id", FieldType.STRING, placeholder="orders"),
            FieldSpec("seq", FieldType.INT, placeholder="14"),
        ),
        description="Classify a sequence number (ok/duplicate/gap/reorder).",
    ))
    specs.append(CommandSpec(
        "AC_cas_put", "Flow", "Optimistic: Put (CAS)",
        fields=(
            FieldSpec("name", FieldType.STRING, placeholder="config"),
            FieldSpec("key", FieldType.STRING, placeholder="db.host"),
            FieldSpec("value", FieldType.STRING, placeholder='"prod-1"'),
            FieldSpec("expected_version", FieldType.INT, optional=True),
        ),
        description="Put only if expected_version matches (returns new version).",
    ))
    specs.append(CommandSpec(
        "AC_cas_get", "Flow", "Optimistic: Get",
        fields=(
            FieldSpec("name", FieldType.STRING, placeholder="config"),
            FieldSpec("key", FieldType.STRING, placeholder="db.host"),
        ),
        description="Read a versioned record {value, version}.",
    ))
    specs.append(CommandSpec(
        "AC_outbox_enqueue", "Flow", "Outbox: Enqueue",
        fields=(
            FieldSpec("name", FieldType.STRING, placeholder="orders"),
            FieldSpec("event", FieldType.STRING,
                      placeholder='{"type": "order.created", "id": 7}'),
        ),
        description="Durably buffer an event for at-least-once delivery.",
    ))
    specs.append(CommandSpec(
        "AC_outbox_pending", "Flow", "Outbox: Pending",
        fields=(
            FieldSpec("name", FieldType.STRING, placeholder="orders"),
        ),
        description="List events still awaiting successful delivery.",
    ))
    specs.append(CommandSpec(
        "AC_collation_sort", "Data", "Text: Collation Sort",
        fields=(
            FieldSpec("items", FieldType.STRING,
                      placeholder='["zebra", "apple", "Äpple"]'),
            FieldSpec("strength", FieldType.STRING, optional=True,
                      placeholder="tertiary"),
            FieldSpec("tailoring", FieldType.STRING, optional=True,
                      placeholder="abc...xyzåäö"),
            FieldSpec("reverse", FieldType.BOOL, optional=True),
        ),
        description="Locale-aware sort (base letter, then accent, then case).",
    ))
    specs.append(CommandSpec(
        "AC_collation_compare", "Data", "Text: Collation Compare",
        fields=(
            FieldSpec("first", FieldType.STRING, placeholder="apple"),
            FieldSpec("second", FieldType.STRING, placeholder="Äpple"),
            FieldSpec("strength", FieldType.STRING, optional=True,
                      placeholder="tertiary"),
            FieldSpec("tailoring", FieldType.STRING, optional=True),
        ),
        description="Locale-aware compare; returns order -1/0/1.",
    ))
    specs.append(CommandSpec(
        "AC_confusable_scan", "Data", "Text: Confusable Scan",
        fields=(
            FieldSpec("text", FieldType.STRING, placeholder="pаypal.com"),
        ),
        description="Homoglyph / mixed-script spoofing report for a string.",
    ))
    specs.append(CommandSpec(
        "AC_confusable_compare", "Data", "Text: Confusable Compare",
        fields=(
            FieldSpec("first", FieldType.STRING, placeholder="paypal"),
            FieldSpec("second", FieldType.STRING, placeholder="pаypal"),
        ),
        description="Whether two strings share the same confusable skeleton.",
    ))
    specs.append(CommandSpec(
        "AC_readability_report", "Data", "Text: Readability Report",
        fields=(
            FieldSpec("text", FieldType.STRING,
                      placeholder="The cat sat on the mat."),
        ),
        description="Flesch / Flesch-Kincaid / Fog / SMOG / ARI scores + counts.",
    ))
    specs.append(CommandSpec(
        "AC_bidi_check", "Data", "Text: Bidi / Trojan-Source Check",
        fields=(
            FieldSpec("text", FieldType.STRING, placeholder="value = admin"),
        ),
        description="Bidi controls, nesting balance, base dir, Trojan-source flag.",
    ))
    specs.append(CommandSpec(
        "AC_bidi_strip", "Data", "Text: Strip Bidi Controls",
        fields=(
            FieldSpec("text", FieldType.STRING, placeholder="value = admin"),
        ),
        description="Remove all bidirectional control characters from a string.",
    ))
    specs.append(CommandSpec(
        "AC_format_list", "Data", "Text: Format List",
        fields=(
            FieldSpec("items", FieldType.STRING,
                      placeholder='["apple", "pear", "grape"]'),
            FieldSpec("style", FieldType.STRING, optional=True,
                      placeholder="and | or | unit"),
            FieldSpec("locale", FieldType.STRING, optional=True,
                      placeholder="en | es | fr | de | pt"),
        ),
        description="Join items into a localised list ('A, B, and C').",
    ))
    specs.append(CommandSpec(
        "AC_format_message", "Data", "Text: Format Message (ICU)",
        fields=(
            FieldSpec("pattern", FieldType.STRING,
                      placeholder="{count, plural, one {# item} other {# items}}"),
            FieldSpec("args", FieldType.STRING, placeholder='{"count": 3}'),
            FieldSpec("locale", FieldType.STRING, optional=True,
                      placeholder="en | fr"),
        ),
        description="Render ICU plural/select/selectordinal message.",
    ))
    specs.append(CommandSpec(
        "AC_gettext_translate", "Data", "Text: gettext Translate (.po)",
        fields=(
            FieldSpec("po", FieldType.STRING,
                      placeholder='msgid "Hello"\\nmsgstr "Hola"'),
            FieldSpec("msgid", FieldType.STRING, placeholder="Hello"),
            FieldSpec("context", FieldType.STRING, optional=True),
        ),
        description="Look up a singular translation in a gettext .po catalog.",
    ))
    specs.append(CommandSpec(
        "AC_gettext_ngettext", "Data", "Text: gettext Plural (.po)",
        fields=(
            FieldSpec("po", FieldType.STRING, placeholder="(.po source)"),
            FieldSpec("msgid", FieldType.STRING, placeholder="file"),
            FieldSpec("msgid_plural", FieldType.STRING, placeholder="files"),
            FieldSpec("n", FieldType.INT, placeholder="3"),
        ),
        description="Pick the plural-correct translation for count n.",
    ))
    specs.append(CommandSpec(
        "AC_checksum_validate", "Data", "Checksum: Validate",
        fields=(
            FieldSpec("scheme", FieldType.STRING,
                      placeholder="luhn | verhoeff | damm | mod97"),
            FieldSpec("number", FieldType.STRING, placeholder="4111111111111111"),
        ),
        description="Validate a number's check digit (Luhn/Verhoeff/Damm/mod97).",
    ))
    specs.append(CommandSpec(
        "AC_checksum_digit", "Data", "Checksum: Check Digit",
        fields=(
            FieldSpec("scheme", FieldType.STRING,
                      placeholder="luhn | verhoeff | damm | mod97"),
            FieldSpec("partial", FieldType.STRING, placeholder="799273987"),
        ),
        description="Compute the check digit(s) to append to a value.",
    ))
    specs.append(CommandSpec(
        "AC_diff_rows", "Data", "Dataset Diff: Rows by Key",
        fields=(
            FieldSpec("old_rows", FieldType.STRING,
                      placeholder='[{"id": 1, "name": "a"}]'),
            FieldSpec("new_rows", FieldType.STRING,
                      placeholder='[{"id": 1, "name": "b"}]'),
            FieldSpec("key", FieldType.STRING,
                      placeholder='id  (or ["id", "region"])'),
        ),
        description="Diff two row-sets by key: added/removed/changed/unchanged.",
    ))
    specs.append(CommandSpec(
        "AC_cell_changes", "Data", "Dataset Diff: Cell Changes",
        fields=(
            FieldSpec("old_rows", FieldType.STRING,
                      placeholder='[{"id": 1, "name": "a"}]'),
            FieldSpec("new_rows", FieldType.STRING,
                      placeholder='[{"id": 1, "name": "b"}]'),
            FieldSpec("key", FieldType.STRING, placeholder="id"),
        ),
        description="Per-cell {key, column, old, new} changes between row-sets.",
    ))
    specs.append(CommandSpec(
        "AC_check_foreign_key", "Data", "Referential: Foreign Key",
        fields=(
            FieldSpec("child_rows", FieldType.STRING,
                      placeholder='[{"user_id": 1}]'),
            FieldSpec("child_col", FieldType.STRING, placeholder="user_id"),
            FieldSpec("parent_rows", FieldType.STRING,
                      placeholder='[{"id": 1}]'),
            FieldSpec("parent_col", FieldType.STRING, placeholder="id"),
        ),
        description="Every child value must exist in the parent column.",
    ))
    specs.append(CommandSpec(
        "AC_check_unique_key", "Data", "Referential: Unique Key",
        fields=(
            FieldSpec("rows", FieldType.STRING,
                      placeholder='[{"id": 1}, {"id": 1}]'),
            FieldSpec("cols", FieldType.STRING,
                      placeholder='id  (or ["region", "id"])'),
        ),
        description="A single or composite key must be unique across rows.",
    ))
    specs.append(CommandSpec(
        "AC_check_accepted_values", "Data", "Referential: Accepted Values",
        fields=(
            FieldSpec("rows", FieldType.STRING,
                      placeholder='[{"status": "open"}]'),
            FieldSpec("col", FieldType.STRING, placeholder="status"),
            FieldSpec("allowed", FieldType.STRING,
                      placeholder='["open", "closed"]'),
        ),
        description="Every non-null column value must be in the allowed set.",
    ))
    specs.append(CommandSpec(
        "AC_check_row_count", "Data", "Referential: Row Count",
        fields=(
            FieldSpec("rows", FieldType.STRING, placeholder='[{"id": 1}]'),
            FieldSpec("minimum", FieldType.INT, optional=True),
            FieldSpec("maximum", FieldType.INT, optional=True),
        ),
        description="The row count must fall within the given bounds.",
    ))
    specs.append(CommandSpec(
        "AC_rate_limit", "Flow", "Rate Limit (Token Bucket)",
        fields=(
            FieldSpec("name", FieldType.STRING),
            FieldSpec("rate", FieldType.FLOAT, optional=True, default=1.0),
            FieldSpec("capacity", FieldType.FLOAT, optional=True, default=1.0),
            FieldSpec("n", FieldType.FLOAT, optional=True, default=1.0),
        ),
        description="Try to take 'n' tokens from a named limiter; {acquired, wait}.",
    ))


def _add_input_macro_specs(specs: List[CommandSpec]) -> None:
    specs.append(CommandSpec(
        "AC_replay_timeline", "Flow", "Replay Timed Events",
        fields=(FieldSpec("speed", FieldType.FLOAT, optional=True,
                          default=1.0),),
        description="Replay 'events' (JSON view) honoring delta_ms, scaled by "
                    "speed.",
    ))
    specs.append(CommandSpec(
        "AC_input_sequence", "Flow", "Run Input Sequence (DSL)",
        description="Run 'steps' (JSON view): press/hold/release/repeat/wait.",
    ))


def _add_screen_state_specs(specs: List[CommandSpec]) -> None:
    app = FieldSpec("app_name", FieldType.STRING, optional=True)
    specs.append(CommandSpec(
        "AC_screen_snapshot", "Native UI", "Screen: Snapshot Baseline",
        fields=(app,),
        description="Snapshot the a11y tree as a semantic-diff baseline.",
    ))
    specs.append(CommandSpec(
        "AC_screen_diff", "Native UI", "Screen: Diff Snapshots",
        description="Semantic diff of 'before'/'after' snapshots (JSON view).",
    ))
    specs.append(CommandSpec(
        "AC_screen_changed", "Native UI", "Screen: What Changed",
        fields=(app,),
        description="Diff the live screen against the last snapshot baseline.",
    ))
    specs.append(CommandSpec(
        "AC_describe_screen", "Native UI", "Screen: Describe",
        fields=(app,),
        description="Structured 'where am I' (role counts + control labels).",
    ))


def _add_set_of_marks_specs(specs: List[CommandSpec]) -> None:
    specs.append(CommandSpec(
        "AC_mark_screen", "Native UI", "Set-of-Marks: Number Elements",
        fields=(
            FieldSpec("app_name", FieldType.STRING, optional=True),
            FieldSpec("render_path", FieldType.FILE_PATH, optional=True),
        ),
        description="Number live UI elements (id->bbox legend) for VLM "
                    "grounding; optional numbered-box overlay screenshot.",
    ))
    specs.append(CommandSpec(
        "AC_mark_click", "Native UI", "Set-of-Marks: Click Number",
        fields=(FieldSpec("mark_id", FieldType.INT),),
        description="Click the element behind a numbered mark.",
    ))


def _add_checkpoint_specs(specs: List[CommandSpec]) -> None:
    run_id = FieldSpec("run_id", FieldType.STRING)
    db = FieldSpec("db", FieldType.FILE_PATH)
    specs.append(CommandSpec(
        "AC_run_resumable", "Flow", "Run Resumable (checkpoint)",
        fields=(run_id, db),
        description="Run 'actions' (JSON view) with checkpoint/resume keyed "
                    "by run_id; resumes past completed steps after a crash.",
    ))
    specs.append(CommandSpec(
        "AC_checkpoint_status", "Flow", "Checkpoint: Status",
        fields=(run_id, db),
        description="Return the saved checkpoint for a run (step + variables).",
    ))
    specs.append(CommandSpec(
        "AC_checkpoint_clear", "Flow", "Checkpoint: Clear",
        fields=(run_id, db),
        description="Delete a run's checkpoint.",
    ))
    specs.append(CommandSpec(
        "AC_wcag_audit", "Accessibility", "WCAG 2.2 Conformance Audit",
        fields=(
            FieldSpec("app_name", FieldType.STRING, optional=True),
            FieldSpec("level", FieldType.ENUM, choices=("A", "AA", "AAA"),
                      optional=True, default="AA"),
            FieldSpec("min_target_px", FieldType.INT, optional=True,
                      default=24),
        ),
        description="WCAG 2.2 audit: SC-tagged findings + Target Size 2.5.8.",
    ))
    _add_observer_specs(specs)
    _add_ops_specs(specs)


def _add_ops_specs(specs: List[CommandSpec]) -> None:
    specs.append(CommandSpec(
        "AC_generate_sbom", "Tools", "Generate SBOM (CycloneDX)",
        fields=(
            FieldSpec("path", FieldType.FILE_PATH, optional=True,
                      default="sbom.cdx.json"),
            FieldSpec("root", FieldType.STRING, optional=True,
                      default="je_auto_control"),
        ),
        description="Emit a CycloneDX 1.6 dependency SBOM for the project.",
    ))
    specs.append(CommandSpec(
        "AC_shard_suite", "Testing", "Shard Suite (duration-aware)",
        fields=(
            FieldSpec("shards", FieldType.INT, default=2),
            FieldSpec("history_path", FieldType.FILE_PATH, optional=True),
            FieldSpec("window", FieldType.INT, optional=True, default=20),
        ),
        description="Balance 'flows' (JSON view) into N shards by duration.",
    ))
    specs.append(CommandSpec(
        "AC_merge_results", "Testing", "Merge Shard Results",
        description="Merge per-shard 'reports' (JSON view) into one report.",
    ))


def _add_observer_specs(specs: List[CommandSpec]) -> None:
    specs.append(CommandSpec(
        "AC_observe_add", "Flow", "Observe: Add Watch",
        fields=(
            FieldSpec("name", FieldType.STRING),
            FieldSpec("kind", FieldType.ENUM,
                      choices=("image", "text", "pixel"), default="image"),
            FieldSpec("event", FieldType.ENUM,
                      choices=("appear", "vanish", "change"),
                      default="appear"),
            FieldSpec("image", FieldType.FILE_PATH, optional=True),
            FieldSpec("threshold", FieldType.FLOAT, optional=True,
                      default=0.8),
            FieldSpec("text", FieldType.STRING, optional=True),
            FieldSpec("x", FieldType.INT, optional=True),
            FieldSpec("y", FieldType.INT, optional=True),
        ),
        description="Run 'actions' (JSON view) on appear/vanish/change of an "
                    "image/text/pixel.",
    ))
    specs.append(CommandSpec(
        "AC_observe_remove", "Flow", "Observe: Remove Watch",
        fields=(FieldSpec("name", FieldType.STRING),),
        description="Remove a registered watch.",
    ))
    specs.append(CommandSpec(
        "AC_observe_list", "Flow", "Observe: List Watches",
        description="List registered watch names."))
    specs.append(CommandSpec(
        "AC_observe_poll", "Flow", "Observe: Poll Once",
        description="Evaluate all watches once; return fired events."))
    specs.append(CommandSpec(
        "AC_observe_start", "Flow", "Observe: Start",
        description="Start the background observer thread."))
    specs.append(CommandSpec(
        "AC_observe_stop", "Flow", "Observe: Stop",
        description="Stop the background observer thread."))


def _add_i18n_specs(specs: List[CommandSpec]) -> None:
    specs.append(CommandSpec(
        "AC_pseudo_localize", "Data", "Pseudo-Localize",
        fields=(
            FieldSpec("text", FieldType.STRING, optional=True),
            FieldSpec("expansion", FieldType.FLOAT, optional=True,
                      default=0.4),
        ),
        description="Accent+pad a string (or 'mapping' via JSON view) for "
                    "i18n stress testing.",
    ))
    specs.append(CommandSpec(
        "AC_check_overflow", "Data", "Check Text Overflow",
        fields=(
            FieldSpec("app_name", FieldType.STRING, optional=True),
            FieldSpec("avg_char_px", FieldType.FLOAT, optional=True,
                      default=7.0),
        ),
        description="Flag text wider than its widget (translation overflow).",
    ))
    specs.append(CommandSpec(
        "AC_check_catalog", "Data", "Check Translation Catalog",
        description="Diff 'target' vs 'base' catalog (JSON view): missing / "
                    "empty / placeholder mismatch.",
    ))


def _add_data_quality_specs(specs: List[CommandSpec]) -> None:
    specs.append(CommandSpec(
        "AC_validate_rows", "Data", "Validate Rows (schema)",
        description="Validate 'rows' against a 'schema' (both via JSON view).",
    ))
    specs.append(CommandSpec(
        "AC_extract_fields", "Data", "Extract Fields (regex)",
        fields=(FieldSpec("text", FieldType.STRING),),
        description="Pull email/url/phone/amount/... from text; 'fields' / "
                    "'patterns' via JSON view.",
    ))
    specs.append(CommandSpec(
        "AC_mask_rows", "Data", "Mask Rows",
        description="Mask columns in 'rows' per 'rules' (redact/hash/partial),"
                    " via JSON view.",
    ))


def _add_memory_specs(specs: List[CommandSpec]) -> None:
    db = FieldSpec("db", FieldType.FILE_PATH)
    specs.append(CommandSpec(
        "AC_memory_remember", "Agent", "Memory: Remember Episode",
        fields=(db, FieldSpec("goal", FieldType.STRING),
                FieldSpec("outcome", FieldType.STRING, optional=True)),
        description="Store an episode (goal -> 'steps' via JSON view -> "
                    "outcome).",
    ))
    specs.append(CommandSpec(
        "AC_memory_recall", "Agent", "Memory: Recall",
        fields=(db, FieldSpec("query", FieldType.STRING),
                FieldSpec("limit", FieldType.INT, optional=True, default=5)),
        description="Recall episodes most relevant to a query.",
    ))
    specs.append(CommandSpec(
        "AC_memory_recent", "Agent", "Memory: Recent",
        fields=(db, FieldSpec("limit", FieldType.INT, optional=True,
                              default=10)),
        description="List the most recent episodes.",
    ))
    specs.append(CommandSpec(
        "AC_memory_forget", "Agent", "Memory: Forget",
        fields=(db, FieldSpec("episode_id", FieldType.INT)),
        description="Delete an episode by id.",
    ))
    specs.append(CommandSpec(
        "AC_memory_stats", "Agent", "Memory: Stats",
        fields=(db,),
        description="Episode count for a memory store.",
    ))
    specs.append(CommandSpec(
        "AC_seed_everything", "Flow", "Seed RNG (deterministic)",
        fields=(FieldSpec("seed", FieldType.INT, optional=True, default=0),),
        description="Seed all RNG run-wide for reproducible runs.",
    ))


def _add_office_specs(specs: List[CommandSpec]) -> None:
    xlsx = FieldSpec("path", FieldType.FILE_PATH)
    specs.append(CommandSpec(
        "AC_read_workbook", "Office", "Excel: Read Workbook",
        fields=(xlsx, FieldSpec("sheet", FieldType.STRING, optional=True)),
        description="Read an .xlsx worksheet into rows (needs [office] extra).",
    ))
    specs.append(CommandSpec(
        "AC_write_workbook", "Office", "Excel: Write Workbook",
        fields=(xlsx, FieldSpec("sheet", FieldType.STRING, optional=True,
                                default="Sheet1")),
        description="Write 'rows' (JSON view) to an .xlsx file.",
    ))
    specs.append(CommandSpec(
        "AC_read_document", "Office", "Word: Read Document",
        fields=(xlsx,),
        description="Read a .docx file's paragraphs (needs [office] extra).",
    ))
    specs.append(CommandSpec(
        "AC_write_document", "Office", "Word: Write Document",
        fields=(xlsx,),
        description="Write 'paragraphs' (JSON view) to a .docx file.",
    ))
    specs.append(CommandSpec(
        "AC_read_presentation", "Office", "PowerPoint: Read",
        fields=(xlsx,),
        description="Read a .pptx file's per-slide text (needs [office]).",
    ))
    specs.append(CommandSpec(
        "AC_write_presentation", "Office", "PowerPoint: Write",
        fields=(xlsx,),
        description="Write 'slides' (JSON view) to a .pptx file.",
    ))


def _add_authoring_specs(specs: List[CommandSpec]) -> None:
    path = FieldSpec("path", FieldType.FILE_PATH)
    key = FieldSpec("key", FieldType.STRING)
    specs.append(CommandSpec(
        "AC_element_save", "Native UI", "Element: Save Locator",
        fields=(path, key,
                FieldSpec("name", FieldType.STRING, optional=True),
                FieldSpec("role", FieldType.STRING, optional=True),
                FieldSpec("app_name", FieldType.STRING, optional=True)),
        description="Save a named native-UI locator (object repository).",
    ))
    specs.append(CommandSpec(
        "AC_element_find", "Native UI", "Element: Find Saved",
        fields=(path, key),
        description="Resolve a saved locator to a live element summary.",
    ))
    specs.append(CommandSpec(
        "AC_element_click", "Native UI", "Element: Click Saved",
        fields=(path, key),
        description="Click the element behind a saved locator.",
    ))
    specs.append(CommandSpec(
        "AC_element_remove", "Native UI", "Element: Remove Saved",
        fields=(path, key),
        description="Delete a saved locator.",
    ))
    specs.append(CommandSpec(
        "AC_element_list", "Native UI", "Element: List Saved",
        fields=(path,),
        description="List saved locator names in a repository file.",
    ))
    specs.append(CommandSpec(
        "AC_debug_trace", "Flow", "Debug: Trace Actions",
        fields=(FieldSpec("dry_run", FieldType.BOOL, optional=True,
                          default=False),),
        description="Run 'actions' (JSON view) and return a per-step trace.",
    ))


def _add_agent_specs(specs: List[CommandSpec]) -> None:
    path = FieldSpec("path", FieldType.FILE_PATH)
    name = FieldSpec("name", FieldType.STRING)
    specs.append(CommandSpec(
        "AC_skill_save", "Agent", "Skill: Save Playbook",
        fields=(path, name,
                FieldSpec("description", FieldType.STRING, optional=True),
                FieldSpec("tags", FieldType.STRING, optional=True)),
        description="Save a reusable action sequence ('actions' via JSON "
                    "view) under a name.",
    ))
    specs.append(CommandSpec(
        "AC_skill_run", "Agent", "Skill: Run Playbook",
        fields=(path, name),
        description="Execute a stored skill's actions.",
    ))
    specs.append(CommandSpec(
        "AC_skill_list", "Agent", "Skill: List",
        fields=(path,),
        description="List saved skill names.",
    ))
    specs.append(CommandSpec(
        "AC_skill_remove", "Agent", "Skill: Remove",
        fields=(path, name),
        description="Delete a saved skill.",
    ))
    specs.append(CommandSpec(
        "AC_skill_search", "Agent", "Skill: Search",
        fields=(path, FieldSpec("query", FieldType.STRING)),
        description="Search skills by name/description/tags.",
    ))
    specs.append(CommandSpec(
        "AC_guard_text", "Agent", "Guardrail: Scan Text",
        fields=(FieldSpec("text", FieldType.STRING),
                FieldSpec("threshold", FieldType.INT, optional=True,
                          default=2)),
        description="Scan untrusted text for prompt-injection patterns.",
    ))
    specs.append(CommandSpec(
        "AC_agent_card", "Agent", "A2A Agent Card",
        fields=(FieldSpec("path", FieldType.FILE_PATH, optional=True,
                          default="agent-card.json"),),
        description="Write an A2A agent card describing AutoControl's skills.",
    ))


def _add_tooling_specs(specs: List[CommandSpec]) -> None:
    specs.append(CommandSpec(
        "AC_generate_data", "Data", "Generate Synthetic Data",
        fields=(
            FieldSpec("count", FieldType.INT, optional=True, default=10),
            FieldSpec("path", FieldType.FILE_PATH, optional=True),
            FieldSpec("fmt", FieldType.ENUM, choices=("json", "csv"),
                      optional=True),
            FieldSpec("seed", FieldType.INT, optional=True),
        ),
        description="Generate seeded fake rows from a 'schema' (JSON view); "
                    "writes a file when 'path' is set.",
    ))
    specs.append(CommandSpec(
        "AC_mcp_manifest", "Tools", "MCP Registry Manifest",
        fields=(
            FieldSpec("path", FieldType.FILE_PATH, optional=True,
                      default="server.json"),
            FieldSpec("include_tools", FieldType.BOOL, optional=True,
                      default=False),
        ),
        description="Write an MCP registry server.json for this server.",
    ))
    specs.append(CommandSpec(
        "AC_rank_tests", "Testing", "Rank Tests by Risk",
        fields=(
            FieldSpec("history_path", FieldType.FILE_PATH, optional=True),
            FieldSpec("window", FieldType.INT, optional=True, default=10),
        ),
        description="Score 'flows' (JSON view) by risk from run history.",
    ))
    specs.append(CommandSpec(
        "AC_select_tests", "Testing", "Select Risky Tests",
        fields=(
            FieldSpec("k", FieldType.INT, optional=True),
            FieldSpec("threshold", FieldType.FLOAT, optional=True),
            FieldSpec("history_path", FieldType.FILE_PATH, optional=True),
            FieldSpec("window", FieldType.INT, optional=True, default=10),
        ),
        description="Pick riskiest 'flows' (JSON view): top-k or threshold.",
    ))


def _add_work_queue_specs(specs: List[CommandSpec]) -> None:
    db = FieldSpec("db", FieldType.FILE_PATH)
    name = FieldSpec("name", FieldType.STRING, optional=True, default="default")
    specs.append(CommandSpec(
        "AC_queue_add", "Queue", "Queue: Add Item",
        fields=(db, FieldSpec("reference", FieldType.STRING, optional=True),
                name),
        description="Enqueue a work item (data via JSON view); dedupes by "
                    "reference.",
    ))
    specs.append(CommandSpec(
        "AC_queue_next", "Queue", "Queue: Get Next Item",
        fields=(db, name),
        description="Atomically claim the next work item (performer).",
    ))
    specs.append(CommandSpec(
        "AC_queue_complete", "Queue", "Queue: Complete Item",
        fields=(db, FieldSpec("item_id", FieldType.INT), name),
        description="Mark a work item successfully processed.",
    ))
    specs.append(CommandSpec(
        "AC_queue_fail", "Queue", "Queue: Fail Item",
        fields=(db, FieldSpec("item_id", FieldType.INT),
                FieldSpec("error", FieldType.STRING),
                FieldSpec("kind", FieldType.ENUM,
                          choices=("application", "business"),
                          optional=True, default="application"),
                FieldSpec("max_retries", FieldType.INT, optional=True,
                          default=3),
                name),
        description="Fail an item; application errors retry, business don't.",
    ))
    specs.append(CommandSpec(
        "AC_queue_stats", "Queue", "Queue: Stats",
        fields=(db, name),
        description="Per-status counts for a work queue.",
    ))
    specs.append(CommandSpec(
        "AC_shell_command", "Shell", "Shell Command",
        fields=(FieldSpec("shell_command", FieldType.STRING),),
    ))
    specs.append(CommandSpec(
        "AC_take_golden", "Report", "Capture Golden Image",
        fields=(FieldSpec("path", FieldType.FILE_PATH),),
        description="Capture and save a baseline image for visual regression.",
    ))
    specs.append(CommandSpec(
        "AC_assert_visual", "Report", "Assert Visual (Golden)",
        fields=(
            FieldSpec("golden_path", FieldType.FILE_PATH),
            FieldSpec("tolerance", FieldType.FLOAT, optional=True, default=0.0,
                      min_value=0.0),
            FieldSpec("per_pixel_threshold", FieldType.INT, optional=True,
                      default=16, min_value=0),
            FieldSpec("diff_path", FieldType.FILE_PATH, optional=True),
        ),
        description=("Compare the screen to a golden image; first run creates "
                     "the baseline. Use the JSON view for a region / masks."),
    ))
    specs.append(CommandSpec(
        "AC_run_state_machine", "Flow", "Run State Machine",
        description=("Run a finite-state-machine; configure the 'spec' "
                     "{initial, states} dict in the JSON view."),
    ))
    specs.append(CommandSpec(
        "AC_shell_to_var", "Shell", "Shell Output into Variable",
        fields=(
            FieldSpec("command", FieldType.STRING),
            FieldSpec("var", FieldType.STRING, default="shell_output"),
            FieldSpec("timeout", FieldType.FLOAT, optional=True, default=30.0),
        ),
        description="Run a command and store its stdout in a flow variable.",
    ))
    specs.append(CommandSpec(
        "AC_read_file_to_var", "Shell", "Read File into Variable",
        fields=(
            FieldSpec("path", FieldType.FILE_PATH),
            FieldSpec("var", FieldType.STRING, default="file_content"),
            FieldSpec("encoding", FieldType.STRING, optional=True,
                      default="utf-8"),
        ),
        description="Read a file's text content into a flow variable.",
    ))
    specs.append(CommandSpec(
        "AC_sql_to_var", "Report", "SQL Query into Variable",
        fields=(
            FieldSpec("database", FieldType.FILE_PATH),
            FieldSpec("query", FieldType.STRING,
                      placeholder="SELECT name FROM users WHERE id = ?"),
            FieldSpec("var", FieldType.STRING, default="sql_result"),
            FieldSpec("fetch", FieldType.ENUM,
                      choices=("all", "one", "scalar"),
                      optional=True, default="all"),
        ),
        description=("Run a read-only SQLite SELECT; store rows / a row / a "
                     "scalar in a variable. Bind values via params (JSON view)."),
    ))
    specs.append(CommandSpec(
        "AC_assert_db", "Report", "Assert SQL Result",
        fields=(
            FieldSpec("database", FieldType.FILE_PATH),
            FieldSpec("query", FieldType.STRING,
                      placeholder="SELECT COUNT(*) FROM users"),
            FieldSpec("op", FieldType.ENUM,
                      choices=("eq", "ne", "lt", "le", "gt", "ge",
                               "contains", "startswith", "endswith"),
                      optional=True, default="eq"),
            FieldSpec("expected", FieldType.STRING, optional=True),
        ),
        description=("Run a scalar SELECT and assert its value (use the JSON "
                     "view for non-string expected values / params)."),
    ))
    specs.append(CommandSpec(
        "AC_http_to_var", "Report", "HTTP Request into Variable",
        fields=(
            FieldSpec("url", FieldType.STRING, placeholder="https://..."),
            FieldSpec("method", FieldType.ENUM,
                      choices=("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"),
                      optional=True, default="GET"),
            FieldSpec("var", FieldType.STRING, default="http_response"),
            FieldSpec("json_path", FieldType.STRING, optional=True,
                      placeholder="data.0.name"),
            FieldSpec("timeout", FieldType.FLOAT, optional=True, default=30.0),
        ),
        description="Request a URL; store the body or a JSON field in a variable.",
    ))
    specs.append(CommandSpec(
        "AC_pdf_to_var", "Report", "PDF Text into Variable",
        fields=(
            FieldSpec("path", FieldType.FILE_PATH),
            FieldSpec("var", FieldType.STRING, default="pdf_text"),
            FieldSpec("page", FieldType.INT, optional=True, min_value=1),
        ),
        description="Extract a PDF's text (all pages or one) into a variable.",
    ))
    specs.append(CommandSpec(
        "AC_assert_pdf_text", "Report", "Assert PDF Text",
        fields=(
            FieldSpec("path", FieldType.FILE_PATH),
            FieldSpec("text", FieldType.STRING),
            FieldSpec("present", FieldType.BOOL, optional=True, default=True),
            FieldSpec("page", FieldType.INT, optional=True, min_value=1),
            FieldSpec("case_sensitive", FieldType.BOOL, optional=True,
                      default=True),
        ),
        description="Assert text is present (or absent) in a PDF document.",
    ))
    specs.append(CommandSpec(
        "AC_send_email", "Report", "Send Email",
        description=("Send an email via SMTP. Configure the 'message' "
                     "{sender,to,subject,body,attachments} and 'smtp' "
                     "{host,port,username,password} dicts in the JSON view."),
    ))
    specs.append(CommandSpec(
        "AC_http_request", "Report", "HTTP Request",
        fields=(
            FieldSpec("url", FieldType.STRING, placeholder="https://..."),
            FieldSpec("method", FieldType.ENUM,
                      choices=("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"),
                      default="GET"),
            FieldSpec("data", FieldType.STRING, optional=True,
                      placeholder="raw request body"),
            FieldSpec("timeout", FieldType.FLOAT, optional=True, default=30.0),
        ),
        description=("Perform an HTTP(S) request; returns status/headers/text/"
                     "json. Use the JSON view for headers/json_body/auth."),
    ))
    specs.append(CommandSpec(
        "AC_execute_process", "Shell", "Start Executable",
        fields=(FieldSpec("program_path", FieldType.FILE_PATH),),
    ))
    specs.append(CommandSpec(
        "AC_move_to_trash", "Shell", "Move File to Recycle Bin",
        fields=(FieldSpec("path", FieldType.FILE_PATH),),
        description="Delete a file to the OS recycle bin (recoverable).",
    ))
    specs.append(CommandSpec(
        "AC_sign_action_file", "Security", "Sign Action File",
        fields=(
            FieldSpec("path", FieldType.FILE_PATH),
            FieldSpec("key", FieldType.STRING, optional=True),
        ),
        description="Write an HMAC-SHA256 signature sidecar for an action file.",
    ))
    specs.append(CommandSpec(
        "AC_verify_action_file", "Security", "Verify Action File",
        fields=(
            FieldSpec("path", FieldType.FILE_PATH),
            FieldSpec("key", FieldType.STRING, optional=True),
            FieldSpec("raise_on_fail", FieldType.BOOL, optional=True,
                      default=False),
        ),
        description="Verify an action file against its signature sidecar.",
    ))
    specs.append(CommandSpec(
        "AC_encrypt_action_file", "Security", "Encrypt Action File",
        fields=(
            FieldSpec("path", FieldType.FILE_PATH),
            FieldSpec("key", FieldType.STRING, optional=True),
        ),
        description="Fernet-encrypt an action file to <path>.enc.",
    ))
    specs.append(CommandSpec(
        "AC_decrypt_action_file", "Security", "Decrypt Action File",
        fields=(
            FieldSpec("enc_path", FieldType.FILE_PATH),
            FieldSpec("key", FieldType.STRING, optional=True),
            FieldSpec("output_path", FieldType.STRING, optional=True),
        ),
        description="Decrypt a Fernet-encrypted action file.",
    ))
    specs.append(CommandSpec(
        "AC_annotate_screenshot", "Report", "Annotate Screenshot",
        fields=(
            FieldSpec("source", FieldType.FILE_PATH),
            FieldSpec("output_path", FieldType.STRING),
            FieldSpec("annotations", FieldType.STRING, optional=True,
                      placeholder='[{"type":"box","rect":[10,10,80,40]}]'),
        ),
        description="Draw boxes / highlights / arrows / labels onto an image.",
    ))
    specs.append(CommandSpec(
        "AC_notify", "Report", "Desktop Notification",
        fields=(
            FieldSpec("title", FieldType.STRING),
            FieldSpec("message", FieldType.STRING, optional=True),
        ),
        description="Show a cross-platform desktop notification.",
    ))
    specs.append(CommandSpec(
        "AC_region_color_stats", "Report", "Region Colour Stats",
        fields=(
            FieldSpec("region", FieldType.STRING, optional=True,
                      placeholder="[0, 0, 200, 100]"),
            FieldSpec("buckets", FieldType.INT, optional=True, default=8,
                      min_value=1),
        ),
        description="Average + dominant colour of a screen region.",
    ))


_SPECS: Tuple[CommandSpec, ...] = tuple(_build_specs())
COMMAND_SPECS: Mapping[str, CommandSpec] = {spec.command: spec for spec in _SPECS}
CATEGORIES: Tuple[str, ...] = tuple(dict.fromkeys(spec.category for spec in _SPECS))


def specs_in_category(category: str) -> List[CommandSpec]:
    """Return all specs belonging to ``category`` in declaration order."""
    return [spec for spec in _SPECS if spec.category == category]
