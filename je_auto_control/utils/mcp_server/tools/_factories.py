"""Tool-factory functions: each returns a list of MCPTool for one domain.

Keeping factories separate from adapters lets ``_handlers.py`` stay
focused on argument / return-value normalisation while this module
owns the JSON Schemas, descriptions, and annotation choices that the
MCP client surfaces to the model.
"""
from typing import List

from je_auto_control.utils.mcp_server.tools import _handlers as h
from je_auto_control.utils.mcp_server.tools._base import (
    DESTRUCTIVE, MCPTool, MCPToolAnnotations, NON_DESTRUCTIVE, READ_ONLY,
    SIDE_EFFECT_ONLY, schema,
)


def mouse_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_click_mouse",
            description=("Click a mouse button at (x, y). "
                         "mouse_keycode: mouse_left, mouse_right, mouse_middle. "
                         "If x/y are omitted, clicks at the current cursor."),
            input_schema=schema({
                "mouse_keycode": {"type": "string",
                                   "description": "mouse_left | mouse_right | mouse_middle"},
                "x": {"type": "integer"},
                "y": {"type": "integer"},
            }),
            handler=h.click_mouse,
            annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_get_mouse_position",
            description="Return the current cursor position as [x, y].",
            input_schema=schema({}),
            handler=h.get_mouse_position,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_set_mouse_position",
            description="Move the cursor to absolute screen coordinates (x, y).",
            input_schema=schema({
                "x": {"type": "integer"},
                "y": {"type": "integer"},
            }, required=["x", "y"]),
            handler=h.set_mouse_position,
            annotations=NON_DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_mouse_scroll",
            description=("Scroll the mouse wheel by scroll_value units. "
                         "scroll_direction is Linux-only: scroll_up | scroll_down."),
            input_schema=schema({
                "scroll_value": {"type": "integer"},
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "scroll_direction": {"type": "string"},
            }, required=["scroll_value"]),
            handler=h.mouse_scroll,
            annotations=DESTRUCTIVE,
        ),
    ]


def keyboard_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_type_text",
            description=("Type a string by pressing each character. "
                         "Use ac_press_key or ac_hotkey for control keys."),
            input_schema=schema({"text": {"type": "string"}},
                                required=["text"]),
            handler=h.type_text,
            annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_press_key",
            description=("Press and release one keyboard key. keycode is a "
                         "name from get_keyboard_keys_table (e.g. enter, tab, "
                         "f1, a, 1)."),
            input_schema=schema({"keycode": {"type": "string"}},
                                required=["keycode"]),
            handler=h.press_key,
            annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_hotkey",
            description=("Press a key combination, e.g. ['ctrl', 'c']. "
                         "Keys are pressed in order then released in reverse."),
            input_schema=schema({
                "keys": {"type": "array", "items": {"type": "string"}},
            }, required=["keys"]),
            handler=h.hotkey,
            annotations=DESTRUCTIVE,
        ),
    ]


def screen_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_screen_size",
            description="Return the primary screen size as [width, height].",
            input_schema=schema({}),
            handler=h.screen_size,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_screenshot",
            description=("Take a screenshot and return it as a base64 PNG "
                         "image content block so the model can see the "
                         "screen. If file_path is provided, the image is "
                         "also saved there. screen_region is "
                         "[x, y, width, height]."),
            input_schema=schema({
                "file_path": {"type": "string"},
                "screen_region": {"type": "array",
                                   "items": {"type": "integer"}},
            }),
            handler=h.screenshot,
            annotations=MCPToolAnnotations(destructive=False, idempotent=False),
        ),
        MCPTool(
            name="ac_get_pixel",
            description="Return the pixel colour at (x, y) as a list of channels.",
            input_schema=schema({
                "x": {"type": "integer"},
                "y": {"type": "integer"},
            }, required=["x", "y"]),
            handler=h.get_pixel,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_diff_screenshots",
            description=("Compare two screenshots and return the bounding "
                         "boxes that changed. Result shape: {size: [w, h], "
                         "boxes: [[x, y, w, h], ...]}. Pixels differing by "
                         "at most threshold (per channel) are treated as "
                         "equal; components smaller than min_box_pixels "
                         "are ignored to filter antialias noise."),
            input_schema=schema({
                "image_path_a": {"type": "string"},
                "image_path_b": {"type": "string"},
                "threshold": {"type": "integer"},
                "min_box_pixels": {"type": "integer"},
            }, required=["image_path_a", "image_path_b"]),
            handler=h.diff_screenshots,
            annotations=READ_ONLY,
        ),
    ]


def image_and_ocr_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_locate_image_center",
            description=("Find a template image on screen and return its "
                         "centre [x, y]. detect_threshold is 0.0–1.0."),
            input_schema=schema({
                "image_path": {"type": "string"},
                "detect_threshold": {"type": "number"},
            }, required=["image_path"]),
            handler=h.locate_image_center,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_locate_and_click",
            description="Find a template image and click its centre.",
            input_schema=schema({
                "image_path": {"type": "string"},
                "mouse_keycode": {"type": "string"},
                "detect_threshold": {"type": "number"},
            }, required=["image_path"]),
            handler=h.locate_and_click,
            annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_locate_text",
            description=("OCR the screen for ``text`` and return the centre "
                         "[x, y] of the first match. region is "
                         "[x, y, width, height]. Requires Tesseract."),
            input_schema=schema({
                "text": {"type": "string"},
                "region": {"type": "array", "items": {"type": "integer"}},
                "min_confidence": {"type": "number"},
            }, required=["text"]),
            handler=h.locate_text,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_click_text",
            description="OCR for ``text`` and click its centre.",
            input_schema=schema({
                "text": {"type": "string"},
                "mouse_keycode": {"type": "string"},
                "region": {"type": "array", "items": {"type": "integer"}},
                "min_confidence": {"type": "number"},
            }, required=["text"]),
            handler=h.click_text,
            annotations=DESTRUCTIVE,
        ),
    ]


def window_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_list_windows",
            description=("List visible top-level windows as "
                         "[{hwnd, title}, ...] (Windows only)."),
            input_schema=schema({}),
            handler=h.list_windows,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_focus_window",
            description="Bring the first window matching title_substring to the front.",
            input_schema=schema({
                "title_substring": {"type": "string"},
                "case_sensitive": {"type": "boolean"},
            }, required=["title_substring"]),
            handler=h.focus_window,
            annotations=NON_DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_wait_for_window",
            description="Poll until a window with title_substring exists; return its hwnd.",
            input_schema=schema({
                "title_substring": {"type": "string"},
                "timeout": {"type": "number"},
                "case_sensitive": {"type": "boolean"},
            }, required=["title_substring"]),
            handler=h.wait_for_window,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_close_window",
            description="Minimise the first window matching title_substring.",
            input_schema=schema({
                "title_substring": {"type": "string"},
                "case_sensitive": {"type": "boolean"},
            }, required=["title_substring"]),
            handler=h.close_window,
            annotations=DESTRUCTIVE,
        ),
    ]


def system_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_get_clipboard",
            description="Return the current text clipboard contents.",
            input_schema=schema({}),
            handler=h.get_clipboard,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_set_clipboard",
            description="Replace the text clipboard contents with ``text``.",
            input_schema=schema({"text": {"type": "string"}},
                                required=["text"]),
            handler=h.set_clipboard,
            annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_execute_actions",
            description=("Run a list of AutoControl actions through the "
                         "executor. Each action is [name, args] where name "
                         "starts with AC_ (see ac_list_action_commands)."),
            input_schema=schema({
                "actions": {"type": "array",
                            "items": {"type": "array"}},
            }, required=["actions"]),
            handler=h.execute_actions,
            annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_execute_action_file",
            description="Load a JSON action file from disk and execute it.",
            input_schema=schema({"file_path": {"type": "string"}},
                                required=["file_path"]),
            handler=h.execute_action_file,
            annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_list_action_commands",
            description="Return every action command name the executor recognises.",
            input_schema=schema({}),
            handler=h.list_action_commands,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_list_run_history",
            description=("Return recent script-run history records "
                         "(id, status, source_type, started_at, ...)."),
            input_schema=schema({
                "limit": {"type": "integer"},
                "source_type": {"type": "string"},
            }),
            handler=h.list_run_history,
            annotations=READ_ONLY,
        ),
    ]


def screen_record_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_screen_record_start",
            description=("Start recording the screen to a video file. "
                         "recorder_name is a handle for ac_screen_record_stop. "
                         "Codec defaults to XVID (.avi); use MP4V for .mp4."),
            input_schema=schema({
                "recorder_name": {"type": "string"},
                "file_path": {"type": "string"},
                "codec": {"type": "string"},
                "frame_per_sec": {"type": "integer"},
                "width": {"type": "integer"},
                "height": {"type": "integer"},
            }, required=["recorder_name", "file_path"]),
            handler=h.screen_record_start,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_screen_record_stop",
            description="Stop the named screen recorder.",
            input_schema=schema({"recorder_name": {"type": "string"}},
                                required=["recorder_name"]),
            handler=h.screen_record_stop,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_screen_record_list",
            description="Return the names of currently running screen recorders.",
            input_schema=schema({}),
            handler=h.screen_record_list,
            annotations=READ_ONLY,
        ),
    ]


def recording_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_record_start",
            description=("Start recording mouse and keyboard events in the "
                         "background. Call ac_record_stop to retrieve the "
                         "captured action list. Not supported on macOS."),
            input_schema=schema({}),
            handler=h.record_start,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_record_stop",
            description=("Stop the active recorder and return the captured "
                         "action list ([[command, args], ...]) ready to "
                         "feed back into ac_execute_actions."),
            input_schema=schema({}),
            handler=h.record_stop,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_read_action_file",
            description="Read a JSON action file from disk and return its parsed contents.",
            input_schema=schema({"file_path": {"type": "string"}},
                                required=["file_path"]),
            handler=h.read_action_file,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_write_action_file",
            description="Persist an action list to a JSON file at file_path.",
            input_schema=schema({
                "file_path": {"type": "string"},
                "actions": {"type": "array"},
            }, required=["file_path", "actions"]),
            handler=h.write_action_file,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_trim_actions",
            description=("Return actions[start:end] as a new list — useful "
                         "for cleaning up the head/tail of a recording."),
            input_schema=schema({
                "actions": {"type": "array"},
                "start": {"type": "integer"},
                "end": {"type": "integer"},
            }, required=["actions"]),
            handler=h.trim_actions,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_adjust_delays",
            description=("Scale every AC_sleep delay by ``factor`` and "
                         "optionally clamp to a minimum of clamp_ms."),
            input_schema=schema({
                "actions": {"type": "array"},
                "factor": {"type": "number"},
                "clamp_ms": {"type": "integer"},
            }, required=["actions"]),
            handler=h.adjust_delays,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_scale_coordinates",
            description=("Scale every x/y coordinate in an action list — "
                         "useful when replaying a recording on a different "
                         "resolution."),
            input_schema=schema({
                "actions": {"type": "array"},
                "x_factor": {"type": "number"},
                "y_factor": {"type": "number"},
            }, required=["actions"]),
            handler=h.scale_coordinates,
            annotations=READ_ONLY,
        ),
    ]


def drag_and_send_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_drag",
            description=("Drag the mouse from (start_x, start_y) to "
                         "(end_x, end_y). mouse_keycode defaults to "
                         "mouse_left."),
            input_schema=schema({
                "start_x": {"type": "integer"},
                "start_y": {"type": "integer"},
                "end_x": {"type": "integer"},
                "end_y": {"type": "integer"},
                "mouse_keycode": {"type": "string"},
            }, required=["start_x", "start_y", "end_x", "end_y"]),
            handler=h.drag,
            annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_send_key_to_window",
            description=("Post a key event to a specific window without "
                         "stealing focus (Windows / Linux only)."),
            input_schema=schema({
                "window_title": {"type": "string"},
                "keycode": {"type": "string"},
            }, required=["window_title", "keycode"]),
            handler=h.send_key_to_window,
            annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_send_mouse_to_window",
            description=("Post a mouse event to a specific window without "
                         "stealing focus (Windows / Linux only)."),
            input_schema=schema({
                "window_title": {"type": "string"},
                "mouse_keycode": {"type": "string"},
                "x": {"type": "integer"},
                "y": {"type": "integer"},
            }, required=["window_title"]),
            handler=h.send_mouse_to_window,
            annotations=DESTRUCTIVE,
        ),
    ]


def semantic_locator_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_a11y_list",
            description=("List accessibility-tree elements (buttons, fields, "
                         "menu items, ...) optionally filtered by app_name. "
                         "Each element exposes name, role, and bounding box."),
            input_schema=schema({
                "app_name": {"type": "string"},
                "max_results": {"type": "integer"},
            }),
            handler=h.a11y_list,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_a11y_find",
            description=("Find the first accessibility element matching name "
                         "/ role / app_name. Returns null when nothing matches."),
            input_schema=schema({
                "name": {"type": "string"},
                "role": {"type": "string"},
                "app_name": {"type": "string"},
            }),
            handler=h.a11y_find,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_a11y_click",
            description=("Click the centre of the first accessibility "
                         "element matching name / role / app_name."),
            input_schema=schema({
                "name": {"type": "string"},
                "role": {"type": "string"},
                "app_name": {"type": "string"},
            }),
            handler=h.a11y_click,
            annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_vlm_locate",
            description=("Ask a vision-language model where ``description`` "
                         "is on screen. Returns [x, y] in screen coords or "
                         "null. Requires ANTHROPIC_API_KEY or OPENAI_API_KEY."),
            input_schema=schema({
                "description": {"type": "string"},
                "screen_region": {"type": "array",
                                   "items": {"type": "integer"}},
                "model": {"type": "string"},
            }, required=["description"]),
            handler=h.vlm_locate,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_vlm_click",
            description="Locate by description with a VLM, then click the centre.",
            input_schema=schema({
                "description": {"type": "string"},
                "screen_region": {"type": "array",
                                   "items": {"type": "integer"}},
                "model": {"type": "string"},
            }, required=["description"]),
            handler=h.vlm_click,
            annotations=DESTRUCTIVE,
        ),
    ]


def scheduler_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_scheduler_add_job",
            description=("Schedule an action JSON file. Provide either "
                         "interval_seconds (run every N seconds) or "
                         "cron_expression (5-field cron rule)."),
            input_schema=schema({
                "script_path": {"type": "string"},
                "interval_seconds": {"type": "number"},
                "cron_expression": {"type": "string"},
                "repeat": {"type": "boolean"},
                "max_runs": {"type": "integer"},
                "job_id": {"type": "string"},
            }, required=["script_path"]),
            handler=h.scheduler_add_job,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_scheduler_remove_job",
            description="Remove a scheduled job by id; returns True if it existed.",
            input_schema=schema({"job_id": {"type": "string"}},
                                required=["job_id"]),
            handler=h.scheduler_remove_job,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_scheduler_list_jobs",
            description="List currently registered scheduler jobs.",
            input_schema=schema({}),
            handler=h.scheduler_list_jobs,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_scheduler_start",
            description="Start the scheduler polling thread (idempotent).",
            input_schema=schema({}),
            handler=h.scheduler_start,
            annotations=NON_DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_scheduler_stop",
            description="Stop the scheduler polling thread.",
            input_schema=schema({}),
            handler=h.scheduler_stop,
            annotations=NON_DESTRUCTIVE,
        ),
    ]


def trigger_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_trigger_add",
            description=("Add a trigger to the default engine. ``kind`` is "
                         "image (provide image_path/threshold), window "
                         "(title_substring/case_sensitive), pixel "
                         "(x/y/target_rgb/tolerance), or file (watch_path). "
                         "When fired, ``script_path`` is executed."),
            input_schema=schema({
                "kind": {"type": "string",
                         "enum": ["image", "window", "pixel", "file"]},
                "script_path": {"type": "string"},
                "repeat": {"type": "boolean"},
                "image_path": {"type": "string"},
                "threshold": {"type": "number"},
                "title_substring": {"type": "string"},
                "case_sensitive": {"type": "boolean"},
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "target_rgb": {"type": "array",
                                "items": {"type": "integer"}},
                "tolerance": {"type": "integer"},
                "watch_path": {"type": "string"},
            }, required=["kind", "script_path"]),
            handler=h.trigger_add,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_trigger_remove",
            description="Remove a trigger by id.",
            input_schema=schema({"trigger_id": {"type": "string"}},
                                required=["trigger_id"]),
            handler=h.trigger_remove,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_trigger_list",
            description="List currently registered triggers.",
            input_schema=schema({}),
            handler=h.trigger_list,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_trigger_start",
            description="Start the trigger engine polling thread (idempotent).",
            input_schema=schema({}),
            handler=h.trigger_start,
            annotations=NON_DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_trigger_stop",
            description="Stop the trigger engine polling thread.",
            input_schema=schema({}),
            handler=h.trigger_stop,
            annotations=NON_DESTRUCTIVE,
        ),
    ]


def hotkey_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_hotkey_bind",
            description=("Bind a global hotkey combo (e.g. 'ctrl+alt+1') to "
                         "an action JSON file. Call ac_hotkey_daemon_start "
                         "to begin listening."),
            input_schema=schema({
                "combo": {"type": "string"},
                "script_path": {"type": "string"},
                "binding_id": {"type": "string"},
            }, required=["combo", "script_path"]),
            handler=h.hotkey_bind,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_hotkey_unbind",
            description="Remove a hotkey binding by id.",
            input_schema=schema({"binding_id": {"type": "string"}},
                                required=["binding_id"]),
            handler=h.hotkey_unbind,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_hotkey_list",
            description="List the registered hotkey bindings.",
            input_schema=schema({}),
            handler=h.hotkey_list,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_hotkey_daemon_start",
            description="Start the global hotkey listener thread (idempotent).",
            input_schema=schema({}),
            handler=h.hotkey_daemon_start,
            annotations=NON_DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_hotkey_daemon_stop",
            description="Stop the global hotkey listener thread.",
            input_schema=schema({}),
            handler=h.hotkey_daemon_stop,
            annotations=NON_DESTRUCTIVE,
        ),
    ]


ALL_FACTORIES = (
    mouse_tools, keyboard_tools, screen_tools, image_and_ocr_tools,
    window_tools, system_tools, recording_tools, drag_and_send_tools,
    semantic_locator_tools, scheduler_tools, trigger_tools, hotkey_tools,
    screen_record_tools,
)
