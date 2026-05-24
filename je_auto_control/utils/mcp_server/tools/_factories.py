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


ALL_FACTORIES = (
    mouse_tools, keyboard_tools, screen_tools, image_and_ocr_tools,
    window_tools, system_tools, recording_tools, drag_and_send_tools,
    semantic_locator_tools, self_healing_tools, anchor_locator_tools,
    ab_locator_tools, a11y_tree_tools, ocr_structure_tools,
    smart_wait_tools, cost_telemetry_tools, failure_hook_tools,
    computer_use_tools, dag_tools, presence_tools, chatops_tools,
    webrunner_tools,
    scheduler_tools, trigger_tools, hotkey_tools, screen_record_tools,
    process_and_shell_tools, remote_desktop_tools, gamepad_tools,
)
