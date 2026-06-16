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


def _add_misc_specs(specs: List[CommandSpec]) -> None:
    specs.append(CommandSpec(
        "AC_shell_command", "Shell", "Shell Command",
        fields=(FieldSpec("shell_command", FieldType.STRING),),
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
        "AC_http_to_var", "Report", "HTTP GET into Variable",
        fields=(
            FieldSpec("url", FieldType.STRING, placeholder="https://..."),
            FieldSpec("var", FieldType.STRING, default="http_response"),
            FieldSpec("json_path", FieldType.STRING, optional=True,
                      placeholder="data.0.name"),
            FieldSpec("timeout", FieldType.FLOAT, optional=True, default=30.0),
        ),
        description="GET a URL; store the body or a JSON field in a variable.",
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
