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
