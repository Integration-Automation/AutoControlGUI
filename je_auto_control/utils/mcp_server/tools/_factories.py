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
    screen_record_tools,
    process_and_shell_tools, remote_desktop_tools, gamepad_tools,
    usb_passthrough_tools, assertion_tools, data_source_tools,
    sql_tools, http_tools, email_tools, pdf_tools,
    visual_regression_tools, state_machine_tools, codegen_tools,
    flakiness_tools, suite_tools, quarantine_tools,
    a11y_audit_tools, device_matrix_tools, media_assert_tools,
)
