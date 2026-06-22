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
                         "screen. file_path saves to disk. screen_region "
                         "is [left, top, right, bottom]. monitor_index "
                         "captures one monitor across multi-display setups "
                         "(0 = virtual desktop spanning all, 1+ = single "
                         "screens — see ac_list_monitors)."),
            input_schema=schema({
                "file_path": {"type": "string"},
                "screen_region": {"type": "array",
                                   "items": {"type": "integer"}},
                "monitor_index": {"type": "integer"},
            }),
            handler=h.screenshot,
            annotations=MCPToolAnnotations(destructive=False, idempotent=False),
        ),
        MCPTool(
            name="ac_list_monitors",
            description=("List every connected monitor's geometry. Index 0 "
                         "spans all monitors; 1+ are single displays. Use "
                         "the index with ac_screenshot's monitor_index."),
            input_schema=schema({}),
            handler=h.list_monitors,
            annotations=READ_ONLY,
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
            name="ac_wait_for_image",
            description=("Poll the screen until ``image_path`` appears, "
                         "returning its centre [x, y]. Raises after "
                         "``timeout`` seconds. Cancellable: clients can "
                         "send notifications/cancelled to abort."),
            input_schema=schema({
                "image_path": {"type": "string"},
                "timeout": {"type": "number"},
                "poll": {"type": "number"},
                "detect_threshold": {"type": "number"},
            }, required=["image_path"]),
            handler=h.wait_for_image,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_wait_for_pixel",
            description=("Poll pixel (x, y) until it matches ``target_rgb`` "
                         "within ``tolerance`` per channel. Returns the "
                         "actual [r, g, b] reading on match."),
            input_schema=schema({
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "target_rgb": {"type": "array",
                                "items": {"type": "integer"}},
                "tolerance": {"type": "integer"},
                "timeout": {"type": "number"},
                "poll": {"type": "number"},
            }, required=["x", "y", "target_rgb"]),
            handler=h.wait_for_pixel,
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
        MCPTool(
            name="ac_window_move",
            description=("Move and resize the first matching window to "
                         "(x, y) with dimensions (width, height). "
                         "Windows-only."),
            input_schema=schema({
                "title_substring": {"type": "string"},
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "width": {"type": "integer"},
                "height": {"type": "integer"},
                "case_sensitive": {"type": "boolean"},
            }, required=["title_substring", "x", "y", "width", "height"]),
            handler=h.window_move,
            annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_window_minimize",
            description="Minimise the first matching window.",
            input_schema=schema({
                "title_substring": {"type": "string"},
                "case_sensitive": {"type": "boolean"},
            }, required=["title_substring"]),
            handler=h.window_minimize,
            annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_window_maximize",
            description="Maximise the first matching window.",
            input_schema=schema({
                "title_substring": {"type": "string"},
                "case_sensitive": {"type": "boolean"},
            }, required=["title_substring"]),
            handler=h.window_maximize,
            annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_window_restore",
            description=("Restore the first matching window to its previous "
                         "size and position."),
            input_schema=schema({
                "title_substring": {"type": "string"},
                "case_sensitive": {"type": "boolean"},
            }, required=["title_substring"]),
            handler=h.window_restore,
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
            name="ac_get_clipboard_image",
            description=("Return the current clipboard image as a base64 "
                         "PNG content block (so the model can see it). "
                         "Returns a text block 'clipboard does not contain "
                         "an image' when the clipboard has no image."),
            input_schema=schema({}),
            handler=h.get_clipboard_image,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_set_clipboard_image",
            description=("Place a Pillow-readable image file on the "
                         "clipboard. Windows-only today; macOS / Linux "
                         "raise NotImplementedError."),
            input_schema=schema({"image_path": {"type": "string"}},
                                required=["image_path"]),
            handler=h.set_clipboard_image,
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
        MCPTool(
            name="ac_dedupe_moves",
            description=("Collapse each run of consecutive mouse-move actions "
                         "into its last position — shrinks a raw recording "
                         "(one event per cursor sample) without changing "
                         "replay behaviour. move_commands defaults to "
                         "['AC_set_mouse_position']."),
            input_schema=schema({
                "actions": {"type": "array"},
                "move_commands": {"type": "array",
                                  "items": {"type": "string"}},
            }, required=["actions"]),
            handler=h.dedupe_moves,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_merge_sleeps",
            description=("Collapse each run of consecutive AC_sleep actions "
                         "into a single sleep summing their durations — "
                         "de-clutters a recording's idle delays."),
            input_schema=schema({
                "actions": {"type": "array"},
            }, required=["actions"]),
            handler=h.merge_sleeps,
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


def presence_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_presence_register",
            description=("Register a viewer in the multi-viewer presence "
                         "roster (role: controller | observer). Used by the "
                         "remote-desktop host to track who is currently "
                         "watching and who is allowed to push input."),
            input_schema=schema({
                "viewer_id": {"type": "string"},
                "label": {"type": "string"},
                "role": {"type": "string",
                         "enum": ["controller", "observer"]},
            }, required=["viewer_id"]),
            handler=h.presence_register,
            annotations=NON_DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_presence_unregister",
            description="Drop a viewer from the presence roster.",
            input_schema=schema({
                "viewer_id": {"type": "string"},
            }, required=["viewer_id"]),
            handler=h.presence_unregister,
            annotations=NON_DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_presence_update_cursor",
            description=("Update the cached cursor position of one viewer so "
                         "other viewers can render its ghost cursor."),
            input_schema=schema({
                "viewer_id": {"type": "string"},
                "x": {"type": "integer"},
                "y": {"type": "integer"},
            }, required=["viewer_id", "x", "y"]),
            handler=h.presence_update_cursor,
            annotations=NON_DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_presence_set_role",
            description=("Promote / demote a viewer between controller and "
                         "observer roles. Observers are read-only."),
            input_schema=schema({
                "viewer_id": {"type": "string"},
                "role": {"type": "string",
                         "enum": ["controller", "observer"]},
            }, required=["viewer_id", "role"]),
            handler=h.presence_set_role,
            annotations=NON_DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_presence_list",
            description="List every viewer currently in the presence roster.",
            input_schema=schema({}),
            handler=h.presence_list,
            annotations=READ_ONLY,
        ),
    ]


def chatops_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_chatops_dispatch",
            description=("Route one chat message through the default chat-ops "
                         "command router. Returns {matched, text, "
                         "succeeded, ...} so the calling bot can post the "
                         "reply back to Slack / Discord / webhook."),
            input_schema=schema({
                "message": {"type": "string"},
                "context": {"type": "object"},
                "script_root": {"type": "string"},
            }, required=["message"]),
            handler=h.chatops_dispatch,
            annotations=DESTRUCTIVE,
        ),
    ]


def dag_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_run_dag",
            description=("Execute a cross-host DAG (directed acyclic graph) "
                         "of automation steps. Each node carries (host, "
                         "actions|action_file, depends_on). Local nodes run "
                         "in-process; remote nodes go through the admin "
                         "console REST clients. Failures cascade — "
                         "downstream nodes are skipped, not retried."),
            input_schema=schema({
                "definition": {"type": "object"},
                "max_parallel": {"type": "integer"},
            }, required=["definition"]),
            handler=h.run_dag,
            annotations=DESTRUCTIVE,
        ),
    ]


def android_widget_tools() -> List[MCPTool]:
    """uiautomator2-backed Android widget tree operations.

    Complements the existing adb-based AC_android_* primitives by
    adding selector-based element lookup (find / click / dump). Each
    tool accepts a ``serial`` to target one device in a multi-device
    rig.
    """
    selector_schema = {
        "text": {"type": "string"},
        "resource_id": {"type": "string"},
        "description": {"type": "string"},
        "class_name": {"type": "string"},
        "timeout_s": {"type": "number"},
        "serial": {"type": "string"},
    }
    return [
        MCPTool(
            name="ac_android_find_element",
            description=("Find an Android widget by text / resource_id / "
                         "description / class_name via uiautomator2. "
                         "Returns {x1, y1, x2, y2}. Raises if no match "
                         "within timeout_s."),
            input_schema=schema(selector_schema),
            handler=h.android_find_element,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_android_click_element",
            description=("Tap the first widget matching the selectors. "
                         "Returns {x, y} click centre. Driven by "
                         "uiautomator2 so the daemon sees the press."),
            input_schema=schema(selector_schema),
            handler=h.android_click_element,
            annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_android_dump_hierarchy",
            description=("Return the device's current widget tree as "
                         "an XML string."),
            input_schema=schema({"serial": {"type": "string"}}),
            handler=h.android_dump_hierarchy,
            annotations=READ_ONLY,
        ),
    ]


def ios_tools() -> List[MCPTool]:
    """XCUITest-backed iOS surface (WebDriverAgent / facebook-wda)."""
    selector_schema = {
        "name": {"type": "string"},
        "class_name": {"type": "string"},
        "predicate": {"type": "string"},
        "timeout_s": {"type": "number"},
        "url": {"type": "string"},
    }
    return [
        MCPTool(
            name="ac_ios_tap",
            description="Tap absolute (x, y) on the iOS device via WDA.",
            input_schema=schema({
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "url": {"type": "string"},
            }, required=["x", "y"]),
            handler=h.ios_tap,
            annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_ios_swipe",
            description=("Swipe from (x1, y1) to (x2, y2) over "
                         "duration_s seconds."),
            input_schema=schema({
                "x1": {"type": "integer"},
                "y1": {"type": "integer"},
                "x2": {"type": "integer"},
                "y2": {"type": "integer"},
                "duration_s": {"type": "number"},
                "url": {"type": "string"},
            }, required=["x1", "y1", "x2", "y2"]),
            handler=h.ios_swipe,
            annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_ios_type",
            description="Send text to the currently focused iOS input.",
            input_schema=schema({
                "text": {"type": "string"},
                "url": {"type": "string"},
            }, required=["text"]),
            handler=h.ios_type,
            annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_ios_screenshot",
            description="Save the device screen as a PNG to file_path.",
            input_schema=schema({
                "file_path": {"type": "string"},
                "url": {"type": "string"},
            }, required=["file_path"]),
            handler=h.ios_screenshot,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_ios_find_element",
            description=("Find an XCUITest element by name / class_name / "
                         "predicate. Returns {x1, y1, x2, y2}."),
            input_schema=schema(selector_schema),
            handler=h.ios_find_element,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_ios_click_element",
            description="Tap the first XCUITest element matching the selectors.",
            input_schema=schema(selector_schema),
            handler=h.ios_click_element,
            annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_ios_dump_source",
            description="Return the XCUITest page source XML for the active app.",
            input_schema=schema({"url": {"type": "string"}}),
            handler=h.ios_dump_source,
            annotations=READ_ONLY,
        ),
    ]


def redaction_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_redact_screenshot",
            description=("Blur PII regions in a saved screenshot. "
                         "policy: 'off'|'moderate'|'strict'. Optional "
                         "regions (list of [x1,y1,x2,y2]) are blurred "
                         "unconditionally. Returns {output_path, boxes, "
                         "detectors_used}."),
            input_schema=schema({
                "file_path": {"type": "string"},
                "output_path": {"type": "string"},
                "policy": {"type": "string",
                            "enum": ["off", "moderate", "strict"]},
                "regions": {"type": "array",
                             "items": {"type": "array",
                                       "items": {"type": "integer"}}},
                "accessibility": {"type": "array",
                                   "items": {"type": "object"}},
                "ocr": {"type": "array",
                         "items": {"type": "object"}},
            }, required=["file_path"]),
            handler=h.redact_screenshot,
            annotations=SIDE_EFFECT_ONLY,
        ),
    ]


def computer_use_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_computer_use",
            description=("Drive Anthropic's Computer-Use agent loop to "
                         "accomplish goal on the live screen. Wraps "
                         "ComputerUseAgentBackend + AgentLoop. Returns "
                         "{succeeded, final_message, elapsed_s, steps[]}. "
                         "Requires anthropic SDK + ANTHROPIC_API_KEY."),
            input_schema=schema({
                "goal": {"type": "string"},
                "display_width_px": {"type": "integer"},
                "display_height_px": {"type": "integer"},
                "display_number": {"type": "integer"},
                "max_steps": {"type": "integer"},
                "wall_seconds": {"type": "number"},
                "model": {"type": "string"},
                "max_tokens": {"type": "integer"},
            }, required=["goal"]),
            handler=h.computer_use,
            annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_run_agent",
            description=("Drive the generic plan→act→verify→retry "
                         "AgentLoop against goal. backend='anthropic' "
                         "uses tool-use messages; 'openai' uses the "
                         "Responses API. Returns {succeeded, "
                         "final_message, elapsed_s, steps[]}. Requires "
                         "the matching SDK + API key."),
            input_schema=schema({
                "goal": {"type": "string"},
                "backend": {"type": "string",
                             "enum": ["anthropic", "openai"]},
                "max_steps": {"type": "integer"},
                "wall_seconds": {"type": "number"},
                "model": {"type": "string"},
                "max_tokens": {"type": "integer"},
            }, required=["goal"]),
            handler=h.run_agent,
            annotations=DESTRUCTIVE,
        ),
    ]


def webrunner_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_web_available",
            description=("Check whether je_web_runner (browser automation) "
                         "is installed in this environment."),
            input_schema=schema({}),
            handler=h.web_available,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_web_list_commands",
            description=("List every WR_* command exposed by the installed "
                         "WebRunner (~440 Selenium / Playwright actions)."),
            input_schema=schema({}),
            handler=h.web_list_commands,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_web_run",
            description=("Run one WR_* WebRunner action. action is a dict "
                         "of the form {\"action\": \"WR_*\", "
                         "\"params\": {...}} matching the JSON action "
                         "schema."),
            input_schema=schema({
                "action": {"type": "object"},
            }, required=["action"]),
            handler=h.web_run,
            annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_web_run_actions",
            description=("Run a list of WR_* actions in order. Stops at the "
                         "first failure."),
            input_schema=schema({
                "actions": {"type": "array",
                             "items": {"type": "object"}},
            }, required=["actions"]),
            handler=h.web_run_actions,
            annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_web_open",
            description=("Convenience: start a Selenium browser driver and "
                         "navigate to url. browser defaults to chrome."),
            input_schema=schema({
                "url": {"type": "string"},
                "browser": {"type": "string"},
            }, required=["url"]),
            handler=h.web_open,
            annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_web_quit",
            description="Convenience: quit every active WebRunner browser session.",
            input_schema=schema({}),
            handler=h.web_quit,
            annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_web_screenshot",
            description="Convenience: save a screenshot of the active browser tab.",
            input_schema=schema({
                "file_path": {"type": "string"},
            }, required=["file_path"]),
            handler=h.web_screenshot,
            annotations=NON_DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_web_current_url",
            description="Convenience: return the active browser tab's URL.",
            input_schema=schema({}),
            handler=h.web_current_url,
            annotations=READ_ONLY,
        ),
    ]


def a11y_control_tools() -> List[MCPTool]:
    _M = {
        "name": {"type": "string"},
        "role": {"type": "string"},
        "app_name": {"type": "string"},
        "automation_id": {"type": "string"},
    }
    return [
        MCPTool(
            name="ac_control_get_value",
            description=("Read a native control's value (textbox/combo/etc.) "
                         "via the OS accessibility API, located by name/role/"
                         "app_name/automation_id. Far more reliable than OCR. "
                         "Returns the value string or null."),
            input_schema=schema(dict(_M)),
            handler=h.control_get_value,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_control_set_value",
            description=("Set a native control's value directly (no per-key "
                         "typing). Located by name/role/app_name/automation_id. "
                         "Returns true on success."),
            input_schema=schema({"value": {"type": "string"}, **_M},
                                required=["value"]),
            handler=h.control_set_value,
            annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_control_invoke",
            description=("Invoke a native control's default action (e.g. press "
                         "a button) via the accessibility API."),
            input_schema=schema(dict(_M)),
            handler=h.control_invoke,
            annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_control_toggle",
            description=("Toggle a native control (e.g. a checkbox/switch) via "
                         "the accessibility API."),
            input_schema=schema(dict(_M)),
            handler=h.control_toggle,
            annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_read_table",
            description=("Read a grid/table/list control as rows of cell "
                         "strings via the accessibility Grid pattern. Located "
                         "by name/role/app_name/automation_id. Reliable "
                         "desktop data scraping without OCR."),
            input_schema=schema(dict(_M)),
            handler=h.read_table,
            annotations=READ_ONLY,
        ),
    ]


def a11y_tree_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_a11y_dump",
            description=("Dump the accessibility tree as a nested JSON "
                         "structure (root → app → element). Pairs with the "
                         "existing ac_a11y_list / ac_a11y_find which only "
                         "return flat lists."),
            input_schema=schema({
                "app_name": {"type": "string"},
                "max_results": {"type": "integer"},
            }),
            handler=h.a11y_dump,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_a11y_record_start",
            description=("Start the polling accessibility recorder. "
                         "Captures focus / bounds changes on the focused "
                         "element so they can be replayed later. Stop "
                         "with ac_a11y_record_stop."),
            input_schema=schema({
                "app_name": {"type": "string"},
                "poll_interval_s": {"type": "number"},
                "min_movement_px": {"type": "integer"},
            }),
            handler=h.a11y_record_start,
            annotations=NON_DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_a11y_record_stop",
            description=("Stop the recorder and return every captured "
                         "event in chronological order."),
            input_schema=schema({}),
            handler=h.a11y_record_stop,
            annotations=NON_DESTRUCTIVE,
        ),
    ]


def ab_locator_tools() -> List[MCPTool]:
    locator_schema = {
        "type": "object",
        "properties": {
            "kind": {"type": "string",
                     "enum": ["image", "ocr", "vlm", "a11y"]},
            "template_path": {"type": "string"},
            "detect_threshold": {"type": "number"},
            "text": {"type": "string"},
            "min_confidence": {"type": "number"},
            "description": {"type": "string"},
            "model": {"type": "string"},
            "role": {"type": "string"},
            "name": {"type": "string"},
        },
        "required": ["kind"],
    }
    return [
        MCPTool(
            name="ac_ab_locate",
            description=("Race N locator strategies (keyed by name) for the "
                         "same target. Returns per-strategy result and a "
                         "winner; appends per-strategy win/loss counts to "
                         "the on-disk ledger for ac_ab_best_strategy."),
            input_schema=schema({
                "target_id": {"type": "string"},
                "strategies": {
                    "type": "object",
                    "additionalProperties": locator_schema,
                },
                "max_parallel": {"type": "integer"},
                "record": {"type": "boolean"},
            }, required=["target_id", "strategies"]),
            handler=h.ab_locate,
            annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_ab_report",
            description=("Return the historical strategies + success rate "
                         "for one target_id."),
            input_schema=schema({
                "target_id": {"type": "string"},
            }, required=["target_id"]),
            handler=h.ab_report,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_ab_best_strategy",
            description=("Recommend the historically-best strategy name for "
                         "target_id, or null if no data yet."),
            input_schema=schema({
                "target_id": {"type": "string"},
            }, required=["target_id"]),
            handler=h.ab_best_strategy,
            annotations=READ_ONLY,
        ),
    ]


def failure_hook_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_failure_hook_fire",
            description=("Fan a failure report out to every registered "
                         "ticket backend (Jira / Linear / GitHub). Use from "
                         "scheduler / trigger / REST error handlers to file "
                         "a ticket automatically when a run breaks."),
            input_schema=schema({
                "source": {"type": "string"},
                "source_id": {"type": "string"},
                "error_text": {"type": "string"},
                "script_path": {"type": "string"},
                "screenshot_path": {"type": "string"},
                "log_tail": {"type": "string"},
                "metadata": {"type": "object"},
            }, required=["source", "source_id"]),
            handler=h.failure_hook_fire,
            annotations=NON_DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_failure_hook_list",
            description="List every registered failure-hook backend.",
            input_schema=schema({}),
            handler=h.failure_hook_list,
            annotations=READ_ONLY,
        ),
    ]


def cost_telemetry_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_costs_record",
            description=("Append one LLM API call to the cost-telemetry "
                         "log so spend can be aggregated per model / "
                         "provider / day. estimated_usd is auto-derived "
                         "from the bundled pricing table."),
            input_schema=schema({
                "provider": {"type": "string"},
                "model": {"type": "string"},
                "input_tokens": {"type": "integer"},
                "output_tokens": {"type": "integer"},
                "label": {"type": "string"},
                "run_id": {"type": "string"},
                "user": {"type": "string"},
            }, required=["provider", "model",
                          "input_tokens", "output_tokens"]),
            handler=h.costs_record,
            annotations=NON_DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_costs_summary",
            description=("Aggregate cost events by model / provider / day. "
                         "Returns total_calls, total_usd, by_model, "
                         "by_provider, by_day."),
            input_schema=schema({
                "limit": {"type": "integer"},
            }),
            handler=h.costs_summary,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_costs_list",
            description="Return the most-recent N cost events as a list.",
            input_schema=schema({
                "limit": {"type": "integer"},
            }),
            handler=h.costs_list,
            annotations=READ_ONLY,
        ),
    ]


def smart_wait_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_wait_screen_stable",
            description=("Block until the screen stops moving (consecutive "
                         "frames differ by <= max_pixel_diff bytes for "
                         "stable_for_s seconds). Smarter than time.sleep."),
            input_schema=schema({
                "region": {"type": "array", "items": {"type": "integer"}},
                "timeout_s": {"type": "number"},
                "poll_interval_s": {"type": "number"},
                "stable_for_s": {"type": "number"},
                "max_pixel_diff": {"type": "integer"},
            }),
            handler=h.wait_screen_stable,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_wait_pixel_changes",
            description=("Block until the pixel at (x, y) differs from its "
                         "initial RGB by more than rgb_tolerance."),
            input_schema=schema({
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "timeout_s": {"type": "number"},
                "poll_interval_s": {"type": "number"},
                "rgb_tolerance": {"type": "integer"},
            }, required=["x", "y"]),
            handler=h.wait_pixel_changes,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_wait_region_idle",
            description=("Block until a sub-region stops moving. "
                         "region = [x1, y1, x2, y2]."),
            input_schema=schema({
                "region": {"type": "array", "items": {"type": "integer"}},
                "timeout_s": {"type": "number"},
                "poll_interval_s": {"type": "number"},
                "stable_for_s": {"type": "number"},
                "max_pixel_diff": {"type": "integer"},
            }, required=["region"]),
            handler=h.wait_region_idle,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_wait_for_file",
            description=("Block until a file exists, is >= min_size bytes, and "
                         "its size has held steady for stable_for_s seconds "
                         "(i.e. a download finished writing). Returns a "
                         "WaitOutcome (succeeded/reason/elapsed_s)."),
            input_schema=schema({
                "path": {"type": "string"},
                "timeout_s": {"type": "number"},
                "poll_interval_s": {"type": "number"},
                "stable_for_s": {"type": "number"},
                "min_size": {"type": "integer"},
            }, required=["path"]),
            handler=h.wait_for_file,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_wait_for_port",
            description=("Block until a TCP connection to host:port succeeds "
                         "(e.g. wait for a server to come up after launching "
                         "it). Returns a WaitOutcome (succeeded/reason/"
                         "elapsed_s)."),
            input_schema=schema({
                "host": {"type": "string"},
                "port": {"type": "integer"},
                "timeout_s": {"type": "number"},
                "poll_interval_s": {"type": "number"},
                "connect_timeout_s": {"type": "number"},
            }, required=["host", "port"]),
            handler=h.wait_for_port,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_wait_for_process",
            description=("Block until a process whose name contains 'name' "
                         "appears (present=true) or exits (present=false) — "
                         "e.g. after launching or killing one. Requires "
                         "psutil. Returns a WaitOutcome (succeeded/reason/"
                         "elapsed_s)."),
            input_schema=schema({
                "name": {"type": "string"},
                "present": {"type": "boolean"},
                "timeout_s": {"type": "number"},
                "poll_interval_s": {"type": "number"},
            }, required=["name"]),
            handler=h.wait_for_process,
            annotations=READ_ONLY,
        ),
    ]


def ocr_structure_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_ocr_read_structure",
            description=("Run OCR over region (or whole screen) and return "
                         "matches grouped into rows, tables (sets of rows "
                         "sharing column alignment), and form-field "
                         "key:value pairs. Each cell carries its original "
                         "bbox so callers can click on the value of "
                         "'Username:' without picking pixel offsets."),
            input_schema=schema({
                "region": {"type": "array", "items": {"type": "integer"}},
                "lang": {"type": "string"},
                "min_confidence": {"type": "number"},
            }),
            handler=h.ocr_read_structure,
            annotations=READ_ONLY,
        ),
    ]


def anchor_locator_tools() -> List[MCPTool]:
    locator_schema = {
        "type": "object",
        "properties": {
            "kind": {"type": "string",
                     "enum": ["image", "ocr", "vlm", "a11y"]},
            "template_path": {"type": "string"},
            "detect_threshold": {"type": "number"},
            "text": {"type": "string"},
            "min_confidence": {"type": "number"},
            "region": {"type": "array", "items": {"type": "integer"}},
            "description": {"type": "string"},
            "model": {"type": "string"},
            "role": {"type": "string"},
            "name": {"type": "string"},
            "app_name": {"type": "string"},
        },
        "required": ["kind"],
    }
    return [
        MCPTool(
            name="ac_anchor_locate",
            description=("Find target element by spatial relation to anchor "
                         "(above / below / left_of / right_of / near). Both "
                         "anchor and target are Locator objects {kind, …} "
                         "and may use different backends — e.g. anchor by "
                         "OCR text, target by image template."),
            input_schema=schema({
                "anchor": locator_schema,
                "target": locator_schema,
                "relation": {"type": "string",
                              "enum": ["above", "below", "left_of",
                                       "right_of", "near"]},
                "max_distance_px": {"type": "number"},
            }, required=["anchor", "target"]),
            handler=h.anchor_locate,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_anchor_click",
            description="Anchor-locate then click the resolved target point.",
            input_schema=schema({
                "anchor": locator_schema,
                "target": locator_schema,
                "relation": {"type": "string",
                              "enum": ["above", "below", "left_of",
                                       "right_of", "near"]},
                "max_distance_px": {"type": "number"},
                "mouse_keycode": {"type": "string"},
            }, required=["anchor", "target"]),
            handler=h.anchor_click,
            annotations=DESTRUCTIVE,
        ),
    ]


def self_healing_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_self_heal_locate",
            description=("Locate an element by image template; if the template "
                         "match misses, fall back to a vision-language model "
                         "using the natural-language ``description``. Every "
                         "attempt is appended to the self-healing audit log. "
                         "Returns {found, coordinates, method, ...}."),
            input_schema=schema({
                "template_path": {"type": "string"},
                "description": {"type": "string"},
                "detect_threshold": {"type": "number"},
                "screen_region": {"type": "array",
                                   "items": {"type": "integer"}},
                "model": {"type": "string"},
                "raise_on_miss": {"type": "boolean"},
            }),
            handler=h.self_heal_locate,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_self_heal_click",
            description=("Self-heal locate then click the resolved point. "
                         "Provide template_path, description, or both — "
                         "description triggers the VLM fallback when the "
                         "template fails."),
            input_schema=schema({
                "template_path": {"type": "string"},
                "description": {"type": "string"},
                "mouse_keycode": {"type": "string"},
                "detect_threshold": {"type": "number"},
                "screen_region": {"type": "array",
                                   "items": {"type": "integer"}},
                "model": {"type": "string"},
                "raise_on_miss": {"type": "boolean"},
            }),
            handler=h.self_heal_click,
            annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_self_heal_log_list",
            description=("Return the most-recent self-healing events recorded "
                         "by ac_self_heal_locate / ac_self_heal_click."),
            input_schema=schema({
                "limit": {"type": "integer"},
            }),
            handler=h.self_heal_log_list,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_self_heal_log_clear",
            description="Wipe the self-healing audit log.",
            input_schema=schema({}),
            handler=h.self_heal_log_clear,
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


def process_and_shell_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_launch_process",
            description=("Spawn a subprocess with the given argv list "
                         "(detached, stdio piped to /dev/null). Returns "
                         "{pid, argv}. Optional working_directory."),
            input_schema=schema({
                "argv": {"type": "array", "items": {"type": "string"}},
                "working_directory": {"type": "string"},
            }, required=["argv"]),
            handler=h.launch_process,
            annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_list_processes",
            description=("List running processes (psutil required). "
                         "Optionally filter by case-insensitive substring."),
            input_schema=schema({
                "name_contains": {"type": "string"},
            }),
            handler=h.list_processes,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_kill_process",
            description=("Terminate a PID gracefully, escalating to "
                         "SIGKILL after ``timeout``. Returns 'terminated' "
                         "/ 'killed' / 'not-found'. psutil required."),
            input_schema=schema({
                "pid": {"type": "integer"},
                "timeout": {"type": "number"},
            }, required=["pid"]),
            handler=h.kill_process,
            annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_shell",
            description=("Run a shell-style command line via shlex.split "
                         "(NO shell expansion). Returns {exit_code, "
                         "stdout, stderr}."),
            input_schema=schema({
                "command": {"type": "string"},
                "timeout": {"type": "number"},
            }, required=["command"]),
            handler=h.shell_command,
            annotations=DESTRUCTIVE,
        ),
    ]


def work_queue_tools() -> List[MCPTool]:
    _Q = {"db": {"type": "string"}, "name": {"type": "string"}}
    return [
        MCPTool(
            name="ac_queue_add",
            description=("Enqueue a work item into a SQLite-backed queue "
                         "(dispatcher). 'data' is the item payload; a live "
                         "duplicate 'reference' is skipped. Returns {id} (null "
                         "if deduped)."),
            input_schema=schema({"data": {"type": "object"},
                                 "reference": {"type": "string"}, **_Q},
                                required=["db", "data"]),
            handler=h.queue_add,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_queue_next",
            description=("Atomically claim the next 'new' work item "
                         "(performer), marking it in-progress. Returns the "
                         "item or null when the queue is drained."),
            input_schema=schema(dict(_Q), required=["db"]),
            handler=h.queue_next,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_queue_complete",
            description="Mark a claimed work item successfully processed.",
            input_schema=schema({"item_id": {"type": "integer"},
                                 "output": {}, **_Q},
                                required=["db", "item_id"]),
            handler=h.queue_complete,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_queue_fail",
            description=("Fail a work item. kind='application' (default) "
                         "retries up to max_retries then marks failed; "
                         "kind='business' fails immediately (bad data, no "
                         "retry). Returns the resulting status."),
            input_schema=schema({"item_id": {"type": "integer"},
                                 "error": {"type": "string"},
                                 "kind": {"type": "string"},
                                 "max_retries": {"type": "integer"}, **_Q},
                                required=["db", "item_id", "error"]),
            handler=h.queue_fail,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_queue_stats",
            description=("Return per-status item counts (new / in_progress / "
                         "success / failed) for a work queue."),
            input_schema=schema(dict(_Q), required=["db"]),
            handler=h.queue_stats,
            annotations=READ_ONLY,
        ),
    ]


def synthetic_data_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_generate_data",
            description=("Generate deterministic synthetic test rows from a "
                         "field schema (e.g. {name:'name', age:{type:'int', "
                         "min:18,max:65}}). Same 'seed' -> same rows. Writes "
                         "JSON/CSV when 'path' is given, else returns rows."),
            input_schema=schema({
                "schema": {"type": "object"},
                "count": {"type": "integer"},
                "path": {"type": "string"},
                "fmt": {"type": "string", "enum": ["json", "csv"]},
                "seed": {"type": "integer"},
            }, required=["schema"]),
            handler=h.generate_data,
            annotations=SIDE_EFFECT_ONLY,
        ),
    ]


def mcp_registry_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_mcp_manifest",
            description=("Build an MCP registry server.json manifest for this "
                         "AutoControl server (discoverability). Writes to "
                         "'path' when given, else returns the manifest. "
                         "include_tools embeds the live tool list."),
            input_schema=schema({
                "path": {"type": "string"},
                "include_tools": {"type": "boolean"},
            }),
            handler=h.mcp_manifest,
            annotations=SIDE_EFFECT_ONLY,
        ),
    ]


def test_selection_tools() -> List[MCPTool]:
    _flows = {"flows": {"type": "array", "items": {"type": "string"}},
              "history_path": {"type": "string"},
              "window": {"type": "integer"}}
    return [
        MCPTool(
            name="ac_rank_tests",
            description=("Score flows by risk (recent failures, flakiness, "
                         "staleness, never-run) from run history; returns the "
                         "ranked list, riskiest first."),
            input_schema=schema(dict(_flows), required=["flows"]),
            handler=h.rank_tests,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_select_tests",
            description=("Pick the riskiest flows to run: top-'k', or score "
                         ">= 'threshold', else all ordered by risk. Returns "
                         "the selected flow names."),
            input_schema=schema({
                "k": {"type": "integer"},
                "threshold": {"type": "number"}, **_flows,
            }, required=["flows"]),
            handler=h.select_tests,
            annotations=READ_ONLY,
        ),
    ]


def element_repository_tools() -> List[MCPTool]:
    _R = {"path": {"type": "string"}, "key": {"type": "string"}}
    return [
        MCPTool(
            name="ac_element_save",
            description=("Save a named native-UI locator (object repository): "
                         "store name/role/app under a friendly 'key' for "
                         "reuse. Needs at least one of name/role/app_name."),
            input_schema=schema({
                "name": {"type": "string"}, "role": {"type": "string"},
                "app_name": {"type": "string"}, **_R},
                required=["path", "key"]),
            handler=h.element_save,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_element_find",
            description=("Resolve a saved locator to a live element; returns "
                         "{found, name, role, center}."),
            input_schema=schema(dict(_R), required=["path", "key"]),
            handler=h.element_find,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_element_click",
            description="Click the element behind a saved locator.",
            input_schema=schema(dict(_R), required=["path", "key"]),
            handler=h.element_click,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_element_remove",
            description="Delete a saved locator; returns {removed}.",
            input_schema=schema(dict(_R), required=["path", "key"]),
            handler=h.element_remove,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_element_list",
            description="List saved locator names in a repository file.",
            input_schema=schema({"path": {"type": "string"}},
                                required=["path"]),
            handler=h.element_list,
            annotations=READ_ONLY,
        ),
    ]


def flow_debugger_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_debug_trace",
            description=("Run an action list and return a per-step trace "
                         "({index, command, result}). With dry_run=true the "
                         "actions are planned but not executed."),
            input_schema=schema({
                "actions": {"type": "array"},
                "dry_run": {"type": "boolean"}},
                required=["actions"]),
            handler=h.debug_trace,
            annotations=SIDE_EFFECT_ONLY,
        ),
    ]


def skill_library_tools() -> List[MCPTool]:
    _S = {"path": {"type": "string"}, "name": {"type": "string"}}
    return [
        MCPTool(
            name="ac_skill_save",
            description=("Save a reusable action sequence (skill/playbook) "
                         "under a name, with optional description and tags, "
                         "for recall and replay across runs."),
            input_schema=schema({
                "actions": {"type": "array"},
                "description": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}}, **_S},
                required=["path", "name", "actions"]),
            handler=h.skill_save,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_skill_run",
            description="Execute a stored skill's actions; returns the record.",
            input_schema=schema(dict(_S), required=["path", "name"]),
            handler=h.skill_run,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_skill_list",
            description="List saved skill names in a library file.",
            input_schema=schema({"path": {"type": "string"}},
                                required=["path"]),
            handler=h.skill_list,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_skill_remove",
            description="Delete a saved skill; returns {removed}.",
            input_schema=schema(dict(_S), required=["path", "name"]),
            handler=h.skill_remove,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_skill_search",
            description=("Search skills by name/description/tags; returns "
                         "matching names."),
            input_schema=schema({"path": {"type": "string"},
                                 "query": {"type": "string"}},
                                required=["path", "query"]),
            handler=h.skill_search,
            annotations=READ_ONLY,
        ),
    ]


def guardrail_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_guard_text",
            description=("Scan untrusted on-screen / OCR text for prompt-"
                         "injection patterns before feeding it to an LLM. "
                         "Returns {suspicious, score, findings, redacted}."),
            input_schema=schema({"text": {"type": "string"},
                                 "threshold": {"type": "integer"}},
                                required=["text"]),
            handler=h.guard_text,
            annotations=READ_ONLY,
        ),
    ]


def a2a_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_agent_card",
            description=("Build an A2A (agent-to-agent) Agent Card describing "
                         "AutoControl's skills. Writes to 'path' when given, "
                         "else returns the card."),
            input_schema=schema({"path": {"type": "string"}}),
            handler=h.agent_card,
            annotations=SIDE_EFFECT_ONLY,
        ),
    ]


def office_tools() -> List[MCPTool]:
    _P = {"path": {"type": "string"}}
    return [
        MCPTool(
            name="ac_read_workbook",
            description=("Read an Excel (.xlsx) worksheet into rows (first row "
                         "= keys). 'sheet' defaults to the active sheet. "
                         "Requires the [office] extra."),
            input_schema=schema({"sheet": {"type": "string"}, **_P},
                                required=["path"]),
            handler=h.read_workbook,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_write_workbook",
            description=("Write rows (list of objects) to an Excel (.xlsx) "
                         "file. Requires the [office] extra."),
            input_schema=schema({
                "rows": {"type": "array", "items": {"type": "object"}},
                "sheet": {"type": "string"}, **_P},
                required=["path", "rows"]),
            handler=h.write_workbook,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_read_document",
            description=("Read a Word (.docx) file's paragraph texts. "
                         "Requires the [office] extra."),
            input_schema=schema(dict(_P), required=["path"]),
            handler=h.read_document,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_write_document",
            description=("Write paragraphs (list of strings) to a Word "
                         "(.docx) file. Requires the [office] extra."),
            input_schema=schema({
                "paragraphs": {"type": "array", "items": {"type": "string"}},
                **_P}, required=["path", "paragraphs"]),
            handler=h.write_document,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_read_presentation",
            description=("Read a PowerPoint (.pptx) file's per-slide text. "
                         "Requires the [office] extra."),
            input_schema=schema(dict(_P), required=["path"]),
            handler=h.read_presentation,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_write_presentation",
            description=("Write slides (each {title, body:[...]}) to a "
                         "PowerPoint (.pptx) file. Requires the [office] "
                         "extra."),
            input_schema=schema({"slides": {"type": "array"}, **_P},
                                required=["path", "slides"]),
            handler=h.write_presentation,
            annotations=SIDE_EFFECT_ONLY,
        ),
    ]


def agent_memory_tools() -> List[MCPTool]:
    _D = {"db": {"type": "string"}}
    return [
        MCPTool(
            name="ac_memory_remember",
            description=("Store an agent episode (goal -> trajectory -> "
                         "outcome) for cross-run recall. 'steps' is the "
                         "trajectory; optional 'tags'. Returns {id}."),
            input_schema=schema({
                "goal": {"type": "string"},
                "steps": {"type": "array"},
                "outcome": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}}, **_D},
                required=["db", "goal"]),
            handler=h.memory_remember,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_memory_recall",
            description=("Recall past episodes most relevant to 'query' "
                         "(keyword score over goal/tags/outcome) to inject "
                         "into the planner's context."),
            input_schema=schema({"query": {"type": "string"},
                                 "limit": {"type": "integer"}, **_D},
                                required=["db", "query"]),
            handler=h.memory_recall,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_memory_recent",
            description="List the most recently stored episodes (newest first).",
            input_schema=schema({"limit": {"type": "integer"}, **_D},
                                required=["db"]),
            handler=h.memory_recent,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_memory_forget",
            description="Delete an episode by id; returns {removed}.",
            input_schema=schema({"episode_id": {"type": "integer"}, **_D},
                                required=["db", "episode_id"]),
            handler=h.memory_forget,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_memory_stats",
            description="Return the episode count for a memory store.",
            input_schema=schema(dict(_D), required=["db"]),
            handler=h.memory_stats,
            annotations=READ_ONLY,
        ),
    ]


def determinism_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_seed_everything",
            description=("Seed all RNG (random, numpy if present) run-wide for "
                         "reproducible runs. Returns {seed}."),
            input_schema=schema({"seed": {"type": "integer"}}),
            handler=h.seed_everything,
            annotations=SIDE_EFFECT_ONLY,
        ),
    ]


def observer_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_observe_add",
            description=("Register a non-blocking watch that runs 'actions' "
                         "when an image/text/pixel appears, vanishes, or "
                         "changes. kind=image|text|pixel; event=appear|vanish|"
                         "change. Provide image+threshold, text, or x+y."),
            input_schema=schema({
                "name": {"type": "string"},
                "kind": {"type": "string",
                         "enum": ["image", "text", "pixel"]},
                "event": {"type": "string",
                          "enum": ["appear", "vanish", "change"]},
                "actions": {"type": "array"},
                "image": {"type": "string"},
                "threshold": {"type": "number"},
                "text": {"type": "string"},
                "x": {"type": "integer"}, "y": {"type": "integer"},
            }, required=["name"]),
            handler=h.observe_add,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_observe_remove",
            description="Remove a registered watch by name; returns {removed}.",
            input_schema=schema({"name": {"type": "string"}},
                                required=["name"]),
            handler=h.observe_remove,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_observe_list",
            description="List registered watch names.",
            input_schema=schema({}),
            handler=h.observe_list,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_observe_poll",
            description=("Evaluate all watches once and return fired events "
                         "({rule, event, time}); useful without the thread."),
            input_schema=schema({}),
            handler=h.observe_poll,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_observe_start",
            description="Start the background observer poll thread.",
            input_schema=schema({}),
            handler=h.observe_start,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_observe_stop",
            description="Stop the background observer poll thread.",
            input_schema=schema({}),
            handler=h.observe_stop,
            annotations=SIDE_EFFECT_ONLY,
        ),
    ]


def sbom_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_generate_sbom",
            description=("Generate a CycloneDX 1.6 SBOM of the project's "
                         "dependencies (supply-chain compliance). 'root' "
                         "limits to a distribution's closure (empty = all "
                         "installed). Writes to 'path' or returns the SBOM."),
            input_schema=schema({"path": {"type": "string"},
                                 "root": {"type": "string"}}),
            handler=h.generate_sbom,
            annotations=SIDE_EFFECT_ONLY,
        ),
    ]


def sharding_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_shard_suite",
            description=("Split 'flows' into 'shards' balanced lists using "
                         "historical per-flow duration from run history "
                         "(greedy bin-pack), so each worker takes ~equal "
                         "time. Returns the shard lists."),
            input_schema=schema({
                "flows": {"type": "array", "items": {"type": "string"}},
                "shards": {"type": "integer"},
                "history_path": {"type": "string"},
                "window": {"type": "integer"},
            }, required=["flows"]),
            handler=h.shard_suite,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_merge_results",
            description=("Merge per-shard report dicts into one consolidated "
                         "report (sums total/passed/failed/skipped/errors, "
                         "concatenates results)."),
            input_schema=schema({
                "reports": {"type": "array", "items": {"type": "object"}},
            }, required=["reports"]),
            handler=h.merge_results,
            annotations=READ_ONLY,
        ),
    ]


def data_quality_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_validate_rows",
            description=("Validate rows against a declarative schema "
                         "(type/required/regex/min/max/min_len/max_len/"
                         "allowed/unique). Returns {ok, valid, invalid, "
                         "errors} — the data-quality gate after load_rows."),
            input_schema=schema({
                "rows": {"type": "array", "items": {"type": "object"}},
                "schema": {"type": "object"},
            }, required=["rows", "schema"]),
            output_schema=schema({
                "ok": {"type": "boolean"},
                "total": {"type": "integer"},
                "valid_count": {"type": "integer"},
                "invalid_count": {"type": "integer"},
                "valid": {"type": "array"},
                "invalid": {"type": "array"},
                "errors": {"type": "array", "items": {"type": "object"}},
            }, required=["ok", "errors"]),
            handler=h.validate_rows,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_extract_fields",
            description=("Extract structured values from free text using "
                         "named presets (email/url/ipv4/phone/date_iso/"
                         "amount/hashtag) and/or custom 'patterns'. Returns "
                         "{fields: {name: [matches]}}."),
            input_schema=schema({
                "text": {"type": "string"},
                "fields": {"type": "array", "items": {"type": "string"}},
                "patterns": {"type": "object"},
            }, required=["text"]),
            handler=h.extract_fields,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_mask_rows",
            description=("Mask sensitive columns in rows before export. "
                         "'rules' maps a field to redact / hash / partial. "
                         "Returns {rows}."),
            input_schema=schema({
                "rows": {"type": "array", "items": {"type": "object"}},
                "rules": {"type": "object"},
            }, required=["rows", "rules"]),
            handler=h.mask_rows,
            annotations=READ_ONLY,
        ),
    ]


def i18n_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_pseudo_localize",
            description=("Pseudo-localize a 'text' string or a 'mapping' "
                         "catalog (accent + pad + bracket, placeholders "
                         "preserved) to flush out hardcoded strings and "
                         "pre-stress layout before real translation."),
            input_schema=schema({
                "text": {"type": "string"},
                "mapping": {"type": "object"},
                "expansion": {"type": "number"},
            }),
            handler=h.pseudo_localize,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_check_overflow",
            description=("Flag text elements whose estimated width exceeds "
                         "their widget bounds (translation overflow). Uses "
                         "the live a11y tree unless 'elements' are supplied."),
            input_schema=schema({
                "elements": {"type": "array"},
                "avg_char_px": {"type": "number"},
                "app_name": {"type": "string"},
            }),
            handler=h.check_overflow,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_check_catalog",
            description=("Diff a translation 'target' catalog against 'base': "
                         "missing / orphaned / empty keys and placeholder "
                         "mismatches. Returns {ok, ...}."),
            input_schema=schema({
                "base": {"type": "object"},
                "target": {"type": "object"},
            }, required=["base", "target"]),
            handler=h.check_catalog,
            annotations=READ_ONLY,
        ),
    ]


def checkpoint_tools() -> List[MCPTool]:
    _R = {"run_id": {"type": "string"}, "db": {"type": "string"}}
    return [
        MCPTool(
            name="ac_run_resumable",
            description=("Run an action list with checkpoint/resume keyed by "
                         "'run_id': persists step-index+variables after each "
                         "step to 'db' and, on re-run, resumes past completed "
                         "steps. Durable execution for long flows."),
            input_schema=schema({
                "actions": {"type": "array"},
                "variables": {"type": "object"}, **_R},
                required=["actions", "run_id", "db"]),
            handler=h.run_resumable,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_checkpoint_status",
            description=("Return the saved checkpoint for a run_id "
                         "({step_index, variables}) or null."),
            input_schema=schema(dict(_R), required=["run_id", "db"]),
            handler=h.checkpoint_status,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_checkpoint_clear",
            description="Delete a run's checkpoint; returns {cleared}.",
            input_schema=schema(dict(_R), required=["run_id", "db"]),
            handler=h.checkpoint_clear,
            annotations=SIDE_EFFECT_ONLY,
        ),
    ]


def set_of_marks_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_mark_screen",
            description=("Set-of-Marks: number the live UI elements (a11y "
                         "tree) and return an id->bbox/center/role/text "
                         "legend for VLM grounding — the model picks a number "
                         "instead of pixels. Optionally render a numbered-box "
                         "overlay screenshot to 'render_path'."),
            input_schema=schema({"app_name": {"type": "string"},
                                 "render_path": {"type": "string"}}),
            handler=h.mark_screen,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_mark_click",
            description=("Click the element behind a numbered mark from the "
                         "last ac_mark_screen. Returns {clicked}."),
            input_schema=schema({"mark_id": {"type": "integer"}},
                                required=["mark_id"]),
            handler=h.mark_click,
            annotations=SIDE_EFFECT_ONLY,
        ),
    ]


def screen_state_tools() -> List[MCPTool]:
    _SNAP = {"type": "array", "items": {"type": "object"}}
    return [
        MCPTool(
            name="ac_screen_snapshot",
            description=("Snapshot the live accessibility tree to "
                         "[{role, name, bbox}] and cache it as the diff "
                         "baseline."),
            input_schema=schema({"app_name": {"type": "string"}}),
            handler=h.screen_snapshot,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_screen_diff",
            description=("Semantic diff between two snapshots: what appeared / "
                         "vanished / moved, with a human-readable summary."),
            input_schema=schema({"before": _SNAP, "after": _SNAP},
                                required=["before", "after"]),
            handler=h.screen_diff,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_screen_changed",
            description=("Diff the live screen against the last "
                         "ac_screen_snapshot baseline (agent feedback signal: "
                         "'Save dialog appeared')."),
            input_schema=schema({"app_name": {"type": "string"}}),
            handler=h.screen_changed,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_describe_screen",
            description=("Compact 'where am I' description of the live screen: "
                         "{app, element_count, by_role, controls}."),
            input_schema=schema({"app_name": {"type": "string"}}),
            handler=h.describe_screen,
            annotations=READ_ONLY,
        ),
    ]


def input_macro_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_replay_timeline",
            description=("Replay a list of input events honoring each event's "
                         "'delta_ms' gap, scaled by 'speed' (2.0 = twice as "
                         "fast). Events are {op, ...} (op=move/click/press/"
                         "release/key/scroll). Returns {played}."),
            input_schema=schema({
                "events": {"type": "array", "items": {"type": "object"}},
                "speed": {"type": "number"}},
                required=["events"]),
            handler=h.replay_timeline,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_input_sequence",
            description=("Run a declarative input sequence: 'steps' of {op: "
                         "press|release|key|click|move|scroll} plus {op:wait,"
                         "ms} and {op:repeat,times,steps:[...]}. Encodes "
                         "press-hold-release chords. Returns the {log}."),
            input_schema=schema({
                "steps": {"type": "array", "items": {"type": "object"}}},
                required=["steps"]),
            handler=h.input_sequence,
            annotations=SIDE_EFFECT_ONLY,
        ),
    ]


def resilience_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_circuit_call",
            description=("Run an action list through a named circuit breaker: "
                         "after 'threshold' failures it opens and short-"
                         "circuits for 'reset_s' seconds. Returns {state, "
                         "record}."),
            input_schema=schema({
                "name": {"type": "string"},
                "actions": {"type": "array"},
                "threshold": {"type": "integer"},
                "reset_s": {"type": "number"}},
                required=["name", "actions"]),
            handler=h.circuit_call,
            annotations=SIDE_EFFECT_ONLY,
        ),
    ]


def ci_annotation_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_ci_annotations",
            description=("Emit GitHub Actions workflow annotations from result "
                         "dicts ({level, message, file?, line?, title?}) so "
                         "failures show inline in a PR. Returns the {lines}."),
            input_schema=schema({
                "annotations": {"type": "array",
                                "items": {"type": "object"}}},
                required=["annotations"]),
            handler=h.ci_annotations,
            annotations=READ_ONLY,
        ),
    ]


def clipboard_history_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_clip_history_capture",
            description="Capture the live clipboard text into history.",
            input_schema=schema({}),
            handler=h.clip_history_capture,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_clip_history_list",
            description="List the clipboard history (newest first).",
            input_schema=schema({}),
            handler=h.clip_history_list,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_clip_history_search",
            description="Search clipboard history (case-insensitive).",
            input_schema=schema({"query": {"type": "string"}},
                                required=["query"]),
            handler=h.clip_history_search,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_clip_history_start",
            description="Start the background clipboard-history poller.",
            input_schema=schema({}),
            handler=h.clip_history_start,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_clip_history_stop",
            description="Stop the background clipboard-history poller.",
            input_schema=schema({}),
            handler=h.clip_history_stop,
            annotations=SIDE_EFFECT_ONLY,
        ),
    ]


def audit_analysis_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_heal_stats",
            description=("Aggregate the self-healing event log into metrics: "
                         "heal_rate, by_method, fallback_rate, avg latency, "
                         "and the most-brittle locators."),
            input_schema=schema({"limit": {"type": "integer"}}),
            handler=h.heal_stats,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_scan_secrets",
            description=("Scan a JSON/data structure for hardcoded secrets "
                         "(by key name, value pattern — AWS/GitHub/private-key "
                         "— or high entropy) that should use ${secrets.*}. "
                         "Returns masked {findings}."),
            input_schema=schema({"data": {}}, required=["data"]),
            handler=h.scan_secrets,
            annotations=READ_ONLY,
        ),
    ]


def process_doc_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_generate_sop",
            description=("Generate a step-by-step SOP document from an action "
                         "list (numbered steps + HTML, the Task-Capture "
                         "deliverable). Writes to 'path' when given, else "
                         "returns the structured doc."),
            input_schema=schema({
                "actions": {"type": "array"},
                "title": {"type": "string"},
                "path": {"type": "string"}},
                required=["actions"]),
            handler=h.generate_sop,
            annotations=SIDE_EFFECT_ONLY,
        ),
    ]


def tween_drag_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_tween_drag",
            description=("Drag from 'start' [x,y] to 'end' [x,y] along an "
                         "eased path (easing: linear / ease_in_out_quad / "
                         "ease_out_cubic / ease_in_cubic). Returns {points}."),
            input_schema=schema({
                "start": {"type": "array", "items": {"type": "integer"}},
                "end": {"type": "array", "items": {"type": "integer"}},
                "steps": {"type": "integer"},
                "easing": {"type": "string"},
                "button": {"type": "string"}},
                required=["start", "end"]),
            handler=h.tween_drag,
            annotations=SIDE_EFFECT_ONLY,
        ),
    ]


def field_entry_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_set_field_text",
            description=("Clear the focused field and enter 'text' (Playwright "
                         "fill). 'clear' select_all|none; 'paste' True for "
                         "Unicode/emoji via clipboard; 'modifier' ctrl|command. "
                         "Returns {ops, plan}."),
            input_schema=schema({
                "text": {"type": "string"}, "clear": {"type": "string"},
                "paste": {"type": "boolean"}, "modifier": {"type": "string"}},
                required=["text"]),
            handler=h.set_field_text,
            annotations=SIDE_EFFECT_ONLY,
        ),
    ]


def mouse_path_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_move_along_path",
            description=("Move the pointer through 'waypoints' ([[x,y],...]) as "
                         "an eased polyline. 'per_segment_steps' + 'easing' "
                         "(linear / ease_*). Returns {points, path}."),
            input_schema=schema({
                "waypoints": {"type": "array",
                              "items": {"type": "array",
                                        "items": {"type": "integer"}}},
                "easing": {"type": "string"},
                "per_segment_steps": {"type": "integer"}},
                required=["waypoints"]),
            handler=h.move_along_path,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_drag_path",
            description=("Press at the first of 'waypoints' ([[x,y],...]), drag "
                         "through them, release at the last. 'button', 'easing', "
                         "'per_segment_steps'. Returns {points, path}."),
            input_schema=schema({
                "waypoints": {"type": "array",
                              "items": {"type": "array",
                                        "items": {"type": "integer"}}},
                "button": {"type": "string"},
                "easing": {"type": "string"},
                "per_segment_steps": {"type": "integer"}},
                required=["waypoints"]),
            handler=h.drag_path,
            annotations=SIDE_EFFECT_ONLY,
        ),
    ]


def plugin_sdk_tools() -> List[MCPTool]:
    _G = {"group": {"type": "string"}}
    return [
        MCPTool(
            name="ac_list_plugins",
            description=("Discover third-party AC_* commands registered via "
                         "the 'je_auto_control.commands' entry-point group "
                         "(without registering them). Returns {commands}."),
            input_schema=schema(dict(_G)),
            handler=h.list_plugins,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_load_plugins",
            description=("Discover and register third-party plugin commands "
                         "into the executor. Returns {loaded} names."),
            input_schema=schema(dict(_G)),
            handler=h.load_plugins,
            annotations=SIDE_EFFECT_ONLY,
        ),
    ]


def governance_tools() -> List[MCPTool]:
    _AD = {"action": {"type": "string"}, "requester": {"type": "string"},
           "db": {"type": "string"}}
    _TA = {"token": {"type": "string"}, "approver": {"type": "string"},
           "db": {"type": "string"}}
    return [
        MCPTool(
            name="ac_approval_request",
            description=("Maker-checker gate: file an approval request for a "
                         "high-risk 'action' and get a token. The action must "
                         "wait until a different principal approves. 'db' is an "
                         "optional JSON file shared across processes."),
            input_schema=schema(_AD, ["action"]),
            handler=h.approval_request,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_approval_approve",
            description=("Approve a pending request token as 'approver'. "
                         "Rejected (returns approved=False) if the approver "
                         "equals the requester (segregation of duties)."),
            input_schema=schema(_TA, ["token", "approver"]),
            handler=h.approval_approve,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_approval_reject",
            description=("Reject a pending request token as 'approver' (must "
                         "differ from the requester). Returns {rejected}."),
            input_schema=schema(_TA, ["token", "approver"]),
            handler=h.approval_reject,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_approval_status",
            description=("Report a request token's status (pending/approved/"
                         "rejected) and an 'approved' boolean to gate an "
                         "action on."),
            input_schema=schema({"token": {"type": "string"},
                                 "db": {"type": "string"}}, ["token"]),
            handler=h.approval_status,
            annotations=READ_ONLY,
        ),
    ]


def credential_lease_tools() -> List[MCPTool]:
    _T = {"token": {"type": "string"}}
    return [
        MCPTool(
            name="ac_lease_secret",
            description=("Issue a just-in-time lease for secret 'name', valid "
                         "for 'ttl' seconds (default 300). Returns {token, ttl} "
                         "only — never the value. Redeeming the value is a "
                         "Python-API-only operation, by design."),
            input_schema=schema({"name": {"type": "string"},
                                 "ttl": {"type": "number"}}, ["name"]),
            handler=h.lease_secret,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_lease_valid",
            description=("Report whether a lease token is still valid (exists "
                         "and not expired). Returns {valid}."),
            input_schema=schema(dict(_T), ["token"]),
            handler=h.lease_valid,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_revoke_lease",
            description="Revoke a lease token immediately. Returns {revoked}.",
            input_schema=schema(dict(_T), ["token"]),
            handler=h.revoke_lease,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_lease_active",
            description=("List active (non-expired) leases as {token, name, "
                         "ttl_remaining} — no secret values are returned."),
            input_schema=schema({}),
            handler=h.lease_active,
            annotations=READ_ONLY,
        ),
    ]


def egress_tools() -> List[MCPTool]:
    _LISTS = {"allow": {"type": "array", "items": {"type": "string"}},
              "deny": {"type": "array", "items": {"type": "string"}}}
    return [
        MCPTool(
            name="ac_egress_allow",
            description=("Lock the headless HTTP client to an egress policy. "
                         "'allow' is a default-deny host allowlist (fnmatch "
                         "globs over the URL hostname, e.g. '*.example.com'); "
                         "'deny' blocks hosts even if allowed. Omitting both "
                         "is allow-all. Returns the effective {allow, deny}."),
            input_schema=schema(dict(_LISTS)),
            handler=h.egress_allow,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_egress_check",
            description=("Report whether a URL's host is permitted by the "
                         "current egress policy. Returns {allowed}."),
            input_schema=schema({"url": {"type": "string"}}, ["url"]),
            handler=h.egress_check,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_egress_reset",
            description="Clear the egress policy back to allow-all.",
            input_schema=schema({}),
            handler=h.egress_reset,
            annotations=SIDE_EFFECT_ONLY,
        ),
    ]


def approval_testing_tools() -> List[MCPTool]:
    _ND = {"name": {"type": "string"},
           "approvals_dir": {"type": "string"},
           "extension": {"type": "string"}}
    return [
        MCPTool(
            name="ac_verify_artifact",
            description=("Approval testing: compare produced 'content' (text) "
                         "to the approved baseline <name>.approved.<ext> under "
                         "'approvals_dir'. On mismatch/new, the content is "
                         "written to <name>.received.<ext> for review. Returns "
                         "{status (verified/mismatch/new), match, "
                         "approved_path, received_path}."),
            input_schema=schema({**_ND, "content": {"type": "string"}},
                                ["name", "content"]),
            handler=h.verify_artifact,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_approve_artifact",
            description=("Promote the received artifact for 'name' to be the "
                         "approved baseline. Returns {approved} path."),
            input_schema=schema(dict(_ND), ["name"]),
            handler=h.approve_artifact,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_pending_artifacts",
            description=("List artifact names with a received file awaiting "
                         "approval under 'approvals_dir'. Returns {pending}."),
            input_schema=schema({"approvals_dir": {"type": "string"}}),
            handler=h.pending_artifacts,
            annotations=READ_ONLY,
        ),
    ]


def trajectory_eval_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_evaluate_trajectory",
            description=("Score an agent's recorded 'trajectory' (a list of "
                         "{action, args, observation} steps) against a 'rubric' "
                         "with optional keys required_actions (+ordered), "
                         "forbidden_actions, max_steps, success_contains. "
                         "Returns {passed, score, steps, checks} for agent "
                         "regression testing."),
            input_schema=schema(
                {"trajectory": {"type": "array",
                                "items": {"type": "object"}},
                 "rubric": {"type": "object"}},
                ["trajectory", "rubric"]),
            handler=h.evaluate_trajectory,
            annotations=READ_ONLY,
        ),
    ]


def compliance_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_compliance_report",
            description=("Map a flat 'evidence' object (e.g. "
                         "{egress_allowlist_enforced: true, "
                         "jit_credentials_used: true, secrets_scanned: true, "
                         "audit_logging_enabled: true, "
                         "change_approval_required: true, sbom_generated: "
                         "true}) to SOC2/ISO 27001 controls. Each is satisfied/"
                         "gap/not_assessed. Optional 'frameworks' filter, and "
                         "'path'+'fmt' (json|html) to write. Returns the "
                         "report {summary, controls}."),
            input_schema=schema(
                {"evidence": {"type": "object"},
                 "frameworks": {"type": "array", "items": {"type": "string"}},
                 "path": {"type": "string"},
                 "fmt": {"type": "string", "enum": ["json", "html"]}},
                ["evidence"]),
            handler=h.compliance_report,
            annotations=READ_ONLY,
        ),
    ]


def agent_trace_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_trace_record",
            description=("Record a GenAI-convention span on the default agent "
                         "trace: 'operation' (e.g. chat/tool), optional model, "
                         "system, input_tokens, output_tokens, tool_name, "
                         "duration_s, status (ok/error). Returns the span."),
            input_schema=schema(
                {"operation": {"type": "string"},
                 "model": {"type": "string"}, "system": {"type": "string"},
                 "input_tokens": {"type": "integer"},
                 "output_tokens": {"type": "integer"},
                 "tool_name": {"type": "string"},
                 "duration_s": {"type": "number"},
                 "status": {"type": "string", "enum": ["ok", "error"]}},
                ["operation"]),
            handler=h.trace_record,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_trace_summary",
            description=("Roll up the default agent trace: span_count, "
                         "error_count, input_tokens, output_tokens, "
                         "duration_s."),
            input_schema=schema({}),
            handler=h.trace_summary,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_trace_export",
            description=("Export the default agent trace as OTLP-friendly "
                         "spans (gen_ai.* attributes). Returns {spans}."),
            input_schema=schema({}),
            handler=h.trace_export,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_trace_reset",
            description="Clear the default agent trace. Returns {reset}.",
            input_schema=schema({}),
            handler=h.trace_reset,
            annotations=SIDE_EFFECT_ONLY,
        ),
    ]


def video_report_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_write_step_video",
            description=("Render captioned screenshots into a walkthrough "
                         "video. 'steps' is a list of {image (path), caption, "
                         "status (ok/error)}; each frame is held for "
                         "'seconds_per_step' at 'fps' with a caption banner "
                         "burned in. Writes 'output' (mp4/avi). Returns "
                         "{output, steps, fps, frame_count}."),
            input_schema=schema(
                {"steps": {"type": "array", "items": {"type": "object"}},
                 "output": {"type": "string"},
                 "fps": {"type": "integer"},
                 "seconds_per_step": {"type": "number"}},
                ["steps", "output"]),
            handler=h.write_step_video,
            annotations=SIDE_EFFECT_ONLY,
        ),
    ]


def fuzzy_tools() -> List[MCPTool]:
    _CHOICES = {"type": "array", "items": {"type": "string"}}
    return [
        MCPTool(
            name="ac_fuzzy_ratio",
            description=("Similarity score (0..1) between two strings, robust "
                         "to OCR/UI noise (difflib, or rapidfuzz if "
                         "installed). 'ignore_case' defaults true. Returns "
                         "{score}."),
            input_schema=schema(
                {"left": {"type": "string"}, "right": {"type": "string"},
                 "ignore_case": {"type": "boolean"}}, ["left", "right"]),
            handler=h.fuzzy_ratio,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_fuzzy_best_match",
            description=("Best fuzzy match of 'query' within 'choices' scoring "
                         ">= 'score_cutoff'. Returns {match, score, index} or "
                         "{match: null} when nothing qualifies."),
            input_schema=schema(
                {"query": {"type": "string"}, "choices": _CHOICES,
                 "score_cutoff": {"type": "number"},
                 "ignore_case": {"type": "boolean"}}, ["query", "choices"]),
            handler=h.fuzzy_best_match,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_fuzzy_dedupe",
            description=("Collapse near-duplicate strings, keeping the first "
                         "of each cluster (items >= 'threshold' similar are "
                         "dropped). Returns {unique}."),
            input_schema=schema(
                {"items": _CHOICES, "threshold": {"type": "number"},
                 "ignore_case": {"type": "boolean"}}, ["items"]),
            handler=h.fuzzy_dedupe,
            annotations=READ_ONLY,
        ),
    ]


def artifact_store_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_s3_upload",
            description=("Upload a local artifact to the configured default "
                         "S3-compatible store. Optional 'key' (defaults to the "
                         "file name). Returns {key}."),
            input_schema=schema(
                {"local_path": {"type": "string"}, "key": {"type": "string"}},
                ["local_path"]),
            handler=h.s3_upload,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_s3_download",
            description=("Download object 'key' from the default S3 store to "
                         "'local_path'. Returns {path}."),
            input_schema=schema(
                {"key": {"type": "string"},
                 "local_path": {"type": "string"}}, ["key", "local_path"]),
            handler=h.s3_download,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_s3_list",
            description=("List object keys in the default S3 store, optionally "
                         "under an extra 'prefix'. Returns {keys}."),
            input_schema=schema({"prefix": {"type": "string"}}),
            handler=h.s3_list,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_s3_delete",
            description="Delete object 'key' from the default S3 store. "
                        "Returns {deleted}.",
            input_schema=schema({"key": {"type": "string"}}, ["key"]),
            handler=h.s3_delete,
            annotations=SIDE_EFFECT_ONLY,
        ),
    ]


def image_dedup_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_image_hash",
            description=("Perceptual hash of an image file for similarity "
                         "comparison. 'algo' is 'average' (default) or "
                         "'dhash'. Returns {hash} (hex)."),
            input_schema=schema(
                {"path": {"type": "string"},
                 "algo": {"type": "string", "enum": ["average", "dhash"]}},
                ["path"]),
            handler=h.image_hash,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_dedupe_images",
            description=("Collapse near-duplicate images by perceptual hash, "
                         "keeping the first of each cluster (images within "
                         "'max_distance' bits are dropped). Returns {unique}."),
            input_schema=schema(
                {"paths": {"type": "array", "items": {"type": "string"}},
                 "max_distance": {"type": "integer"}}, ["paths"]),
            handler=h.dedupe_images,
            annotations=READ_ONLY,
        ),
    ]


def locale_tools() -> List[MCPTool]:
    _LOC = {"type": "string"}
    return [
        MCPTool(
            name="ac_parse_decimal",
            description=("Parse a locale-formatted decimal string (e.g. "
                         "'1.234,56' in de_DE) to a float. Returns {value}."),
            input_schema=schema(
                {"text": {"type": "string"}, "locale": _LOC}, ["text"]),
            handler=h.parse_decimal,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_parse_number",
            description=("Parse a locale-formatted integer string to an int. "
                         "Returns {value}."),
            input_schema=schema(
                {"text": {"type": "string"}, "locale": _LOC}, ["text"]),
            handler=h.parse_number,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_format_decimal",
            description="Format a number the way a locale writes decimals. "
                        "Returns {text}.",
            input_schema=schema(
                {"value": {"type": "number"}, "locale": _LOC}, ["value"]),
            handler=h.format_decimal,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_format_currency",
            description=("Format a value as a currency (ISO 4217) for a "
                         "locale. Returns {text}."),
            input_schema=schema(
                {"value": {"type": "number"}, "currency": {"type": "string"},
                 "locale": _LOC}, ["value", "currency"]),
            handler=h.format_currency,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_format_date",
            description=("Format an ISO (YYYY-MM-DD) date for a locale. 'fmt' "
                         "is short/medium/long/full. Returns {text}."),
            input_schema=schema(
                {"value": {"type": "string"}, "locale": _LOC,
                 "fmt": {"type": "string"}}, ["value"]),
            handler=h.format_date,
            annotations=READ_ONLY,
        ),
    ]


def voice_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_voice_register",
            description=("Register a voice command: a trigger 'phrase' and an "
                         "'actions' list (AC_* steps) to run when recognized "
                         "speech best-matches it. Returns {phrases}."),
            input_schema=schema(
                {"phrase": {"type": "string"},
                 "actions": {"type": "array", "items": {"type": "object"}}},
                ["phrase", "actions"]),
            handler=h.voice_register,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_voice_dispatch",
            description=("Run the command whose phrase best matches recognized "
                         "'text' (fuzzy). Returns {matched, phrase}."),
            input_schema=schema({"text": {"type": "string"}}, ["text"]),
            handler=h.voice_dispatch,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_voice_list",
            description="List registered voice-command phrases. Returns "
                        "{phrases}.",
            input_schema=schema({}),
            handler=h.voice_list,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_voice_clear",
            description="Remove all registered voice commands. Returns "
                        "{cleared}.",
            input_schema=schema({}),
            handler=h.voice_clear,
            annotations=SIDE_EFFECT_ONLY,
        ),
    ]


def coordinate_space_tools() -> List[MCPTool]:
    _DIMS = {"x": {"type": "number"}, "y": {"type": "number"},
             "physical_w": {"type": "integer"},
             "physical_h": {"type": "integer"},
             "model_w": {"type": "integer"}, "model_h": {"type": "integer"}}
    _REQ = ["x", "y", "physical_w", "physical_h", "model_w", "model_h"]
    return [
        MCPTool(
            name="ac_to_physical",
            description=("Map a model-grid coordinate (e.g. a 1000x1000 or XGA "
                         "click from a computer-use model) to physical screen "
                         "pixels. Returns {x, y}."),
            input_schema=schema(dict(_DIMS), list(_REQ)),
            handler=h.to_physical,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_to_model",
            description=("Map a physical-pixel coordinate to a model grid "
                         "(inverse of ac_to_physical). Returns {x, y}."),
            input_schema=schema(dict(_DIMS), list(_REQ)),
            handler=h.to_model,
            annotations=READ_ONLY,
        ),
    ]


def loop_guard_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_loop_guard_observe",
            description=("Feed an agent step (tool, args, optional "
                         "result_digest) to the default stuck-loop guard. "
                         "Detects repeat / ping_pong / no_op patterns. Returns "
                         "{pattern, level (ok/warn/critical), count}."),
            input_schema=schema(
                {"tool": {"type": "string"}, "args": {"type": "object"},
                 "result_digest": {"type": "string"}}, ["tool"]),
            handler=h.loop_guard_observe,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_loop_guard_reset",
            description="Clear the default loop guard's history. Returns "
                        "{reset}.",
            input_schema=schema({}),
            handler=h.loop_guard_reset,
            annotations=SIDE_EFFECT_ONLY,
        ),
    ]


def process_mining_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_mine_actions",
            description=("Mine a recorded 'actions' log for repeated command "
                         "sub-sequences (n-grams of length min_len..max_len "
                         "seen >= min_count) and rank automation candidates by "
                         "count*length. Returns {total_actions, patterns, "
                         "candidates}."),
            input_schema=schema(
                {"actions": {"type": "array"},
                 "min_len": {"type": "integer"},
                 "max_len": {"type": "integer"},
                 "min_count": {"type": "integer"}}, ["actions"]),
            handler=h.mine_actions,
            annotations=READ_ONLY,
        ),
    ]


def asset_tools() -> List[MCPTool]:
    _ENV = {"environment": {"type": "string"}, "db": {"type": "string"}}
    return [
        MCPTool(
            name="ac_set_asset",
            description=("Store a typed, environment-scoped asset. 'asset_type' "
                         "is text/int/bool/credential (credential 'value' is a "
                         "secret name, not the secret). Returns {ok}."),
            input_schema=schema(
                {"name": {"type": "string"}, "value": {},
                 "asset_type": {"type": "string",
                                "enum": ["text", "int", "bool",
                                         "credential"]},
                 **_ENV}, ["name", "value"]),
            handler=h.set_asset,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_get_asset",
            description=("Read a typed asset for an environment (falls back to "
                         "the default env). Credential values are returned as a "
                         "reference, never the secret. Returns {name, type, "
                         "value}."),
            input_schema=schema({"name": {"type": "string"}, **_ENV},
                                ["name"]),
            handler=h.get_asset,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_list_assets",
            description=("List assets (optionally for one environment) as "
                         "{name, type, environment} — no values. Returns "
                         "{assets}."),
            input_schema=schema(dict(_ENV)),
            handler=h.list_assets,
            annotations=READ_ONLY,
        ),
    ]


def events_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_emit_event",
            description=("Wrap 'data' in a CloudEvents 1.0 envelope "
                         "('event_type', 'source', optional 'subject') and "
                         "optionally POST it to 'url' over the egress-guarded "
                         "HTTP client. Returns {event, status?}."),
            input_schema=schema(
                {"event_type": {"type": "string"}, "data": {},
                 "source": {"type": "string"},
                 "subject": {"type": "string"}, "url": {"type": "string"}},
                ["event_type"]),
            handler=h.emit_event,
            annotations=SIDE_EFFECT_ONLY,
        ),
    ]


def notify_channel_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_notify_webhook",
            description=("Send a chat/webhook notification. 'transport' shapes "
                         "the payload: slack/discord/teams/raw (Slack & Teams "
                         "MessageCard use text, Discord uses content). POSTs via "
                         "the egress-guarded HTTP client. Returns {ok, status, "
                         "transport}."),
            input_schema=schema(
                {"url": {"type": "string"}, "text": {"type": "string"},
                 "transport": {"type": "string",
                               "enum": ["raw", "slack", "discord", "teams"]},
                 "title": {"type": "string"}}, ["url", "text"]),
            handler=h.notify_webhook,
            annotations=SIDE_EFFECT_ONLY,
        ),
    ]


def jsonpath_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_json_query",
            description=("Query parsed JSON with a JSONPath subset ($, .key, "
                         "[n]/[-n], * / [*], .. recursive, [?(@.k op v)] "
                         "filter). Returns {matches} (all matches)."),
            input_schema=schema(
                {"data": {"type": "object"}, "path": {"type": "string"}},
                ["data", "path"]),
            handler=h.json_query,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_json_extract",
            description=("Extract a {key: jsonpath} 'mapping' from 'data' into a "
                         "flat object (first match per path). Returns {result}."),
            input_schema=schema(
                {"data": {"type": "object"}, "mapping": {"type": "object"}},
                ["data", "mapping"]),
            handler=h.json_extract,
            annotations=READ_ONLY,
        ),
    ]


def json_schema_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_validate_json",
            description=("Validate parsed JSON 'data' against a JSON Schema "
                         "(Draft 2020-12 subset: type/enum/const, numeric & "
                         "string bounds, array/object keywords, allOf/anyOf/"
                         "oneOf/not, local $ref). Returns {ok, errors:[{path, "
                         "keyword, message}]}."),
            input_schema=schema(
                {"data": {"type": "object"}, "schema": {"type": "object"}},
                ["data", "schema"]),
            handler=h.validate_json,
            annotations=READ_ONLY,
        ),
    ]


def vuln_scan_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_scan_vulns",
            description=("Match SBOM 'components' (or a full SBOM dict) against "
                         "an OSV 'advisories' database. Returns {findings:"
                         "[{id, package, version, severity, fixed, aliases}], "
                         "count}. Advisories are supplied as data (offline)."),
            input_schema=schema(
                {"components": {"type": "object"},
                 "advisories": {"type": "array"}},
                ["components"]),
            handler=h.scan_vulns,
            annotations=READ_ONLY,
        ),
    ]


def vex_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_apply_vex",
            description=("Apply an OpenVEX document to vulnerability "
                         "'findings': drop the ones marked not_affected/fixed "
                         "and annotate the rest with their VEX status. Returns "
                         "{findings, count}."),
            input_schema=schema(
                {"findings": {"type": "array"}, "vex": {"type": "object"}},
                ["findings", "vex"]),
            handler=h.apply_vex,
            annotations=READ_ONLY,
        ),
    ]


def license_policy_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_check_licenses",
            description=("Evaluate SBOM 'components' (or a full SBOM dict) "
                         "licenses against 'allow'/'deny' SPDX lists. Returns "
                         "{violations:[{name, version, license, status}], "
                         "count} where status is denied/unknown."),
            input_schema=schema(
                {"components": {"type": "object"},
                 "allow": {"type": "array"}, "deny": {"type": "array"}},
                ["components"]),
            handler=h.check_licenses,
            annotations=READ_ONLY,
        ),
    ]


def jwt_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_jwt_encode",
            description=("Sign a compact JWT from 'claims' with 'key' (HMAC "
                         "alg HS256/384/512). Returns {token}."),
            input_schema=schema(
                {"claims": {"type": "object"}, "key": {"type": "string"},
                 "alg": {"type": "string"}},
                ["claims", "key"]),
            handler=h.jwt_encode,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_jwt_decode",
            description=("Verify a JWT 'token' with 'key' and an 'algorithms' "
                         "allowlist (rejects alg=none/confusion), checking exp/"
                         "nbf/aud. Returns {ok, claims} or {ok:false, error}."),
            input_schema=schema(
                {"token": {"type": "string"}, "key": {"type": "string"},
                 "algorithms": {"type": "array"},
                 "audience": {"type": "string"}},
                ["token", "key"]),
            handler=h.jwt_decode,
            annotations=READ_ONLY,
        ),
    ]


def rate_limit_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_rate_limit",
            description=("Try to take 'n' tokens from a named token-bucket "
                         "limiter ('rate' tokens/sec, 'capacity' burst). "
                         "Returns {acquired, tokens, wait}."),
            input_schema=schema(
                {"name": {"type": "string"}, "rate": {"type": "number"},
                 "capacity": {"type": "number"}, "n": {"type": "number"}},
                ["name"]),
            handler=h.rate_limit,
            annotations=READ_ONLY,
        ),
    ]


def http_conditional_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_parse_cache_control",
            description=("Parse the 'headers' Cache-Control into {directives} "
                         "(max-age as int, flags as true)."),
            input_schema=schema({"headers": {"type": "object"}}, ["headers"]),
            handler=h.parse_cache_control,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_store_validators",
            description=("Extract cache validators (etag, last_modified, date, "
                         "cache_control) from an HTTP 'response'. Returns "
                         "{validators}."),
            input_schema=schema({"response": {"type": "object"}}, ["response"]),
            handler=h.store_validators,
            annotations=READ_ONLY,
        ),
    ]


def cookie_jar_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_cookie_header",
            description=("Build a Cookie request header from one or many "
                         "'set_cookies' (Set-Cookie strings or a JSON list). "
                         "Returns {cookie_header, cookies}."),
            input_schema=schema(
                {"set_cookies": {"type": ["string", "array"]}},
                ["set_cookies"]),
            handler=h.cookie_header,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_parse_set_cookie",
            description=("Parse one Set-Cookie 'header' into {cookie: {name, "
                         "value, attributes}} (or null)."),
            input_schema=schema({"header": {"type": "string"}}, ["header"]),
            handler=h.parse_set_cookie,
            annotations=READ_ONLY,
        ),
    ]


def http_content_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_decode_body",
            description=("Decode a base64 'body_base64' per its 'headers' "
                         "Content-Encoding (gzip / deflate / identity). Returns "
                         "{body_base64, text}."),
            input_schema=schema(
                {"headers": {"type": "object"},
                 "body_base64": {"type": "string"}},
                ["headers", "body_base64"]),
            handler=h.decode_body,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_parse_quality_values",
            description=("Parse a quality-value 'header' (Accept / "
                         "Accept-Encoding) into {values}: [token, q] sorted by q "
                         "descending."),
            input_schema=schema({"header": {"type": "string"}}, ["header"]),
            handler=h.parse_quality_values,
            annotations=READ_ONLY,
        ),
    ]


def multipart_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_build_multipart",
            description=("Build a multipart/form-data body from 'fields' "
                         "(object/list) and 'files' (each {name, filename, "
                         "content, content_type?}); optional 'boundary'. Returns "
                         "{content_type, body_base64}."),
            input_schema=schema(
                {"fields": {"type": "object"}, "files": {"type": "array"},
                 "boundary": {"type": "string"}},
                []),
            handler=h.build_multipart,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_parse_multipart",
            description=("Parse a base64 multipart body ('body_base64') with its "
                         "'content_type' into {fields, files}."),
            input_schema=schema(
                {"content_type": {"type": "string"},
                 "body_base64": {"type": "string"}},
                ["content_type", "body_base64"]),
            handler=h.parse_multipart,
            annotations=READ_ONLY,
        ),
    ]


def link_header_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_parse_link_header",
            description=("Parse an RFC 8288 Link header 'value' into {links} "
                         "(each {uri, rel, params}), handling quoted params and "
                         "multiple links."),
            input_schema=schema({"value": {"type": "string"}}, ["value"]),
            handler=h.parse_link_header,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_next_url",
            description=("Return the rel=next URL from a Link header 'value' as "
                         "{url} (null when absent)."),
            input_schema=schema({"value": {"type": "string"}}, ["value"]),
            handler=h.next_url,
            annotations=READ_ONLY,
        ),
    ]


def referential_tools() -> List[MCPTool]:
    rows = {"type": "array", "items": {"type": "object"}}
    return [
        MCPTool(
            name="ac_check_foreign_key",
            description=("Every non-null 'child_col' value in 'child_rows' must "
                         "exist in 'parent_col' of 'parent_rows'. Returns {ok, "
                         "violations, missing}."),
            input_schema=schema(
                {"child_rows": rows, "child_col": {"type": "string"},
                 "parent_rows": rows, "parent_col": {"type": "string"}},
                ["child_rows", "child_col", "parent_rows", "parent_col"]),
            handler=h.check_foreign_key,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_check_unique_key",
            description=("A single or composite key ('cols': column name or "
                         "list) must be unique across 'rows'. Returns {ok, "
                         "duplicates}."),
            input_schema=schema(
                {"rows": rows, "cols": {"type": ["string", "array"]}},
                ["rows", "cols"]),
            handler=h.check_unique_key,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_check_accepted_values",
            description=("Every non-null 'col' value in 'rows' must be within "
                         "'allowed'. Returns {ok, violations, unexpected}."),
            input_schema=schema(
                {"rows": rows, "col": {"type": "string"},
                 "allowed": {"type": "array"}},
                ["rows", "col", "allowed"]),
            handler=h.check_accepted_values,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_check_row_count",
            description=("The 'rows' count must fall within optional 'minimum' / "
                         "'maximum'. Returns {ok, count}."),
            input_schema=schema(
                {"rows": rows, "minimum": {"type": "integer"},
                 "maximum": {"type": "integer"}},
                ["rows"]),
            handler=h.check_row_count,
            annotations=READ_ONLY,
        ),
    ]


def dataset_diff_tools() -> List[MCPTool]:
    rows_schema = {"type": "array", "items": {"type": "object"}}
    key_schema = {"type": ["string", "array"]}
    return [
        MCPTool(
            name="ac_diff_rows",
            description=("Diff 'old_rows' against 'new_rows' keyed by 'key' "
                         "(column name or list). Returns {diff: {added, removed, "
                         "changed, unchanged}, summary}."),
            input_schema=schema(
                {"old_rows": rows_schema, "new_rows": rows_schema,
                 "key": key_schema},
                ["old_rows", "new_rows", "key"]),
            handler=h.diff_rows,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_cell_changes",
            description=("Per-cell changes between 'old_rows' and 'new_rows' "
                         "keyed by 'key'. Returns {changes: [{key, column, old, "
                         "new}]}."),
            input_schema=schema(
                {"old_rows": rows_schema, "new_rows": rows_schema,
                 "key": key_schema},
                ["old_rows", "new_rows", "key"]),
            handler=h.cell_changes,
            annotations=READ_ONLY,
        ),
    ]


def optimistic_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_cas_put",
            description=("Optimistic put 'value' at 'key' in named store 'name' "
                         "if 'expected_version' matches (0=absent, omit=blind). "
                         "Returns {ok, version} or {ok: false, error}."),
            input_schema=schema(
                {"name": {"type": "string"}, "key": {"type": "string"},
                 "value": {"type": "object"},
                 "expected_version": {"type": "integer"}},
                ["name", "key", "value"]),
            handler=h.cas_put,
            annotations=NON_DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_cas_get",
            description=("Read {record: {value, version}} (or null) for 'key' in "
                         "named versioned store 'name'."),
            input_schema=schema(
                {"name": {"type": "string"}, "key": {"type": "string"}},
                ["name", "key"]),
            handler=h.cas_get,
            annotations=READ_ONLY,
        ),
    ]


def outbox_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_outbox_enqueue",
            description=("Enqueue 'event' into named outbox 'name' for durable "
                         "at-least-once delivery. Returns {id, pending}."),
            input_schema=schema(
                {"name": {"type": "string"}, "event": {"type": "object"}},
                ["name", "event"]),
            handler=h.outbox_enqueue,
            annotations=NON_DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_outbox_pending",
            description=("List the pending entries of named outbox 'name'. "
                         "Returns {pending}."),
            input_schema=schema({"name": {"type": "string"}}, ["name"]),
            handler=h.outbox_pending,
            annotations=READ_ONLY,
        ),
    ]


def locale_collation_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_collation_sort",
            description=("Locale-aware sort of string list 'items'. 'strength' "
                         "primary|secondary|tertiary; 'tailoring' is an ordered "
                         "alphabet (e.g. Swedish '...xyzåäö'). Returns {sorted}."),
            input_schema=schema(
                {"items": {"type": "array", "items": {"type": "string"}},
                 "strength": {"type": "string"},
                 "tailoring": {"type": "string"},
                 "reverse": {"type": "boolean"}},
                ["items"]),
            handler=h.collation_sort,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_collation_compare",
            description=("Locale-aware compare of 'first' vs 'second'; returns "
                         "{order: -1|0|1}. Same 'strength'/'tailoring' options."),
            input_schema=schema(
                {"first": {"type": "string"}, "second": {"type": "string"},
                 "strength": {"type": "string"},
                 "tailoring": {"type": "string"}},
                ["first", "second"]),
            handler=h.collation_compare,
            annotations=READ_ONLY,
        ),
    ]


def confusables_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_confusable_scan",
            description=("Homoglyph / mixed-script spoofing report for 'text'. "
                         "Returns {skeleton, homoglyphs, mixed_script, scripts}."),
            input_schema=schema({"text": {"type": "string"}}, ["text"]),
            handler=h.confusable_scan,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_confusable_compare",
            description=("Whether 'first' and 'second' render to the same "
                         "confusable skeleton. Returns {confusable}."),
            input_schema=schema(
                {"first": {"type": "string"}, "second": {"type": "string"}},
                ["first", "second"]),
            handler=h.confusable_compare,
            annotations=READ_ONLY,
        ),
    ]


def readability_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_readability_report",
            description=("Readability report for 'text': Flesch reading ease, "
                         "Flesch-Kincaid grade, Gunning Fog, SMOG, ARI + counts."),
            input_schema=schema({"text": {"type": "string"}}, ["text"]),
            handler=h.readability_report,
            annotations=READ_ONLY,
        ),
    ]


def list_format_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_format_list",
            description=("Join 'items' into a localised list string. 'style' "
                         "and|or|unit; 'locale' en|es|fr|de|pt. Returns {text}."),
            input_schema=schema(
                {"items": {"type": "array", "items": {"type": "string"}},
                 "style": {"type": "string"}, "locale": {"type": "string"}},
                ["items"]),
            handler=h.format_list,
            annotations=READ_ONLY,
        ),
    ]


def gettext_catalog_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_gettext_translate",
            description=("Parse a gettext '.po' string 'po' and translate "
                         "'msgid' (optional 'context'). Returns {text}."),
            input_schema=schema(
                {"po": {"type": "string"}, "msgid": {"type": "string"},
                 "context": {"type": "string"}},
                ["po", "msgid"]),
            handler=h.gettext_translate,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_gettext_ngettext",
            description=("Parse a '.po' string 'po' and pick the plural-correct "
                         "translation of 'msgid'/'msgid_plural' for count 'n'."),
            input_schema=schema(
                {"po": {"type": "string"}, "msgid": {"type": "string"},
                 "msgid_plural": {"type": "string"}, "n": {"type": "integer"}},
                ["po", "msgid", "msgid_plural", "n"]),
            handler=h.gettext_ngettext,
            annotations=READ_ONLY,
        ),
    ]


def checksum_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_checksum_validate",
            description=("Validate a number's check digit. 'scheme' is "
                         "luhn|verhoeff|damm|mod97. Returns {valid}."),
            input_schema=schema(
                {"scheme": {"type": "string"}, "number": {"type": "string"}},
                ["scheme", "number"]),
            handler=h.checksum_validate,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_checksum_digit",
            description=("Compute the check digit(s) to append to 'partial'. "
                         "'scheme' is luhn|verhoeff|damm|mod97. "
                         "Returns {check_digit}."),
            input_schema=schema(
                {"scheme": {"type": "string"}, "partial": {"type": "string"}},
                ["scheme", "partial"]),
            handler=h.checksum_digit,
            annotations=READ_ONLY,
        ),
    ]


def message_format_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_format_message",
            description=("Render an ICU-lite MessageFormat 'pattern' against "
                         "'args' (plural/select/selectordinal, =N, #). "
                         "'locale' picks plural rules. Returns {text}."),
            input_schema=schema(
                {"pattern": {"type": "string"}, "args": {"type": "object"},
                 "locale": {"type": "string"}},
                ["pattern"]),
            handler=h.format_message,
            annotations=READ_ONLY,
        ),
    ]


def bidi_check_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_bidi_check",
            description=("Bidirectional-text QA for 'text': bidi controls, "
                         "nesting balance, base direction, Trojan-source flag."),
            input_schema=schema({"text": {"type": "string"}}, ["text"]),
            handler=h.bidi_check,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_bidi_strip",
            description=("Remove every bidi control character from 'text'. "
                         "Returns {text}."),
            input_schema=schema({"text": {"type": "string"}}, ["text"]),
            handler=h.bidi_strip,
            annotations=NON_DESTRUCTIVE,
        ),
    ]


def sequence_gap_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_sequence_observe",
            description=("Observe sequence number 'seq' on 'stream_id' in named "
                         "tracker 'name'. Returns {status: ok|duplicate|gap|"
                         "reorder, seq, missing}."),
            input_schema=schema(
                {"name": {"type": "string"}, "stream_id": {"type": "string"},
                 "seq": {"type": "integer"}},
                ["name", "stream_id", "seq"]),
            handler=h.sequence_observe,
            annotations=NON_DESTRUCTIVE,
        ),
    ]


def dedup_window_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_dedup_check",
            description=("Check-and-mark a 'message_id' in a named dedup window "
                         "'name' (TTL 'ttl_s'). Returns {first_seen, size} — "
                         "first_seen is false for a duplicate within the window."),
            input_schema=schema(
                {"name": {"type": "string"},
                 "message_id": {"type": "string"}, "ttl_s": {"type": "number"}},
                ["name", "message_id"]),
            handler=h.dedup_check,
            annotations=NON_DESTRUCTIVE,
        ),
    ]


def idempotency_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_idempotency_begin",
            description=("Register/look up idempotency 'key' in a named store "
                         "'name' (optional 'request' for conflict detection). "
                         "Returns {status: new|in_progress|completed, response}."),
            input_schema=schema(
                {"name": {"type": "string"}, "key": {"type": "string"},
                 "request": {"type": "object"}},
                ["name", "key"]),
            handler=h.idempotency_begin,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_idempotency_complete",
            description=("Store the completed 'response' for idempotency 'key' "
                         "in named store 'name'. Returns {status}."),
            input_schema=schema(
                {"name": {"type": "string"}, "key": {"type": "string"},
                 "response": {"type": "object"}},
                ["name", "key", "response"]),
            handler=h.idempotency_complete,
            annotations=NON_DESTRUCTIVE,
        ),
    ]


def smoothing_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_sma",
            description=("Trailing simple moving average of a numeric 'values' "
                         "series over the last 'window' points. Returns {series}."),
            input_schema=schema(
                {"values": {"type": "array"}, "window": {"type": "integer"}},
                ["values", "window"]),
            handler=h.sma,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_ewma",
            description=("Exponentially-weighted moving average of 'values' with "
                         "smoothing factor 'alpha'. Returns {series}."),
            input_schema=schema(
                {"values": {"type": "array"}, "alpha": {"type": "number"}},
                ["values"]),
            handler=h.ewma,
            annotations=READ_ONLY,
        ),
    ]


def anomaly_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_detect_anomalies",
            description=("Flag anomalies in a numeric 'values' series by 'method' "
                         "(mad / zscore) with optional 'threshold'. Returns "
                         "{results: [{index, value, score, is_anomaly}]}."),
            input_schema=schema(
                {"values": {"type": "array"}, "method": {"type": "string"},
                 "threshold": {"type": "number"}},
                ["values"]),
            handler=h.detect_anomalies,
            annotations=READ_ONLY,
        ),
    ]


def timeseries_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_ts_rate",
            description=("Per-second counter rate (reset-aware) over a 'series' "
                         "of [timestamp, value] pairs, optional 'window_s'. "
                         "Returns {rate}."),
            input_schema=schema(
                {"series": {"type": "array"}, "window_s": {"type": "number"}},
                ["series"]),
            handler=h.ts_rate,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_ts_downsample",
            description=("Roll a 'series' of [timestamp, value] pairs into "
                         "'bucket_s' tumbling buckets aggregated by 'agg' "
                         "(avg/sum/min/max/first/last/count). Returns {buckets}."),
            input_schema=schema(
                {"series": {"type": "array"}, "bucket_s": {"type": "number"},
                 "agg": {"type": "string"}},
                ["series", "bucket_s"]),
            handler=h.ts_downsample,
            annotations=READ_ONLY,
        ),
    ]


def schema_compat_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_check_compatibility",
            description=("Classify JSON-Schema changes from 'old' to 'new' under "
                         "'mode' (backward / forward / full). Returns "
                         "{compatible, mode, changes, breaking}."),
            input_schema=schema(
                {"old": {"type": "object"}, "new": {"type": "object"},
                 "mode": {"type": "string"}},
                ["old", "new"]),
            handler=h.check_compatibility,
            annotations=READ_ONLY,
        ),
    ]


def data_drift_tools() -> List[MCPTool]:
    seq_schema = {"type": "array"}
    return [
        MCPTool(
            name="ac_detect_drift",
            description=("Numeric distribution drift of 'current' vs "
                         "'reference': Population Stability Index (with verdict "
                         "at 'threshold') plus the KS two-sample test. Returns "
                         "{psi, drifted, ks}."),
            input_schema=schema(
                {"reference": seq_schema, "current": seq_schema,
                 "threshold": {"type": "number"}, "bins": {"type": "integer"}},
                ["reference", "current"]),
            handler=h.detect_drift,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_categorical_drift",
            description=("Categorical drift of 'current' vs 'reference': "
                         "chi-square statistic and total-variation distance. "
                         "Returns {chi_square, total_variation, categories}."),
            input_schema=schema(
                {"reference": seq_schema, "current": seq_schema},
                ["reference", "current"]),
            handler=h.categorical_drift,
            annotations=READ_ONLY,
        ),
    ]


def layered_config_tools() -> List[MCPTool]:
    layer_schema = {"type": "array", "items": {"type": "object"}}
    return [
        MCPTool(
            name="ac_resolve_config",
            description=("Deep-merge ordered config 'layers' (each {name, "
                         "mapping, priority?}; higher priority wins) into a "
                         "single {config}."),
            input_schema=schema({"layers": layer_schema}, ["layers"]),
            handler=h.resolve_config,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_explain_config",
            description=("Report the value and winning layer name for a dotted "
                         "'key' across config 'layers'. Returns {trace}."),
            input_schema=schema(
                {"layers": layer_schema, "key": {"type": "string"}},
                ["layers", "key"]),
            handler=h.explain_config,
            annotations=READ_ONLY,
        ),
    ]


def sse_client_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_parse_sse",
            description=("Parse a Server-Sent Events ('text/event-stream') "
                         "'text' blob into {events} (event/data/id/retry), "
                         "flushing a trailing event without a final blank line."),
            input_schema=schema({"text": {"type": "string"}}, ["text"]),
            handler=h.parse_sse,
            annotations=READ_ONLY,
        ),
    ]


def dotenv_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_parse_dotenv",
            description=("Parse .env 'text' (KEY=VALUE lines, export prefixes, "
                         "quoting, escapes, inline comments) into {values}."),
            input_schema=schema({"text": {"type": "string"}}, ["text"]),
            handler=h.parse_dotenv,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_load_dotenv",
            description=("Load a .env file at 'path' into a fresh {values} dict. "
                         "'override' is accepted for symmetry (fresh dict)."),
            input_schema=schema(
                {"path": {"type": "string"}, "override": {"type": "boolean"}},
                ["path"]),
            handler=h.load_dotenv,
            annotations=READ_ONLY,
        ),
    ]


def http_problem_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_parse_problem",
            description=("Parse an RFC 9457 application/problem+json HTTP "
                         "'response' ({status, headers, json}). Returns "
                         "{problem} (type/title/status/detail/instance + "
                         "extensions) or null when not a problem document."),
            input_schema=schema({"response": {"type": "object"}}, ["response"]),
            handler=h.parse_problem,
            annotations=READ_ONLY,
        ),
    ]


def data_profile_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_profile_rows",
            description=("Profile 'rows' into per-column stats (count, null "
                         "fraction, distinct, inferred type, top values, numeric "
                         "min/max/mean). Optional 'columns' subset. Returns "
                         "{profile}."),
            input_schema=schema(
                {"rows": {"type": "array"}, "columns": {"type": "array"}},
                ["rows"]),
            handler=h.profile_rows,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_infer_schema",
            description=("Infer a validate_rows-compatible schema from observed "
                         "'rows' (type, required, unique, numeric bounds). "
                         "Optional 'columns' subset. Returns {schema}."),
            input_schema=schema(
                {"rows": {"type": "array"}, "columns": {"type": "array"}},
                ["rows"]),
            handler=h.infer_schema,
            annotations=READ_ONLY,
        ),
    ]


def config_redaction_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_redact_config",
            description=("Return a deep copy of 'obj' with secret-looking values "
                         "masked (key-name / value-format / high-entropy "
                         "detection). Optional 'mask'. Returns {redacted}."),
            input_schema=schema(
                {"obj": {"type": "object"}, "mask": {"type": "string"}},
                ["obj"]),
            handler=h.redact_config,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_redact_secret_text",
            description=("Mask secret-looking tokens within a free-text 'text' "
                         "string (e.g. a log line). Optional 'mask'. Returns "
                         "{text}."),
            input_schema=schema(
                {"text": {"type": "string"}, "mask": {"type": "string"}},
                ["text"]),
            handler=h.redact_secret_text,
            annotations=READ_ONLY,
        ),
    ]


def config_schema_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_validate_config",
            description=("Validate a 'config' mapping against a 'schema' spec "
                         "({name: {type, default, required, choices}}); coerces "
                         "types. Returns {ok, config, errors}."),
            input_schema=schema(
                {"schema": {"type": "object"}, "config": {"type": "object"}},
                ["schema", "config"]),
            handler=h.validate_config,
            annotations=READ_ONLY,
        ),
    ]


def secret_ref_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_resolve_ref",
            description=("Resolve a value reference 'ref' (env://VAR, "
                         "file://path, or secret://name) to {value}."),
            input_schema=schema({"ref": {"type": "string"}}, ["ref"]),
            handler=h.resolve_ref,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_resolve_refs",
            description=("Recursively resolve every env:// / file:// / secret:// "
                         "reference inside 'obj'. Returns {resolved}."),
            input_schema=schema({"obj": {"type": "object"}}, ["obj"]),
            handler=h.resolve_refs,
            annotations=READ_ONLY,
        ),
    ]


def otlp_export_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_spans_to_otlp",
            description=("Wrap 'spans' (each {trace_id, span_id, name, "
                         "start_unix_nano, end_unix_nano, attributes?}) in an "
                         "OTLP/JSON resourceSpans envelope; optional "
                         "'resource_attrs'. Returns {payload}."),
            input_schema=schema(
                {"spans": {"type": "array"},
                 "resource_attrs": {"type": "object"}},
                ["spans"]),
            handler=h.spans_to_otlp,
            annotations=READ_ONLY,
        ),
    ]


def near_dup_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_simhash",
            description=("SimHash fingerprint (int) of 'text' (optional 'bits'). "
                         "Returns {simhash}."),
            input_schema=schema(
                {"text": {"type": "string"}, "bits": {"type": "integer"}},
                ["text"]),
            handler=h.simhash,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_near_duplicates",
            description=("Cluster near-duplicate 'texts' within 'max_distance' "
                         "SimHash bits. Returns {clusters} of index lists."),
            input_schema=schema(
                {"texts": {"type": "array"},
                 "max_distance": {"type": "integer"}},
                ["texts"]),
            handler=h.near_duplicates,
            annotations=READ_ONLY,
        ),
    ]


def text_similarity_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_text_similarity",
            description=("Normalised [0,1] string similarity between 'a' and 'b' "
                         "for 'metric' (levenshtein / damerau_levenshtein / jaro "
                         "/ jaro_winkler / jaccard / dice). Returns {score}."),
            input_schema=schema(
                {"a": {"type": "string"}, "b": {"type": "string"},
                 "metric": {"type": "string"}},
                ["a", "b"]),
            handler=h.text_similarity,
            annotations=READ_ONLY,
        ),
    ]


def text_normalize_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_normalize_text",
            description=("Unicode-normalise 'text' (form NFKC/NFC/..., casefold, "
                         "collapse whitespace) for robust matching. Returns "
                         "{text}."),
            input_schema=schema(
                {"text": {"type": "string"}, "form": {"type": "string"},
                 "casefold": {"type": "boolean"},
                 "collapse_ws": {"type": "boolean"}},
                ["text"]),
            handler=h.normalize_text,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_slugify",
            description=("Produce an ASCII slug from 'text' (de-accent, "
                         "lowercase, join alnum runs with 'sep'). Returns "
                         "{slug}."),
            input_schema=schema(
                {"text": {"type": "string"}, "sep": {"type": "string"}},
                ["text"]),
            handler=h.slugify,
            annotations=READ_ONLY,
        ),
    ]


def canonical_log_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_canonical_log",
            description=("Build a canonical (wide-event) log line from a "
                         "'fields' object. Returns {line, json}."),
            input_schema=schema({"fields": {"type": "object"}}, ["fields"]),
            handler=h.canonical_log,
            annotations=READ_ONLY,
        ),
    ]


def baggage_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_baggage_parse",
            description=("Parse a W3C 'baggage' header (percent-encoded "
                         "key=value list, optional ;metadata) into {items}."),
            input_schema=schema({"header": {"type": "string"}}, ["header"]),
            handler=h.baggage_parse,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_baggage_format",
            description=("Serialise an 'items' object into a percent-encoded "
                         "W3C baggage {header}."),
            input_schema=schema({"items": {"type": "object"}}, ["items"]),
            handler=h.baggage_format,
            annotations=READ_ONLY,
        ),
    ]


def trace_context_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_trace_inject",
            description=("Propagate a W3C trace context into outgoing 'headers'. "
                         "With 'traceparent' set, derive a child span of that "
                         "parent; else start a fresh root. Returns updated "
                         "{headers, traceparent, trace_id, span_id}."),
            input_schema=schema(
                {"headers": {"type": "object"},
                 "traceparent": {"type": "string"}},
                []),
            handler=h.trace_inject,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_trace_extract",
            description=("Extract a W3C trace context from request 'headers'. "
                         "Returns {context} (or null when no traceparent)."),
            input_schema=schema({"headers": {"type": "object"}}, ["headers"]),
            handler=h.trace_extract,
            annotations=READ_ONLY,
        ),
    ]


def http_cassette_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_http_replay",
            description=("Replay a recorded HTTP response from a 'cassette' "
                         "(interactions list or {interactions}) for a 'url' / "
                         "'method' — no network. Returns {response}."),
            input_schema=schema(
                {"cassette": {"type": "object"}, "url": {"type": "string"},
                 "method": {"type": "string"}},
                ["cassette", "url"]),
            handler=h.http_replay,
            annotations=READ_ONLY,
        ),
    ]


def bulkhead_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_bulkhead_run",
            description=("Run an 'actions' list under a named bulkhead permit "
                         "(max 'max_concurrent' in-flight; rejects when full). "
                         "Returns {entered, in_flight, record?}."),
            input_schema=schema(
                {"name": {"type": "string"},
                 "max_concurrent": {"type": "integer"},
                 "actions": {"type": "array"}},
                ["name", "max_concurrent", "actions"]),
            handler=h.bulkhead_run,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_retry_after",
            description=("Server-advised wait (seconds) from an HTTP 'response' "
                         "{status, headers} via Retry-After / RateLimit-*. "
                         "Returns {delay}."),
            input_schema=schema({"response": {"type": "object"}}, ["response"]),
            handler=h.retry_after,
            annotations=READ_ONLY,
        ),
    ]


def percentiles_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_percentiles",
            description=("Exact percentiles of a numeric 'samples' list at the "
                         "requested 'qs' quantiles (default 50/90/95/99). "
                         "Returns {percentiles}."),
            input_schema=schema(
                {"samples": {"type": "array"}, "qs": {"type": "array"}},
                ["samples"]),
            handler=h.percentiles,
            annotations=READ_ONLY,
        ),
    ]


def slo_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_evaluate_slo",
            description=("Compute the SLI and error budget for outcome "
                         "'records' [{timestamp, ok}] against 'target' "
                         "(0-1). Returns {sli, budget_remaining, burn_rate, ...}."),
            input_schema=schema(
                {"records": {"type": "array"}, "target": {"type": "number"},
                 "window_s": {"type": "number"}},
                ["records", "target"]),
            handler=h.evaluate_slo,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_burn_alerts",
            description=("Multi-window burn-rate alerts (Google SRE tiers) for "
                         "outcome 'records' against 'target'. Returns "
                         "{alerts, firing}."),
            input_schema=schema(
                {"records": {"type": "array"}, "target": {"type": "number"}},
                ["records", "target"]),
            handler=h.burn_alerts,
            annotations=READ_ONLY,
        ),
    ]


def chaos_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_run_chaos",
            description=("Run a chaos experiment 'spec' {title, probes:[{name, "
                         "action}], method:[{name, action}], rollbacks:[[...]]}"
                         " — verify steady state, inject faults, re-verify, roll "
                         "back. Returns the journal {status, deviated, ...}."),
            input_schema=schema({"spec": {"type": "object"}}, ["spec"]),
            handler=h.run_chaos,
            annotations=READ_ONLY,
        ),
    ]


def json_contract_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_match_json",
            description=("Match 'actual' JSON against 'expected' with optional "
                         "'partial' (ignore extra keys) and 'match_type' "
                         "(type-only). Returns {ok, mismatches}."),
            input_schema=schema(
                {"actual": {"type": "object"}, "expected": {"type": "object"},
                 "partial": {"type": "boolean"},
                 "match_type": {"type": "boolean"}},
                ["actual", "expected"]),
            handler=h.match_json,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_diff_json",
            description=("Path-tagged diff between 'actual' and 'expected' JSON "
                         "(missing/extra/changed). Returns {diffs}."),
            input_schema=schema(
                {"actual": {"type": "object"}, "expected": {"type": "object"}},
                ["actual", "expected"]),
            handler=h.diff_json,
            annotations=READ_ONLY,
        ),
    ]


def provenance_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_build_provenance",
            description=("Build a SLSA in-toto v1 provenance statement over a "
                         "list of file 'paths' (sha256 subjects). Returns "
                         "{statement}."),
            input_schema=schema(
                {"paths": {"type": "array"}, "builder_id": {"type": "string"}},
                ["paths"]),
            handler=h.build_provenance,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_verify_provenance",
            description=("Re-hash 'files' (name->path) against a provenance "
                         "'statement'. Returns {ok, mismatches}."),
            input_schema=schema(
                {"statement": {"type": "object"}, "files": {"type": "object"}},
                ["statement", "files"]),
            handler=h.verify_provenance,
            annotations=READ_ONLY,
        ),
    ]


def feature_flag_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_evaluate_flag",
            description=("Evaluate a feature 'flags' store for 'key' under an "
                         "evaluation 'context'. Returns {value, variant, "
                         "reason}."),
            input_schema=schema(
                {"flags": {"type": "object"}, "key": {"type": "string"},
                 "context": {"type": "object"}},
                ["flags", "key"]),
            handler=h.evaluate_flag,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_flag_enabled",
            description=("Boolean feature-flag check for 'key' in 'flags' under "
                         "'context'. Returns {enabled}."),
            input_schema=schema(
                {"flags": {"type": "object"}, "key": {"type": "string"},
                 "context": {"type": "object"}, "default": {"type": "boolean"}},
                ["flags", "key"]),
            handler=h.flag_enabled,
            annotations=READ_ONLY,
        ),
    ]


def text_diff_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_unified_diff",
            description="Unified diff transforming text 'a' into 'b'. "
                        "Returns {diff}.",
            input_schema=schema(
                {"a": {"type": "string"}, "b": {"type": "string"}}, ["a", "b"]),
            handler=h.unified_diff,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_apply_unified",
            description="Apply a unified 'diff' to 'text' (raises on context "
                        "mismatch). Returns {result}.",
            input_schema=schema(
                {"text": {"type": "string"}, "diff": {"type": "string"}},
                ["text", "diff"]),
            handler=h.apply_unified,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_three_way_merge",
            description="Three-way merge 'ours' and 'theirs' against 'base' "
                        "(line-based). Returns {text, clean, conflicts}.",
            input_schema=schema(
                {"base": {"type": "string"}, "ours": {"type": "string"},
                 "theirs": {"type": "string"}}, ["base", "ours", "theirs"]),
            handler=h.three_way_merge,
            annotations=READ_ONLY,
        ),
    ]


def recurrence_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_rrule_occurrences",
            description=("Expand an RFC 5545 'rule' (RRULE) from an ISO "
                         "'dtstart' into the next 'count' ISO datetimes. "
                         "Returns {occurrences}."),
            input_schema=schema(
                {"rule": {"type": "string"}, "dtstart": {"type": "string"},
                 "count": {"type": "integer"}},
                ["rule", "dtstart"]),
            handler=h.rrule_occurrences,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_rrule_next",
            description=("Next occurrence of an RRULE 'rule' at/after 'now' "
                         "(ISO; defaults to current time), anchored at ISO "
                         "'dtstart'. Returns {next}."),
            input_schema=schema(
                {"rule": {"type": "string"}, "dtstart": {"type": "string"},
                 "now": {"type": "string"}},
                ["rule", "dtstart"]),
            handler=h.rrule_next,
            annotations=READ_ONLY,
        ),
    ]


def stats_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_describe_stats",
            description=("Summary statistics + percentiles (n/min/max/mean/"
                         "stdev/variance/p50/p90/p95/p99) of a numeric "
                         "'values' list."),
            input_schema=schema({"values": {"type": "array"}}, ["values"]),
            handler=h.describe_stats,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_ab_significance",
            description=("Two-proportion z-test on A/B conversion counts. "
                         "Returns {z, p_value, significant, diff, ci_low, "
                         "ci_high}."),
            input_schema=schema(
                {"a_conv": {"type": "integer"}, "a_n": {"type": "integer"},
                 "b_conv": {"type": "integer"}, "b_n": {"type": "integer"}},
                ["a_conv", "a_n", "b_conv", "b_n"]),
            handler=h.ab_significance,
            annotations=READ_ONLY,
        ),
    ]


def search_index_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_search_documents",
            description=("Rank a 'docs' corpus ({doc_id: text}) for a text "
                         "'query' using BM25 (or mode='tfidf'). Returns "
                         "{hits:[{doc_id, score}]} top 'top_k'."),
            input_schema=schema(
                {"docs": {"type": "object"}, "query": {"type": "string"},
                 "top_k": {"type": "integer"}, "mode": {"type": "string"}},
                ["docs", "query"]),
            handler=h.search_documents,
            annotations=READ_ONLY,
        ),
    ]


def json_patch_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_resolve_pointer",
            description=("Resolve an RFC 6901 JSON Pointer ('pointer' like "
                         "'/a/b/0') in 'doc'. Returns {value}."),
            input_schema=schema(
                {"doc": {"type": "object"}, "pointer": {"type": "string"}},
                ["doc", "pointer"]),
            handler=h.resolve_pointer,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_apply_json_patch",
            description=("Apply an RFC 6902 JSON Patch 'patch' (add/remove/"
                         "replace/move/copy/test) to 'doc'. Returns {result}."),
            input_schema=schema(
                {"doc": {"type": "object"}, "patch": {"type": "array"}},
                ["doc", "patch"]),
            handler=h.apply_json_patch,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_make_json_patch",
            description=("Compute an RFC 6902 JSON Patch turning 'old' into "
                         "'new'. Returns {patch}."),
            input_schema=schema(
                {"old": {"type": "object"}, "new": {"type": "object"}},
                ["old", "new"]),
            handler=h.make_json_patch,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_merge_patch",
            description=("Apply an RFC 7386 JSON Merge Patch 'patch' to 'doc' "
                         "(null deletes a key). Returns {result}."),
            input_schema=schema(
                {"doc": {"type": "object"}, "patch": {"type": "object"}},
                ["doc", "patch"]),
            handler=h.merge_patch,
            annotations=READ_ONLY,
        ),
    ]


def saga_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_run_saga",
            description=("Run a saga: a list of steps {name, action:[AC...], "
                         "compensation:[AC...]}. On any step failure, the "
                         "compensations of completed steps run in LIFO order. "
                         "Returns {ok, completed, compensated, failed_step, "
                         "error}."),
            input_schema=schema(
                {"steps": {"type": "array", "items": {"type": "object"}}},
                ["steps"]),
            handler=h.run_saga,
            annotations=SIDE_EFFECT_ONLY,
        ),
    ]


def decision_table_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_decision_table",
            description=("Evaluate a DMN-style decision table 'spec' "
                         "({inputs, hit_policy: UNIQUE/FIRST/PRIORITY/COLLECT, "
                         "rules:[{conditions, outputs}]}) against a 'context'. "
                         "Conditions are wildcard/literal/{op,value}. Returns "
                         "{result} (outputs dict, or list for COLLECT)."),
            input_schema=schema(
                {"spec": {"type": "object"}, "context": {"type": "object"}},
                ["spec", "context"]),
            handler=h.decision_table,
            annotations=READ_ONLY,
        ),
    ]


def locator_repair_tools() -> List[MCPTool]:
    _DB = {"db": {"type": "string"}}
    return [
        MCPTool(
            name="ac_repair_record",
            description=("Record a corrected locator from a successful heal "
                         "(method + coordinates/description). Auto-applies when "
                         "'confidence' >= 'auto_threshold' (default 0.9), else "
                         "queues a pending suggestion. Returns {id, status}."),
            input_schema=schema(
                {"key": {"type": "string"}, "method": {"type": "string"},
                 "coordinates": {"type": "array", "items": {"type": "integer"}},
                 "description": {"type": "string"},
                 "confidence": {"type": "number"},
                 "auto_threshold": {"type": "number"}, **_DB},
                ["key", "method"]),
            handler=h.repair_record,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_repair_resolved",
            description=("Return the latest applied/approved corrected locator "
                         "for 'key' (or null) — the learned fix for reuse."),
            input_schema=schema({"key": {"type": "string"}, **_DB}, ["key"]),
            handler=h.repair_resolved,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_repair_pending",
            description="List locator-repair suggestions awaiting review. "
                        "Returns {pending}.",
            input_schema=schema(dict(_DB)),
            handler=h.repair_pending,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_repair_approve",
            description="Approve a pending locator-repair suggestion by id. "
                        "Returns {approved}.",
            input_schema=schema({"suggestion_id": {"type": "string"}, **_DB},
                                ["suggestion_id"]),
            handler=h.repair_approve,
            annotations=SIDE_EFFECT_ONLY,
        ),
    ]


def pii_text_tools() -> List[MCPTool]:
    _KINDS = {"type": "array", "items": {"type": "string"}}
    return [
        MCPTool(
            name="ac_detect_pii",
            description=("Detect PII spans (email/phone/ssn/credit_card/ipv4/"
                         "iban) in free text. Optional 'kinds' filter. Returns "
                         "{findings:[{kind, value, start, end}]}."),
            input_schema=schema(
                {"text": {"type": "string"}, "kinds": _KINDS}, ["text"]),
            handler=h.detect_pii,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_redact_pii",
            description=("Redact PII in text. 'mode' is label ([email]) / mask "
                         "(****) / partial (keep last 4) / hash. Returns "
                         "{text}."),
            input_schema=schema(
                {"text": {"type": "string"}, "kinds": _KINDS,
                 "mode": {"type": "string",
                          "enum": ["label", "mask", "partial", "hash"]},
                 "mask_char": {"type": "string"}}, ["text"]),
            handler=h.redact_pii,
            annotations=READ_ONLY,
        ),
    ]


def sarif_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_export_sarif",
            description=("Build a SARIF 2.1.0 document from normalized "
                         "'findings' ([{rule_id, level, message, file?, "
                         "line?}]) for GitHub/Azure code-scanning. Optional "
                         "'path' writes it; 'tool_name' labels the driver. "
                         "Returns {sarif, path?}."),
            input_schema=schema(
                {"findings": {"type": "array", "items": {"type": "object"}},
                 "path": {"type": "string"},
                 "tool_name": {"type": "string"}}, ["findings"]),
            handler=h.export_sarif,
            annotations=READ_ONLY,
        ),
    ]


def unattended_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_generate_otp",
            description=("Generate the current TOTP code from a base32 secret "
                         "for automated 2FA logins. step/digits default to "
                         "30/6. Returns the numeric code string."),
            input_schema=schema({
                "secret": {"type": "string"},
                "step": {"type": "integer"},
                "digits": {"type": "integer"},
            }, required=["secret"]),
            handler=h.generate_otp,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_handle_file_dialog",
            description=("Wait for a native file dialog (action=open|save|"
                         "folder, or a custom window_title), type 'path' into "
                         "it, and confirm (default Enter). Returns "
                         "{handled, title}."),
            input_schema=schema({
                "path": {"type": "string"},
                "action": {"type": "string"},
                "window_title": {"type": "string"},
                "timeout_s": {"type": "number"},
                "confirm_key": {"type": "string"},
            }, required=["path"]),
            handler=h.handle_file_dialog,
            annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_assert_session_active",
            description=("Raise when the interactive session is locked / "
                         "disconnected (so an unattended run fails clearly "
                         "instead of emitting phantom input). Returns "
                         "{interactive: true} when OK."),
            input_schema=schema({}),
            handler=h.assert_session_active,
            annotations=READ_ONLY,
        ),
    ]


def watchdog_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_watchdog_add",
            description=("Register a background popup-dismissal rule: when a "
                         "window whose title contains 'title' appears, the "
                         "watchdog closes it (action='close') or presses a key "
                         "(action='enter'/'esc'). Guards unattended runs "
                         "against unexpected dialogs (UAC, update prompts)."),
            input_schema=schema({
                "title": {"type": "string"},
                "action": {"type": "string"},
                "case_sensitive": {"type": "boolean"},
                "name": {"type": "string"},
            }, required=["title"]),
            handler=h.watchdog_add,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_watchdog_start",
            description=("Start the background popup watchdog (concurrent guard "
                         "thread that dismisses registered popups)."),
            input_schema=schema({}),
            handler=h.watchdog_start,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_watchdog_stop",
            description="Stop the background popup watchdog.",
            input_schema=schema({}),
            handler=h.watchdog_stop,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_watchdog_list",
            description=("Report the watchdog's run state, registered rules, "
                         "and the popups it has dismissed."),
            input_schema=schema({}),
            handler=h.watchdog_list,
            annotations=READ_ONLY,
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


def remote_desktop_tools() -> List[MCPTool]:
    """MCP wrappers for the remote-desktop registry singletons."""
    return [
        MCPTool(
            name="ac_remote_host_start",
            description=(
                "Start (or restart) the singleton TCP remote-desktop "
                "host this process owns. Returns "
                "{running, port, host_id, connected_clients}."
            ),
            input_schema=schema({
                "token": {"type": "string",
                          "description": "Bearer token clients must present"},
                "bind": {"type": "string",
                         "description": "Bind address (default 127.0.0.1)"},
                "port": {"type": "integer",
                         "description": "Listen port; 0 → kernel-assigned"},
                "fps": {"type": "number",
                        "description": "Target frames per second"},
                "quality": {"type": "integer",
                            "description": "JPEG quality (1–95)"},
                "max_clients": {"type": "integer"},
                "host_id": {"type": "string",
                            "description": "Optional 9-digit ID; auto-generated when omitted"},
            }, required=["token"]),
            handler=h.remote_host_start,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_remote_host_stop",
            description="Stop the singleton TCP remote-desktop host.",
            input_schema=schema({"timeout": {"type": "number"}}),
            handler=h.remote_host_stop,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_remote_host_status",
            description=(
                "Read-only snapshot of the host: "
                "{running, port, host_id, connected_clients}."
            ),
            input_schema=schema({}),
            handler=h.remote_host_status,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_remote_viewer_connect",
            description=(
                "Connect the singleton viewer to a remote host and wait "
                "for the auth handshake. Returns "
                "{connected, host_id}."
            ),
            input_schema=schema({
                "host": {"type": "string"},
                "port": {"type": "integer"},
                "token": {"type": "string"},
                "timeout": {"type": "number"},
                "expected_host_id": {
                    "type": "string",
                    "description": "If set, the handshake fails when the "
                                   "host advertises a different ID.",
                },
            }, required=["host", "port", "token"]),
            handler=h.remote_viewer_connect,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_remote_viewer_disconnect",
            description="Disconnect the singleton viewer.",
            input_schema=schema({"timeout": {"type": "number"}}),
            handler=h.remote_viewer_disconnect,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_remote_viewer_status",
            description="Read-only viewer state: {connected, host_id}.",
            input_schema=schema({}),
            handler=h.remote_viewer_status,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_remote_viewer_send_input",
            description=(
                "Forward an input action (mouse_move / mouse_press / "
                "mouse_release / mouse_scroll / key_press / key_release / "
                "type / hotkey) through the connected viewer to the "
                "remote host."
            ),
            input_schema=schema({
                "action": {
                    "type": "object",
                    "description": "Input payload, e.g. "
                                   "{action: 'mouse_move', x: 100, y: 200}",
                },
            }, required=["action"]),
            handler=h.remote_viewer_send_input,
            annotations=DESTRUCTIVE,
        ),
    ]


def gamepad_tools() -> List[MCPTool]:
    """MCP wrappers for the ViGEm virtual-gamepad facade."""
    return [
        MCPTool(
            name="ac_gamepad_press",
            description=(
                "Press a virtual Xbox 360 button (a / b / x / y / lb / "
                "rb / back / start / guide / ls / rs)."
            ),
            input_schema=schema({"button": {"type": "string"}},
                                required=["button"]),
            handler=h.gamepad_press,
            annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_gamepad_release",
            description="Release a virtual Xbox 360 button.",
            input_schema=schema({"button": {"type": "string"}},
                                required=["button"]),
            handler=h.gamepad_release,
            annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_gamepad_click",
            description="Press then release a virtual Xbox 360 button.",
            input_schema=schema({"button": {"type": "string"}},
                                required=["button"]),
            handler=h.gamepad_click,
            annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_gamepad_dpad",
            description=(
                "Hold a dpad direction (up / down / left / right / "
                "up_left / up_right / down_left / down_right / none)."
            ),
            input_schema=schema({"direction": {"type": "string"}},
                                required=["direction"]),
            handler=h.gamepad_dpad,
            annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_gamepad_left_stick",
            description=(
                "Move the left analogue stick. ``x`` and ``y`` are "
                "signed-int16 (-32768..32767)."
            ),
            input_schema=schema({
                "x": {"type": "integer"},
                "y": {"type": "integer"},
            }, required=["x", "y"]),
            handler=h.gamepad_left_stick,
            annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_gamepad_right_stick",
            description="Move the right analogue stick (signed-int16).",
            input_schema=schema({
                "x": {"type": "integer"},
                "y": {"type": "integer"},
            }, required=["x", "y"]),
            handler=h.gamepad_right_stick,
            annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_gamepad_left_trigger",
            description="Set left-trigger pressure (0..255).",
            input_schema=schema({"value": {"type": "integer"}},
                                required=["value"]),
            handler=h.gamepad_left_trigger,
            annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_gamepad_right_trigger",
            description="Set right-trigger pressure (0..255).",
            input_schema=schema({"value": {"type": "integer"}},
                                required=["value"]),
            handler=h.gamepad_right_trigger,
            annotations=DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_gamepad_reset",
            description=(
                "Clear every pressed button / stick offset / trigger "
                "pressure on the virtual gamepad."
            ),
            input_schema=schema({}),
            handler=h.gamepad_reset,
            annotations=DESTRUCTIVE,
        ),
    ]


_VID_PID = {
    "vendor_id": {"type": "string"},
    "product_id": {"type": "string"},
    "serial": {"type": "string"},
}


def usb_passthrough_tools() -> List[MCPTool]:
    """First-class MCP tools for USB passthrough (default-off feature)."""
    return [
        MCPTool(
            name="ac_usb_passthrough_enable",
            description=("Toggle the USB passthrough feature flag. Default "
                         "off; must be enabled before any usb channel is "
                         "honoured."),
            input_schema=schema({"enabled": {"type": "boolean"}}),
            handler=h.usb_passthrough_enable,
            annotations=NON_DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_usb_passthrough_status",
            description="Report whether USB passthrough is enabled.",
            input_schema=schema({}),
            handler=h.usb_passthrough_status,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_usb_acl_list",
            description=("List USB ACL rules plus the default policy and the "
                         "HMAC integrity state."),
            input_schema=schema({}),
            handler=h.usb_acl_list,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_usb_acl_add",
            description=("Add a per-device USB ACL rule (allow/deny, optional "
                         "prompt-on-open). vendor_id/product_id are 4 hex "
                         "digits, e.g. 1050/0407."),
            input_schema=schema({
                **_VID_PID,
                "allow": {"type": "boolean"},
                "prompt_on_open": {"type": "boolean"},
                "label": {"type": "string"},
            }, required=["vendor_id", "product_id"]),
            handler=h.usb_acl_add,
            annotations=NON_DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_usb_acl_remove",
            description="Remove a per-device USB ACL rule.",
            input_schema=schema(
                dict(_VID_PID), required=["vendor_id", "product_id"],
            ),
            handler=h.usb_acl_remove,
            annotations=NON_DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_usb_acl_set_default",
            description="Set the USB ACL default policy (allow | deny).",
            input_schema=schema({
                "policy": {"type": "string", "enum": ["allow", "deny"]},
            }, required=["policy"]),
            handler=h.usb_acl_set_default,
            annotations=NON_DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_usb_loopback_list",
            description=("List ACL-visible USB devices on this machine over "
                         "the in-process loopback channel."),
            input_schema=schema({}),
            handler=h.usb_loopback_list,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_usb_loopback_open",
            description=("Claim a local USB device over loopback and read its "
                         "device descriptor (a full protocol-stack probe). "
                         "Fails closed if the ACL denies it."),
            input_schema=schema(
                dict(_VID_PID), required=["vendor_id", "product_id"],
            ),
            handler=h.usb_loopback_open,
            annotations=NON_DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_usb_remote_list",
            description=("List the remote host's USB devices over the live "
                         "WebRTC usb channel. Requires a connected WebRTC "
                         "viewer."),
            input_schema=schema({}),
            handler=h.usb_remote_list,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_usb_remote_open",
            description=("Claim a remote USB device over the live WebRTC usb "
                         "channel and read its descriptor."),
            input_schema=schema(
                dict(_VID_PID), required=["vendor_id", "product_id"],
            ),
            handler=h.usb_remote_open,
            annotations=NON_DESTRUCTIVE,
        ),
    ]


def assertion_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_assert_text",
            description=("Assert OCR text is (present=true) or is not "
                         "(present=false) on screen. Set regex=true to treat "
                         "'text' as a regular expression. Raises on mismatch "
                         "when raise_on_fail is true (default)."),
            input_schema=schema({
                "text": {"type": "string"},
                "region": {"type": "array", "items": {"type": "integer"}},
                "lang": {"type": "string"},
                "regex": {"type": "boolean"},
                "present": {"type": "boolean"},
                "ignore_case": {"type": "boolean"},
                "min_confidence": {"type": "number"},
                "raise_on_fail": {"type": "boolean"},
                "capture_on_fail": {"type": "boolean"},
            }, required=["text"]),
            handler=h.assert_text,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_assert_image",
            description=("Assert a template image is (or is not) visible on "
                         "screen at the given match threshold."),
            input_schema=schema({
                "template_path": {"type": "string"},
                "threshold": {"type": "number"},
                "present": {"type": "boolean"},
                "raise_on_fail": {"type": "boolean"},
                "capture_on_fail": {"type": "boolean"},
            }, required=["template_path"]),
            handler=h.assert_image,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_assert_pixel",
            description=("Assert the pixel at (x, y) matches (match=true) or "
                         "differs from (match=false) rgb within tolerance."),
            input_schema=schema({
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "rgb": {"type": "array", "items": {"type": "integer"}},
                "tolerance": {"type": "integer"},
                "match": {"type": "boolean"},
                "raise_on_fail": {"type": "boolean"},
                "capture_on_fail": {"type": "boolean"},
            }, required=["x", "y", "rgb"]),
            handler=h.assert_pixel,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_assert_window",
            description=("Assert a window whose title contains 'title' does "
                         "(exists=true) or does not (exists=false) exist."),
            input_schema=schema({
                "title": {"type": "string"},
                "exists": {"type": "boolean"},
                "ignore_case": {"type": "boolean"},
                "raise_on_fail": {"type": "boolean"},
                "capture_on_fail": {"type": "boolean"},
            }, required=["title"]),
            handler=h.assert_window,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_assert_clipboard",
            description=("Assert the system clipboard text matches 'text'. "
                         "mode is 'equals' (default), 'contains', or 'regex'. "
                         "Set present=false to assert the clipboard does NOT "
                         "match (e.g. a secret was cleared)."),
            input_schema=schema({
                "text": {"type": "string"},
                "mode": {"type": "string",
                         "enum": ["equals", "contains", "regex"]},
                "ignore_case": {"type": "boolean"},
                "present": {"type": "boolean"},
                "raise_on_fail": {"type": "boolean"},
                "capture_on_fail": {"type": "boolean"},
            }, required=["text"]),
            handler=h.assert_clipboard,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_assert_process",
            description=("Assert a process whose name contains 'name' is "
                         "(running=true) or is not (running=false) running. "
                         "Requires psutil."),
            input_schema=schema({
                "name": {"type": "string"},
                "running": {"type": "boolean"},
                "raise_on_fail": {"type": "boolean"},
                "capture_on_fail": {"type": "boolean"},
            }, required=["name"]),
            handler=h.assert_process,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_assert_file",
            description=("Assert a file's state: existence (exists), a "
                         "substring (contains), a SHA-256 digest (sha256), "
                         "or a minimum byte size (min_size). Set exists=false "
                         "to assert the file is absent."),
            input_schema=schema({
                "path": {"type": "string"},
                "exists": {"type": "boolean"},
                "contains": {"type": "string"},
                "sha256": {"type": "string"},
                "min_size": {"type": "integer"},
                "raise_on_fail": {"type": "boolean"},
            }, required=["path"]),
            handler=h.assert_file,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_assert_http",
            description=("Assert an http/https endpoint returns 'status' "
                         "(default 200) and optionally that the body contains "
                         "'contains'. Always uses an explicit timeout; an "
                         "unreachable host counts as a failed assertion."),
            input_schema=schema({
                "url": {"type": "string"},
                "status": {"type": "integer"},
                "contains": {"type": "string"},
                "timeout": {"type": "number"},
                "method": {"type": "string"},
                "raise_on_fail": {"type": "boolean"},
            }, required=["url"]),
            handler=h.assert_http,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_assert_all",
            description=("Run a batch of assertion specs as soft assertions: "
                         "every spec is evaluated (no short-circuit) and all "
                         "failures are collected before raising. Each spec is "
                         "an object like {\"kind\": \"text\", \"text\": "
                         "\"Saved\"}; kind is one of text/image/pixel/window/"
                         "clipboard."),
            input_schema=schema({
                "specs": {"type": "array", "items": {"type": "object"}},
                "raise_on_fail": {"type": "boolean"},
            }, required=["specs"]),
            handler=h.assert_all,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_assert_any",
            description=("Pass when AT LEAST ONE assertion spec passes (OR "
                         "semantics; short-circuits on the first pass) — the "
                         "complement of ac_assert_all. Each spec is an object "
                         "like {\"kind\": \"text\", \"text\": \"Welcome\"}."),
            input_schema=schema({
                "specs": {"type": "array", "items": {"type": "object"}},
                "raise_on_fail": {"type": "boolean"},
            }, required=["specs"]),
            handler=h.assert_any,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_assert_eventually",
            description=("Retry a single assertion spec until it passes or "
                         "'timeout' seconds elapse, polling every 'interval' "
                         "seconds. The spec is an object like {\"kind\": "
                         "\"window\", \"title\": \"Done\"}."),
            input_schema=schema({
                "spec": {"type": "object"},
                "timeout": {"type": "number"},
                "interval": {"type": "number"},
                "raise_on_fail": {"type": "boolean"},
            }, required=["spec"]),
            handler=h.assert_eventually,
            annotations=READ_ONLY,
        ),
    ]


def data_source_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_load_data",
            description=("Load tabular rows from a data source spec and return "
                         "them as a list of row objects. 'source' is a dict "
                         "with kind=csv|json|sqlite|excel|inline plus "
                         "kind-specific fields (path / query / rows). Combine "
                         "with the AC_for_each_row flow-control command to "
                         "drive a script once per row."),
            input_schema=schema({
                "source": {"type": "object"},
                "limit": {"type": "integer"},
            }, required=["source"]),
            handler=h.load_data,
            annotations=READ_ONLY,
        ),
    ]


def pdf_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_extract_pdf_text",
            description=("Extract text from a PDF file. 'pages' is null (all "
                         "pages), a 1-based page number, or a list of them. "
                         "Requires the optional pypdf package."),
            input_schema=schema({
                "path": {"type": "string"},
                "pages": {"type": ["integer", "array", "null"]},
            }, required=["path"]),
            handler=h.extract_pdf_text,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_assert_pdf_text",
            description=("Assert that text is present (or absent when "
                         "present=false) in a PDF, optionally restricted to a "
                         "1-based 'page'. Set case_sensitive=false for a "
                         "case-insensitive match. Raises on failure unless "
                         "raise_on_fail is false."),
            input_schema=schema({
                "path": {"type": "string"},
                "text": {"type": "string"},
                "present": {"type": "boolean"},
                "page": {"type": "integer"},
                "case_sensitive": {"type": "boolean"},
                "raise_on_fail": {"type": "boolean"},
            }, required=["path", "text"]),
            handler=h.assert_pdf_text,
            annotations=READ_ONLY,
        ),
    ]


def email_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_send_email",
            description=("Send an email via SMTP. 'message' = {sender, to, "
                         "subject, body, cc?, html?, attachments?} (to/cc may "
                         "be a string or list; attachments are file paths). "
                         "'smtp' = {host, port?, username?, password?, "
                         "use_tls?, use_ssl?, timeout?}; TLS is on by default. "
                         "Sends mail (irreversible side effect)."),
            input_schema=schema({
                "message": {"type": "object"},
                "smtp": {"type": "object"},
            }, required=["message", "smtp"]),
            handler=h.send_email,
            annotations=SIDE_EFFECT_ONLY,
        ),
    ]


def sql_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_sql_query",
            description=("Run a read-only SELECT/WITH query against a SQLite "
                         "database file and return the result. fetch=all (list "
                         "of row objects), one (a single row or null), or "
                         "scalar (first column of first row). Bind values via "
                         "'params' (?/:name placeholders) — never interpolate. "
                         "A single read-only statement only."),
            input_schema=schema({
                "database": {"type": "string"},
                "query": {"type": "string"},
                "params": {"type": ["array", "object"]},
                "fetch": {"type": "string", "enum": ["all", "one", "scalar"]},
            }, required=["database", "query"]),
            handler=h.sql_query,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_assert_db",
            description=("Run a scalar SELECT and assert its value against "
                         "'expected' with op=eq|ne|lt|le|gt|ge|contains|"
                         "startswith|endswith (e.g. SELECT COUNT(*) ... == 0). "
                         "Bind values via 'params'. Raises on failure unless "
                         "raise_on_fail is false."),
            input_schema=schema({
                "database": {"type": "string"},
                "query": {"type": "string"},
                "params": {"type": ["array", "object"]},
                "op": {"type": "string"},
                "expected": {},
                "raise_on_fail": {"type": "boolean"},
            }, required=["database", "query"]),
            handler=h.assert_db,
            annotations=READ_ONLY,
        ),
    ]


def http_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_http_request",
            description=("Perform an HTTP(S) request and return a response dict "
                         "(status, ok, headers, text, json, url). method=GET|"
                         "POST|PUT|PATCH|DELETE|HEAD; send a JSON body via "
                         "'json_body' or a raw body via 'data'; 'auth' is "
                         "{type:bearer, token} or {type:basic, username, "
                         "password}. Non-2xx responses are returned, not raised, "
                         "so you can assert on status. http/https only."),
            input_schema=schema({
                "url": {"type": "string"},
                "method": {"type": "string",
                           "enum": ["GET", "POST", "PUT", "PATCH",
                                    "DELETE", "HEAD"]},
                "headers": {"type": "object"},
                "json_body": {"type": "object"},
                "data": {"type": "string"},
                "auth": {"type": "object"},
                "timeout": {"type": "number"},
            }, required=["url"]),
            handler=h.http_request,
            annotations=SIDE_EFFECT_ONLY,
        ),
    ]


def visual_regression_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_take_golden",
            description=("Capture and save a golden/baseline image of the "
                         "screen (or a [x, y, w, h] region) for later visual "
                         "regression checks."),
            input_schema=schema({
                "path": {"type": "string"},
                "region": {"type": "array", "items": {"type": "integer"}},
            }, required=["path"]),
            handler=h.take_golden,
            annotations=SIDE_EFFECT_ONLY,
        ),
        MCPTool(
            name="ac_assert_visual",
            description=("Compare the screen (or a region) against a golden "
                         "image; fail when more than 'tolerance' percent of "
                         "pixels differ beyond per_pixel_threshold. On the "
                         "first run (golden missing) it captures the baseline "
                         "and passes unless create_if_missing=false. Pass "
                         "diff_path to save a highlighted diff on mismatch."),
            input_schema=schema({
                "golden_path": {"type": "string"},
                "region": {"type": "array", "items": {"type": "integer"}},
                "tolerance": {"type": "number"},
                "per_pixel_threshold": {"type": "integer"},
                "diff_path": {"type": "string"},
                "create_if_missing": {"type": "boolean"},
                "raise_on_fail": {"type": "boolean"},
            }, required=["golden_path"]),
            handler=h.assert_visual,
            annotations=READ_ONLY,
        ),
    ]


def state_machine_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_run_state_machine",
            description=("Run a declarative finite-state-machine 'spec' "
                         "{initial, states:{name:{on_enter:[...], "
                         "transitions:[{go_to, after?/if_var_eq?}], final?}}}. "
                         "on_enter actions run through the executor; returns "
                         "{final_state, steps, elapsed_s}."),
            input_schema=schema({"spec": {"type": "object"}},
                                required=["spec"]),
            handler=h.run_state_machine,
            annotations=SIDE_EFFECT_ONLY,
        ),
    ]


def codegen_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_generate_code",
            description=("Generate runnable test code from an action list or a "
                         "JSON action-file path. target=pytest|python|robot; "
                         "style=calls (readable ac.<fn>(...) statements, the "
                         "default) or actions (embed the list and replay via "
                         "execute_action). Pass 'output' to also write the file. "
                         "Returns the generated source code."),
            input_schema=schema({
                "source": {"type": ["array", "string"],
                           "description": "Action list, or path to a JSON action file."},
                "target": {"type": "string",
                           "enum": ["pytest", "python", "robot"]},
                "style": {"type": "string", "enum": ["calls", "actions"]},
                "name": {"type": "string"},
                "output": {"type": "string"},
            }, required=["source"]),
            handler=h.generate_code,
            annotations=SIDE_EFFECT_ONLY,
        ),
    ]


def flakiness_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_flaky_report",
            description=("Score run-history flakiness: group recent runs by "
                         "script_path (or source_id), count pass/fail flips, "
                         "and rank scripts that intermittently fail. "
                         "Read-only analytics over the run-history store."),
            input_schema=schema({
                "limit": {"type": "integer"},
                "min_runs": {"type": "integer"},
                "group_by": {"type": "string",
                             "enum": ["script_path", "source_id"]},
            }),
            handler=h.flaky_report,
            annotations=READ_ONLY,
        ),
    ]


def suite_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_run_suite",
            description=("Run a QA suite spec (name + optional setup/teardown "
                         "+ cases) and return per-case pass/fail/error/skip "
                         "results. Cases with a 'data' source expand to one "
                         "scored case per row. Pass junit_path / allure_dir to "
                         "also write CI-native reports. Quarantined case names "
                         "are skipped."),
            input_schema=schema({
                "spec": {"type": "object"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "respect_quarantine": {"type": "boolean"},
                "junit_path": {"type": "string"},
                "allure_dir": {"type": "string"},
            }, required=["spec"]),
            handler=h.run_suite,
            annotations=SIDE_EFFECT_ONLY,
        ),
    ]


def quarantine_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_quarantine_add",
            description=("Quarantine a case name so the suite runner skips it "
                         "(records it as skipped, not failed)."),
            input_schema=schema({
                "name": {"type": "string"},
                "reason": {"type": "string"},
            }, required=["name"]),
            handler=h.quarantine_add,
            annotations=NON_DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_quarantine_remove",
            description="Release a case name from quarantine.",
            input_schema=schema({"name": {"type": "string"}},
                                required=["name"]),
            handler=h.quarantine_remove,
            annotations=NON_DESTRUCTIVE,
        ),
        MCPTool(
            name="ac_quarantine_list",
            description="List every quarantined case name with its reason.",
            input_schema=schema({}),
            handler=h.quarantine_list,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_quarantine_auto",
            description=("Auto-quarantine flaky scripts from run history whose "
                         "flip rate meets flip_rate_threshold."),
            input_schema=schema({
                "flip_rate_threshold": {"type": "number"},
                "min_runs": {"type": "integer"},
                "limit": {"type": "integer"},
                "group_by": {"type": "string",
                             "enum": ["script_path", "source_id"]},
            }),
            handler=h.quarantine_auto,
            annotations=NON_DESTRUCTIVE,
        ),
    ]


def a11y_audit_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_audit_accessibility",
            description=("Audit the accessibility tree for interactive widgets "
                         "missing an accessible name; optionally also check "
                         "supplied foreground/background contrast_pairs (WCAG) "
                         "and OCR 'texts' for ellipsis truncation. Returns an "
                         "issue list with severities."),
            input_schema=schema({
                "app_name": {"type": "string"},
                "contrast_pairs": {"type": "array",
                                   "items": {"type": "object"}},
                "texts": {"type": "array", "items": {"type": "string"}},
                "min_ratio": {"type": "number"},
                "max_results": {"type": "integer"},
            }),
            handler=h.audit_accessibility,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_audit_contrast",
            description=("Compute the WCAG contrast ratio between a foreground "
                         "and background RGB colour; reports pass/fail against "
                         "the AA threshold."),
            input_schema=schema({
                "foreground": {"type": "array", "items": {"type": "integer"}},
                "background": {"type": "array", "items": {"type": "integer"}},
                "min_ratio": {"type": "number"},
            }, required=["foreground", "background"]),
            handler=h.audit_contrast,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_wcag_audit",
            description=("WCAG 2.2 conformance audit: tags each defect with its "
                         "success-criterion id/level/impact and adds the 2.2 "
                         "Target Size (2.5.8) rule from element bounds. Filters "
                         "to 'level' (A/AA/AAA). Returns a conformance report "
                         "with by_criterion / by_impact counts and findings."),
            input_schema=schema({
                "app_name": {"type": "string"},
                "contrast_pairs": {"type": "array",
                                   "items": {"type": "object"}},
                "texts": {"type": "array", "items": {"type": "string"}},
                "level": {"type": "string", "enum": ["A", "AA", "AAA"]},
                "min_target_px": {"type": "integer"},
                "max_results": {"type": "integer"},
            }),
            handler=h.wcag_audit,
            annotations=READ_ONLY,
        ),
    ]


def device_matrix_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_run_device_matrix",
            description=("Run one AC_* action list across many mobile devices "
                         "in parallel (each on an isolated executor). Each "
                         "device spec (platform + serial/url) is bound to "
                         "${device.*} so the script targets the current "
                         "device. Returns per-device pass/fail."),
            input_schema=schema({
                "actions": {"type": "array"},
                "devices": {"type": "array", "items": {"type": "object"}},
                "max_parallel": {"type": "integer"},
                "var_name": {"type": "string"},
            }, required=["actions", "devices"]),
            handler=h.run_device_matrix,
            annotations=SIDE_EFFECT_ONLY,
        ),
    ]


def media_assert_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="ac_assert_audio",
            description=("Record from an input device for duration_s and "
                         "assert sound (expect_sound=true) or silence "
                         "(false) by comparing RMS level to threshold."),
            input_schema=schema({
                "duration_s": {"type": "number"},
                "threshold": {"type": "number"},
                "expect_sound": {"type": "boolean"},
                "samplerate": {"type": "integer"},
                "channels": {"type": "integer"},
                "raise_on_fail": {"type": "boolean"},
            }),
            handler=h.assert_audio,
            annotations=READ_ONLY,
        ),
        MCPTool(
            name="ac_assert_video_changes",
            description=("Measure mean frame-to-frame difference over a "
                         "segment of a recorded video and assert motion "
                         "(expect_motion=true) or a static segment."),
            input_schema=schema({
                "video_path": {"type": "string"},
                "start_s": {"type": "number"},
                "end_s": {"type": "number"},
                "threshold": {"type": "number"},
                "expect_motion": {"type": "boolean"},
                "region": {"type": "array", "items": {"type": "integer"}},
                "raise_on_fail": {"type": "boolean"},
            }, required=["video_path"]),
            handler=h.assert_video_changes,
            annotations=READ_ONLY,
        ),
    ]


ALL_FACTORIES = (
    mouse_tools, keyboard_tools, screen_tools, image_and_ocr_tools,
    window_tools, system_tools, recording_tools, drag_and_send_tools,
    semantic_locator_tools, self_healing_tools, anchor_locator_tools,
    ab_locator_tools, a11y_tree_tools, a11y_control_tools,
    ocr_structure_tools,
    smart_wait_tools, cost_telemetry_tools, failure_hook_tools,
    computer_use_tools, dag_tools, presence_tools, chatops_tools,
    redaction_tools, android_widget_tools, ios_tools, webrunner_tools,
    scheduler_tools, trigger_tools, hotkey_tools, watchdog_tools,
    unattended_tools, work_queue_tools,
    synthetic_data_tools, mcp_registry_tools, test_selection_tools,
    element_repository_tools, flow_debugger_tools,
    skill_library_tools, guardrail_tools, a2a_tools, office_tools,
    agent_memory_tools, determinism_tools, observer_tools,
    sbom_tools, sharding_tools, data_quality_tools, i18n_tools,
    checkpoint_tools, set_of_marks_tools, screen_state_tools,
    input_macro_tools, resilience_tools,
    ci_annotation_tools, clipboard_history_tools, audit_analysis_tools,
    process_doc_tools, tween_drag_tools, mouse_path_tools, field_entry_tools,
    plugin_sdk_tools, governance_tools,
    credential_lease_tools, egress_tools, approval_testing_tools,
    trajectory_eval_tools, compliance_tools, agent_trace_tools,
    video_report_tools, fuzzy_tools, artifact_store_tools, image_dedup_tools,
    locale_tools, voice_tools, coordinate_space_tools, loop_guard_tools,
    process_mining_tools, asset_tools, events_tools, notify_channel_tools,
    jsonpath_tools, json_schema_tools, vuln_scan_tools, vex_tools,
    license_policy_tools, jwt_tools, rate_limit_tools, json_patch_tools,
    search_index_tools, stats_tools, recurrence_tools, text_diff_tools,
    feature_flag_tools, provenance_tools, json_contract_tools, chaos_tools,
    slo_tools, percentiles_tools, bulkhead_tools, http_cassette_tools,
    trace_context_tools, baggage_tools, canonical_log_tools, otlp_export_tools,
    text_normalize_tools, text_similarity_tools, near_dup_tools,
    secret_ref_tools, config_schema_tools, config_redaction_tools,
    data_profile_tools, http_problem_tools, dotenv_tools,
    sse_client_tools, layered_config_tools, data_drift_tools, schema_compat_tools,
    timeseries_tools, anomaly_tools, smoothing_tools, idempotency_tools,
    dedup_window_tools, sequence_gap_tools, optimistic_tools, outbox_tools,
    locale_collation_tools, confusables_tools, readability_tools,
    bidi_check_tools, list_format_tools, message_format_tools,
    gettext_catalog_tools, checksum_tools,
    dataset_diff_tools, referential_tools, link_header_tools, multipart_tools,
    http_content_tools, cookie_jar_tools, http_conditional_tools,
    saga_tools, decision_table_tools, locator_repair_tools,
    pii_text_tools, sarif_tools,
    screen_record_tools,
    process_and_shell_tools, remote_desktop_tools, gamepad_tools,
    usb_passthrough_tools, assertion_tools, data_source_tools,
    sql_tools, http_tools, email_tools, pdf_tools,
    visual_regression_tools, state_machine_tools, codegen_tools,
    flakiness_tools, suite_tools, quarantine_tools,
    a11y_audit_tools, device_matrix_tools, media_assert_tools,
)
