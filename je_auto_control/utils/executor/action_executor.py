import types
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

from je_auto_control.utils.exception.exception_tags import (
    action_is_null_error_message, add_command_exception_error_message,
    executor_list_error_message, cant_execute_action_error_message
)
from je_auto_control.utils.exception.exceptions import (
    AutoControlActionException, AutoControlAddCommandException,
    AutoControlActionNullException
)
from je_auto_control.utils.accessibility.accessibility_api import (
    click_accessibility_element, find_accessibility_element,
)
from je_auto_control.utils.self_healing import (
    default_heal_log,
    self_heal_click as _self_heal_click_impl,
    self_heal_locate as _self_heal_locate_impl,
)
from je_auto_control.utils.vision.vlm_api import (
    click_by_description, locate_by_description,
)
from je_auto_control.utils.clipboard.clipboard import (
    get_clipboard, set_clipboard,
)
from je_auto_control.utils.executor.action_schema import validate_actions
from je_auto_control.utils.executor.flow_control import (
    BLOCK_COMMANDS, LoopBreak, LoopContinue,
)
from je_auto_control.utils.executor.mouse_aliases import MOUSE_BUTTON_COMMANDS
from je_auto_control.utils.llm.planner import (
    plan_actions as llm_plan_actions,
    run_from_description as llm_run_from_description,
)
from je_auto_control.utils.remote_desktop.registry import (
    registry as remote_desktop_registry,
)
from je_auto_control.utils.rest_api.rest_registry import (
    rest_api_registry,
)
from je_auto_control.utils.admin.admin_client import (
    default_admin_console,
)
from je_auto_control.utils.ocr.ocr_engine import (
    click_text as ocr_click_text,
    find_text_regex as ocr_find_text_regex,
    locate_text_center as ocr_locate_text_center,
    read_text_in_region as ocr_read_text_in_region,
    wait_for_text as ocr_wait_for_text,
)
from je_auto_control.utils.profiler.profiler import default_profiler
from je_auto_control.utils.run_history.history_store import default_history_store
from je_auto_control.utils.secrets import default_secret_manager
from je_auto_control.utils.script_vars.interpolate import (
    interpolate_actions, interpolate_value,
)
from je_auto_control.utils.script_vars.scope import VariableScope
from je_auto_control.utils.http_client.http_client import http_request
from je_auto_control.utils.generate_report.generate_html_report import generate_html, generate_html_report
from je_auto_control.utils.generate_report.generate_json_report import generate_json, generate_json_report
from je_auto_control.utils.generate_report.generate_xml_report import generate_xml, generate_xml_report
from je_auto_control.utils.json.json_file import read_action_json
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.mcp_server.http_transport import start_mcp_http_server
from je_auto_control.utils.mcp_server.server import start_mcp_stdio_server
from je_auto_control.utils.package_manager.package_manager_class import package_manager
from je_auto_control.utils.project.create_project_structure import create_project_dir
from je_auto_control.utils.shell_process.shell_exec import default_shell_manager
from je_auto_control.utils.start_exe.start_another_process import start_exe
from je_auto_control.utils.test_record.record_test_class import record_action_to_list, test_record_instance
from je_auto_control.wrapper.auto_control_image import locate_all_image, locate_and_click, locate_image_center
from je_auto_control.wrapper.auto_control_keyboard import (
    check_key_is_press, get_keyboard_keys_table,
    press_keyboard_key, release_keyboard_key, hotkey, type_keyboard, write
)
from je_auto_control.wrapper.auto_control_mouse import (
    get_mouse_position, press_mouse, release_mouse, click_mouse,
    mouse_scroll, get_mouse_table, set_mouse_position
)
from je_auto_control.wrapper.auto_control_record import record, stop_record
from je_auto_control.wrapper.auto_control_screen import screenshot, screen_size
from je_auto_control.wrapper.auto_control_window import (
    close_window_by_title, focus_window, list_windows, wait_for_window,
)


def _a11y_list_as_dicts(app_name: Optional[str] = None,
                        max_results: int = 200) -> List[dict]:
    """Executor adapter: list accessibility elements as plain dicts."""
    from je_auto_control.utils.accessibility.accessibility_api import (
        list_accessibility_elements,
    )
    return [
        element.to_dict()
        for element in list_accessibility_elements(
            app_name=app_name, max_results=int(max_results),
        )
    ]


def _a11y_find_as_dict(name: Optional[str] = None,
                       role: Optional[str] = None,
                       app_name: Optional[str] = None) -> Optional[dict]:
    """Executor adapter: find an accessibility element, return its dict."""
    element = find_accessibility_element(
        name=name, role=role, app_name=app_name,
    )
    return None if element is None else element.to_dict()


def _vlm_locate_as_list(description: str,
                        screen_region: Optional[List[int]] = None,
                        model: Optional[str] = None) -> Optional[List[int]]:
    """Executor adapter: return VLM-located coords as a JSON-safe list."""
    coords = locate_by_description(
        description, screen_region=screen_region, model=model,
    )
    return None if coords is None else [coords[0], coords[1]]


def _self_heal_locate(template_path: Optional[str] = None,
                      description: Optional[str] = None,
                      detect_threshold: float = 0.9,
                      screen_region: Optional[List[int]] = None,
                      model: Optional[str] = None,
                      raise_on_miss: bool = False) -> Dict[str, Any]:
    """Executor adapter: template-first locate with VLM fallback."""
    outcome = _self_heal_locate_impl(
        template_path=template_path, description=description,
        detect_threshold=float(detect_threshold),
        screen_region=screen_region, model=model,
        raise_on_miss=bool(raise_on_miss),
    )
    return outcome.to_dict()


def _self_heal_click(template_path: Optional[str] = None,
                     description: Optional[str] = None,
                     mouse_keycode: str = "mouse_left",
                     detect_threshold: float = 0.9,
                     screen_region: Optional[List[int]] = None,
                     model: Optional[str] = None,
                     raise_on_miss: bool = False) -> Dict[str, Any]:
    """Executor adapter: locate with self-heal, then click."""
    outcome = _self_heal_click_impl(
        template_path=template_path, description=description,
        mouse_keycode=mouse_keycode,
        detect_threshold=float(detect_threshold),
        screen_region=screen_region, model=model,
        raise_on_miss=bool(raise_on_miss),
    )
    return outcome.to_dict()


def _self_heal_log_list(limit: int = 50) -> List[Dict[str, Any]]:
    """Executor adapter: return the recent self-healing events."""
    return [event.to_dict()
            for event in default_heal_log.list_events(limit=int(limit))]


def _self_heal_log_clear() -> Dict[str, Any]:
    default_heal_log.clear()
    return {"cleared": True, "path": str(default_heal_log.path)}


def _run_dag(definition: Dict[str, Any],
             max_parallel: int = 4) -> Dict[str, Any]:
    """Executor adapter: run a cross-host DAG definition."""
    from je_auto_control.utils.dag import run_dag
    return run_dag(definition, max_parallel=int(max_parallel)).to_dict()


_AX_RECORDER_SINGLETON = None
_DEFAULT_APPROVALS_DIR = ".approvals"


def _a11y_dump(app_name: Optional[str] = None,
                max_results: int = 500) -> Dict[str, Any]:
    """Executor adapter: dump the accessibility tree as nested dict."""
    from je_auto_control.utils.accessibility import dump_accessibility_tree
    return dump_accessibility_tree(
        app_name=app_name, max_results=int(max_results),
    ).to_dict()


def _walk_tree(app_name: Optional[str] = None,
               max_results: int = 500) -> Dict[str, Any]:
    """Executor adapter: dump the a11y tree with friendly roles + node paths."""
    from je_auto_control.utils.accessibility import dump_accessibility_tree
    from je_auto_control.utils.ax_tree_walk import (
        assign_node_paths, humanize_tree)
    root = dump_accessibility_tree(app_name=app_name,
                                   max_results=int(max_results))
    return assign_node_paths(humanize_tree(root)).to_dict()


def _humanize_role(role: str) -> Dict[str, Any]:
    """Executor adapter: translate a raw UIA role to a friendly name."""
    from je_auto_control.utils.ax_tree_walk import humanize_role
    return {"role": humanize_role(role)}


def _tab_order(app_name: Optional[str] = None,
               max_results: int = 500) -> Dict[str, Any]:
    """Executor adapter: focusable elements in keyboard Tab order."""
    from je_auto_control.utils.accessibility import list_accessibility_elements
    from je_auto_control.utils.focus_order import tab_order
    elements = list_accessibility_elements(app_name=app_name,
                                           max_results=int(max_results))
    return {"order": [el.to_dict() for el in tab_order(elements)]}


def _audit_focus_order(app_name: Optional[str] = None,
                       max_results: int = 500) -> Dict[str, Any]:
    """Executor adapter: WCAG focus-order audit over the app's elements."""
    from je_auto_control.utils.accessibility import list_accessibility_elements
    from je_auto_control.utils.focus_order import audit_focus_order
    elements = list_accessibility_elements(app_name=app_name,
                                           max_results=int(max_results))
    return audit_focus_order(elements)


def _focus_control(name: Optional[str] = None, role: Optional[str] = None,
                   app_name: Optional[str] = None,
                   automation_id: Optional[str] = None) -> bool:
    """Executor adapter: set keyboard focus on a control (UIA SetFocus)."""
    from je_auto_control.utils.focus_order import focus_control
    return focus_control(name=name, role=role, app_name=app_name,
                         automation_id=automation_id)


def _a11y_record_start(app_name: Optional[str] = None,
                        poll_interval_s: float = 0.25,
                        min_movement_px: int = 8) -> Dict[str, Any]:
    """Executor adapter: start the singleton accessibility recorder."""
    from je_auto_control.utils.accessibility import AccessibilityRecorder
    global _AX_RECORDER_SINGLETON
    if (_AX_RECORDER_SINGLETON is not None
            and _AX_RECORDER_SINGLETON.is_running):
        return {"running": True, "already": True}
    _AX_RECORDER_SINGLETON = AccessibilityRecorder(
        app_name=app_name,
        poll_interval_s=float(poll_interval_s),
        min_movement_px=int(min_movement_px),
    )
    _AX_RECORDER_SINGLETON.start()
    return {"running": True, "already": False}


def _a11y_record_stop() -> List[Dict[str, Any]]:
    """Executor adapter: stop the recorder and return the captured events."""
    global _AX_RECORDER_SINGLETON
    if _AX_RECORDER_SINGLETON is None:
        return []
    events = _AX_RECORDER_SINGLETON.stop()
    _AX_RECORDER_SINGLETON = None
    return [event.to_dict() for event in events]


def _a11y_record_events() -> List[Dict[str, Any]]:
    """Executor adapter: peek at events without stopping the recorder."""
    if _AX_RECORDER_SINGLETON is None:
        return []
    return [event.to_dict() for event in _AX_RECORDER_SINGLETON.events()]


def _ab_locate(target_id: str,
               strategies: Dict[str, Dict[str, Any]],
               max_parallel: int = 4,
               record: bool = True) -> Dict[str, Any]:
    """Executor adapter: race N locator strategies for the same target."""
    from je_auto_control.utils.ab_locator import ab_locate
    from je_auto_control.utils.anchor_locator import (
        Locator as AnchorLocator,
    )
    locators = {name: AnchorLocator(**spec)
                for name, spec in strategies.items()}
    return ab_locate(
        target_id=target_id, strategies=locators,
        max_parallel=int(max_parallel), record=bool(record),
    ).to_dict()


def _ab_report(target_id: str) -> Dict[str, Any]:
    from je_auto_control.utils.ab_locator import ab_report_for
    return ab_report_for(target_id).to_dict()


def _ab_best_strategy(target_id: str) -> Dict[str, Any]:
    from je_auto_control.utils.ab_locator import ab_best_strategy
    return {"target_id": target_id,
            "strategy": ab_best_strategy(target_id)}


def _ab_clear() -> Dict[str, Any]:
    from je_auto_control.utils.ab_locator import default_ab_store
    default_ab_store.clear()
    return {"cleared": True}


def _failure_hook_fire(source: str, source_id: str,
                       error_text: str = "",
                       script_path: Optional[str] = None,
                       screenshot_path: Optional[str] = None,
                       log_tail: str = "",
                       metadata: Optional[Dict[str, Any]] = None,
                       ) -> List[Dict[str, Any]]:
    """Executor adapter: file a ticket through every registered backend."""
    from je_auto_control.utils.failure_hooks import (
        FailureReport, default_failure_hook_manager,
    )
    report = FailureReport(
        source=source, source_id=source_id, error_text=error_text,
        script_path=script_path, screenshot_path=screenshot_path,
        log_tail=log_tail, metadata=dict(metadata or {}),
    )
    return [result.to_dict()
            for result in default_failure_hook_manager.fire(report)]


def _failure_hook_list() -> List[Dict[str, Any]]:
    from je_auto_control.utils.failure_hooks import default_failure_hook_manager
    return default_failure_hook_manager.list_backends()


def _failure_hook_clear() -> Dict[str, Any]:
    from je_auto_control.utils.failure_hooks import default_failure_hook_manager
    default_failure_hook_manager.clear()
    return {"cleared": True}


def _costs_record(provider: str, model: str,
                  input_tokens: int, output_tokens: int,
                  label: Optional[str] = None,
                  run_id: Optional[str] = None,
                  user: Optional[str] = None) -> Dict[str, Any]:
    """Executor adapter: append one LLM call to the cost-telemetry log."""
    from je_auto_control.utils.cost_telemetry import record_llm_call
    event = record_llm_call(
        provider=provider, model=model,
        input_tokens=int(input_tokens),
        output_tokens=int(output_tokens),
        label=label, run_id=run_id, user=user,
    )
    return event.to_dict()


def _costs_summary(limit: int = 10000) -> Dict[str, Any]:
    """Executor adapter: aggregate cost events by model / provider / day."""
    from je_auto_control.utils.cost_telemetry import (
        default_cost_store, summarise_llm_costs,
    )
    events = default_cost_store.list_events(limit=int(limit))
    return summarise_llm_costs(events).to_dict()


def _costs_list(limit: int = 100) -> List[Dict[str, Any]]:
    from je_auto_control.utils.cost_telemetry import default_cost_store
    return [event.to_dict()
            for event in default_cost_store.list_events(limit=int(limit))]


def _costs_clear() -> Dict[str, Any]:
    from je_auto_control.utils.cost_telemetry import default_cost_store
    default_cost_store.clear()
    return {"cleared": True, "path": str(default_cost_store.path)}


def _wait_screen_stable(region: Optional[List[int]] = None,
                        timeout_s: float = 10.0,
                        poll_interval_s: float = 0.2,
                        stable_for_s: float = 0.5,
                        max_pixel_diff: int = 0) -> Dict[str, Any]:
    """Executor adapter: smart wait for the screen to stop moving."""
    from je_auto_control.utils.smart_waits import wait_until_screen_stable
    return wait_until_screen_stable(
        region=region, timeout_s=float(timeout_s),
        poll_interval_s=float(poll_interval_s),
        stable_for_s=float(stable_for_s),
        max_pixel_diff=int(max_pixel_diff),
    ).to_dict()


def _wait_pixel_changes(x: int, y: int,
                         timeout_s: float = 10.0,
                         poll_interval_s: float = 0.1,
                         rgb_tolerance: int = 5) -> Dict[str, Any]:
    """Executor adapter: smart wait for one pixel to change colour."""
    from je_auto_control.utils.smart_waits import wait_until_pixel_changes
    return wait_until_pixel_changes(
        x=int(x), y=int(y),
        timeout_s=float(timeout_s),
        poll_interval_s=float(poll_interval_s),
        rgb_tolerance=int(rgb_tolerance),
    ).to_dict()


def _wait_clipboard_change(baseline: Optional[str] = None,
                           target: Optional[str] = None,
                           contains: bool = False,
                           timeout_s: float = 10.0,
                           poll_interval_s: float = 0.2) -> Dict[str, Any]:
    """Executor adapter: wait until the clipboard changes (or matches target)."""
    from je_auto_control.utils.smart_waits import wait_until_clipboard_changes
    return wait_until_clipboard_changes(
        baseline=baseline, target=target, contains=bool(contains),
        timeout_s=float(timeout_s), poll_interval_s=float(poll_interval_s),
    ).to_dict()


def _wait_image_gone(image: Any, detect_threshold: float = 1.0,
                     timeout_s: float = 10.0, poll_interval_s: float = 0.2,
                     gone_for_s: float = 0.0) -> Dict[str, Any]:
    """Executor adapter: wait until an image is no longer on screen."""
    from je_auto_control.utils.smart_waits import wait_until_image_gone
    return wait_until_image_gone(
        image, detect_threshold=float(detect_threshold),
        timeout_s=float(timeout_s), poll_interval_s=float(poll_interval_s),
        gone_for_s=float(gone_for_s),
    ).to_dict()


def _wait_text_gone(text: str, timeout_s: float = 10.0,
                    poll_interval_s: float = 0.2,
                    gone_for_s: float = 0.0) -> Dict[str, Any]:
    """Executor adapter: wait until text is no longer on screen (OCR)."""
    from je_auto_control.utils.smart_waits import wait_until_text_gone
    return wait_until_text_gone(
        text, timeout_s=float(timeout_s),
        poll_interval_s=float(poll_interval_s), gone_for_s=float(gone_for_s),
    ).to_dict()


def _wait_window_title(pattern: str, present: bool = True, regex: bool = True,
                       timeout_s: float = 10.0,
                       poll_interval_s: float = 0.2) -> Dict[str, Any]:
    """Executor adapter: wait for a window title (regex) to appear / vanish."""
    from je_auto_control.utils.smart_waits import wait_until_window_title
    return wait_until_window_title(
        pattern, present=bool(present), regex=bool(regex),
        timeout_s=float(timeout_s), poll_interval_s=float(poll_interval_s),
    ).to_dict()


def _wait_color(target_rgb: Any, region: Any = None,
                tolerance: int = 10, min_fraction: float = 0.5,
                present: bool = True, timeout_s: float = 10.0,
                poll_interval_s: float = 0.2) -> Dict[str, Any]:
    """Executor adapter: wait until a colour fills/leaves a region."""
    import json
    from je_auto_control.utils.smart_waits import wait_until_color
    if isinstance(target_rgb, str):
        target_rgb = json.loads(target_rgb)
    if isinstance(region, str):
        region = json.loads(region) if region.strip() else None
    return wait_until_color(
        region=region, target_rgb=target_rgb, tolerance=int(tolerance),
        min_fraction=float(min_fraction), present=bool(present),
        timeout_s=float(timeout_s), poll_interval_s=float(poll_interval_s),
    ).to_dict()


def _wait_window_closed(title: str, case_sensitive: bool = False,
                        timeout_s: float = 10.0,
                        poll_interval_s: float = 0.2) -> Dict[str, Any]:
    """Executor adapter: wait until a window matching ``title`` disappears."""
    from je_auto_control.utils.smart_waits import wait_until_window_closed
    return wait_until_window_closed(
        title, case_sensitive=bool(case_sensitive),
        timeout_s=float(timeout_s), poll_interval_s=float(poll_interval_s),
    ).to_dict()


def _wait_region_idle(region: List[int],
                      timeout_s: float = 10.0,
                      poll_interval_s: float = 0.2,
                      stable_for_s: float = 0.5,
                      max_pixel_diff: int = 0) -> Dict[str, Any]:
    """Executor adapter: smart wait for a sub-region to stop moving."""
    from je_auto_control.utils.smart_waits import wait_until_region_idle
    return wait_until_region_idle(
        region=region, timeout_s=float(timeout_s),
        poll_interval_s=float(poll_interval_s),
        stable_for_s=float(stable_for_s),
        max_pixel_diff=int(max_pixel_diff),
    ).to_dict()


def _wait_for_file(path: str, timeout_s: float = 30.0,
                   poll_interval_s: float = 0.25,
                   stable_for_s: float = 1.0,
                   min_size: int = 1) -> Dict[str, Any]:
    """Executor adapter: wait until a file exists and finishes being written."""
    from je_auto_control.utils.smart_waits import wait_until_file
    return wait_until_file(
        path, timeout_s=float(timeout_s),
        poll_interval_s=float(poll_interval_s),
        stable_for_s=float(stable_for_s), min_size=int(min_size),
    ).to_dict()


def _wait_for_port(host: str, port: int, timeout_s: float = 30.0,
                   poll_interval_s: float = 0.25,
                   connect_timeout_s: float = 1.0) -> Dict[str, Any]:
    """Executor adapter: wait until a TCP port accepts connections."""
    from je_auto_control.utils.smart_waits import wait_until_port
    return wait_until_port(
        host, int(port), timeout_s=float(timeout_s),
        poll_interval_s=float(poll_interval_s),
        connect_timeout_s=float(connect_timeout_s),
    ).to_dict()


def _wait_for_process(name: str, present: bool = True, timeout_s: float = 30.0,
                      poll_interval_s: float = 0.25) -> Dict[str, Any]:
    """Executor adapter: wait until a process appears or exits."""
    from je_auto_control.utils.smart_waits import wait_until_process
    return wait_until_process(
        name, present=bool(present), timeout_s=float(timeout_s),
        poll_interval_s=float(poll_interval_s),
    ).to_dict()


def _ocr_read_structure(region: Optional[List[int]] = None,
                        lang: str = "eng",
                        min_confidence: float = 60.0,
                        ) -> Dict[str, Any]:
    """Executor adapter: structured OCR (rows / tables / form fields)."""
    from je_auto_control.utils.ocr.structure import read_structure
    structured = read_structure(
        region=region, lang=lang,
        min_confidence=float(min_confidence),
    )
    return structured.to_dict()


def _anchor_locate(anchor: Dict[str, Any], target: Dict[str, Any],
                   relation: str = "near",
                   max_distance_px: float = 200.0,
                   ordinal: Any = 1) -> Dict[str, Any]:
    """Executor adapter: anchor-based spatial locator (Nth match via ordinal)."""
    from je_auto_control.utils.anchor_locator import (
        Locator, anchor_locate,
    )
    anchor_loc = Locator(**anchor)
    target_loc = Locator(**target)
    outcome = anchor_locate(
        anchor=anchor_loc, target=target_loc,
        relation=relation, max_distance_px=float(max_distance_px),
        ordinal=int(ordinal),
    )
    return outcome.to_dict()


def _anchor_locate_all(anchor: Dict[str, Any], target: Dict[str, Any],
                       relation: str = "near",
                       max_distance_px: float = 200.0) -> Dict[str, Any]:
    """Executor adapter: every anchor-relative match, nearest-first."""
    from je_auto_control.utils.anchor_locator import Locator, anchor_locate_all
    outcomes = anchor_locate_all(
        anchor=Locator(**anchor), target=Locator(**target),
        relation=relation, max_distance_px=float(max_distance_px),
    )
    return {"count": len(outcomes), "matches": [o.to_dict() for o in outcomes]}


def _anchor_click(anchor: Dict[str, Any], target: Dict[str, Any],
                  mouse_keycode: str = "mouse_left",
                  relation: str = "near",
                  max_distance_px: float = 200.0) -> Dict[str, Any]:
    """Executor adapter: anchor-locate + click."""
    outcome = _anchor_locate(anchor, target, relation, max_distance_px)
    if outcome.get("found") and outcome.get("target_coords"):
        cx, cy = outcome["target_coords"]
        from je_auto_control.wrapper.auto_control_mouse import (
            click_mouse, set_mouse_position,
        )
        set_mouse_position(int(cx), int(cy))
        click_mouse(mouse_keycode, int(cx), int(cy))
    return outcome


def _chatops_dispatch(message: str,
                      context: Optional[Dict[str, Any]] = None,
                      script_root: Optional[str] = None) -> Dict[str, Any]:
    """Executor adapter: route one chat message through the default router."""
    from je_auto_control.utils.chatops import (
        CommandRouter, register_chatops_default_commands,
    )
    router = CommandRouter()
    register_chatops_default_commands(router)
    merged_context: Dict[str, Any] = dict(context or {})
    if script_root is not None:
        merged_context.setdefault("script_root", script_root)
    result = router.dispatch(message, context=merged_context)
    return {"matched": False} if result is None else {
        "matched": True, **result.to_dict(),
    }


def _presence_register(viewer_id: str, label: str = "",
                       role: str = "observer") -> Dict[str, Any]:
    from je_auto_control.utils.remote_desktop.presence import (
        default_presence_registry,
    )
    return default_presence_registry().register(
        viewer_id, label, role=role,
    ).to_dict()


def _presence_unregister(viewer_id: str) -> Dict[str, Any]:
    from je_auto_control.utils.remote_desktop.presence import (
        default_presence_registry,
    )
    removed = default_presence_registry().unregister(viewer_id)
    return {"viewer_id": viewer_id, "removed": removed}


def _presence_update_cursor(viewer_id: str, x: int, y: int) -> Dict[str, Any]:
    from je_auto_control.utils.remote_desktop.presence import (
        default_presence_registry,
    )
    return default_presence_registry().update_cursor(
        viewer_id, int(x), int(y),
    ).to_dict()


def _presence_set_role(viewer_id: str, role: str) -> Dict[str, Any]:
    from je_auto_control.utils.remote_desktop.presence import (
        default_presence_registry,
    )
    return default_presence_registry().update_role(viewer_id, role).to_dict()


def _presence_list() -> List[Dict[str, Any]]:
    from je_auto_control.utils.remote_desktop.presence import (
        default_presence_registry,
    )
    return [row.to_dict() for row in default_presence_registry().list()]


def _presence_clear() -> Dict[str, Any]:
    from je_auto_control.utils.remote_desktop.presence import (
        default_presence_registry,
    )
    default_presence_registry().clear()
    return {"cleared": True}


def _run_agent(goal: str,
               backend: str = "anthropic",
               max_steps: int = 25,
               wall_seconds: float = 300.0,
               model: Optional[str] = None,
               max_tokens: int = 1024) -> Dict[str, Any]:
    """Executor adapter: drive the closed-loop ``AgentLoop`` against ``goal``.

    ``backend`` selects between the production backends (Anthropic /
    OpenAI). The Anthropic computer-use raw path remains available
    via :func:`_computer_use` / ``AC_computer_use``.
    """
    from je_auto_control.utils.agent import AgentBudget, AgentLoop
    from je_auto_control.utils.agent.backends import (
        AnthropicAgentBackend, OpenAIAgentBackend,
    )
    from je_auto_control.utils.tool_use_schema import (
        export_anthropic_tools, export_openai_tools,
    )
    name = (backend or "anthropic").strip().lower()
    if name == "anthropic":
        tools = export_anthropic_tools()
        backend_obj = AnthropicAgentBackend(
            tools=tools,
            model=model or "claude-opus-4-7",
            max_tokens=int(max_tokens),
        )
    elif name == "openai":
        tools = export_openai_tools()
        # OpenAIAgentBackend does not accept max_tokens (Anthropic-only).
        backend_obj = OpenAIAgentBackend(
            tools=tools,
            model=model or "gpt-4o",
        )
    else:
        raise ValueError(f"unknown agent backend: {backend!r}")
    budget = AgentBudget(
        max_steps=int(max_steps), wall_seconds=float(wall_seconds),
    )
    result = AgentLoop(backend_obj, budget=budget).run(goal)
    return {
        "succeeded": bool(result.succeeded),
        "elapsed_s": float(result.elapsed_s),
        "final_message": result.final_message,
        "steps": [
            {
                "index": step.index,
                "tool": step.tool,
                "arguments": step.arguments,
                "error": step.error,
                "stop_reason": step.stop_reason,
            }
            for step in result.steps
        ],
    }


def _redact_screenshot(file_path: str,
                       output_path: Optional[str] = None,
                       policy: str = "moderate",
                       regions: Optional[List[List[int]]] = None,
                       accessibility: Optional[List[Dict[str, Any]]] = None,
                       ocr: Optional[List[Dict[str, Any]]] = None,
                       ) -> Dict[str, Any]:
    """Executor adapter: blur PII regions in a saved screenshot.

    Reads ``file_path``, applies the chosen redaction policy
    (optionally with caller-supplied accessibility / OCR context),
    and writes the result to ``output_path`` (or overwrites the
    source when omitted). Returns ``{output_path, boxes,
    detectors_used}`` for downstream audit.
    """
    from je_auto_control.utils.redaction import (
        RedactionEngine, policy_from_name,
    )
    target = output_path or file_path
    chosen = policy_from_name(policy)
    if regions:
        chosen = chosen.with_extra_regions(
            [tuple(int(v) for v in r) for r in regions],
        )
    engine = RedactionEngine(chosen)
    context: Dict[str, Any] = {}
    if accessibility is not None:
        context["accessibility"] = list(accessibility)
    if ocr is not None:
        context["ocr"] = [(item["text"], item["bbox"]) for item in ocr]
    with open(file_path, "rb") as src:
        png_bytes = src.read()
    redacted, result = engine.redact_bytes(png_bytes, context)
    with open(target, "wb") as dest:
        dest.write(redacted)
    return {
        "output_path": str(target),
        "boxes": [list(b) for b in result.boxes],
        "detectors_used": list(result.detectors_used),
    }


def _assert_text(text: str,
                 region: Optional[List[int]] = None,
                 lang: str = "eng",
                 regex: bool = False,
                 present: bool = True,
                 ignore_case: bool = True,
                 min_confidence: float = 60.0,
                 raise_on_fail: bool = True,
                 capture_on_fail: bool = False) -> Dict[str, Any]:
    """Executor adapter: assert OCR text is (not) on screen."""
    from je_auto_control.utils.assertion import assert_text
    return assert_text(
        text, region=region, lang=lang, regex=bool(regex),
        present=bool(present), ignore_case=bool(ignore_case),
        min_confidence=float(min_confidence),
        raise_on_fail=bool(raise_on_fail),
        capture_on_fail=bool(capture_on_fail),
    ).to_dict()


def _assert_image(template_path: str,
                  threshold: float = 0.9,
                  present: bool = True,
                  raise_on_fail: bool = True,
                  capture_on_fail: bool = False) -> Dict[str, Any]:
    """Executor adapter: assert a template image is (not) on screen."""
    from je_auto_control.utils.assertion import assert_image
    return assert_image(
        template_path, threshold=float(threshold), present=bool(present),
        raise_on_fail=bool(raise_on_fail),
        capture_on_fail=bool(capture_on_fail),
    ).to_dict()


def _assert_pixel(x: int, y: int, rgb: List[int],
                  tolerance: int = 0,
                  match: bool = True,
                  raise_on_fail: bool = True,
                  capture_on_fail: bool = False) -> Dict[str, Any]:
    """Executor adapter: assert a pixel matches (or differs from) ``rgb``."""
    from je_auto_control.utils.assertion import assert_pixel
    return assert_pixel(
        int(x), int(y), rgb, tolerance=int(tolerance), match=bool(match),
        raise_on_fail=bool(raise_on_fail),
        capture_on_fail=bool(capture_on_fail),
    ).to_dict()


def _assert_window(title: str,
                   exists: bool = True,
                   ignore_case: bool = True,
                   raise_on_fail: bool = True,
                   capture_on_fail: bool = False) -> Dict[str, Any]:
    """Executor adapter: assert a window matching ``title`` does (not) exist."""
    from je_auto_control.utils.assertion import assert_window
    return assert_window(
        title, exists=bool(exists), ignore_case=bool(ignore_case),
        raise_on_fail=bool(raise_on_fail),
        capture_on_fail=bool(capture_on_fail),
    ).to_dict()


def _assert_vlm(description: str,
                present: bool = True,
                screen_region: Optional[List[int]] = None,
                model: Optional[str] = None,
                raise_on_fail: bool = True,
                capture_on_fail: bool = False) -> Dict[str, Any]:
    """Executor adapter: assert the screen matches a description (VLM judged)."""
    from je_auto_control.utils.assertion import assert_by_description
    return assert_by_description(
        description, present=bool(present), screen_region=screen_region,
        model=model, raise_on_fail=bool(raise_on_fail),
        capture_on_fail=bool(capture_on_fail),
    ).to_dict()


def _assert_clipboard(text: str,
                      mode: str = "equals",
                      ignore_case: bool = False,
                      present: bool = True,
                      raise_on_fail: bool = True,
                      capture_on_fail: bool = False) -> Dict[str, Any]:
    """Executor adapter: assert clipboard text matches ``text``."""
    from je_auto_control.utils.assertion import assert_clipboard
    return assert_clipboard(
        text, mode=mode, ignore_case=bool(ignore_case),
        present=bool(present), raise_on_fail=bool(raise_on_fail),
        capture_on_fail=bool(capture_on_fail),
    ).to_dict()


def _assert_process(name: str,
                    running: bool = True,
                    raise_on_fail: bool = True,
                    capture_on_fail: bool = False) -> Dict[str, Any]:
    """Executor adapter: assert a process matching ``name`` is (not) running."""
    from je_auto_control.utils.assertion import assert_process
    return assert_process(
        name, running=bool(running), raise_on_fail=bool(raise_on_fail),
        capture_on_fail=bool(capture_on_fail),
    ).to_dict()


def _assert_file(path: str,
                 exists: bool = True,
                 contains: Optional[str] = None,
                 sha256: Optional[str] = None,
                 min_size: Optional[int] = None,
                 raise_on_fail: bool = True) -> Dict[str, Any]:
    """Executor adapter: assert a file's existence / content / hash / size."""
    from je_auto_control.utils.assertion import assert_file
    return assert_file(
        path, exists=bool(exists), contains=contains, sha256=sha256,
        min_size=None if min_size is None else int(min_size),
        raise_on_fail=bool(raise_on_fail),
    ).to_dict()


def _assert_http(url: str,
                 status: int = 200,
                 contains: Optional[str] = None,
                 timeout: float = 10.0,
                 method: str = "GET",
                 raise_on_fail: bool = True) -> Dict[str, Any]:
    """Executor adapter: assert an HTTP(S) endpoint status / body."""
    from je_auto_control.utils.assertion import assert_http
    return assert_http(
        url, status=int(status), contains=contains, timeout=float(timeout),
        method=method, raise_on_fail=bool(raise_on_fail),
    ).to_dict()


def _assert_all(specs: List[Dict[str, Any]],
                raise_on_fail: bool = True) -> Dict[str, Any]:
    """Executor adapter: run a batch of assertion specs (soft assertions)."""
    from je_auto_control.utils.assertion import assert_all
    return assert_all(specs, raise_on_fail=bool(raise_on_fail)).to_dict()


def _assert_any(specs: List[Dict[str, Any]],
                raise_on_fail: bool = True) -> Dict[str, Any]:
    """Executor adapter: pass when at least one assertion spec passes."""
    from je_auto_control.utils.assertion import assert_any
    return assert_any(specs, raise_on_fail=bool(raise_on_fail)).to_dict()


def _assert_eventually(spec: Dict[str, Any],
                       timeout: float = 5.0,
                       interval: float = 0.25,
                       raise_on_fail: bool = True) -> Dict[str, Any]:
    """Executor adapter: poll one assertion spec until it passes / times out."""
    from je_auto_control.utils.assertion import assert_eventually
    return assert_eventually(
        spec, timeout=float(timeout), interval=float(interval),
        raise_on_fail=bool(raise_on_fail),
    ).to_dict()


def _load_data(source: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Executor adapter: load tabular rows from a data source spec."""
    from je_auto_control.utils.data_source import load_rows
    return load_rows(source)


def _flaky_report(limit: int = 500,
                  min_runs: int = 2,
                  group_by: str = "script_path") -> Dict[str, Any]:
    """Executor adapter: score run-history flakiness per script / source."""
    from je_auto_control.utils.flakiness import analyze_flakiness
    return analyze_flakiness(
        limit=int(limit), min_runs=int(min_runs), group_by=group_by,
    ).to_dict()


def _run_suite(spec: Dict[str, Any],
               tags: Optional[List[str]] = None,
               respect_quarantine: bool = True,
               junit_path: Optional[str] = None,
               allure_dir: Optional[str] = None) -> Dict[str, Any]:
    """Executor adapter: run a QA suite and optionally write CI reports."""
    from je_auto_control.utils.test_suite import (
        run_suite, write_allure_results, write_junit_xml,
    )
    result = run_suite(
        spec, executor=executor, tags=tags,
        respect_quarantine=bool(respect_quarantine),
    )
    payload = result.to_dict()
    reports: Dict[str, Any] = {}
    if junit_path:
        reports["junit"] = write_junit_xml(result, junit_path)
    if allure_dir:
        reports["allure"] = write_allure_results(result, allure_dir)
    if reports:
        payload["reports"] = reports
    return payload


def _quarantine_add(name: str, reason: str = "") -> Dict[str, Any]:
    from je_auto_control.utils.quarantine import default_quarantine_store
    return default_quarantine_store().add(name, reason=reason).to_dict()


def _quarantine_remove(name: str) -> Dict[str, Any]:
    from je_auto_control.utils.quarantine import default_quarantine_store
    return {"name": name, "removed": default_quarantine_store().remove(name)}


def _quarantine_list() -> List[Dict[str, Any]]:
    from je_auto_control.utils.quarantine import default_quarantine_store
    return [entry.to_dict() for entry in default_quarantine_store().list()]


def _quarantine_clear() -> Dict[str, Any]:
    from je_auto_control.utils.quarantine import default_quarantine_store
    return {"cleared": default_quarantine_store().clear()}


def _quarantine_auto(flip_rate_threshold: float = 0.5,
                     min_runs: int = 3,
                     limit: int = 500,
                     group_by: str = "script_path") -> List[Dict[str, Any]]:
    from je_auto_control.utils.quarantine import auto_quarantine_from_flakiness
    return [
        entry.to_dict()
        for entry in auto_quarantine_from_flakiness(
            flip_rate_threshold=float(flip_rate_threshold),
            min_runs=int(min_runs), limit=int(limit), group_by=group_by,
        )
    ]


def _audit_accessibility(app_name: Optional[str] = None,
                         contrast_pairs: Optional[List[Dict[str, Any]]] = None,
                         texts: Optional[List[str]] = None,
                         min_ratio: float = 4.5,
                         max_results: int = 500) -> Dict[str, Any]:
    """Executor adapter: run the accessibility / i18n audit."""
    from je_auto_control.utils.a11y_audit import run_audit
    return run_audit(
        app_name=app_name, contrast_pairs=contrast_pairs, texts=texts,
        min_ratio=float(min_ratio), max_results=int(max_results),
    ).to_dict()


def _audit_contrast(foreground: List[int], background: List[int],
                    min_ratio: float = 4.5) -> Dict[str, Any]:
    """Executor adapter: WCAG contrast ratio for one colour pair."""
    from je_auto_control.utils.a11y_audit import contrast_ratio
    ratio = contrast_ratio(foreground, background)
    return {
        "ratio": round(ratio, 2),
        "passes_aa": ratio >= float(min_ratio),
        "foreground": list(foreground), "background": list(background),
    }


def _wcag_audit(app_name: Optional[str] = None,
                contrast_pairs: Optional[List[Dict[str, Any]]] = None,
                texts: Optional[List[str]] = None, level: str = "AA",
                min_target_px: int = 24, max_results: int = 500
                ) -> Dict[str, Any]:
    """Executor adapter: WCAG-tagged conformance audit (SC ids + levels)."""
    from je_auto_control.utils.a11y_audit import wcag_audit
    return wcag_audit(
        app_name=app_name, contrast_pairs=contrast_pairs, texts=texts,
        level=str(level), min_target_px=int(min_target_px),
        max_results=int(max_results))


def _run_device_matrix(actions: List[Any], devices: List[Dict[str, Any]],
                       max_parallel: int = 4,
                       var_name: str = "device") -> Dict[str, Any]:
    """Executor adapter: run an action list across many devices in parallel."""
    from je_auto_control.utils.device_matrix import run_on_devices
    return run_on_devices(
        actions, devices, max_parallel=int(max_parallel), var_name=var_name,
    ).to_dict()


def _assert_audio(duration_s: float = 1.0,
                  threshold: float = 0.01,
                  expect_sound: bool = True,
                  samplerate: int = 44100,
                  channels: int = 1,
                  raise_on_fail: bool = True) -> Dict[str, Any]:
    """Executor adapter: assert audio activity / silence."""
    from je_auto_control.utils.media_assert import assert_audio_activity
    return assert_audio_activity(
        duration_s=float(duration_s), threshold=float(threshold),
        expect_sound=bool(expect_sound), samplerate=int(samplerate),
        channels=int(channels), raise_on_fail=bool(raise_on_fail),
    ).to_dict()


def _assert_video_changes(video_path: str,
                          start_s: float = 0.0,
                          end_s: Optional[float] = None,
                          threshold: float = 1.0,
                          expect_motion: bool = True,
                          region: Optional[List[int]] = None,
                          raise_on_fail: bool = True) -> Dict[str, Any]:
    """Executor adapter: assert a video segment has motion / is static."""
    from je_auto_control.utils.media_assert import assert_video_changes
    return assert_video_changes(
        video_path, start_s=float(start_s),
        end_s=None if end_s is None else float(end_s),
        threshold=float(threshold), expect_motion=bool(expect_motion),
        region=region, raise_on_fail=bool(raise_on_fail),
    ).to_dict()


def _computer_use(goal: str,
                  display_width_px: Optional[int] = None,
                  display_height_px: Optional[int] = None,
                  display_number: Optional[int] = None,
                  max_steps: int = 25,
                  wall_seconds: float = 300.0,
                  model: str = "claude-opus-4-7",
                  max_tokens: int = 1024) -> Dict[str, Any]:
    """Executor adapter: run Anthropic Computer-Use to achieve ``goal``."""
    from je_auto_control.utils.agent.computer_use import (
        result_to_dict, run_computer_use,
    )
    result = run_computer_use(
        goal,
        display_width_px=display_width_px,
        display_height_px=display_height_px,
        display_number=display_number,
        max_steps=int(max_steps), wall_seconds=float(wall_seconds),
        model=model, max_tokens=int(max_tokens),
    )
    return result_to_dict(result)


def _remote_start_host(token: str,
                       bind: str = "127.0.0.1",
                       port: int = 0,
                       fps: float = 10.0,
                       quality: int = 70,
                       region: Optional[List[int]] = None,
                       max_clients: int = 4) -> Dict[str, Any]:
    """Executor adapter: start the singleton remote-desktop host."""
    return remote_desktop_registry.start_host(
        token=token, bind=bind, port=int(port),
        fps=float(fps), quality=int(quality),
        region=region, max_clients=int(max_clients),
    )


def _remote_stop_host() -> Dict[str, Any]:
    return remote_desktop_registry.stop_host()


def _remote_host_status() -> Dict[str, Any]:
    return remote_desktop_registry.host_status()


def _remote_connect(host: str, port: int, token: str,
                    timeout: float = 5.0) -> Dict[str, Any]:
    """Executor adapter: connect the singleton viewer."""
    return remote_desktop_registry.connect_viewer(
        host=host, port=int(port), token=token, timeout=float(timeout),
    )


def _remote_disconnect() -> Dict[str, Any]:
    return remote_desktop_registry.disconnect_viewer()


def _remote_viewer_status() -> Dict[str, Any]:
    return remote_desktop_registry.viewer_status()


def _remote_send_input(action: Dict[str, Any]) -> Dict[str, Any]:
    return remote_desktop_registry.send_input(action)


# --- WebSocket-transport remote desktop ------------------------------------

def _ws_start_host(token: str,
                   bind: str = "127.0.0.1",
                   port: int = 0,
                   fps: float = 10.0,
                   quality: int = 70,
                   region: Optional[List[int]] = None,
                   max_clients: int = 4) -> Dict[str, Any]:
    """Executor adapter: start the singleton WebSocket-transport host."""
    return remote_desktop_registry.start_ws_host(
        token=token, bind=bind, port=int(port),
        fps=float(fps), quality=int(quality),
        region=region, max_clients=int(max_clients),
    )


def _ws_stop_host() -> Dict[str, Any]:
    return remote_desktop_registry.stop_ws_host()


def _ws_host_status() -> Dict[str, Any]:
    return remote_desktop_registry.ws_host_status()


def _ws_connect(host: str, port: int, token: str,
                path: str = "/",
                timeout: float = 5.0) -> Dict[str, Any]:
    """Executor adapter: connect the singleton WS viewer."""
    return remote_desktop_registry.connect_ws_viewer(
        host=host, port=int(port), token=token,
        path=path, timeout=float(timeout),
    )


def _ws_disconnect() -> Dict[str, Any]:
    return remote_desktop_registry.disconnect_ws_viewer()


def _ws_viewer_status() -> Dict[str, Any]:
    return remote_desktop_registry.ws_viewer_status()


def _ws_send_input(action: Dict[str, Any]) -> Dict[str, Any]:
    return remote_desktop_registry.ws_send_input(action)


# --- WebRTC-transport remote desktop (manual SDP signaling) ----------------

def _webrtc_start_host(token: str,
                       read_only: bool = False) -> Dict[str, Any]:
    """Executor adapter: allocate the singleton WebRTC host.

    Follow up with ``AC_webrtc_create_offer`` then
    ``AC_webrtc_accept_answer`` once the viewer's answer SDP arrives.
    """
    return remote_desktop_registry.start_webrtc_host(
        token=token, read_only=bool(read_only),
    )


def _webrtc_create_offer(peer_label: str = "remote viewer") -> Dict[str, Any]:
    return remote_desktop_registry.webrtc_create_offer(peer_label=peer_label)


def _webrtc_accept_answer(answer_sdp: str) -> Dict[str, Any]:
    return remote_desktop_registry.webrtc_accept_answer(answer_sdp)


def _webrtc_stop_host() -> Dict[str, Any]:
    return remote_desktop_registry.stop_webrtc_host()


def _webrtc_host_status() -> Dict[str, Any]:
    return remote_desktop_registry.webrtc_host_status()


def _webrtc_start_viewer(token: str,
                         viewer_id: Optional[str] = None) -> Dict[str, Any]:
    """Executor adapter: allocate the singleton WebRTC viewer."""
    return remote_desktop_registry.start_webrtc_viewer(
        token=token, viewer_id=viewer_id,
    )


def _webrtc_process_offer(offer_sdp: str,
                          expected_dtls_fingerprint: Optional[str] = None,
                          ) -> Dict[str, Any]:
    return remote_desktop_registry.webrtc_process_offer(
        offer_sdp,
        expected_dtls_fingerprint=expected_dtls_fingerprint,
    )


def _webrtc_send_input(action: Dict[str, Any]) -> Dict[str, Any]:
    return remote_desktop_registry.webrtc_send_input(action)


def _webrtc_stop_viewer() -> Dict[str, Any]:
    return remote_desktop_registry.stop_webrtc_viewer()


def _webrtc_viewer_status() -> Dict[str, Any]:
    return remote_desktop_registry.webrtc_viewer_status()


# --- Virtual gamepad (ViGEm) -----------------------------------------------

def _gamepad_press(button: str) -> Dict[str, Any]:
    from je_auto_control.utils.gamepad import default_gamepad
    default_gamepad().press_button(button)
    return {"button": button, "state": "down"}


def _gamepad_release(button: str) -> Dict[str, Any]:
    from je_auto_control.utils.gamepad import default_gamepad
    default_gamepad().release_button(button)
    return {"button": button, "state": "up"}


def _gamepad_click(button: str) -> Dict[str, Any]:
    from je_auto_control.utils.gamepad import default_gamepad
    default_gamepad().click_button(button)
    return {"button": button, "state": "click"}


def _gamepad_dpad(direction: str) -> Dict[str, Any]:
    from je_auto_control.utils.gamepad import default_gamepad
    default_gamepad().set_dpad(direction)
    return {"dpad": direction}


def _gamepad_left_stick(x: int, y: int) -> Dict[str, Any]:
    from je_auto_control.utils.gamepad import default_gamepad
    default_gamepad().set_left_stick(int(x), int(y))
    return {"left_stick": [int(x), int(y)]}


def _gamepad_right_stick(x: int, y: int) -> Dict[str, Any]:
    from je_auto_control.utils.gamepad import default_gamepad
    default_gamepad().set_right_stick(int(x), int(y))
    return {"right_stick": [int(x), int(y)]}


def _gamepad_left_trigger(value: int) -> Dict[str, Any]:
    from je_auto_control.utils.gamepad import default_gamepad
    default_gamepad().set_left_trigger(int(value))
    return {"left_trigger": int(value)}


def _gamepad_right_trigger(value: int) -> Dict[str, Any]:
    from je_auto_control.utils.gamepad import default_gamepad
    default_gamepad().set_right_trigger(int(value))
    return {"right_trigger": int(value)}


def _gamepad_reset() -> Dict[str, Any]:
    from je_auto_control.utils.gamepad import default_gamepad
    default_gamepad().reset()
    return {"reset": True}


def _rest_api_start(host: str = "127.0.0.1",
                    port: int = 9939,
                    token: Optional[str] = None,
                    enable_audit: bool = True) -> Dict[str, Any]:
    """Executor adapter: start the singleton REST API server."""
    return rest_api_registry.start(
        host=host, port=int(port), token=token,
        enable_audit=bool(enable_audit),
    )


def _rest_api_stop() -> Dict[str, Any]:
    return rest_api_registry.stop()


def _rest_api_status() -> Dict[str, Any]:
    return rest_api_registry.status()


def _admin_add_host(label: str, base_url: str, token: str,
                    tags: Optional[List[str]] = None) -> Dict[str, Any]:
    """Executor adapter: register a remote AutoControl REST endpoint."""
    host = default_admin_console().add_host(
        label=label, base_url=base_url, token=token, tags=tags,
    )
    return {"label": host.label, "base_url": host.base_url, "tags": host.tags}


def _admin_remove_host(label: str) -> Dict[str, Any]:
    return {"removed": default_admin_console().remove_host(label)}


def _admin_list_hosts() -> List[Dict[str, Any]]:
    return [
        {"label": h.label, "base_url": h.base_url, "tags": list(h.tags)}
        for h in default_admin_console().list_hosts()
    ]


def _admin_poll(labels: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    return [
        {
            "label": s.label, "base_url": s.base_url, "healthy": s.healthy,
            "latency_ms": s.latency_ms, "error": s.error,
            "sessions": s.sessions, "job_count": s.job_count,
        }
        for s in default_admin_console().poll_all(labels=labels)
    ]


def _admin_broadcast_execute(actions: List[Any],
                             labels: Optional[List[str]] = None,
                             ) -> List[Dict[str, Any]]:
    return default_admin_console().broadcast_execute(
        actions=actions, labels=labels,
    )


def _audit_log_list(event_type: Optional[str] = None,
                    host_id: Optional[str] = None,
                    limit: int = 200) -> List[Dict[str, Any]]:
    """Executor adapter: query the audit log."""
    from je_auto_control.utils.remote_desktop.audit_log import default_audit_log
    return default_audit_log().query(
        event_type=event_type, host_id=host_id, limit=int(limit),
    )


def _audit_log_verify() -> Dict[str, Any]:
    from je_auto_control.utils.remote_desktop.audit_log import default_audit_log
    result = default_audit_log().verify_chain()
    return {
        "ok": result.ok,
        "broken_at_id": result.broken_at_id,
        "total_rows": result.total_rows,
    }


def _audit_log_clear() -> Dict[str, Any]:
    from je_auto_control.utils.remote_desktop.audit_log import default_audit_log
    return {"deleted": default_audit_log().clear()}


def _inspector_recent(n: int = 60) -> List[Dict[str, Any]]:
    """Executor adapter: most recent N WebRTC stat samples."""
    from je_auto_control.utils.remote_desktop.webrtc_inspector import (
        default_webrtc_inspector,
    )
    return default_webrtc_inspector().recent(int(n))


def _inspector_summary() -> Dict[str, Any]:
    from je_auto_control.utils.remote_desktop.webrtc_inspector import (
        default_webrtc_inspector,
    )
    return default_webrtc_inspector().summary()


def _inspector_reset() -> Dict[str, Any]:
    from je_auto_control.utils.remote_desktop.webrtc_inspector import (
        default_webrtc_inspector,
    )
    return {"cleared": default_webrtc_inspector().reset()}


def _list_usb_devices() -> Dict[str, Any]:
    """Executor adapter: enumerate USB devices on this host."""
    from je_auto_control.utils.usb.usb_devices import list_usb_devices
    return list_usb_devices().to_dict()


def _diagnose() -> Dict[str, Any]:
    """Executor adapter: run system diagnostics and return the report."""
    from je_auto_control.utils.diagnostics.diagnostics import run_diagnostics
    return run_diagnostics().to_dict()


def _config_export() -> Dict[str, Any]:
    """Executor adapter: build the config bundle dict in-memory."""
    from je_auto_control.utils.config_bundle import export_config_bundle
    return export_config_bundle()


def _config_import(bundle: Dict[str, Any],
                   dry_run: bool = False) -> Dict[str, Any]:
    """Executor adapter: apply a config bundle dict to the user config root."""
    from je_auto_control.utils.config_bundle import import_config_bundle
    return import_config_bundle(bundle, dry_run=bool(dry_run)).to_dict()


def _usb_watch_start(poll_interval_s: float = 2.0) -> Dict[str, Any]:
    """Executor adapter: start the singleton USB hotplug watcher."""
    from je_auto_control.utils.usb.usb_watcher import default_usb_watcher
    watcher = default_usb_watcher()
    # poll_interval_s is consumed at watcher construction time only;
    # honor it on a fresh singleton, otherwise just (re-)start.
    watcher.start()
    return {"running": watcher.is_running, "interval_s": poll_interval_s}


def _usb_watch_stop() -> Dict[str, Any]:
    from je_auto_control.utils.usb.usb_watcher import default_usb_watcher
    watcher = default_usb_watcher()
    watcher.stop()
    return {"running": watcher.is_running}


def _usb_recent_events(since: int = 0,
                       limit: Optional[int] = None) -> List[Dict[str, Any]]:
    from je_auto_control.utils.usb.usb_watcher import default_usb_watcher
    return default_usb_watcher().recent_events(
        since=int(since),
        limit=int(limit) if limit is not None else None,
    )


# --- USB passthrough (Phase 2) — delegate to the shared command module --

def _usb_passthrough_enable(enabled: bool = True) -> Dict[str, Any]:
    from je_auto_control.utils.usb.passthrough import commands
    return commands.passthrough_enable(enabled)


def _usb_passthrough_status() -> Dict[str, Any]:
    from je_auto_control.utils.usb.passthrough import commands
    return commands.passthrough_status()


def _usb_acl_list() -> Dict[str, Any]:
    from je_auto_control.utils.usb.passthrough import commands
    return commands.acl_list()


def _usb_acl_add(vendor_id: str, product_id: str,
                 serial: Optional[str] = None, allow: bool = True,
                 prompt_on_open: bool = False, label: str = "") -> Dict[str, Any]:
    from je_auto_control.utils.usb.passthrough import commands
    return commands.acl_add(
        vendor_id, product_id, serial=serial, allow=allow,
        prompt_on_open=prompt_on_open, label=label,
    )


def _usb_acl_remove(vendor_id: str, product_id: str,
                    serial: Optional[str] = None) -> Dict[str, Any]:
    from je_auto_control.utils.usb.passthrough import commands
    return commands.acl_remove(vendor_id, product_id, serial=serial)


def _usb_acl_set_default(policy: str) -> Dict[str, Any]:
    from je_auto_control.utils.usb.passthrough import commands
    return commands.acl_set_default(policy)


def _usb_acl_export(path: str) -> Dict[str, Any]:
    from je_auto_control.utils.usb.passthrough import commands
    return commands.acl_export(path)


def _usb_acl_import(path: str, replace: bool = False) -> Dict[str, Any]:
    from je_auto_control.utils.usb.passthrough import commands
    return commands.acl_import(path, replace=replace)


def _usb_loopback_list() -> Dict[str, Any]:
    from je_auto_control.utils.usb.passthrough import commands
    return commands.loopback_list()


def _usb_loopback_open(vendor_id: str, product_id: str,
                       serial: Optional[str] = None) -> Dict[str, Any]:
    from je_auto_control.utils.usb.passthrough import commands
    return commands.loopback_open(vendor_id, product_id, serial=serial)


def _usb_remote_list() -> Dict[str, Any]:
    from je_auto_control.utils.usb.passthrough import commands
    return commands.remote_list()


def _usb_remote_open(vendor_id: str, product_id: str,
                     serial: Optional[str] = None) -> Dict[str, Any]:
    from je_auto_control.utils.usb.passthrough import commands
    return commands.remote_open(vendor_id, product_id, serial=serial)


def _ac_web_run(action: Optional[Dict[str, Any]] = None,
                **action_kwargs: Any) -> Any:
    """Bridge one WR_* action into the WebRunner executor (Phase 7.7).

    Accepts ``{"action": "WR_*", "params": {...}}`` either as a positional
    dict or unpacked kwargs so it composes with the existing AC_ schema.
    """
    from je_auto_control.utils.webrunner_bridge import run_webrunner_action
    payload = action if isinstance(action, dict) else action_kwargs
    return run_webrunner_action(payload)


def _ac_web_run_actions(actions: list) -> list:
    """Bridge a list of WR_* actions through the WebRunner executor."""
    from je_auto_control.utils.webrunner_bridge import run_webrunner_actions
    return run_webrunner_actions(actions)


def _ac_web_available() -> bool:
    """Return True when ``je_web_runner`` is importable."""
    from je_auto_control.utils.webrunner_bridge import is_webrunner_available
    return is_webrunner_available()


def _ac_web_list_commands() -> list:
    """Return every WR_* command the local WebRunner install exposes."""
    from je_auto_control.utils.webrunner_bridge import list_webrunner_commands
    return list_webrunner_commands()


def _ac_web_open(url: str, browser: str = "chrome",
                 **driver_kwargs: Any) -> Any:
    """Convenience executor: start a browser then navigate to ``url``."""
    from je_auto_control.utils.webrunner_bridge import web_open
    return web_open(url, browser=browser, **driver_kwargs)


def _ac_web_quit() -> Any:
    """Convenience executor: tear down WebRunner driver sessions."""
    from je_auto_control.utils.webrunner_bridge import web_quit
    return web_quit()


def _ac_web_screenshot(file_path: str) -> Any:
    """Convenience executor: save a screenshot of the active browser."""
    from je_auto_control.utils.webrunner_bridge import web_screenshot
    return web_screenshot(file_path)


def _ac_web_current_url() -> Any:
    """Convenience executor: return the active browser tab's URL."""
    from je_auto_control.utils.webrunner_bridge import web_current_url
    return web_current_url()


# --- Android via ADB (Phase 9.7) ---------------------------------------

_android_client_cache: Dict[Optional[str], Any] = {}


def _android_client(serial: Optional[str] = None,
                    adb_path: Optional[str] = None) -> Any:
    """Build (or return) a cached :class:`AdbClient` for ``serial``."""
    key = (serial, adb_path)
    cached = _android_client_cache.get(key)
    if cached is not None:
        return cached
    from je_auto_control.android import AdbClient
    cached = AdbClient(adb_path=adb_path, default_serial=serial)
    _android_client_cache[key] = cached
    return cached


def _ac_android_tap(x: int, y: int,
                    serial: Optional[str] = None,
                    adb_path: Optional[str] = None) -> None:
    """Send a single ``input tap`` to an Android device."""
    _android_client(serial, adb_path).tap(int(x), int(y))


def _ac_android_swipe(x1: int, y1: int, x2: int, y2: int,
                      duration_ms: int = 250,
                      serial: Optional[str] = None,
                      adb_path: Optional[str] = None) -> None:
    """Send a touch swipe via ``input swipe``."""
    _android_client(serial, adb_path).swipe(
        int(x1), int(y1), int(x2), int(y2),
        duration_ms=int(duration_ms),
    )


def _ac_android_key(key: str,
                    serial: Optional[str] = None,
                    adb_path: Optional[str] = None) -> None:
    """Send a keycode (``KEYCODE_HOME`` etc.) via ``input keyevent``."""
    _android_client(serial, adb_path).key_event(key)


def _ac_android_text(text: str,
                     serial: Optional[str] = None,
                     adb_path: Optional[str] = None) -> None:
    """Type a string via ``input text``."""
    _android_client(serial, adb_path).text(text)


def _ac_android_screenshot(file_path: str,
                           serial: Optional[str] = None,
                           adb_path: Optional[str] = None) -> str:
    """Capture the live Android screen and save it as PNG at ``file_path``."""
    path = _android_client(serial, adb_path).save_screenshot(file_path)
    return str(path)


def _ac_android_list_devices(adb_path: Optional[str] = None) -> list:
    """Return ``{serial, state, model, …}`` for every adb-attached device."""
    devices = _android_client(None, adb_path).list_devices()
    return [
        {"serial": d.serial, "state": d.state,
         "model": d.model, "product": d.product,
         "transport_id": d.transport_id}
        for d in devices
    ]


def _ac_android_shell(command: str,
                      serial: Optional[str] = None,
                      adb_path: Optional[str] = None) -> str:
    """Run an ``adb shell`` command and return its stdout."""
    return _android_client(serial, adb_path).shell(command)


def _ac_android_find_element(text: Optional[str] = None,
                              resource_id: Optional[str] = None,
                              description: Optional[str] = None,
                              class_name: Optional[str] = None,
                              timeout_s: float = 5.0,
                              serial: Optional[str] = None,
                              ) -> Dict[str, int]:
    """Find an Android widget via uiautomator2; return its bounding rect."""
    from je_auto_control.android import (
        UIAutomatorDevice, find_element,
    )
    device = UIAutomatorDevice(serial=serial)
    x1, y1, x2, y2 = find_element(
        text=text, resource_id=resource_id, description=description,
        class_name=class_name, timeout_s=float(timeout_s), device=device,
    )
    return {"x1": x1, "y1": y1, "x2": x2, "y2": y2}


def _ac_android_click_element(text: Optional[str] = None,
                               resource_id: Optional[str] = None,
                               description: Optional[str] = None,
                               class_name: Optional[str] = None,
                               timeout_s: float = 5.0,
                               serial: Optional[str] = None,
                               ) -> Dict[str, int]:
    """Tap the first widget matching the selectors; return click centre."""
    from je_auto_control.android import (
        UIAutomatorDevice, click_element,
    )
    device = UIAutomatorDevice(serial=serial)
    cx, cy = click_element(
        text=text, resource_id=resource_id, description=description,
        class_name=class_name, timeout_s=float(timeout_s), device=device,
    )
    return {"x": cx, "y": cy}


def _ac_android_dump_hierarchy(serial: Optional[str] = None) -> str:
    """Return the device's widget tree as an XML string."""
    from je_auto_control.android import UIAutomatorDevice, dump_hierarchy
    device = UIAutomatorDevice(serial=serial)
    return dump_hierarchy(device=device)


# === iOS executor adapters (WebDriverAgent / facebook-wda) ==================

def _ios_device(url: Optional[str]) -> Any:
    from je_auto_control.ios import IOSDevice
    return IOSDevice(url=url)


def _ac_ios_tap(x: int, y: int, url: Optional[str] = None) -> Dict[str, int]:
    from je_auto_control.ios import tap
    tap(int(x), int(y), device=_ios_device(url))
    return {"x": int(x), "y": int(y)}


def _ac_ios_swipe(x1: int, y1: int, x2: int, y2: int,
                  duration_s: float = 0.5,
                  url: Optional[str] = None) -> Dict[str, Any]:
    from je_auto_control.ios import swipe
    swipe(int(x1), int(y1), int(x2), int(y2),
          duration_s=float(duration_s), device=_ios_device(url))
    return {"x1": int(x1), "y1": int(y1),
            "x2": int(x2), "y2": int(y2)}


def _ac_ios_type(text: str, url: Optional[str] = None) -> str:
    from je_auto_control.ios import type_text
    type_text(text, device=_ios_device(url))
    return text


def _ac_ios_screenshot(file_path: str,
                       url: Optional[str] = None) -> str:
    from je_auto_control.ios import screenshot
    written = screenshot(file_path, device=_ios_device(url))
    if written is None:
        raise RuntimeError("screenshot returned no path")
    return written


def _ac_ios_find_element(name: Optional[str] = None,
                          class_name: Optional[str] = None,
                          predicate: Optional[str] = None,
                          timeout_s: float = 5.0,
                          url: Optional[str] = None) -> Dict[str, int]:
    from je_auto_control.ios import find_element
    x1, y1, x2, y2 = find_element(
        name=name, class_name=class_name, predicate=predicate,
        timeout_s=float(timeout_s), device=_ios_device(url),
    )
    return {"x1": x1, "y1": y1, "x2": x2, "y2": y2}


def _ac_ios_click_element(name: Optional[str] = None,
                           class_name: Optional[str] = None,
                           predicate: Optional[str] = None,
                           timeout_s: float = 5.0,
                           url: Optional[str] = None) -> Dict[str, int]:
    from je_auto_control.ios import click_element
    cx, cy = click_element(
        name=name, class_name=class_name, predicate=predicate,
        timeout_s=float(timeout_s), device=_ios_device(url),
    )
    return {"x": cx, "y": cy}


def _ac_ios_dump_source(url: Optional[str] = None) -> str:
    from je_auto_control.ios import dump_source
    return dump_source(device=_ios_device(url))


def _llm_plan_for_executor(description: str,
                           examples: Optional[list] = None,
                           model: Optional[str] = None,
                           max_tokens: int = 2048) -> list:
    """Executor adapter: plan without executing, using current command set."""
    return llm_plan_actions(
        description,
        known_commands=executor.known_commands(),
        examples=examples,
        model=model,
        max_tokens=int(max_tokens),
    )


def _llm_run_for_executor(description: str,
                          examples: Optional[list] = None,
                          model: Optional[str] = None,
                          max_tokens: int = 2048) -> Dict[str, Any]:
    """Executor adapter: plan and execute against the global executor."""
    return llm_run_from_description(
        description,
        executor=executor,
        examples=examples,
        model=model,
        max_tokens=int(max_tokens),
    )


def _ocr_read_region_as_dicts(region: Optional[List[int]] = None,
                              lang: str = "eng",
                              min_confidence: float = 60.0) -> List[dict]:
    """Executor adapter: dump OCR hits in a region as JSON-friendly dicts."""
    return [
        {
            "text": match.text, "x": match.x, "y": match.y,
            "width": match.width, "height": match.height,
            "confidence": match.confidence,
        }
        for match in ocr_read_text_in_region(
            region=region, lang=lang, min_confidence=float(min_confidence),
        )
    ]


def _ocr_find_regex_as_dicts(pattern: str,
                             lang: str = "eng",
                             region: Optional[List[int]] = None,
                             min_confidence: float = 60.0,
                             flags: int = 0) -> List[dict]:
    """Executor adapter: regex OCR search returning JSON-friendly dicts."""
    return [
        {
            "text": match.text, "x": match.x, "y": match.y,
            "width": match.width, "height": match.height,
            "confidence": match.confidence,
        }
        for match in ocr_find_text_regex(
            pattern, lang=lang, region=region,
            min_confidence=float(min_confidence), flags=int(flags),
        )
    ]


def _email_trigger_add(host: str, username: str, password: str,
                       script_path: str,
                       port: Optional[int] = None,
                       use_ssl: bool = True,
                       mailbox: str = "INBOX",
                       search_criteria: str = "UNSEEN",
                       mark_seen: bool = True,
                       poll_seconds: float = 60.0) -> Dict[str, Any]:
    """Executor adapter: register an IMAP poll trigger."""
    from je_auto_control.utils.triggers.email_trigger import (
        default_email_trigger_watcher,
    )
    trigger = default_email_trigger_watcher.add(
        host=host, username=username, password=password,
        script_path=script_path, port=port, use_ssl=bool(use_ssl),
        mailbox=mailbox, search_criteria=search_criteria,
        mark_seen=bool(mark_seen), poll_seconds=float(poll_seconds),
    )
    return {
        "id": trigger.trigger_id, "host": trigger.host,
        "username": trigger.username, "mailbox": trigger.mailbox,
        "search_criteria": trigger.search_criteria,
        "poll_seconds": trigger.poll_seconds,
    }


def _email_trigger_remove(trigger_id: str) -> Dict[str, Any]:
    from je_auto_control.utils.triggers.email_trigger import (
        default_email_trigger_watcher,
    )
    return {"removed": default_email_trigger_watcher.remove(trigger_id)}


def _email_trigger_list() -> List[Dict[str, Any]]:
    from je_auto_control.utils.triggers.email_trigger import (
        default_email_trigger_watcher,
    )
    rows: List[Dict[str, Any]] = []
    for trigger in default_email_trigger_watcher.list_triggers():
        rows.append({
            "id": trigger.trigger_id, "host": trigger.host,
            "username": trigger.username, "mailbox": trigger.mailbox,
            "script_path": trigger.script_path,
            "search_criteria": trigger.search_criteria,
            "poll_seconds": trigger.poll_seconds,
            "enabled": trigger.enabled, "fired": trigger.fired,
            "last_error": trigger.last_error,
        })
    return rows


def _email_trigger_start() -> Dict[str, Any]:
    from je_auto_control.utils.triggers.email_trigger import (
        default_email_trigger_watcher,
    )
    default_email_trigger_watcher.start()
    return {"running": default_email_trigger_watcher.is_running}


def _email_trigger_stop() -> Dict[str, Any]:
    from je_auto_control.utils.triggers.email_trigger import (
        default_email_trigger_watcher,
    )
    default_email_trigger_watcher.stop()
    return {"running": default_email_trigger_watcher.is_running}


def _email_trigger_poll_once() -> Dict[str, Any]:
    from je_auto_control.utils.triggers.email_trigger import (
        default_email_trigger_watcher,
    )
    return {"fired": default_email_trigger_watcher.poll_once()}


def _webhook_start(host: str = "127.0.0.1", port: int = 0) -> Dict[str, Any]:
    """Executor adapter: start the webhook HTTP server."""
    from je_auto_control.utils.triggers.webhook_server import (
        default_webhook_server,
    )
    bound_host, bound_port = default_webhook_server.start(host, int(port))
    return {"host": bound_host, "port": bound_port}


def _webhook_stop() -> Dict[str, Any]:
    from je_auto_control.utils.triggers.webhook_server import (
        default_webhook_server,
    )
    default_webhook_server.stop()
    return {"running": default_webhook_server.is_running}


def _webhook_add(path: str, script_path: str,
                 methods: Optional[List[str]] = None,
                 token: Optional[str] = None) -> Dict[str, Any]:
    from je_auto_control.utils.triggers.webhook_server import (
        default_webhook_server,
    )
    trigger = default_webhook_server.add(
        path=path, script_path=script_path,
        methods=methods, token=token,
    )
    return {
        "id": trigger.webhook_id, "path": trigger.path,
        "methods": list(trigger.methods),
        "script_path": trigger.script_path,
        "has_token": bool(trigger.token),
    }


def _webhook_remove(webhook_id: str) -> Dict[str, Any]:
    from je_auto_control.utils.triggers.webhook_server import (
        default_webhook_server,
    )
    return {"removed": default_webhook_server.remove(webhook_id)}


def _webhook_list() -> List[Dict[str, Any]]:
    from je_auto_control.utils.triggers.webhook_server import (
        default_webhook_server,
    )
    rows: List[Dict[str, Any]] = []
    for trigger in default_webhook_server.list_webhooks():
        rows.append({
            "id": trigger.webhook_id, "path": trigger.path,
            "methods": list(trigger.methods),
            "script_path": trigger.script_path,
            "enabled": trigger.enabled, "fired": trigger.fired,
            "has_token": bool(trigger.token),
        })
    return rows


def _webhook_status() -> Dict[str, Any]:
    from je_auto_control.utils.triggers.webhook_server import (
        default_webhook_server,
    )
    bound = default_webhook_server.bound_address
    return {
        "running": default_webhook_server.is_running,
        "host": bound[0] if bound else None,
        "port": bound[1] if bound else None,
        "registered": len(default_webhook_server.list_webhooks()),
    }


def _secret_initialize(passphrase: str) -> Dict[str, Any]:
    """Executor adapter: create a fresh vault under ``passphrase``."""
    default_secret_manager.initialize(passphrase)
    return {
        "initialized": True,
        "path": str(default_secret_manager.path),
        "unlocked": default_secret_manager.is_unlocked,
    }


def _secret_unlock(passphrase: str) -> Dict[str, Any]:
    return {"unlocked": default_secret_manager.unlock(passphrase)}


def _secret_lock() -> Dict[str, Any]:
    default_secret_manager.lock()
    return {"unlocked": default_secret_manager.is_unlocked}


def _secret_set(name: str, value: str) -> Dict[str, Any]:
    default_secret_manager.set(name, value)
    return {"name": name, "saved": True}


def _secret_remove(name: str) -> Dict[str, Any]:
    return {"name": name, "removed": default_secret_manager.remove(name)}


def _secret_list() -> List[str]:
    return default_secret_manager.list_names()


def _secret_status() -> Dict[str, Any]:
    return {
        "path": str(default_secret_manager.path),
        "initialized": default_secret_manager.is_initialized,
        "unlocked": default_secret_manager.is_unlocked,
    }


def _profiler_stats_as_dicts(limit: Optional[int] = None) -> List[dict]:
    """Executor adapter: dump profiler stats as JSON-friendly dicts."""
    rows = default_profiler.stats()
    if limit is not None:
        rows = rows[: max(0, int(limit))]
    return [row.to_dict() for row in rows]


def _profiler_hot_spots_as_dicts(limit: int = 10) -> List[dict]:
    """Executor adapter: top N actions by total time, as dicts."""
    return [row.to_dict() for row in default_profiler.hot_spots(int(limit))]


def _profiler_enable() -> Dict[str, Any]:
    default_profiler.enable()
    return {"enabled": default_profiler.enabled}


def _profiler_disable() -> Dict[str, Any]:
    default_profiler.disable()
    return {"enabled": default_profiler.enabled}


def _profiler_reset() -> Dict[str, Any]:
    default_profiler.reset()
    return {"reset": True}


def _history_list_as_dicts(limit: int = 100,
                           source_type: Optional[str] = None) -> List[dict]:
    """Executor adapter: list run history as plain dicts (JSON-friendly)."""
    rows = default_history_store.list_runs(
        limit=int(limit), source_type=source_type,
    )
    return [
        {
            "id": r.id, "source_type": r.source_type,
            "source_id": r.source_id, "script_path": r.script_path,
            "started_at": r.started_at, "finished_at": r.finished_at,
            "status": r.status, "error_text": r.error_text,
            "duration_seconds": r.duration_seconds,
        }
        for r in rows
    ]


_EXECUTOR_METRIC_CACHE: Dict[str, Any] = {}


def _executor_metrics():
    """Lazily register the action-executor Counter + Histogram (Phase 10.1)."""
    if "calls" in _EXECUTOR_METRIC_CACHE:
        return _EXECUTOR_METRIC_CACHE
    from je_auto_control.utils.observability import (
        Counter, Histogram, default_registry,
    )
    registry = default_registry()
    _EXECUTOR_METRIC_CACHE["calls"] = registry.register(Counter(
        "autocontrol_action_calls_total",
        "Number of AC_* actions executed, partitioned by name + outcome.",
        label_names=("action", "outcome"),
    ))
    _EXECUTOR_METRIC_CACHE["duration"] = registry.register(Histogram(
        "autocontrol_action_duration_seconds",
        "Wall-clock duration of each AC_* action call.",
        label_names=("action",),
    ))
    return _EXECUTOR_METRIC_CACHE


def _observe_executor_metrics(action: str, started_at: float,
                              *, error: Optional[BaseException]) -> None:
    """Emit Counter + Histogram samples for one action execution."""
    import time as _time
    try:
        metrics = _executor_metrics()
    except (ImportError, ValueError, RuntimeError):
        return
    duration = max(0.0, _time.monotonic() - started_at)
    outcome = "error" if error is not None else "ok"
    try:
        metrics["calls"].inc(labels={"action": action, "outcome": outcome})
        metrics["duration"].observe(duration, labels={"action": action})
    except ValueError:
        # Defensive: if the label set drifts (e.g. tests reset the registry)
        # we'd rather lose a sample than crash the executor.
        pass


def _human_move(x: int, y: int, duration_s: float = 0.4, curve: float = 0.2,
                overshoot: float = 0.0, jitter: float = 1.0,
                seed: Optional[int] = None) -> Dict[str, Any]:
    """Executor adapter: move the mouse to (x, y) along a human-like path."""
    from je_auto_control.utils.humanize.motion import (
        HumanizedMotion, move_mouse_humanized,
    )
    motion = HumanizedMotion(curve=float(curve), overshoot=float(overshoot),
                             jitter=float(jitter), seed=seed)
    path = move_mouse_humanized(int(x), int(y),
                                duration_s=float(duration_s), motion=motion)
    return {"x": int(x), "y": int(y), "waypoints": len(path)}


def _human_type(text: str, base_delay: float = 0.05, jitter: float = 0.04,
                pause_chance: float = 0.0,
                seed: Optional[int] = None) -> Dict[str, Any]:
    """Executor adapter: type text with humanized inter-key delays."""
    from je_auto_control.utils.humanize.typing import type_text_humanized
    delays = type_text_humanized(
        str(text), base_delay=float(base_delay), jitter=float(jitter),
        pause_chance=float(pause_chance), seed=seed,
    )
    return {"chars": len(str(text)), "total_delay_s": round(sum(delays), 3)}


def _sign_action_file(path: str, key: Optional[str] = None) -> Dict[str, Any]:
    """Executor adapter: write an HMAC-SHA256 signature sidecar for a file."""
    from je_auto_control.utils.action_signing import sign_action_file
    return {"signature_path": sign_action_file(path, key)}


def _verify_action_file(path: str, key: Optional[str] = None,
                        raise_on_fail: bool = False) -> Dict[str, Any]:
    """Executor adapter: verify an action file against its signature sidecar."""
    from je_auto_control.utils.action_signing import verify_action_file
    return verify_action_file(
        path, key, raise_on_fail=bool(raise_on_fail),
    ).to_dict()


def _encrypt_action_file(path: str, key: Optional[str] = None) -> Dict[str, Any]:
    """Executor adapter: Fernet-encrypt an action file to <path>.enc."""
    from je_auto_control.utils.action_signing import encrypt_action_file
    return {"encrypted_path": encrypt_action_file(path, key)}


def _decrypt_action_file(enc_path: str, key: Optional[str] = None,
                         output_path: Optional[str] = None) -> Dict[str, Any]:
    """Executor adapter: decrypt a Fernet-encrypted action file."""
    from je_auto_control.utils.action_signing import decrypt_action_file
    return {"output_path": decrypt_action_file(enc_path, key, output_path)}


def _annotate_screenshot(source: str,
                         annotations: Union[List[Dict[str, Any]], str],
                         output_path: str) -> Dict[str, Any]:
    """Executor adapter: draw annotations onto a screenshot and save it.

    ``annotations`` may be a list of annotation dicts, or a JSON string of
    the same (so the visual builder can pass it through a text field).
    """
    import json
    from je_auto_control.utils.annotate import annotate_screenshot
    if isinstance(annotations, str):
        annotations = json.loads(annotations) if annotations.strip() else []
    return {"output_path": annotate_screenshot(
        source, annotations, output_path)}


def _notify(title: str, message: str = "") -> Dict[str, Any]:
    """Executor adapter: show a cross-platform desktop notification."""
    from je_auto_control.utils.notify import notify
    return notify(str(title), str(message)).to_dict()


def _move_to_trash(path: str) -> Dict[str, Any]:
    """Executor adapter: move a file to the OS recycle bin (recoverable)."""
    from je_auto_control.utils.trash import move_to_trash
    return {"trashed": move_to_trash(path)}


def _read_qr(region: Optional[Union[List[int], str]] = None) -> Dict[str, Any]:
    """Executor adapter: decode QR codes in a screen region.

    ``region`` is ``[x1, y1, x2, y2]`` (or a JSON string for the builder);
    omit it to scan the whole screen.
    """
    import json
    import os
    import tempfile
    from je_auto_control.utils.qr import read_qr_codes
    from je_auto_control.wrapper.auto_control_screen import screenshot
    if isinstance(region, str):
        region = json.loads(region) if region.strip() else None
    handle, tmp = tempfile.mkstemp(prefix="qr_", suffix=".png")
    os.close(handle)
    try:
        screenshot(tmp, screen_region=region)
        return {"codes": read_qr_codes(tmp)}
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _scroll_to_find(target: str, kind: str = "image", direction: str = "down",
                    max_scrolls: int = 10,
                    scroll_amount: int = 3) -> Dict[str, Any]:
    """Executor adapter: scroll until a target image / text is visible."""
    from je_auto_control.utils.scroll_find import scroll_until_visible
    return scroll_until_visible(
        target, kind=kind, direction=direction,
        max_scrolls=int(max_scrolls), scroll_amount=int(scroll_amount),
    )


def _capture_window(title: str, output_path: str) -> Dict[str, Any]:
    """Executor adapter: screenshot the window matching ``title``."""
    from je_auto_control.utils.window_capture import capture_window
    return {"output_path": capture_window(title, output_path)}


def _snap_window(title: str, position: str = "left") -> Dict[str, Any]:
    """Executor adapter: snap a window to a screen region."""
    from je_auto_control.utils.window_capture import snap_window
    return {"moved": snap_window(title, position)}


def _arrange_grid(titles: Any, rows: Any = None, cols: Any = None,
                  gap: Any = 0) -> Dict[str, Any]:
    """Executor adapter: tile a list of window titles into a grid."""
    import json
    from je_auto_control.utils.window_capture import arrange_grid
    if isinstance(titles, str):
        titles = json.loads(titles)
    moved = arrange_grid(list(titles),
                         rows=int(rows) if rows is not None else None,
                         cols=int(cols) if cols is not None else None,
                         gap=int(gap))
    return {"moved": moved, "count": len(list(titles))}


def _arrange_cascade(titles: Any, offset: Any = 30) -> Dict[str, Any]:
    """Executor adapter: cascade a list of window titles diagonally."""
    import json
    from je_auto_control.utils.window_capture import arrange_cascade
    if isinstance(titles, str):
        titles = json.loads(titles)
    titles = list(titles)
    return {"moved": arrange_cascade(titles, offset=int(offset)),
            "count": len(titles)}


def _save_window_layout(path: Optional[str] = None) -> Dict[str, Any]:
    """Executor adapter: snapshot every window's geometry (optionally to file)."""
    from je_auto_control.utils.window_capture import save_window_layout
    layout = save_window_layout(path)
    return {"count": len(layout), "path": path, "layout": layout}


def _restore_window_layout(layout: Union[List[Dict[str, Any]], str]
                           ) -> Dict[str, Any]:
    """Executor adapter: move windows back to a saved layout (list or path)."""
    from je_auto_control.utils.window_capture import restore_window_layout
    return {"restored": restore_window_layout(layout)}


def _region_color_stats(region: Optional[Union[List[int], str]] = None,
                        buckets: int = 8) -> Dict[str, Any]:
    """Executor adapter: average + dominant colour of a screen region.

    ``region`` is ``[x1, y1, x2, y2]`` (or a JSON string of it for the
    visual builder); omit it to analyse the whole screen.
    """
    import json
    import os
    import tempfile
    from je_auto_control.utils.color_stats import region_color_stats
    from je_auto_control.wrapper.auto_control_screen import screenshot
    if isinstance(region, str):
        region = json.loads(region) if region.strip() else None
    handle, tmp = tempfile.mkstemp(prefix="colorstats_", suffix=".png")
    os.close(handle)
    try:
        screenshot(tmp, screen_region=region)
        return region_color_stats(tmp, buckets=int(buckets)).to_dict()
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _generate_code(source: Any, output: Optional[str] = None,
                   target: str = "pytest", name: str = "recorded_flow",
                   style: str = "calls") -> str:
    """Render an action list/file as code, optionally writing a file."""
    from je_auto_control.utils.codegen.codegen import (
        generate_code, generate_code_file,
    )
    if output:
        return generate_code_file(source, output, target=target,
                                  name=name, style=style)
    actions = source if isinstance(source, list) else read_action_json(source)
    return generate_code(actions, target=target, name=name, style=style)


def _send_email(message: Any, smtp: Any) -> Dict[str, Any]:
    """Adapter: send an email via SMTP (message/smtp config dicts)."""
    from je_auto_control.utils.email_send.email_sender import send_email
    return send_email(message, smtp)


def _assert_pdf_text(path: str, text: str, present: bool = True,
                     page: Any = None, case_sensitive: bool = True,
                     raise_on_fail: bool = True) -> Dict[str, Any]:
    """Adapter: assert text is present/absent in a PDF document."""
    from je_auto_control.utils.pdf.pdf_reader import assert_pdf_text
    return assert_pdf_text(path, text, present=bool(present), page=page,
                           case_sensitive=bool(case_sensitive),
                           raise_on_fail=bool(raise_on_fail))


def _take_golden(path: str, region: Optional[List[int]] = None) -> str:
    """Adapter: capture and save a golden/baseline image."""
    from je_auto_control.utils.visual_regression import take_golden
    return str(take_golden(path, region=region))


def _assert_visual(golden_path: str, region: Optional[List[int]] = None,
                   tolerance: float = 0.0, per_pixel_threshold: int = 16,
                   diff_path: Optional[str] = None,
                   create_if_missing: bool = True,
                   raise_on_fail: bool = True) -> Dict[str, Any]:
    """Adapter: compare the screen to a golden image (first run creates it)."""
    import os
    from je_auto_control.utils.exception.exceptions import (
        AutoControlAssertionException,
    )
    from je_auto_control.utils.visual_regression import (
        compare_to_golden, take_golden,
    )
    if create_if_missing and not os.path.exists(
            os.path.expanduser(str(golden_path))):
        take_golden(golden_path, region=region)
        return {"created": True, "matched": True, "golden": str(golden_path)}
    result = compare_to_golden(
        golden_path, region=region, tolerance=float(tolerance),
        per_pixel_threshold=int(per_pixel_threshold))
    if diff_path and result.diff_image is not None:
        result.write_diff(diff_path)
    data = {"matched": result.matched, "diff_pct": result.diff_pct,
            "differing_pixels": result.differing_pixels,
            "total_pixels": result.total_pixels,
            "tolerance_pct": result.tolerance_pct}
    if not result.matched and raise_on_fail:
        raise AutoControlAssertionException(result.summary)
    return data


def _run_state_machine(spec: Any) -> Dict[str, Any]:
    """Adapter: run a finite-state-machine spec through the executor."""
    from je_auto_control.utils.state_machine import run_state_machine
    return run_state_machine(spec)


def _control_get_value(name: Optional[str] = None, role: Optional[str] = None,
                       app_name: Optional[str] = None,
                       automation_id: Optional[str] = None) -> Optional[str]:
    """Adapter: read a native control's value via the accessibility backend."""
    from je_auto_control.utils.accessibility import control_get_value
    return control_get_value(name=name, role=role, app_name=app_name,
                             automation_id=automation_id)


def _control_set_value(value: str, name: Optional[str] = None,
                       role: Optional[str] = None, app_name: Optional[str] = None,
                       automation_id: Optional[str] = None) -> bool:
    """Adapter: set a native control's value via the accessibility backend."""
    from je_auto_control.utils.accessibility import control_set_value
    return control_set_value(value, name=name, role=role, app_name=app_name,
                             automation_id=automation_id)


def _control_invoke(name: Optional[str] = None, role: Optional[str] = None,
                    app_name: Optional[str] = None,
                    automation_id: Optional[str] = None) -> bool:
    """Adapter: invoke a native control (e.g. press a button)."""
    from je_auto_control.utils.accessibility import control_invoke
    return control_invoke(name=name, role=role, app_name=app_name,
                          automation_id=automation_id)


def _control_toggle(name: Optional[str] = None, role: Optional[str] = None,
                    app_name: Optional[str] = None,
                    automation_id: Optional[str] = None) -> bool:
    """Adapter: toggle a native control (e.g. a checkbox)."""
    from je_auto_control.utils.accessibility import control_toggle
    return control_toggle(name=name, role=role, app_name=app_name,
                          automation_id=automation_id)


def _expand_control(name: Optional[str] = None, role: Optional[str] = None,
                    app_name: Optional[str] = None,
                    automation_id: Optional[str] = None) -> bool:
    """Adapter: expand a tree node / combobox (ExpandCollapsePattern)."""
    from je_auto_control.utils.control_patterns import expand_control
    return expand_control(name=name, role=role, app_name=app_name,
                          automation_id=automation_id)


def _collapse_control(name: Optional[str] = None, role: Optional[str] = None,
                      app_name: Optional[str] = None,
                      automation_id: Optional[str] = None) -> bool:
    """Adapter: collapse a tree node / combobox (ExpandCollapsePattern)."""
    from je_auto_control.utils.control_patterns import collapse_control
    return collapse_control(name=name, role=role, app_name=app_name,
                            automation_id=automation_id)


def _control_expand_state(name: Optional[str] = None, role: Optional[str] = None,
                          app_name: Optional[str] = None,
                          automation_id: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: the expand/collapse state of a control."""
    from je_auto_control.utils.control_patterns import control_expand_state
    return {"state": control_expand_state(name=name, role=role, app_name=app_name,
                                          automation_id=automation_id)}


def _select_control_item(name: Optional[str] = None, role: Optional[str] = None,
                         app_name: Optional[str] = None,
                         automation_id: Optional[str] = None) -> bool:
    """Adapter: select a list / tree / tab item (SelectionItemPattern)."""
    from je_auto_control.utils.control_patterns import select_control_item
    return select_control_item(name=name, role=role, app_name=app_name,
                               automation_id=automation_id)


def _control_range(name: Optional[str] = None, role: Optional[str] = None,
                   app_name: Optional[str] = None,
                   automation_id: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: read a slider / progress range (RangeValuePattern)."""
    from je_auto_control.utils.control_patterns import control_range
    info = control_range(name=name, role=role, app_name=app_name,
                         automation_id=automation_id)
    return {"found": info is not None, "range": info}


def _set_control_range(value: Any, name: Optional[str] = None,
                       role: Optional[str] = None, app_name: Optional[str] = None,
                       automation_id: Optional[str] = None) -> bool:
    """Adapter: set a slider / progress / spinner value (RangeValuePattern)."""
    from je_auto_control.utils.control_patterns import set_control_range
    return set_control_range(float(value), name=name, role=role,
                             app_name=app_name, automation_id=automation_id)


def _scroll_control_into_view(name: Optional[str] = None, role: Optional[str] = None,
                              app_name: Optional[str] = None,
                              automation_id: Optional[str] = None) -> bool:
    """Adapter: scroll a control into view (ScrollItemPattern)."""
    from je_auto_control.utils.control_patterns import scroll_control_into_view
    return scroll_control_into_view(name=name, role=role, app_name=app_name,
                                    automation_id=automation_id)


def _realize_item(item_name: str, by: str = "name",
                  container_name: Optional[str] = None,
                  container_role: Optional[str] = None,
                  app_name: Optional[str] = None,
                  automation_id: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: find + realize a virtualized list/grid item (VirtualizedItem)."""
    from je_auto_control.utils.virtualized import realize_item
    element = realize_item(item_name, by=str(by), container_name=container_name,
                           container_role=container_role, app_name=app_name,
                           automation_id=automation_id)
    return {"found": element is not None,
            "element": element.to_dict() if element else None}


def _get_element_properties(name: Optional[str] = None, role: Optional[str] = None,
                            app_name: Optional[str] = None,
                            automation_id: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: read rich UIA properties (enabled/offscreen/help/status/keys)."""
    from je_auto_control.utils.ax_props import get_element_properties
    props = get_element_properties(name=name, role=role, app_name=app_name,
                                   automation_id=automation_id)
    return {"found": props is not None, "properties": props}


def _table_headers(name: Optional[str] = None, role: Optional[str] = None,
                   app_name: Optional[str] = None,
                   automation_id: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: a table's row/column header labels (TablePattern)."""
    from je_auto_control.utils.table_pattern import table_headers
    headers = table_headers(name=name, role=role, app_name=app_name,
                            automation_id=automation_id)
    return {"found": headers is not None, "headers": headers}


def _table_cell(row: Any, column: Any, name: Optional[str] = None,
                role: Optional[str] = None, app_name: Optional[str] = None,
                automation_id: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: the cell at (row, column) with its span (GridItemPattern)."""
    from je_auto_control.utils.table_pattern import table_cell
    cell = table_cell(int(row), int(column), name=name, role=role,
                      app_name=app_name, automation_id=automation_id)
    return {"found": cell is not None, "cell": cell}


def _cell_by_header(row: Any, column_header: str, name: Optional[str] = None,
                    role: Optional[str] = None, app_name: Optional[str] = None,
                    automation_id: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: read the cell at (row, named column) — assert by header."""
    from je_auto_control.utils.table_pattern import cell_by_header
    value = cell_by_header(int(row), str(column_header), name=name, role=role,
                           app_name=app_name, automation_id=automation_id)
    return {"found": value is not None, "value": value}


def _move_element(x: Any, y: Any, name: Optional[str] = None,
                  role: Optional[str] = None, app_name: Optional[str] = None,
                  automation_id: Optional[str] = None) -> bool:
    """Adapter: move a UIA element to (x, y) (TransformPattern)."""
    from je_auto_control.utils.transform_window import move_element
    return move_element(float(x), float(y), name=name, role=role,
                        app_name=app_name, automation_id=automation_id)


def _resize_element(width: Any, height: Any, name: Optional[str] = None,
                    role: Optional[str] = None, app_name: Optional[str] = None,
                    automation_id: Optional[str] = None) -> bool:
    """Adapter: resize a UIA element (TransformPattern)."""
    from je_auto_control.utils.transform_window import resize_element
    return resize_element(float(width), float(height), name=name, role=role,
                          app_name=app_name, automation_id=automation_id)


def _set_window_state(state: str, name: Optional[str] = None,
                      role: Optional[str] = None, app_name: Optional[str] = None,
                      automation_id: Optional[str] = None) -> bool:
    """Adapter: set a window's visual state normal/maximized/minimized."""
    from je_auto_control.utils.transform_window import set_window_state
    return set_window_state(str(state), name=name, role=role, app_name=app_name,
                            automation_id=automation_id)


def _window_interaction_state(name: Optional[str] = None,
                              role: Optional[str] = None,
                              app_name: Optional[str] = None,
                              automation_id: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: a window's interaction state (ready/blocked/not_responding)."""
    from je_auto_control.utils.transform_window import window_interaction_state
    return {"state": window_interaction_state(name=name, role=role,
                                              app_name=app_name,
                                              automation_id=automation_id)}


def _legacy_info(name: Optional[str] = None, role: Optional[str] = None,
                 app_name: Optional[str] = None,
                 automation_id: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: MSAA IAccessible info of an old control (LegacyIAccessible)."""
    from je_auto_control.utils.legacy_accessible import legacy_info
    info = legacy_info(name=name, role=role, app_name=app_name,
                       automation_id=automation_id)
    return {"found": info is not None, "info": info}


def _legacy_default_action(name: Optional[str] = None, role: Optional[str] = None,
                           app_name: Optional[str] = None,
                           automation_id: Optional[str] = None) -> bool:
    """Adapter: fire an old control's MSAA default action (Value/Invoke fallback)."""
    from je_auto_control.utils.legacy_accessible import legacy_default_action
    return legacy_default_action(name=name, role=role, app_name=app_name,
                                 automation_id=automation_id)


def _get_selection(name: Optional[str] = None, role: Optional[str] = None,
                   app_name: Optional[str] = None,
                   automation_id: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: a container's selection state (SelectionPattern)."""
    from je_auto_control.utils.selection_view import get_selection
    selection = get_selection(name=name, role=role, app_name=app_name,
                              automation_id=automation_id)
    return {"found": selection is not None, "selection": selection}


def _list_views(name: Optional[str] = None, role: Optional[str] = None,
                app_name: Optional[str] = None,
                automation_id: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: a control's selectable views (MultipleViewPattern)."""
    from je_auto_control.utils.selection_view import list_views
    views = list_views(name=name, role=role, app_name=app_name,
                       automation_id=automation_id)
    return {"found": views is not None, "views": views}


def _set_view(view: str, name: Optional[str] = None, role: Optional[str] = None,
              app_name: Optional[str] = None,
              automation_id: Optional[str] = None) -> bool:
    """Adapter: switch a control to a named view (MultipleViewPattern)."""
    from je_auto_control.utils.selection_view import set_view
    return set_view(str(view), name=name, role=role, app_name=app_name,
                    automation_id=automation_id)


def _wait_for_focus_change(timeout: Any = 5.0) -> Dict[str, Any]:
    """Adapter: block until the keyboard focus moves (UIA focus event)."""
    from je_auto_control.utils.ax_events import wait_for_focus_change
    element = wait_for_focus_change(timeout=float(timeout))
    return {"changed": element is not None, "element": element}


def _plan_open(target: str, verb: str = "open") -> Dict[str, Any]:
    """Adapter: classify how a file path / URL would be opened (pure)."""
    from je_auto_control.utils.shell_open import plan_open
    return plan_open(str(target), verb=str(verb))


def _open_path(target: str, verb: str = "open") -> Dict[str, Any]:
    """Adapter: open a file with its default app / a URL in the browser."""
    from je_auto_control.utils.shell_open import open_path
    return {"opened": bool(open_path(str(target), verb=str(verb)))}


def _idle_seconds() -> Dict[str, Any]:
    """Adapter: seconds since the last user input."""
    from je_auto_control.utils.idle_keepawake import idle_seconds
    return {"idle_seconds": float(idle_seconds())}


def _is_idle(threshold: Any) -> Dict[str, Any]:
    """Adapter: whether the user has been idle for >= ``threshold`` seconds."""
    from je_auto_control.utils.idle_keepawake import idle_seconds, is_idle
    seconds = float(threshold)
    return {"idle": bool(is_idle(seconds)), "idle_seconds": idle_seconds()}


def _plan_keep_awake(display: Any = True, system: Any = True) -> Dict[str, Any]:
    """Adapter: describe a keep-awake request (pure, no OS call)."""
    from je_auto_control.utils.idle_keepawake import plan_keep_awake
    return plan_keep_awake(display=bool(display), system=bool(system))


def _keep_awake_on(display: Any = True, system: Any = True) -> Dict[str, Any]:
    """Adapter: keep the machine awake until ``AC_allow_sleep``."""
    from je_auto_control.utils.idle_keepawake import keep_awake_on
    return keep_awake_on(display=bool(display), system=bool(system))


def _allow_sleep() -> Dict[str, Any]:
    """Adapter: release a previously-started keep-awake."""
    from je_auto_control.utils.idle_keepawake import allow_sleep
    return {"released": bool(allow_sleep())}


def _get_volume() -> Dict[str, Any]:
    """Adapter: the system master volume as an integer percent."""
    from je_auto_control.utils.system_volume import get_volume, is_muted
    return {"volume": int(get_volume()), "muted": bool(is_muted())}


def _set_volume(level: Any) -> Dict[str, Any]:
    """Adapter: set the master volume to ``level`` percent."""
    from je_auto_control.utils.system_volume import set_volume
    return {"volume": int(set_volume(float(level)))}


def _change_volume(delta: Any) -> Dict[str, Any]:
    """Adapter: add ``delta`` percent to the master volume."""
    from je_auto_control.utils.system_volume import change_volume
    return {"volume": int(change_volume(float(delta)))}


def _set_mute(muted: Any = True) -> Dict[str, Any]:
    """Adapter: set the master mute flag."""
    from je_auto_control.utils.system_volume import set_mute
    return {"muted": bool(set_mute(bool(muted)))}


def _toggle_mute() -> Dict[str, Any]:
    """Adapter: flip the master mute flag."""
    from je_auto_control.utils.system_volume import toggle_mute
    return {"muted": bool(toggle_mute())}


def _lock_session() -> Dict[str, Any]:
    """Adapter: lock the workstation now."""
    from je_auto_control.utils.lock_session import lock_session
    return {"locked": bool(lock_session())}


def _plan_lock_session() -> Dict[str, Any]:
    """Adapter: describe how the workstation would be locked (pure)."""
    from je_auto_control.utils.lock_session import plan_lock_session
    return plan_lock_session()


def _wait_for_unlock(timeout: Any = 30.0, interval: Any = 0.5
                     ) -> Dict[str, Any]:
    """Adapter: block until the session is unlocked or timeout."""
    from je_auto_control.utils.lock_session import wait_for_unlock
    unlocked = wait_for_unlock(timeout_s=float(timeout),
                               interval_s=float(interval))
    return {"unlocked": bool(unlocked)}


def _classify_lock_transitions(states: Any) -> Dict[str, Any]:
    """Adapter: reduce lock-state samples to lock / unlock events (pure)."""
    from je_auto_control.utils.lock_session import classify_lock_transitions
    samples = [bool(s) for s in _coerce_list(states)] if states else []
    return {"events": classify_lock_transitions(samples)}


def _ime_state() -> Dict[str, Any]:
    """Adapter: the focused window's live IME composition / conversion state."""
    from je_auto_control.utils.ime_state import ime_state
    return ime_state()


def _is_composing() -> Dict[str, Any]:
    """Adapter: whether the IME has an uncommitted composition."""
    from je_auto_control.utils.ime_state import is_composing
    return {"composing": bool(is_composing())}


def _wait_for_composition_commit(timeout: Any = 5.0, interval: Any = 0.1
                                 ) -> Dict[str, Any]:
    """Adapter: block until the IME finishes composing or timeout."""
    from je_auto_control.utils.ime_state import wait_for_composition_commit
    committed = wait_for_composition_commit(timeout_s=float(timeout),
                                            interval_s=float(interval))
    return {"committed": bool(committed)}


def _decode_conversion_mode(flags: Any) -> Dict[str, Any]:
    """Adapter: decode an IMM32 conversion bitmask into named flags (pure)."""
    from je_auto_control.utils.ime_state import decode_conversion_mode
    return decode_conversion_mode(int(flags))


def _make_retry_budget(base: Any, max_delay: Any, multiplier: Any,
                       jitter: Any) -> Any:
    """Build a RetryBudget from executor scalars (helper for the adapters)."""
    from je_auto_control.utils.retry_budget import RetryBudget
    return RetryBudget(base_delay_s=float(base), max_delay_s=float(max_delay),
                       multiplier=float(multiplier), jitter=str(jitter))


def _retry_delay(attempt: Any, base: Any = 0.1, max_delay: Any = 5.0,
                 multiplier: Any = 2.0, jitter: Any = "none") -> Dict[str, Any]:
    """Adapter: the (jittered) backoff delay before a retry attempt (pure)."""
    budget = _make_retry_budget(base, max_delay, multiplier, jitter)
    return {"delay": float(budget.next_delay(int(attempt)))}


def _plan_retry_delays(attempts: Any, base: Any = 0.1, max_delay: Any = 5.0,
                       multiplier: Any = 2.0, jitter: Any = "none"
                       ) -> Dict[str, Any]:
    """Adapter: the backoff delay schedule for the first N retries (pure)."""
    budget = _make_retry_budget(base, max_delay, multiplier, jitter)
    return {"delays": [float(d) for d in budget.plan(int(attempts))]}


def _compare_field_value(expected: Any, actual: Any,
                         mode: Any = "exact") -> Dict[str, Any]:
    """Adapter: compare an expected vs actual field value under a mode (pure)."""
    from je_auto_control.utils.verify_field import compare_field_value
    return compare_field_value(expected, actual, mode=str(mode))


def _verify_field_value(expected: Any, name: Optional[str] = None,
                        role: Optional[str] = None,
                        app_name: Optional[str] = None,
                        automation_id: Optional[str] = None,
                        mode: Any = "exact") -> Dict[str, Any]:
    """Adapter: read a native control's value back and compare to expected."""
    from je_auto_control.utils.verify_field import verify_field_value
    return verify_field_value(
        expected,
        reader=lambda: _control_get_value(name=name, role=role,
                                          app_name=app_name,
                                          automation_id=automation_id),
        mode=str(mode))


def _normalize_ext(target: str) -> Dict[str, Any]:
    """Adapter: the lowercased extension of a path / bare ext (pure)."""
    from je_auto_control.utils.file_assoc import normalize_ext
    return {"ext": normalize_ext(str(target))}


def _file_association(target: str) -> Dict[str, Any]:
    """Adapter: the app registered to open ``target``'s file type."""
    from je_auto_control.utils.file_assoc import file_association
    return file_association(str(target))


def _get_control_text(name: Optional[str] = None, role: Optional[str] = None,
                      app_name: Optional[str] = None,
                      automation_id: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: read a control's full text via TextPattern (multiline-safe)."""
    from je_auto_control.utils.ax_text import get_control_text
    return {"text": get_control_text(name=name, role=role, app_name=app_name,
                                     automation_id=automation_id)}


def _find_control_text(text: str, ignore_case: Any = True,
                       name: Optional[str] = None, role: Optional[str] = None,
                       app_name: Optional[str] = None,
                       automation_id: Optional[str] = None) -> bool:
    """Adapter: whether text occurs in a control (TextPattern.FindText)."""
    from je_auto_control.utils.ax_text import find_control_text
    return find_control_text(str(text), ignore_case=bool(ignore_case), name=name,
                             role=role, app_name=app_name,
                             automation_id=automation_id)


def _select_control_text(text: str, ignore_case: Any = True,
                         name: Optional[str] = None, role: Optional[str] = None,
                         app_name: Optional[str] = None,
                         automation_id: Optional[str] = None) -> bool:
    """Adapter: find + select text in a control (TextPattern.FindText + Select)."""
    from je_auto_control.utils.ax_text import select_control_text
    return select_control_text(str(text), ignore_case=bool(ignore_case),
                               name=name, role=role, app_name=app_name,
                               automation_id=automation_id)


def _control_text_attributes(name: Optional[str] = None, role: Optional[str] = None,
                             app_name: Optional[str] = None,
                             automation_id: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: read a control selection's font/colour formatting (TextPattern)."""
    from je_auto_control.utils.ax_text import control_text_attributes
    attrs = control_text_attributes(name=name, role=role, app_name=app_name,
                                    automation_id=automation_id)
    return {"found": attrs is not None, "attributes": attrs}


def _get_selected_text(name: Optional[str] = None, role: Optional[str] = None,
                       app_name: Optional[str] = None,
                       automation_id: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: read a control's currently selected text (TextPattern)."""
    from je_auto_control.utils.ax_text import get_selected_text
    return {"text": get_selected_text(name=name, role=role, app_name=app_name,
                                      automation_id=automation_id)}


def _get_visible_text(name: Optional[str] = None, role: Optional[str] = None,
                      app_name: Optional[str] = None,
                      automation_id: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: read only the on-screen text of a control (TextPattern)."""
    from je_auto_control.utils.ax_text import get_visible_text
    return {"text": get_visible_text(name=name, role=role, app_name=app_name,
                                     automation_id=automation_id)}


def _read_table(name: Optional[str] = None, role: Optional[str] = None,
                app_name: Optional[str] = None,
                automation_id: Optional[str] = None) -> List[List[str]]:
    """Adapter: read a grid/table/list control as rows of cell strings."""
    from je_auto_control.utils.accessibility import read_control_table
    return read_control_table(name=name, role=role, app_name=app_name,
                              automation_id=automation_id)


def _watchdog_add(title: str, action: str = "close",
                  case_sensitive: bool = False,
                  name: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: register a popup-dismissal rule on the default watchdog."""
    from je_auto_control.utils.watchdog import default_popup_watchdog
    default_popup_watchdog.add_window_rule(
        title, action=str(action), case_sensitive=bool(case_sensitive),
        name=name)
    return {"rules": default_popup_watchdog.rule_names()}


def _watchdog_start() -> Dict[str, Any]:
    """Adapter: start the background popup watchdog."""
    from je_auto_control.utils.watchdog import default_popup_watchdog
    default_popup_watchdog.start()
    return {"running": True}


def _watchdog_stop() -> Dict[str, Any]:
    """Adapter: stop the background popup watchdog."""
    from je_auto_control.utils.watchdog import default_popup_watchdog
    default_popup_watchdog.stop()
    return {"running": False}


def _watchdog_list() -> Dict[str, Any]:
    """Adapter: report the watchdog's rules, run state and dismissals."""
    from je_auto_control.utils.watchdog import default_popup_watchdog
    w = default_popup_watchdog
    return {"running": w.running, "rules": w.rule_names(), "hits": w.hits}


def _handle_file_dialog(path: str, action: str = "open",
                        window_title: Optional[str] = None,
                        timeout_s: float = 10.0,
                        confirm_key: str = "enter") -> Dict[str, Any]:
    """Adapter: wait for a native file dialog, type the path, confirm."""
    from je_auto_control.utils.file_dialog import handle_file_dialog
    return handle_file_dialog(path, action=action, window_title=window_title,
                              timeout_s=float(timeout_s),
                              confirm_key=confirm_key)


def _assert_session_active() -> Dict[str, Any]:
    """Adapter: raise unless the session is interactive (not locked)."""
    from je_auto_control.utils.session_guard import ensure_interactive_session
    return {"interactive": ensure_interactive_session()}


def _queue(db: str, name: str):
    from je_auto_control.utils.work_queue import WorkQueue
    return WorkQueue(db, name)


def _queue_add(db: str, data: Any, reference: Optional[str] = None,
               name: str = "default") -> Dict[str, Any]:
    """Adapter: enqueue a work item (skips live duplicate references)."""
    return {"id": _queue(db, name).add(data, reference=reference)}


def _queue_next(db: str, name: str = "default") -> Optional[Dict[str, Any]]:
    """Adapter: atomically claim the next work item (or None)."""
    item = _queue(db, name).get_next()
    return None if item is None else {
        "id": item.id, "reference": item.reference, "data": item.data,
        "status": item.status, "retries": item.retries}


def _queue_complete(db: str, item_id: int, output: Any = None,
                    name: str = "default") -> Dict[str, Any]:
    """Adapter: mark a work item successful."""
    _queue(db, name).complete(int(item_id), output=output)
    return {"id": int(item_id), "status": "success"}


def _queue_fail(db: str, item_id: int, error: str,
                kind: str = "application", max_retries: int = 3,
                name: str = "default") -> Dict[str, Any]:
    """Adapter: fail a work item (application errors retry, business don't)."""
    status = _queue(db, name).fail(int(item_id), str(error), kind=str(kind),
                                   max_retries=int(max_retries))
    return {"id": int(item_id), "status": status}


def _queue_stats(db: str, name: str = "default") -> Dict[str, int]:
    """Adapter: return per-status counts for a work queue."""
    return _queue(db, name).stats()


def _generate_data(schema: Dict[str, Any], count: int = 10,
                   path: Optional[str] = None, fmt: Optional[str] = None,
                   seed: Optional[int] = None) -> Dict[str, Any]:
    """Adapter: generate synthetic rows; write to ``path`` when given."""
    from je_auto_control.utils.test_data import generate_rows, write_dataset
    rows = generate_rows(schema, int(count), seed=seed)
    if path:
        return {"path": write_dataset(rows, path, fmt), "count": len(rows)}
    return {"rows": rows, "count": len(rows)}


def _mcp_manifest(path: Optional[str] = None,
                  include_tools: bool = False) -> Dict[str, Any]:
    """Adapter: build (or write) the MCP registry server.json manifest."""
    from je_auto_control.utils.mcp_registry import (
        build_server_manifest, write_server_manifest)
    if path:
        return {"path": write_server_manifest(
            path, include_tools=bool(include_tools))}
    return {"manifest": build_server_manifest(
        include_tools=bool(include_tools))}


def _rank_tests(flows: List[str], history_path: Optional[str] = None,
                window: int = 10) -> Dict[str, Any]:
    """Adapter: score flows by risk (riskiest first)."""
    from je_auto_control.utils.test_select import rank_flows
    return {"ranked": rank_flows(flows, history_path=history_path,
                                 window=int(window))}


def _select_tests(flows: List[str], k: Optional[int] = None,
                  threshold: Optional[float] = None,
                  history_path: Optional[str] = None,
                  window: int = 10) -> Dict[str, Any]:
    """Adapter: pick the riskiest flows to run (top-k / threshold)."""
    from je_auto_control.utils.test_select import select_flows
    return {"selected": select_flows(
        flows, k=k, threshold=threshold, history_path=history_path,
        window=int(window))}


def _element_repo(path: str):
    from je_auto_control.utils.element_repository import ElementRepository
    return ElementRepository(path)


def _element_save(path: str, key: str, name: Optional[str] = None,
                  role: Optional[str] = None,
                  app_name: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: save a named native-UI locator (object repository)."""
    return {"locator": _element_repo(path).save(
        key, name=name, role=role, app_name=app_name)}


def _element_find(path: str, key: str) -> Dict[str, Any]:
    """Adapter: resolve a saved locator to a live element summary."""
    return _element_repo(path).find_info(key)


def _element_click(path: str, key: str) -> Dict[str, Any]:
    """Adapter: click the element behind a saved locator."""
    return {"clicked": _element_repo(path).click(key)}


def _element_remove(path: str, key: str) -> Dict[str, Any]:
    """Adapter: delete a saved locator."""
    return {"removed": _element_repo(path).remove(key)}


def _element_list(path: str) -> Dict[str, Any]:
    """Adapter: list saved locator names."""
    return {"keys": _element_repo(path).keys()}


def _debug_trace(actions: List[Any], dry_run: bool = False) -> Dict[str, Any]:
    """Adapter: run an action list and return a per-step trace."""
    from je_auto_control.utils.flow_debugger import trace_actions
    return {"trace": trace_actions(actions, dry_run=bool(dry_run))}


def _skill_lib(path: str):
    from je_auto_control.utils.skill_library import SkillLibrary
    return SkillLibrary(path)


def _skill_save(path: str, name: str, actions: List[Any],
                description: str = "",
                tags: Optional[List[str]] = None) -> Dict[str, Any]:
    """Adapter: save a reusable action sequence (skill)."""
    skill = _skill_lib(path).save(name, actions, description=description,
                                  tags=tags)
    return {"name": skill.name, "tags": skill.tags}


def _skill_run(path: str, name: str) -> Dict[str, Any]:
    """Adapter: execute a stored skill's actions."""
    return {"record": _skill_lib(path).run(name)}


def _skill_list(path: str) -> Dict[str, Any]:
    """Adapter: list saved skill names."""
    return {"names": _skill_lib(path).names()}


def _skill_remove(path: str, name: str) -> Dict[str, Any]:
    """Adapter: delete a saved skill."""
    return {"removed": _skill_lib(path).remove(name)}


def _skill_search(path: str, query: str) -> Dict[str, Any]:
    """Adapter: search skills by name/description/tags."""
    return {"names": [s.name for s in _skill_lib(path).search(query)]}


def _guard_text(text: str, threshold: int = 2) -> Dict[str, Any]:
    """Adapter: assess text for prompt-injection patterns."""
    from je_auto_control.utils.guardrail import assess_text
    return assess_text(text, threshold=int(threshold))


def _agent_card(path: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: build (or write) the A2A agent card."""
    from je_auto_control.utils.a2a import build_agent_card, write_agent_card
    if path:
        return {"path": write_agent_card(path)}
    return {"card": build_agent_card()}


def _read_workbook(path: str, sheet: str = "") -> Dict[str, Any]:
    """Adapter: read an .xlsx worksheet into rows."""
    from je_auto_control.utils.office import read_workbook
    return {"rows": read_workbook(path, sheet=sheet)}


def _write_workbook(path: str, rows: List[Dict[str, Any]],
                    sheet: str = "Sheet1") -> Dict[str, Any]:
    """Adapter: write rows to an .xlsx file."""
    from je_auto_control.utils.office import write_workbook
    return {"path": write_workbook(path, rows, sheet=sheet)}


def _read_document(path: str) -> Dict[str, Any]:
    """Adapter: read a .docx file's paragraphs."""
    from je_auto_control.utils.office import read_document
    return read_document(path)


def _write_document(path: str, paragraphs: List[str]) -> Dict[str, Any]:
    """Adapter: write paragraphs to a .docx file."""
    from je_auto_control.utils.office import write_document
    return {"path": write_document(path, paragraphs)}


def _read_presentation(path: str) -> Dict[str, Any]:
    """Adapter: read a .pptx file's per-slide text."""
    from je_auto_control.utils.office import read_presentation
    return read_presentation(path)


def _write_presentation(path: str, slides: List[Any]) -> Dict[str, Any]:
    """Adapter: write slides to a .pptx file."""
    from je_auto_control.utils.office import write_presentation
    return {"path": write_presentation(path, slides)}


def _memory(db: str):
    from je_auto_control.utils.agent_memory import AgentMemory
    return AgentMemory(db)


def _memory_remember(db: str, goal: str, steps: Optional[List[Any]] = None,
                     outcome: str = "",
                     tags: Optional[List[str]] = None) -> Dict[str, Any]:
    """Adapter: store an agent episode (goal/trajectory/outcome)."""
    return {"id": _memory(db).remember(goal, steps=steps, outcome=outcome,
                                       tags=tags)}


def _memory_recall(db: str, query: str, limit: int = 5) -> Dict[str, Any]:
    """Adapter: recall episodes most relevant to a query."""
    episodes = _memory(db).recall(query, limit=int(limit))
    return {"episodes": [_episode_to_dict(ep) for ep in episodes]}


def _memory_recent(db: str, limit: int = 10) -> Dict[str, Any]:
    """Adapter: list the most recent episodes."""
    episodes = _memory(db).recent(limit=int(limit))
    return {"episodes": [_episode_to_dict(ep) for ep in episodes]}


def _memory_forget(db: str, episode_id: int) -> Dict[str, Any]:
    """Adapter: delete an episode."""
    return {"removed": _memory(db).forget(int(episode_id))}


def _memory_stats(db: str) -> Dict[str, int]:
    """Adapter: episode count for a memory store."""
    return _memory(db).stats()


def _episode_to_dict(episode: Any) -> Dict[str, Any]:
    return {"id": episode.id, "goal": episode.goal, "steps": episode.steps,
            "outcome": episode.outcome, "tags": episode.tags,
            "score": episode.score}


def _seed_everything(seed: int = 0) -> Dict[str, Any]:
    """Adapter: seed all RNG run-wide for reproducible runs."""
    from je_auto_control.utils.deterministic import seed_everything
    return {"seed": seed_everything(int(seed))}


def _observe_handler(actions: List[Any]) -> Callable[[str, Any], None]:
    """Build an observer callback that runs an action list on each event."""
    def handler(_event: str, _value: Any) -> None:
        if actions:
            executor.execute_action(list(actions))
    return handler


def _observe_predicate(kind: str, params: Dict[str, Any]):
    from je_auto_control.utils.observer import (
        image_predicate, pixel_predicate, text_predicate)
    builders = {
        "image": lambda: image_predicate(params.get("image", ""),
                                         params.get("threshold", 0.8)),
        "text": lambda: text_predicate(params.get("text", "")),
        "pixel": lambda: pixel_predicate(int(params.get("x", 0)),
                                         int(params.get("y", 0))),
    }
    if kind not in builders:
        raise AutoControlActionException(f"unknown observe kind: {kind!r}")
    return builders[kind]()


def _observe_add(name: str, kind: str = "image", event: str = "appear",
                 actions: Optional[List[Any]] = None,
                 **params: Any) -> Dict[str, Any]:
    """Adapter: watch image/text/pixel; run ``actions`` on the event."""
    from je_auto_control.utils.observer import default_observer
    default_observer.add(name, _observe_predicate(kind, params),
                         _observe_handler(actions or []), events=(event,))
    return {"name": name, "kind": kind, "event": event}


def _observe_remove(name: str) -> Dict[str, Any]:
    """Adapter: remove a registered watch."""
    from je_auto_control.utils.observer import default_observer
    return {"removed": default_observer.remove(name)}


def _observe_list() -> Dict[str, Any]:
    """Adapter: list registered watch names."""
    from je_auto_control.utils.observer import default_observer
    return {"names": default_observer.names()}


def _observe_poll() -> Dict[str, Any]:
    """Adapter: evaluate all watches once; return fired events."""
    from je_auto_control.utils.observer import default_observer
    return {"fired": default_observer.poll_once()}


def _observe_start() -> Dict[str, Any]:
    """Adapter: start the background observer thread."""
    from je_auto_control.utils.observer import default_observer
    default_observer.start()
    return {"running": default_observer.running}


def _observe_stop() -> Dict[str, Any]:
    """Adapter: stop the background observer thread."""
    from je_auto_control.utils.observer import default_observer
    default_observer.stop()
    return {"running": default_observer.running}


def _generate_sbom(path: Optional[str] = None,
                   root: str = "je_auto_control") -> Dict[str, Any]:
    """Adapter: build (or write) a CycloneDX SBOM for the project."""
    from je_auto_control.utils.sbom import build_sbom, write_sbom
    root_arg = root or None
    if path:
        return {"path": write_sbom(path, root_arg)}
    return {"sbom": build_sbom(root_arg)}


def _shard_suite(flows: List[str], shards: int = 2,
                 history_path: Optional[str] = None,
                 window: int = 20) -> Dict[str, Any]:
    """Adapter: balance flows into duration-aware shards."""
    from je_auto_control.utils.test_shard import shard_flows
    return {"shards": shard_flows(flows, int(shards),
                                  history_path=history_path,
                                  window=int(window))}


def _merge_results(reports: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Adapter: merge per-shard report dicts into one report."""
    from je_auto_control.utils.test_shard import merge_results
    return merge_results(reports)


def _validate_rows(rows: List[Dict[str, Any]],
                   schema: Dict[str, Any]) -> Dict[str, Any]:
    """Adapter: validate rows against a declarative schema."""
    from je_auto_control.utils.data_quality import validate_rows
    return validate_rows(rows, schema)


def _extract_fields(text: str, fields: Optional[List[str]] = None,
                    patterns: Optional[Dict[str, str]] = None
                    ) -> Dict[str, Any]:
    """Adapter: extract structured fields from free text."""
    from je_auto_control.utils.data_quality import extract_fields
    return {"fields": extract_fields(text, fields=fields, patterns=patterns)}


def _mask_rows(rows: List[Dict[str, Any]],
               rules: Dict[str, str]) -> Dict[str, Any]:
    """Adapter: mask sensitive columns in rows."""
    from je_auto_control.utils.data_quality import mask_rows
    return {"rows": mask_rows(rows, rules)}


def _pseudo_localize(text: Optional[str] = None,
                     mapping: Optional[Dict[str, Any]] = None,
                     expansion: float = 0.4) -> Dict[str, Any]:
    """Adapter: pseudo-localize a string or a whole catalog mapping."""
    from je_auto_control.utils.i18n_test import (
        pseudo_localize, pseudo_localize_catalog)
    if mapping is not None:
        return {"catalog": pseudo_localize_catalog(
            mapping, expansion=float(expansion))}
    return {"text": pseudo_localize(text or "", expansion=float(expansion))}


def _check_overflow(elements: Optional[List[Any]] = None,
                    avg_char_px: float = 7.0,
                    app_name: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: flag text wider than its widget (live a11y unless given)."""
    from je_auto_control.utils.i18n_test import check_overflow
    items = elements
    if items is None:
        from je_auto_control.utils.accessibility.accessibility_api import (
            list_accessibility_elements)
        items = list_accessibility_elements(app_name=app_name)
    return {"issues": check_overflow(items, avg_char_px=float(avg_char_px))}


def _check_catalog(base: Dict[str, Any],
                   target: Dict[str, Any]) -> Dict[str, Any]:
    """Adapter: diff a translation catalog against the base locale."""
    from je_auto_control.utils.i18n_test import check_catalog
    return check_catalog(base, target)


def _run_resumable(actions: List[Any], run_id: str, db: str,
                   variables: Optional[Dict[str, Any]] = None
                   ) -> Dict[str, Any]:
    """Adapter: run actions with checkpoint/resume keyed by run_id."""
    from je_auto_control.utils.checkpoint import CheckpointStore, run_resumable
    return run_resumable(actions, run_id=run_id,
                         store=CheckpointStore(db), variables=variables)


def _checkpoint_status(run_id: str, db: str) -> Dict[str, Any]:
    """Adapter: return the saved checkpoint for a run (or null)."""
    from je_auto_control.utils.checkpoint import CheckpointStore
    checkpoint = CheckpointStore(db).load(run_id)
    if checkpoint is None:
        return {"checkpoint": None}
    return {"checkpoint": {"run_id": checkpoint.run_id,
                           "step_index": checkpoint.step_index,
                           "variables": checkpoint.variables}}


def _checkpoint_clear(run_id: str, db: str) -> Dict[str, Any]:
    """Adapter: delete a run's checkpoint."""
    from je_auto_control.utils.checkpoint import CheckpointStore
    return {"cleared": CheckpointStore(db).clear(run_id)}


def _mark_screen(app_name: Optional[str] = None,
                 render_path: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: number live UI elements (Set-of-Marks) for VLM grounding."""
    from je_auto_control.utils.set_of_marks import mark_screen
    return mark_screen(app_name=app_name, render_path=render_path)


def _mark_click(mark_id: int) -> Dict[str, Any]:
    """Adapter: click the element behind a numbered mark."""
    from je_auto_control.utils.set_of_marks import mark_click
    return {"clicked": mark_click(int(mark_id))}


def _screen_snapshot(app_name: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: snapshot the live a11y tree as a diff baseline."""
    from je_auto_control.utils.screen_state import snapshot_screen
    return {"snapshot": snapshot_screen(app_name=app_name)}


def _screen_diff(before: List[Dict[str, Any]],
                 after: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Adapter: semantic diff between two snapshots."""
    from je_auto_control.utils.screen_state import diff_snapshots
    return diff_snapshots(before, after)


def _screen_changed(app_name: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: diff the live screen against the last snapshot baseline."""
    from je_auto_control.utils.screen_state import screen_changed
    return screen_changed(app_name=app_name)


def _describe_screen(app_name: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: structured 'where am I' description of the live screen."""
    from je_auto_control.utils.screen_state import describe_screen
    return describe_screen(app_name=app_name)


def _replay_timeline(events: List[Dict[str, Any]],
                     speed: float = 1.0) -> Dict[str, Any]:
    """Adapter: replay timed input events at a speed multiplier."""
    from je_auto_control.utils.input_macro import replay_timeline
    return {"played": replay_timeline(events, speed=float(speed))}


def _input_sequence(steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Adapter: run a declarative input sequence (press/hold/repeat/...)."""
    from je_auto_control.utils.input_macro import run_sequence
    return {"log": run_sequence(steps)}


_CIRCUIT_BREAKERS: Dict[str, Any] = {}


def _circuit_call(name: str, actions: List[Any], threshold: int = 5,
                  reset_s: float = 30.0) -> Dict[str, Any]:
    """Adapter: run an action list through a named circuit breaker."""
    from je_auto_control.utils.resilience import CircuitBreaker
    breaker = _CIRCUIT_BREAKERS.setdefault(
        name, CircuitBreaker(int(threshold), float(reset_s)))
    record = breaker.call(
        lambda: executor.execute_action(list(actions), raise_on_error=True))
    return {"state": breaker.state, "record": record}


def _ci_annotations(annotations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Adapter: emit GitHub Actions annotations from result dicts."""
    from je_auto_control.utils.ci_annotations import emit_annotations
    return {"lines": emit_annotations(annotations)}


def _clip_history_capture() -> Dict[str, Any]:
    """Adapter: capture the live clipboard into history."""
    from je_auto_control.utils.clipboard_history import (
        default_clipboard_history)
    return {"added": default_clipboard_history.capture_once()}


def _clip_history_list() -> Dict[str, Any]:
    """Adapter: list clipboard history (newest first)."""
    from je_auto_control.utils.clipboard_history import (
        default_clipboard_history)
    return {"history": default_clipboard_history.snapshot()}


def _clip_history_search(query: str) -> Dict[str, Any]:
    """Adapter: search clipboard history."""
    from je_auto_control.utils.clipboard_history import (
        default_clipboard_history)
    return {"matches": default_clipboard_history.search(query)}


def _clip_history_start() -> Dict[str, Any]:
    """Adapter: start the background clipboard-history poller."""
    from je_auto_control.utils.clipboard_history import (
        default_clipboard_history)
    default_clipboard_history.start()
    return {"running": default_clipboard_history.running}


def _clip_history_stop() -> Dict[str, Any]:
    """Adapter: stop the background clipboard-history poller."""
    from je_auto_control.utils.clipboard_history import (
        default_clipboard_history)
    default_clipboard_history.stop()
    return {"running": default_clipboard_history.running}


def _heal_stats(limit: int = 200) -> Dict[str, Any]:
    """Adapter: aggregate the self-heal log into metrics."""
    from je_auto_control.utils.heal_analytics import analyze_heal_log
    return analyze_heal_log(limit=int(limit))


def _scan_secrets(data: Any) -> Dict[str, Any]:
    """Adapter: scan JSON/data for hardcoded secrets."""
    from je_auto_control.utils.secrets_scan import scan_secrets
    return {"findings": scan_secrets(data)}


def _scan_vulns(components: Any, advisories: Any = None,
                sarif_path: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: match SBOM components against an OSV advisory database."""
    import json
    from je_auto_control.utils.vuln_scan import (
        findings_to_sarif, scan_components)
    if isinstance(components, str):
        components = json.loads(components)
    if isinstance(components, dict):
        components = components.get("components", [])
    if isinstance(advisories, str):
        advisories = json.loads(advisories)
    findings = scan_components(components, advisories or [])
    result: Dict[str, Any] = {"findings": findings, "count": len(findings)}
    if sarif_path:
        from je_auto_control.utils.sarif import write_sarif
        result["sarif_path"] = write_sarif(
            findings_to_sarif(findings), sarif_path,
            tool_name="AutoControl-VulnScan")
    return result


def _apply_vex(findings: Any, vex: Any) -> Dict[str, Any]:
    """Adapter: suppress VEX'd vulnerability findings (each JSON string/obj)."""
    import json
    from je_auto_control.utils.vex import apply_vex
    if isinstance(findings, str):
        findings = json.loads(findings)
    if isinstance(vex, str):
        vex = json.loads(vex)
    kept = apply_vex(findings, vex)
    return {"findings": kept, "count": len(kept)}


def _check_licenses(components: Any, allow: Any = None,
                    deny: Any = None) -> Dict[str, Any]:
    """Adapter: evaluate SBOM component licenses against allow/deny lists."""
    import json
    from je_auto_control.utils.license_policy import evaluate_sbom
    if isinstance(components, str):
        components = json.loads(components)
    if isinstance(components, dict):
        components = components.get("components", [])
    if isinstance(allow, str):
        allow = json.loads(allow)
    if isinstance(deny, str):
        deny = json.loads(deny)
    violations = evaluate_sbom(components, allow=allow, deny=deny)
    return {"violations": violations, "count": len(violations)}


_RATE_LIMITERS: Dict[str, Any] = {}


def _rate_limit(name: str, rate: float = 1.0, capacity: float = 1.0,
                n: float = 1.0) -> Dict[str, Any]:
    """Adapter: try to take ``n`` tokens from a named token-bucket limiter."""
    from je_auto_control.utils.rate_limit import TokenBucket
    bucket = _RATE_LIMITERS.setdefault(
        name, TokenBucket(float(rate), float(capacity)))
    acquired = bucket.try_acquire(float(n))
    return {"acquired": acquired, "tokens": round(bucket.tokens, 4),
            "wait": round(bucket.time_until_available(float(n)), 4)}


_BULKHEADS: Dict[str, Any] = {}
_IDEMPOTENCY_STORES: Dict[str, Any] = {}
_DEDUP_WINDOWS: Dict[str, Any] = {}
_SEQUENCE_TRACKERS: Dict[str, Any] = {}
_VERSIONED_STORES: Dict[str, Any] = {}
_OUTBOXES: Dict[str, Any] = {}


def _outbox_enqueue(name: str, event: Any) -> Dict[str, Any]:
    """Adapter: enqueue an event into a named outbox."""
    import json
    from je_auto_control.utils.outbox import Outbox
    if isinstance(event, str):
        try:
            event = json.loads(event)
        except ValueError:
            pass
    outbox = _OUTBOXES.setdefault(name, Outbox())
    return {"id": outbox.enqueue(event), "pending": len(outbox.pending())}


def _outbox_pending(name: str) -> Dict[str, Any]:
    """Adapter: list pending entries of a named outbox."""
    from je_auto_control.utils.outbox import Outbox
    outbox = _OUTBOXES.setdefault(name, Outbox())
    return {"pending": outbox.pending()}


def _collation_sort(items: Any, strength: str = "tertiary",
                    tailoring: Any = None, reverse: Any = False) -> Dict[str, Any]:
    """Adapter: locale-aware sort of a list of strings."""
    import json
    from je_auto_control.utils.locale_collation import sort_strings
    if isinstance(items, str):
        items = json.loads(items)
    ordered = sort_strings(list(items), strength=strength,
                           tailoring=tailoring or None, reverse=bool(reverse))
    return {"sorted": ordered}


def _collation_compare(first: str, second: str, strength: str = "tertiary",
                       tailoring: Any = None) -> Dict[str, Any]:
    """Adapter: locale-aware comparison of two strings."""
    from je_auto_control.utils.locale_collation import compare
    return {"order": compare(first, second, strength=strength,
                             tailoring=tailoring or None)}


def _confusable_scan(text: str) -> Dict[str, Any]:
    """Adapter: homoglyph / mixed-script spoofing report for a string."""
    from je_auto_control.utils.confusables import (
        detect_homoglyphs, is_mixed_script, scripts_of, skeleton,
    )
    return {"skeleton": skeleton(text),
            "homoglyphs": detect_homoglyphs(text),
            "mixed_script": is_mixed_script(text),
            "scripts": sorted(scripts_of(text))}


def _confusable_compare(first: str, second: str) -> Dict[str, Any]:
    """Adapter: whether two strings render to the same skeleton."""
    from je_auto_control.utils.confusables import is_confusable
    return {"confusable": is_confusable(first, second)}


def _readability_report(text: str) -> Dict[str, Any]:
    """Adapter: full readability report (all metrics + counts) for a string."""
    from je_auto_control.utils.readability import readability_report
    return readability_report(text)


def _bidi_check(text: str) -> Dict[str, Any]:
    """Adapter: bidirectional-text QA report (controls/balance/Trojan-source)."""
    from je_auto_control.utils.bidi_check import detect_bidi_issues
    return detect_bidi_issues(text)


def _bidi_strip(text: str) -> Dict[str, Any]:
    """Adapter: remove all bidi control characters from a string."""
    from je_auto_control.utils.bidi_check import strip_bidi_controls
    return {"text": strip_bidi_controls(text)}


def _format_list(items: Any, style: str = "and",
                 locale: str = "en") -> Dict[str, Any]:
    """Adapter: join items into a localised list string."""
    import json
    from je_auto_control.utils.list_format import format_list
    if isinstance(items, str):
        items = json.loads(items)
    return {"text": format_list(list(items), style=style, locale=locale)}


def _format_message(pattern: str, args: Any = None,
                    locale: str = "en") -> Dict[str, Any]:
    """Adapter: render an ICU-lite MessageFormat pattern."""
    import json
    from je_auto_control.utils.message_format import format_message
    if isinstance(args, str):
        args = json.loads(args)
    return {"text": format_message(pattern, args or {}, locale=locale)}


def _gettext_translate(po: str, msgid: str,
                       context: Any = None) -> Dict[str, Any]:
    """Adapter: parse a .po string and look up a singular translation."""
    from je_auto_control.utils.gettext_catalog import parse_po
    catalog = parse_po(po)
    return {"text": catalog.gettext(msgid, context=context or None)}


def _gettext_ngettext(po: str, msgid: str, msgid_plural: str,
                      n: Any) -> Dict[str, Any]:
    """Adapter: parse a .po string and look up a plural translation."""
    from je_auto_control.utils.gettext_catalog import parse_po
    catalog = parse_po(po)
    return {"text": catalog.ngettext(msgid, msgid_plural, int(n))}


def _checksum_validate(scheme: str, number: str) -> Dict[str, Any]:
    """Adapter: validate a number's check digit under a named scheme."""
    from je_auto_control.utils import checksum as cs
    validators = {"luhn": cs.luhn_validate, "verhoeff": cs.verhoeff_validate,
                  "damm": cs.damm_validate, "mod97": cs.mod97_10_validate}
    func = validators.get(scheme)
    if func is None:
        raise AutoControlActionException(f"unknown checksum scheme: {scheme!r}")
    return {"valid": func(number)}


def _checksum_digit(scheme: str, partial: str) -> Dict[str, Any]:
    """Adapter: compute the check digit(s) for a value under a named scheme."""
    from je_auto_control.utils import checksum as cs
    digits = {"luhn": cs.luhn_check_digit, "verhoeff": cs.verhoeff_check_digit,
              "damm": cs.damm_check_digit, "mod97": cs.mod97_10_check_digits}
    func = digits.get(scheme)
    if func is None:
        raise AutoControlActionException(f"unknown checksum scheme: {scheme!r}")
    return {"check_digit": func(partial)}


def _waypoints(value: Any) -> Any:
    """Coerce a JSON string of waypoints into a list."""
    import json
    return json.loads(value) if isinstance(value, str) else value


def _move_along_path(waypoints: Any, easing: str = "linear",
                     per_segment_steps: Any = 20) -> Dict[str, Any]:
    """Adapter: move the pointer through a polyline of waypoints."""
    from je_auto_control.utils.mouse_path import move_along_path
    return move_along_path(_waypoints(waypoints), easing=easing,
                           per_segment_steps=int(per_segment_steps))


def _drag_path(waypoints: Any, button: str = "mouse_left",
               easing: str = "linear",
               per_segment_steps: Any = 20) -> Dict[str, Any]:
    """Adapter: press, drag through a polyline of waypoints, release."""
    from je_auto_control.utils.mouse_path import drag_path
    return drag_path(_waypoints(waypoints), button=button, easing=easing,
                     per_segment_steps=int(per_segment_steps))


def _set_field_text(text: str, clear: str = "select_all", paste: Any = False,
                    modifier: str = "ctrl") -> Dict[str, Any]:
    """Adapter: clear the focused field and enter text."""
    from je_auto_control.utils.field_entry import set_field_text
    return set_field_text(text, clear=clear, paste=bool(paste),
                          modifier=modifier)


def _hold_key(key: str, duration_s: Any = 1.0,
              rate_hz: Any = None) -> Dict[str, Any]:
    """Adapter: hold a key for a duration (or auto-repeat at rate_hz)."""
    from je_auto_control.utils.key_hold import hold_key
    rate = float(rate_hz) if rate_hz not in (None, "") else None
    return hold_key(key, float(duration_s), rate_hz=rate)


def _move_mouse_relative(dx: Any, dy: Any) -> Dict[str, Any]:
    """Adapter: move the pointer by a delta from its current position."""
    from je_auto_control.utils.mouse_relative import move_mouse_relative
    return move_mouse_relative(int(dx), int(dy))


def _type_unicode(text: str, modifier: str = "ctrl") -> Dict[str, Any]:
    """Adapter: enter arbitrary Unicode text via clipboard paste."""
    from je_auto_control.utils.text_unicode import type_unicode
    return type_unicode(text, modifier=modifier)


def _grid_cell(boxes: Any, row: Any, col: Any,
               row_tolerance: Any = 10) -> Dict[str, Any]:
    """Adapter: address a grid cell by (row, col) from a JSON list of boxes."""
    import json
    from je_auto_control.utils.grid_locator import locate_cell
    if isinstance(boxes, str):
        boxes = json.loads(boxes)
    return locate_cell(list(boxes), int(row), int(col),
                       row_tolerance=int(row_tolerance))


def _match_template(template: str, min_score: Any = 0.8, scales: Any = None,
                    region: Any = None,
                    method: str = "ccoeff_normed") -> Dict[str, Any]:
    """Adapter: best confidence-scored template match on the screen."""
    import json
    from je_auto_control.utils.visual_match import match_template
    if isinstance(scales, str):
        scales = json.loads(scales) if scales.strip() else None
    if isinstance(region, str):
        region = json.loads(region) if region.strip() else None
    match = match_template(template, region=region,
                           scales=tuple(scales) if scales else (1.0,),
                           min_score=float(min_score), method=method)
    return {"found": match is not None,
            "match": match.to_dict() if match else None}


def _match_template_all(template: str, min_score: Any = 0.8,
                        max_results: Any = 20, nms_iou: Any = 0.3,
                        region: Any = None) -> Dict[str, Any]:
    """Adapter: every confidence-scored template match on the screen (NMS)."""
    import json
    from je_auto_control.utils.visual_match import match_template_all
    if isinstance(region, str):
        region = json.loads(region) if region.strip() else None
    matches = match_template_all(template, region=region,
                                 min_score=float(min_score),
                                 max_results=int(max_results),
                                 nms_iou=float(nms_iou))
    return {"count": len(matches), "matches": [m.to_dict() for m in matches]}


def _match_masked(template: str, mask: Any = None, min_score: Any = 0.9,
                  region: Any = None) -> Dict[str, Any]:
    """Adapter: best masked template match (alpha / mask ignores background)."""
    import json
    from je_auto_control.utils.visual_match import match_masked
    if isinstance(region, str):
        region = json.loads(region) if region.strip() else None
    match = match_masked(template, mask=mask, region=region,
                         min_score=float(min_score))
    return {"found": match is not None,
            "match": match.to_dict() if match else None}


def _match_masked_all(template: str, mask: Any = None, min_score: Any = 0.9,
                      max_results: Any = 20, nms_iou: Any = 0.3,
                      region: Any = None) -> Dict[str, Any]:
    """Adapter: every masked template match on the screen (NMS)."""
    import json
    from je_auto_control.utils.visual_match import match_masked_all
    if isinstance(region, str):
        region = json.loads(region) if region.strip() else None
    matches = match_masked_all(template, mask=mask, region=region,
                               min_score=float(min_score),
                               max_results=int(max_results),
                               nms_iou=float(nms_iou))
    return {"count": len(matches), "matches": [m.to_dict() for m in matches]}


def _seq_arg(value: Any, default: Sequence[float]) -> Sequence[float]:
    """Coerce a JSON-string / list arg into a tuple of floats, or the default."""
    import json
    if isinstance(value, str):
        value = json.loads(value) if value.strip() else None
    return tuple(float(v) for v in value) if value else tuple(default)


def _match_rotated(template: str, min_score: Any = 0.8, scales: Any = None,
                   angles: Any = None, region: Any = None,
                   method: str = "ccoeff_normed") -> Dict[str, Any]:
    """Adapter: best rotation/scale-tolerant template match on the screen."""
    import json
    from je_auto_control.utils.rotated_match import match_rotated
    if isinstance(region, str):
        region = json.loads(region) if region.strip() else None
    match = match_rotated(template, region=region,
                          scales=_seq_arg(scales, (1.0,)),
                          angles=_seq_arg(angles, (0.0,)),
                          min_score=float(min_score), method=method)
    return {"found": match is not None,
            "match": match.to_dict() if match else None}


def _match_rotated_all(template: str, min_score: Any = 0.8, scales: Any = None,
                       angles: Any = None, max_results: Any = 20,
                       nms_iou: Any = 0.3, region: Any = None) -> Dict[str, Any]:
    """Adapter: every rotation/scale-tolerant template match (NMS)."""
    import json
    from je_auto_control.utils.rotated_match import match_rotated_all
    if isinstance(region, str):
        region = json.loads(region) if region.strip() else None
    matches = match_rotated_all(template, region=region,
                                scales=_seq_arg(scales, (1.0,)),
                                angles=_seq_arg(angles, (0.0,)),
                                min_score=float(min_score),
                                max_results=int(max_results),
                                nms_iou=float(nms_iou))
    return {"count": len(matches), "matches": [m.to_dict() for m in matches]}


def _match_with_trust(template: str, min_score: Any = 0.0, scales: Any = None,
                      ambiguous_ratio: Any = 0.9, region: Any = None,
                      method: str = "ccoeff_normed") -> Dict[str, Any]:
    """Adapter: best template match with trust metrics (ambiguity / PSR)."""
    import json
    from je_auto_control.utils.match_trust import match_with_trust
    if isinstance(region, str):
        region = json.loads(region) if region.strip() else None
    match = match_with_trust(template, region=region,
                             scales=_seq_arg(scales, (1.0,)),
                             method=method, min_score=float(min_score),
                             ambiguous_ratio=float(ambiguous_ratio))
    return {"found": match is not None,
            "match": match.to_dict() if match else None}


def _auto_threshold(template: str, region: Any = None,
                    method: str = "ccoeff_normed") -> Dict[str, Any]:
    """Adapter: Otsu-derived accept threshold for a template (+ separability)."""
    import json
    from je_auto_control.utils.match_autothresh import auto_threshold
    if isinstance(region, str):
        region = json.loads(region) if region.strip() else None
    info = auto_threshold(template, region=region, method=method)
    return {"found": info is not None, "info": info}


def _match_auto(template: str, floor: Any = 0.5, max_results: Any = 20,
                region: Any = None, method: str = "ccoeff_normed") -> Dict[str, Any]:
    """Adapter: matches above the auto-derived (Otsu) threshold, one per region."""
    import json
    from je_auto_control.utils.match_autothresh import match_auto
    if isinstance(region, str):
        region = json.loads(region) if region.strip() else None
    matches = match_auto(template, region=region, floor=float(floor),
                         max_results=int(max_results), method=method)
    return {"count": len(matches), "matches": [m.to_dict() for m in matches]}


def _edge_match(template: str, min_score: Any = 0.7, scales: Any = None,
                region: Any = None) -> Dict[str, Any]:
    """Adapter: best edge-shape (Chamfer) template match on the screen."""
    import json
    from je_auto_control.utils.edge_match import edge_match
    if isinstance(region, str):
        region = json.loads(region) if region.strip() else None
    match = edge_match(template, region=region,
                       scales=_seq_arg(scales, (1.0,)), min_score=float(min_score))
    return {"found": match is not None,
            "match": match.to_dict() if match else None}


def _edge_match_all(template: str, min_score: Any = 0.7, max_results: Any = 20,
                    nms_iou: Any = 0.3, region: Any = None) -> Dict[str, Any]:
    """Adapter: every edge-shape (Chamfer) match on the screen (NMS)."""
    import json
    from je_auto_control.utils.edge_match import edge_match_all
    if isinstance(region, str):
        region = json.loads(region) if region.strip() else None
    matches = edge_match_all(template, region=region, min_score=float(min_score),
                             max_results=int(max_results), nms_iou=float(nms_iou))
    return {"count": len(matches), "matches": [m.to_dict() for m in matches]}


def _match_subpixel(template: str, min_score: Any = 0.0, region: Any = None,
                    method: str = "ccoeff_normed") -> Dict[str, Any]:
    """Adapter: best template match with a sub-pixel-refined centre."""
    import json
    from je_auto_control.utils.subpixel_match import match_subpixel
    if isinstance(region, str):
        region = json.loads(region) if region.strip() else None
    match = match_subpixel(template, region=region, method=method,
                           min_score=float(min_score))
    return {"found": match is not None,
            "match": match.to_dict() if match else None}


def _vote_centers(centers: Any, agree_px: Any = 10,
                  min_votes: Any = 2) -> Dict[str, Any]:
    """Adapter: vote candidate hit centres into a consensus target."""
    import json
    from je_auto_control.utils.match_ensemble import vote_centers
    if isinstance(centers, str):
        centers = json.loads(centers)
    result = vote_centers(centers, agree_px=float(agree_px),
                          min_votes=int(min_votes))
    return {"found": result is not None, "result": result}


def _match_ensemble(templates: Any, min_score: Any = 0.8, agree_px: Any = 10,
                    min_votes: Any = 2, region: Any = None) -> Dict[str, Any]:
    """Adapter: vote several template references onto one consensus location."""
    import json
    from je_auto_control.utils.match_ensemble import match_ensemble
    if isinstance(templates, str):
        templates = json.loads(templates)
    if isinstance(region, str):
        region = json.loads(region) if region.strip() else None
    result = match_ensemble(templates, region=region, min_score=float(min_score),
                            agree_px=float(agree_px), min_votes=int(min_votes))
    return {"found": result is not None, "result": result}


def _match_color(template: str, channels: Any = None, min_score: Any = 0.7,
                 scales: Any = None, region: Any = None) -> Dict[str, Any]:
    """Adapter: best colour (HSV-channel) template match on the screen."""
    import json
    from je_auto_control.utils.color_match import match_color
    if isinstance(channels, str):
        channels = json.loads(channels) if channels.strip() else None
    if isinstance(region, str):
        region = json.loads(region) if region.strip() else None
    match = match_color(template, region=region,
                        channels=tuple(channels) if channels else ("h", "s"),
                        scales=_seq_arg(scales, (1.0,)), min_score=float(min_score))
    return {"found": match is not None,
            "match": match.to_dict() if match else None}


def _match_color_all(template: str, channels: Any = None, min_score: Any = 0.7,
                     max_results: Any = 20, nms_iou: Any = 0.3,
                     region: Any = None) -> Dict[str, Any]:
    """Adapter: every colour (HSV-channel) match on the screen (NMS)."""
    import json
    from je_auto_control.utils.color_match import match_color_all
    if isinstance(channels, str):
        channels = json.loads(channels) if channels.strip() else None
    if isinstance(region, str):
        region = json.loads(region) if region.strip() else None
    matches = match_color_all(template, region=region,
                              channels=tuple(channels) if channels else ("h", "s"),
                              min_score=float(min_score),
                              max_results=int(max_results), nms_iou=float(nms_iou))
    return {"count": len(matches), "matches": [m.to_dict() for m in matches]}


def _region_stability(frames: Any, settle_threshold: Any = 0.99) -> Dict[str, Any]:
    """Adapter: how settled an injected frame sequence is (consecutive SSIM)."""
    import json
    from je_auto_control.utils.match_stability import region_stability
    if isinstance(frames, str):
        frames = json.loads(frames)
    return region_stability(frames, settle_threshold=float(settle_threshold))


def _match_persistence(template: str, frames: Any, min_score: Any = 0.8,
                       agree_px: Any = 8) -> Dict[str, Any]:
    """Adapter: whether a template match holds steady across frames."""
    import json
    from je_auto_control.utils.match_stability import match_persistence
    if isinstance(frames, str):
        frames = json.loads(frames)
    return match_persistence(template, frames, min_score=float(min_score),
                             agree_px=float(agree_px))


def _region_arg(value: Any) -> Optional[List[int]]:
    """Coerce a JSON-string / list region arg into a list of ints, or None."""
    import json
    if isinstance(value, str):
        value = json.loads(value) if value.strip() else None
    return [int(v) for v in value] if value else None


def _grid_cells(rows: Any, cols: Any, region: Any = None) -> Dict[str, Any]:
    """Adapter: every cell of an rows x cols labelled grid over the screen."""
    from je_auto_control.utils.screen_grid import grid_cells
    cells = grid_cells(int(rows), int(cols), region=_region_arg(region))
    return {"count": len(cells), "cells": [c.to_dict() for c in cells]}


def _cell_for_point(x: Any, y: Any, rows: Any, cols: Any,
                    region: Any = None) -> Dict[str, Any]:
    """Adapter: the grid cell containing a point (or found=False if outside)."""
    from je_auto_control.utils.screen_grid import cell_for_point
    cell = cell_for_point(int(x), int(y), int(rows), int(cols),
                          region=_region_arg(region))
    return {"found": cell is not None,
            "cell": cell.to_dict() if cell else None}


def _point_for_cell(label: str, rows: Any, cols: Any,
                    region: Any = None) -> Dict[str, Any]:
    """Adapter: the centre point of a named grid cell (ready to click)."""
    from je_auto_control.utils.screen_grid import point_for_cell
    point = point_for_cell(str(label), int(rows), int(cols),
                           region=_region_arg(region))
    return {"point": point}


def _populate_table(grid: Any, text_boxes: Any, overlap: Any = 0.4) -> Dict[str, Any]:
    """Adapter: fill a ruling-line grid with OCR text boxes → addressable table."""
    import json
    from je_auto_control.utils.table_grid_fill import populate_table
    if isinstance(grid, str):
        grid = json.loads(grid)
    if isinstance(text_boxes, str):
        text_boxes = json.loads(text_boxes)
    return populate_table(grid, text_boxes, overlap=float(overlap))


def _column_gutters(boxes: Any, page_width: Any = None,
                    min_gap: Any = 8) -> Dict[str, Any]:
    """Adapter: interior whitespace column gutters from OCR boxes."""
    import json
    from je_auto_control.utils.column_layout import column_gutters
    if isinstance(boxes, str):
        boxes = json.loads(boxes)
    gutters = column_gutters(boxes, page_width=int(page_width) if page_width
                             else None, min_gap=int(min_gap))
    return {"count": len(gutters), "gutters": gutters}


def _detect_borderless_table(boxes: Any, page_width: Any = None, min_gap: Any = 8,
                             min_cols: Any = 2, min_rows: Any = 2) -> Dict[str, Any]:
    """Adapter: infer a borderless table from OCR boxes via whitespace columns."""
    import json
    from je_auto_control.utils.column_layout import detect_borderless_table
    if isinstance(boxes, str):
        boxes = json.loads(boxes)
    table = detect_borderless_table(boxes,
                                    page_width=int(page_width) if page_width else None,
                                    min_gap=int(min_gap), min_cols=int(min_cols),
                                    min_rows=int(min_rows))
    return {"found": table is not None, "table": table}


def _associate_fields(text_boxes: Any, directions: Any = None,
                      max_gap: Any = 150) -> Dict[str, Any]:
    """Adapter: pair form labels with their nearest aligned value boxes."""
    import json
    from je_auto_control.utils.form_fields import associate_fields
    if isinstance(text_boxes, str):
        text_boxes = json.loads(text_boxes)
    if isinstance(directions, str):
        directions = json.loads(directions) if directions.strip() else None
    fields = associate_fields(text_boxes,
                              directions=tuple(directions) if directions
                              else ("right", "below"), max_gap=int(max_gap))
    return {"count": len(fields), "fields": fields}


def _match_labels_to_widgets(labels: Any, widgets: Any) -> Dict[str, Any]:
    """Adapter: match each widget (checkbox / radio / input) to its nearest label."""
    import json
    from je_auto_control.utils.form_fields import match_labels_to_widgets
    if isinstance(labels, str):
        labels = json.loads(labels)
    if isinstance(widgets, str):
        widgets = json.loads(widgets)
    pairs = match_labels_to_widgets(labels, widgets)
    return {"count": len(pairs), "pairs": pairs}


def _flow_order(boxes: Any, min_gap: Any = 12) -> Dict[str, Any]:
    """Adapter: column-aware reading order of OCR boxes (XY-cut)."""
    import json
    from je_auto_control.utils.reading_flow import flow_order
    if isinstance(boxes, str):
        boxes = json.loads(boxes)
    ordered = flow_order(boxes, min_gap=int(min_gap))
    return {"count": len(ordered), "elements": ordered}


def _xy_cut(boxes: Any, min_gap: Any = 12) -> Dict[str, Any]:
    """Adapter: recursive XY-cut region tree of OCR boxes."""
    import json
    from je_auto_control.utils.reading_flow import xy_cut
    if isinstance(boxes, str):
        boxes = json.loads(boxes)
    return {"tree": xy_cut(boxes, min_gap=int(min_gap))}


def _group_paragraphs(lines: Any, line_gap_factor: Any = 1.6) -> Dict[str, Any]:
    """Adapter: group OCR lines into paragraphs by vertical spacing."""
    import json
    from je_auto_control.utils.text_blocks import group_paragraphs
    if isinstance(lines, str):
        lines = json.loads(lines)
    paragraphs = group_paragraphs(lines, line_gap_factor=float(line_gap_factor))
    return {"count": len(paragraphs), "paragraphs": paragraphs}


def _detect_lists(lines: Any) -> Dict[str, Any]:
    """Adapter: detect bulleted / numbered list items among OCR lines."""
    import json
    from je_auto_control.utils.text_blocks import detect_lists
    if isinstance(lines, str):
        lines = json.loads(lines)
    items = detect_lists(lines)
    return {"count": len(items), "items": items}


def _classify_lines(lines: Any, heading_ratio: Any = 1.2) -> Dict[str, Any]:
    """Adapter: classify OCR lines as headings vs body with levels."""
    import json
    from je_auto_control.utils.heading_segment import classify_lines
    if isinstance(lines, str):
        lines = json.loads(lines)
    classified = classify_lines(lines, heading_ratio=float(heading_ratio))
    return {"count": len(classified), "lines": classified}


def _outline(lines: Any, heading_ratio: Any = 1.2) -> Dict[str, Any]:
    """Adapter: the document outline (headings in order) from OCR lines."""
    import json
    from je_auto_control.utils.heading_segment import outline
    if isinstance(lines, str):
        lines = json.loads(lines)
    headings = outline(lines, heading_ratio=float(heading_ratio))
    return {"count": len(headings), "headings": headings}


def _find_color_region(rgb: Any, tolerance: Any = 20, min_area: Any = 50,
                       region: Any = None) -> Dict[str, Any]:
    """Adapter: locate coloured regions on the screen, largest first."""
    import json
    from je_auto_control.utils.color_region import find_color_regions
    if isinstance(rgb, str):
        rgb = json.loads(rgb)
    if isinstance(region, str):
        region = json.loads(region) if region.strip() else None
    regions = find_color_regions(list(rgb), region=region,
                                 tolerance=int(tolerance),
                                 min_area=int(min_area))
    return {"count": len(regions), "regions": regions,
            "best": regions[0] if regions else None}


def _ssim_compare(reference: str, current: Any = None, ignore: Any = None,
                  region: Any = None) -> Dict[str, Any]:
    """Adapter: structural-similarity score between reference and current/screen."""
    import json
    from je_auto_control.utils.ssim import ssim_compare
    if isinstance(ignore, str):
        ignore = json.loads(ignore) if ignore.strip() else None
    if isinstance(region, str):
        region = json.loads(region) if region.strip() else None
    score = ssim_compare(reference, current, ignore=ignore, region=region)
    return {"score": score}


def _ssim_changed_regions(reference: str, current: Any = None, ignore: Any = None,
                          threshold: Any = 0.35, min_area: Any = 50,
                          region: Any = None) -> Dict[str, Any]:
    """Adapter: boxes of the regions that structurally changed, largest first."""
    import json
    from je_auto_control.utils.ssim import ssim_changed_regions
    if isinstance(ignore, str):
        ignore = json.loads(ignore) if ignore.strip() else None
    if isinstance(region, str):
        region = json.loads(region) if region.strip() else None
    regions = ssim_changed_regions(reference, current, ignore=ignore,
                                   threshold=float(threshold),
                                   min_area=int(min_area), region=region)
    return {"count": len(regions), "regions": regions}


def _feature_match(template: str, region: Any = None, max_features: Any = 500,
                   ratio: Any = 0.75, min_inliers: Any = 10) -> Dict[str, Any]:
    """Adapter: locate a template by ORB keypoints (rotation/scale/theme robust)."""
    import json
    from je_auto_control.utils.feature_match import feature_match
    if isinstance(region, str):
        region = json.loads(region) if region.strip() else None
    match = feature_match(template, region=region, max_features=int(max_features),
                          ratio=float(ratio), min_inliers=int(min_inliers))
    return {"found": match is not None,
            "match": match.to_dict() if match else None}


def _find_shapes(region: Any = None, min_area: Any = 400,
                 max_area: Any = None) -> Dict[str, Any]:
    """Adapter: bounding boxes of all distinct on-screen shapes, largest first."""
    import json
    from je_auto_control.utils.shape_locator import find_shapes
    if isinstance(region, str):
        region = json.loads(region) if region.strip() else None
    shapes = find_shapes(region=region, min_area=int(min_area),
                         max_area=int(max_area) if max_area is not None else None)
    return {"count": len(shapes), "shapes": shapes}


def _find_rectangles(region: Any = None, min_area: Any = 400, max_area: Any = None,
                     aspect_range: Any = None, epsilon: Any = 0.04
                     ) -> Dict[str, Any]:
    """Adapter: boxes of the ~rectangular shapes (buttons / cards), largest first."""
    import json
    from je_auto_control.utils.shape_locator import find_rectangles
    if isinstance(region, str):
        region = json.loads(region) if region.strip() else None
    if isinstance(aspect_range, str):
        aspect_range = json.loads(aspect_range) if aspect_range.strip() else None
    rects = find_rectangles(
        region=region, min_area=int(min_area),
        max_area=int(max_area) if max_area is not None else None,
        aspect_range=tuple(aspect_range) if aspect_range else None,
        epsilon=float(epsilon))
    return {"count": len(rects), "rectangles": rects}


def _resolve_screen(screen: Any) -> list:
    """Parse a JSON screen rect, or default to the live primary screen work area."""
    import json
    if isinstance(screen, str):
        screen = json.loads(screen) if screen.strip() else None
    if screen:
        return list(screen)
    from je_auto_control.wrapper.auto_control_screen import screen_size
    width, height = screen_size()
    return [0, 0, int(width), int(height)]


def _tile_rect(slot: str, screen: Any = None, gap: Any = 0) -> Dict[str, Any]:
    """Adapter: rectangle for a named tiling slot of the screen work area."""
    from je_auto_control.utils.window_layout import tile_rect
    rect = tile_rect(_resolve_screen(screen), str(slot), gap=int(gap))
    return {"rect": rect.to_dict()}


def _grid_rects(rows: Any, cols: Any, screen: Any = None,
                gap: Any = 0) -> Dict[str, Any]:
    """Adapter: one rectangle per cell of an rows x cols grid over the screen."""
    from je_auto_control.utils.window_layout import grid_rects
    rects = grid_rects(_resolve_screen(screen), int(rows), int(cols), gap=int(gap))
    return {"count": len(rects), "rects": [rect.to_dict() for rect in rects]}


def _cascade_rects(count: Any, screen: Any = None, offset: Any = 30,
                   size: Any = None) -> Dict[str, Any]:
    """Adapter: count staggered, overlapping window rectangles (a cascade)."""
    import json
    from je_auto_control.utils.window_layout import cascade_rects
    if isinstance(size, str):
        size = json.loads(size) if size.strip() else None
    rects = cascade_rects(_resolve_screen(screen), int(count), offset=int(offset),
                          size=tuple(size) if size else None)
    return {"count": len(rects), "rects": [rect.to_dict() for rect in rects]}


def _preprocess_image(output_path: str, source: Any = None, steps: Any = None,
                      scale: Any = 2.0, region: Any = None, block_size: Any = 31,
                      c: Any = 11) -> Dict[str, Any]:
    """Adapter: run the preprocessing pipeline and write the result to a file."""
    import json
    import cv2
    from je_auto_control.utils.preprocess import preprocess_image
    if isinstance(steps, str):
        steps = (json.loads(steps) if steps.strip().startswith("[")
                 else [part.strip() for part in steps.split(",") if part.strip()])
    if isinstance(region, str):
        region = json.loads(region) if region.strip() else None
    result = preprocess_image(
        source, region=region,
        steps=tuple(steps) if steps else ("grayscale", "upscale", "binarize"),
        scale=float(scale), block_size=int(block_size), c=int(c))
    if not cv2.imwrite(str(output_path), result):
        raise AutoControlActionException(f"could not write image: {output_path!r}")
    return {"path": str(output_path), "width": int(result.shape[1]),
            "height": int(result.shape[0])}


def _enumerate_monitors() -> Dict[str, Any]:
    """Adapter: list connected monitors with virtual-desktop geometry."""
    from je_auto_control.utils.monitor_layout import (
        enumerate_monitors, virtual_bounds)
    monitors = enumerate_monitors()
    bounds = virtual_bounds(monitors) if monitors else (0, 0, 0, 0)
    return {"count": len(monitors),
            "monitors": [monitor.to_dict() for monitor in monitors],
            "virtual_bounds": list(bounds)}


def _monitor_at_point(x: Any, y: Any) -> Dict[str, Any]:
    """Adapter: report which monitor contains a virtual point."""
    from je_auto_control.utils.monitor_layout import (
        enumerate_monitors, monitor_at_point)
    monitor = monitor_at_point(enumerate_monitors(), int(x), int(y))
    return {"found": monitor is not None,
            "monitor": monitor.to_dict() if monitor else None}


def _region_pixel_token(bbox):
    """Stability token: a hash of the bbox region's pixels (changes on movement)."""
    from je_auto_control.utils.cv2_utils.screenshot import pil_screenshot
    left, top, width, height = bbox
    image = pil_screenshot(screen_region=[left, top, left + width, top + height])
    return hash(image.tobytes())


def _wait_actionable(template: str, timeout_s: Any = 5.0, stable_for_s: Any = 0.3,
                     min_score: Any = 0.8, region: Any = None) -> Dict[str, Any]:
    """Adapter: wait until a template is visible + stable before acting."""
    import json
    from je_auto_control.utils.actionability import GateConfig, wait_actionable
    from je_auto_control.utils.visual_match import match_template
    if isinstance(region, str):
        region = json.loads(region) if region.strip() else None

    def locate():
        match = match_template(template, region=region, min_score=float(min_score))
        return (match.x, match.y, match.width, match.height) if match else None

    report = wait_actionable(
        locate, region_sampler=_region_pixel_token,
        config=GateConfig(timeout_s=float(timeout_s),
                          stable_for_s=float(stable_for_s)))
    return report.to_dict()


def _fuse_elements(ocr: Any = None, icon: Any = None, a11y: Any = None,
                   iou_threshold: Any = 0.9) -> Dict[str, Any]:
    """Adapter: union OCR / icon / a11y element boxes, dropping duplicates."""
    import json
    from je_auto_control.utils.element_parse import fuse_elements

    def parse(value: Any) -> list:
        if isinstance(value, str):
            return json.loads(value) if value.strip() else []
        return list(value) if value else []

    elements = fuse_elements(parse(ocr), parse(icon), parse(a11y),
                             iou_threshold=float(iou_threshold))
    return {"count": len(elements), "elements": elements}


def _reading_order(elements: Any, row_tol: Any = 12) -> Dict[str, Any]:
    """Adapter: order element boxes top-to-bottom, left-to-right, with an index."""
    import json
    from je_auto_control.utils.element_parse import reading_order
    if isinstance(elements, str):
        elements = json.loads(elements)
    ordered = reading_order(list(elements), row_tol=int(row_tol))
    return {"count": len(ordered), "elements": ordered}


def _segment_hsv(lower_hsv: Any, upper_hsv: Any, min_area: Any = 50,
                 region: Any = None) -> Dict[str, Any]:
    """Adapter: locate blobs inside an explicit HSV band on the screen."""
    import json
    from je_auto_control.utils.hsv_segment import segment_hsv
    if isinstance(lower_hsv, str):
        lower_hsv = json.loads(lower_hsv)
    if isinstance(upper_hsv, str):
        upper_hsv = json.loads(upper_hsv)
    if isinstance(region, str):
        region = json.loads(region) if region.strip() else None
    boxes = segment_hsv(region=region, lower_hsv=list(lower_hsv),
                        upper_hsv=list(upper_hsv), min_area=int(min_area))
    return {"count": len(boxes), "regions": boxes,
            "best": boxes[0] if boxes else None}


def _dominant_hue_regions(hue: Any, hue_tol: Any = 10, sat_min: Any = 80,
                          val_min: Any = 80, min_area: Any = 50,
                          region: Any = None) -> Dict[str, Any]:
    """Adapter: locate any-brightness regions near a hue on the screen."""
    import json
    from je_auto_control.utils.hsv_segment import dominant_hue_regions
    if isinstance(region, str):
        region = json.loads(region) if region.strip() else None
    boxes = dominant_hue_regions(region=region, hue=int(hue), hue_tol=int(hue_tol),
                                 sat_min=int(sat_min), val_min=int(val_min),
                                 min_area=int(min_area))
    return {"count": len(boxes), "regions": boxes,
            "best": boxes[0] if boxes else None}


def _find_text_regions(min_area: Any = 60, max_area: Any = None, merge: Any = True,
                       max_aspect: Any = 12.0, region: Any = None) -> Dict[str, Any]:
    """Adapter: locate text/glyph regions on screen via MSER (no OCR)."""
    import json
    from je_auto_control.utils.text_regions import find_text_regions
    if isinstance(region, str):
        region = json.loads(region) if region.strip() else None
    regions = find_text_regions(
        region=region, min_area=int(min_area),
        max_area=int(max_area) if max_area is not None else None,
        merge=bool(merge), max_aspect=float(max_aspect))
    return {"count": len(regions), "regions": regions}


def _find_text_lines(y_tolerance: Any = 8, region: Any = None) -> Dict[str, Any]:
    """Adapter: locate horizontal text lines on screen via MSER (no OCR)."""
    import json
    from je_auto_control.utils.text_regions import find_text_lines
    if isinstance(region, str):
        region = json.loads(region) if region.strip() else None
    lines = find_text_lines(region=region, y_tolerance=int(y_tolerance))
    return {"count": len(lines), "lines": lines}


def _find_lines(min_length: Any = 80, max_gap: Any = 10, orientation: str = "any",
                region: Any = None) -> Dict[str, Any]:
    """Adapter: detect straight line segments on screen (Hough)."""
    import json
    from je_auto_control.utils.edge_lines import find_lines
    if isinstance(region, str):
        region = json.loads(region) if region.strip() else None
    lines = find_lines(region=region, min_length=int(min_length),
                       max_gap=int(max_gap), orientation=str(orientation))
    return {"count": len(lines), "lines": lines}


def _find_grid(min_length: Any = 120, tol: Any = 10,
               region: Any = None) -> Dict[str, Any]:
    """Adapter: recover a table grid (rows / cols / cells) from screen lines."""
    import json
    from je_auto_control.utils.edge_lines import find_grid
    if isinstance(region, str):
        region = json.loads(region) if region.strip() else None
    return find_grid(region=region, min_length=int(min_length), tol=int(tol))


def _find_separators(axis: str = "horizontal", min_length: Any = 120, tol: Any = 10,
                     region: Any = None) -> Dict[str, Any]:
    """Adapter: coordinates of long divider lines along an axis."""
    import json
    from je_auto_control.utils.edge_lines import find_separators
    if isinstance(region, str):
        region = json.loads(region) if region.strip() else None
    coords = find_separators(region=region, axis=str(axis),
                             min_length=int(min_length), tol=int(tol))
    return {"count": len(coords), "axis": str(axis), "coordinates": coords}


def _expect_poll(action: Any, key: Any = None, op: str = "truthy",
                 expected: Any = None, timeout_s: Any = 5.0,
                 interval_s: Any = 0.25) -> Dict[str, Any]:
    """Adapter: re-run a nested action until a key of its result matches."""
    import json
    from je_auto_control.utils.expect_poll import (
        expect_poll, to_be_greater_than, to_be_truthy, to_contain, to_equal,
        to_match_regex)
    if isinstance(action, str):
        action = json.loads(action)
    builders = {"equals": lambda: to_equal(expected),
                "contains": lambda: to_contain(expected),
                "gt": lambda: to_be_greater_than(expected),
                "regex": lambda: to_match_regex(str(expected)),
                "truthy": to_be_truthy}
    matcher = builders.get(str(op), to_be_truthy)()

    def getter():
        record = executor.execute_action([list(action)])
        value = next(iter(record.values()), None)
        if key is not None and isinstance(value, dict):
            return value.get(key)
        return value

    result = expect_poll(getter, matcher, timeout_s=float(timeout_s),
                         interval_s=float(interval_s))
    return {"ok": result.ok, "value": result.value, "attempts": result.attempts,
            "waited_s": result.waited_s}


def _apply_locate_op(candidates, op: Dict[str, Any]):
    """Apply one locate-chain op spec to a Candidates set."""
    name = op.get("op")
    if name == "within":
        return candidates.within(op["region"])
    if name == "filter":
        return candidates.filter(has_text=op.get("has_text"), near=op.get("near"),
                                 min_area=op.get("min_area"),
                                 max_area=op.get("max_area"))
    if name == "reading":
        return candidates.sort_reading(row_tol=int(op.get("row_tol", 12)))
    if name == "nth":
        return candidates.nth(int(op["index"]))
    if name == "first":
        return candidates.first()
    if name == "last":
        return candidates.last()
    raise AutoControlActionException(f"unknown locate-chain op: {name!r}")


def _locate_chain(boxes: Any, ops: Any = None) -> Dict[str, Any]:
    """Adapter: apply a chain of refinement ops to a set of element boxes."""
    import json
    from je_auto_control.utils.locator_chain import from_boxes
    if isinstance(boxes, str):
        boxes = json.loads(boxes)
    if isinstance(ops, str):
        ops = json.loads(ops) if ops.strip() else []
    candidates = from_boxes(list(boxes))
    for op in ops or ():
        candidates = _apply_locate_op(candidates, op)
    resolved = candidates.resolve()
    return {"count": len(resolved), "boxes": resolved,
            "center": candidates.center()}


def _set_clipboard_html(html: str, fragment_plaintext: Any = None
                        ) -> Dict[str, Any]:
    """Adapter: put an HTML fragment on the clipboard as CF_HTML (Windows)."""
    from je_auto_control.utils.rich_clipboard import set_clipboard_html
    set_clipboard_html(str(html), fragment_plaintext=fragment_plaintext)
    return {"set": True, "length": len(str(html))}


def _get_clipboard_html() -> Dict[str, Any]:
    """Adapter: read the clipboard's HTML fragment (Windows)."""
    from je_auto_control.utils.rich_clipboard import get_clipboard_html
    html = get_clipboard_html()
    return {"found": html is not None, "html": html}


def _set_clipboard_files(paths: Any) -> Dict[str, Any]:
    """Adapter: put a file-drop list (CF_HDROP) on the clipboard (Windows)."""
    import json
    from je_auto_control.utils.clipboard_files import set_clipboard_files
    if isinstance(paths, str):
        paths = json.loads(paths) if paths.strip().startswith("[") else [paths]
    paths = [str(p) for p in paths]
    set_clipboard_files(paths)
    return {"set": True, "count": len(paths)}


def _get_clipboard_files() -> Dict[str, Any]:
    """Adapter: read the clipboard's file-drop list (CF_HDROP) (Windows)."""
    from je_auto_control.utils.clipboard_files import get_clipboard_files
    paths = get_clipboard_files()
    return {"found": paths is not None, "paths": paths or []}


def _set_clipboard_rtf(text: str) -> Dict[str, Any]:
    """Adapter: put text on the clipboard as Rich Text Format (Windows)."""
    from je_auto_control.utils.clipboard_rich_formats import set_clipboard_rtf
    set_clipboard_rtf(str(text))
    return {"set": True, "length": len(str(text))}


def _get_clipboard_rtf() -> Dict[str, Any]:
    """Adapter: read the clipboard's RTF document string (Windows)."""
    from je_auto_control.utils.clipboard_rich_formats import get_clipboard_rtf
    rtf = get_clipboard_rtf()
    return {"found": rtf is not None, "rtf": rtf}


def _set_clipboard_csv(rows: Any, delimiter: str = ",") -> Dict[str, Any]:
    """Adapter: put a table on the clipboard as the Csv format (Windows)."""
    import json
    from je_auto_control.utils.clipboard_rich_formats import set_clipboard_csv
    if isinstance(rows, str):
        rows = json.loads(rows)
    set_clipboard_csv(rows, delimiter=str(delimiter))
    return {"set": True, "rows": len(rows)}


def _get_clipboard_csv(delimiter: str = ",") -> Dict[str, Any]:
    """Adapter: read the clipboard's Csv content as rows (Windows)."""
    from je_auto_control.utils.clipboard_rich_formats import get_clipboard_csv
    rows = get_clipboard_csv(delimiter=str(delimiter))
    return {"found": rows is not None, "rows": rows or []}


def _clipboard_formats() -> Dict[str, Any]:
    """Adapter: enumerate and classify the live clipboard's formats (Windows)."""
    from je_auto_control.utils.clipboard_formats import clipboard_formats
    return clipboard_formats()


def _classify_formats(formats: Any) -> Dict[str, Any]:
    """Adapter: classify a provided list of clipboard formats (pure)."""
    import json
    from je_auto_control.utils.clipboard_formats import classify_formats
    if isinstance(formats, str):
        formats = json.loads(formats)
    return classify_formats(formats)


def _diff_formats(before: Any, after: Any) -> Dict[str, Any]:
    """Adapter: diff two clipboard-format snapshots (pure)."""
    import json
    from je_auto_control.utils.clipboard_formats import diff_formats
    if isinstance(before, str):
        before = json.loads(before)
    if isinstance(after, str):
        after = json.loads(after)
    return diff_formats(before, after)


def _coerce_paths(paths: Any) -> list:
    """Normalise a paths argument (JSON list string / single path / list)."""
    import json
    if isinstance(paths, str):
        paths = json.loads(paths) if paths.strip().startswith("[") else [paths]
    return [str(p) for p in paths]


def _coerce_point(point: Any) -> tuple:
    """Normalise a point argument (JSON '[x,y]' / list / default origin)."""
    import json
    if isinstance(point, str):
        point = json.loads(point) if point.strip().startswith("[") else (0, 0)
    if not point:
        return (0, 0)
    return (int(point[0]), int(point[1]))


def _plan_file_drop(paths: Any, point: Any = None) -> Dict[str, Any]:
    """Adapter: build the WM_DROPFILES payload without sending (pure)."""
    from je_auto_control.utils.file_drop import plan_file_drop
    return plan_file_drop(_coerce_paths(paths), point=_coerce_point(point))


def _drop_files(hwnd: Any, paths: Any, point: Any = None) -> Dict[str, Any]:
    """Adapter: drop files onto a window via WM_DROPFILES (Windows)."""
    from je_auto_control.utils.file_drop import drop_files
    coerced = _coerce_paths(paths)
    dropped = drop_files(int(hwnd), coerced, point=_coerce_point(point))
    return {"dropped": bool(dropped), "count": len(coerced)}


def _coerce_region(region: Any):
    """Normalise a region argument (JSON '[x,y,w,h]' string / list / None)."""
    import json
    if isinstance(region, str):
        return json.loads(region) if region.strip() else None
    return region


def _image_quality(source: Any = None, region: Any = None) -> Dict[str, Any]:
    """Adapter: sharpness / contrast / brightness of an image or the screen."""
    from je_auto_control.utils.image_quality import image_quality
    return image_quality(source, region=_coerce_region(region))


def _quality_gate(source: Any = None, region: Any = None,
                  min_sharpness: Any = 100.0,
                  min_contrast: Any = 12.0) -> Dict[str, Any]:
    """Adapter: pass / fail an image for OCR readability with named issues."""
    from je_auto_control.utils.image_quality import quality_gate
    return quality_gate(source, region=_coerce_region(region),
                        min_sharpness=float(min_sharpness),
                        min_contrast=float(min_contrast))


def _coerce_scales(scales: Any):
    """Normalise a scales argument (JSON '[1.0,1.5]' string / list / None)."""
    import json
    if isinstance(scales, str):
        return json.loads(scales) if scales.strip() else None
    return scales


def _detect_scale(template: Any, haystack: Any = None, region: Any = None,
                  scales: Any = None,
                  method: str = "ccoeff_normed") -> Dict[str, Any]:
    """Adapter: infer the display scale a template renders at (visual DPI)."""
    from je_auto_control.utils.scale_detect import detect_scale
    result = detect_scale(template, haystack, region=_coerce_region(region),
                          scales=_coerce_scales(scales), method=str(method))
    return {"found": result is not None, "result": result}


def _scale_sweep(template: Any, haystack: Any = None, region: Any = None,
                 scales: Any = None,
                 method: str = "ccoeff_normed") -> Dict[str, Any]:
    """Adapter: per-scale match-score profile of a template."""
    from je_auto_control.utils.scale_detect import scale_sweep
    return {"sweep": scale_sweep(template, haystack,
                                 region=_coerce_region(region),
                                 scales=_coerce_scales(scales),
                                 method=str(method))}


def _salient_regions(source: Any = None, region: Any = None, size: Any = 64,
                     threshold: Any = None, min_area: Any = 4) -> Dict[str, Any]:
    """Adapter: ranked visually-salient regions of an image / the screen."""
    from je_auto_control.utils.saliency import salient_regions
    cut = float(threshold) if threshold not in (None, "") else None
    regions = salient_regions(source, region=_coerce_region(region),
                              size=int(size), threshold=cut,
                              min_area=int(min_area))
    return {"regions": regions, "count": len(regions)}


def _most_salient(source: Any = None, region: Any = None, size: Any = 64,
                  threshold: Any = None, min_area: Any = 4) -> Dict[str, Any]:
    """Adapter: the single most visually-salient region (where to look)."""
    from je_auto_control.utils.saliency import most_salient
    cut = float(threshold) if threshold not in (None, "") else None
    result = most_salient(source, region=_coerce_region(region),
                          size=int(size), threshold=cut, min_area=int(min_area))
    return {"found": result is not None, "region": result}


def _failure_signature(error: str, length: Any = 12) -> Dict[str, Any]:
    """Adapter: normalise + hash an error message to a stable signature."""
    from je_auto_control.utils.failure_signature import (
        failure_signature, normalize_error)
    return {"signature": failure_signature(str(error), length=int(length)),
            "normalized": normalize_error(str(error))}


def _group_failures(errors: Any) -> Dict[str, Any]:
    """Adapter: group error messages by failure signature."""
    import json
    from je_auto_control.utils.failure_signature import group_failures
    if isinstance(errors, str):
        errors = json.loads(errors)
    groups = group_failures(errors)
    return {"groups": groups, "count": len(groups)}


def _diff_runs(before: Any, after: Any, key: str = "name",
               regress_factor: Any = 1.5) -> Dict[str, Any]:
    """Adapter: diff two run step-traces (added/removed/flips/regressions)."""
    import json
    from je_auto_control.utils.run_diff import diff_runs, summarize_run_diff
    if isinstance(before, str):
        before = json.loads(before)
    if isinstance(after, str):
        after = json.loads(after)
    diff = diff_runs(before, after, key=str(key),
                     regress_factor=float(regress_factor))
    return {**diff, "summary": summarize_run_diff(diff)}


def _failure_clusters(runs: Any, threshold: Any = 0.5,
                      min_size: Any = 2) -> Dict[str, Any]:
    """Adapter: cluster tests that fail together (co-failure Jaccard)."""
    import json
    from je_auto_control.utils.flake_cluster import failure_clusters
    if isinstance(runs, str):
        runs = json.loads(runs)
    clusters = failure_clusters(runs, threshold=float(threshold),
                                min_size=int(min_size))
    return {"clusters": clusters, "count": len(clusters)}


def _cofailure_pairs(runs: Any, threshold: Any = 0.5) -> Dict[str, Any]:
    """Adapter: test pairs that fail together above a Jaccard threshold."""
    import json
    from je_auto_control.utils.flake_cluster import cofailure_pairs
    if isinstance(runs, str):
        runs = json.loads(runs)
    pairs = cofailure_pairs(runs, threshold=float(threshold))
    return {"pairs": pairs, "count": len(pairs)}


def _build_timeline(steps: Any) -> Dict[str, Any]:
    """Adapter: a per-run step waterfall (offsets / durations / bottleneck)."""
    import json
    from je_auto_control.utils.step_timeline import build_timeline
    if isinstance(steps, str):
        steps = json.loads(steps)
    return build_timeline(steps)


def _critical_steps(steps: Any, top: Any = 3) -> Dict[str, Any]:
    """Adapter: the steps that dominate a run's time (bottlenecks)."""
    import json
    from je_auto_control.utils.step_timeline import critical_steps
    if isinstance(steps, str):
        steps = json.loads(steps)
    return {"steps": critical_steps(steps, top=int(top))}


def _image_histogram(source: Any = None, bins: Any = 32, space: str = "hsv",
                     region: Any = None) -> Dict[str, Any]:
    """Adapter: per-channel colour histogram of an image / the screen."""
    import json
    from je_auto_control.utils.img_histogram import image_histogram
    if isinstance(region, str):
        region = json.loads(region) if region.strip() else None
    hist = image_histogram(source, region=region, bins=int(bins), space=str(space))
    return {"bins": int(bins), "space": str(space), "histogram": hist}


def _histogram_changed(reference: str, current: Any = None, method: str =
                       "correlation", threshold: Any = 0.9, space: str = "hsv",
                       region: Any = None) -> Dict[str, Any]:
    """Adapter: whether the screen / current image differs from a reference."""
    import json
    from je_auto_control.utils.img_histogram import (compare_histograms,
                                                     histogram_changed,
                                                     image_histogram)
    if isinstance(region, str):
        region = json.loads(region) if region.strip() else None
    changed = histogram_changed(reference, current, region=region,
                                method=str(method), threshold=float(threshold),
                                space=str(space))
    ref_hist = image_histogram(reference, space=str(space))
    cur_hist = (image_histogram(current, space=str(space)) if current is not None
                else image_histogram(region=region, space=str(space)))
    return {"changed": changed,
            "score": compare_histograms(ref_hist, cur_hist, method=str(method))}


def _changed_regions(before: str, after: Any = None, threshold: Any = 25,
                     min_area: Any = 80, blur: Any = 5) -> Dict[str, Any]:
    """Adapter: boxes of regions that moved between two frames (after=screen)."""
    from je_auto_control.utils.motion_regions import changed_regions
    regions = changed_regions(before, _resolve_after(after), threshold=int(threshold),
                              min_area=int(min_area), blur=int(blur))
    return {"count": len(regions), "regions": regions}


def _has_motion(before: str, after: Any = None, threshold: Any = 25,
                min_area: Any = 80) -> Dict[str, Any]:
    """Adapter: whether anything moved between two frames (after=screen)."""
    from je_auto_control.utils.motion_regions import activity_score, has_motion
    resolved = _resolve_after(after)
    return {"moved": has_motion(before, resolved, threshold=int(threshold),
                                min_area=int(min_area)),
            "activity": activity_score(before, resolved, threshold=int(threshold))}


def _resolve_after(after: Any):
    """Return the 'after' frame, grabbing the screen when it is not given."""
    if after is not None:
        return after
    import numpy as np
    from je_auto_control.utils.cv2_utils.screenshot import pil_screenshot
    return np.asarray(pil_screenshot().convert("RGB"))


def _set_topmost(title: str, on: Any = True) -> Dict[str, Any]:
    """Adapter: pin a window always-on-top (or release it)."""
    from je_auto_control.utils.window_zorder import set_topmost
    return {"applied": set_topmost(title, bool(on))}


def _bring_to_front(title: str) -> Dict[str, Any]:
    """Adapter: raise a window to the top of the z-order."""
    from je_auto_control.utils.window_zorder import bring_to_front
    return {"applied": bring_to_front(title)}


def _send_to_back(title: str) -> Dict[str, Any]:
    """Adapter: send a window to the bottom of the z-order."""
    from je_auto_control.utils.window_zorder import send_to_back
    return {"applied": send_to_back(title)}


def _eval_check(op: str, value: Any, expected: Any) -> bool:
    """Evaluate one soft-assert check by operator name."""
    table = {"eq": lambda: value == expected,
             "ne": lambda: value != expected,
             "gt": lambda: value > expected,
             "lt": lambda: value < expected,
             "contains": lambda: expected in value,
             "truthy": lambda: bool(value)}
    if op not in table:
        raise AutoControlActionException(f"unknown soft-assert op: {op!r}")
    return bool(table[op]())


def _soft_assert(checks: Any, raise_on_fail: Any = False) -> Dict[str, Any]:
    """Adapter: aggregate a list of {value, op, expected, message} checks."""
    import json
    from je_auto_control.utils.soft_assert import SoftAssertions
    if isinstance(checks, str):
        checks = json.loads(checks)
    soft = SoftAssertions(raise_on_exit=False)
    for check in checks or ():
        op = str(check.get("op", "truthy"))
        ok = _eval_check(op, check.get("value"), check.get("expected"))
        soft.check(ok, check.get("message", "")
                   or f"{check.get('value')!r} {op} {check.get('expected')!r}")
    if raise_on_fail:
        soft.assert_all()
    return {"ok": not soft.failures, "passed": soft.passed,
            "failures": soft.failures}


def _perceptual_diff(actual: str, expected: str, threshold: Any = 0.1,
                     include_aa: Any = False,
                     max_diff_ratio: Any = None) -> Dict[str, Any]:
    """Adapter: perceptual (YIQ) image diff with anti-alias suppression."""
    from je_auto_control.utils.perceptual_diff import perceptual_diff
    result = perceptual_diff(actual, expected, threshold=float(threshold),
                             include_aa=bool(include_aa))
    if max_diff_ratio is not None and result.diff_ratio > float(max_diff_ratio):
        raise AutoControlActionException(
            f"perceptual diff {result.diff_ratio} exceeds {max_diff_ratio}")
    return {"diff_pixels": result.diff_pixels, "total_pixels": result.total_pixels,
            "diff_ratio": result.diff_ratio, "regions": result.regions}


def _get_client_rect(title: str) -> Dict[str, Any]:
    """Adapter: a window's client-area rect in screen coordinates."""
    from je_auto_control.utils.window_geometry import get_client_rect
    rect = get_client_rect(title)
    return {"found": rect is not None,
            "rect": list(rect) if rect is not None else None}


def _client_point(title: str, x: Any, y: Any) -> Dict[str, Any]:
    """Adapter: screen point for a client-area-local (x, y) inside a window."""
    from je_auto_control.utils.window_geometry import client_point
    point = client_point(title, int(x), int(y))
    return {"found": point is not None,
            "point": list(point) if point is not None else None}


def _cua_command(payload: Any, source: str = "canonical") -> Dict[str, Any]:
    """Adapter: normalize a computer-use payload and map it to an AC_* command."""
    import json
    from je_auto_control.utils.cua_action import (from_anthropic, from_openai_cua,
                                                  to_ac_command)
    if isinstance(payload, str):
        payload = json.loads(payload)
    normalizers = {"anthropic": from_anthropic, "openai": from_openai_cua,
                   "canonical": dict}
    if source not in normalizers:
        raise AutoControlActionException(f"unknown cua source: {source!r}")
    canonical = normalizers[source](payload)
    return {"canonical": canonical, "command": to_ac_command(canonical)}


def _serialize_observation(elements: Any, viewport: Any = None,
                           max_elements: Any = 80) -> Dict[str, Any]:
    """Adapter: render an indexed a11y text observation from element dicts."""
    import json
    from je_auto_control.utils.observation import (observation_index,
                                                   serialize_observation)
    if isinstance(elements, str):
        elements = json.loads(elements)
    if isinstance(viewport, str):
        viewport = json.loads(viewport) if viewport.strip() else None
    text = serialize_observation(list(elements), viewport=viewport,
                                 max_elements=int(max_elements))
    indexed = observation_index(list(elements), viewport=viewport,
                                max_elements=int(max_elements))
    return {"observation": text, "count": len(indexed)}


def _observation_index(elements: Any, viewport: Any = None,
                       max_elements: Any = 80) -> Dict[str, Any]:
    """Adapter: the on-screen elements in reading order, capped, each indexed."""
    import json
    from je_auto_control.utils.observation import observation_index
    if isinstance(elements, str):
        elements = json.loads(elements)
    if isinstance(viewport, str):
        viewport = json.loads(viewport) if viewport.strip() else None
    indexed = observation_index(list(elements), viewport=viewport,
                                max_elements=int(max_elements))
    return {"count": len(indexed), "elements": indexed}


def _delta_observation(prev: Any, curr: Any, viewport: Any = None,
                       max_elements: Any = 80, max_lines: Any = 40,
                       interactive_only: Any = True) -> Dict[str, Any]:
    """Adapter: token-budgeted "what changed" delta between two element frames."""
    import json
    from je_auto_control.utils.observation_delta import (delta_index,
                                                         delta_observation)
    if isinstance(prev, str):
        prev = json.loads(prev)
    if isinstance(curr, str):
        curr = json.loads(curr)
    if isinstance(viewport, str):
        viewport = json.loads(viewport) if viewport.strip() else None
    text = delta_observation(list(prev), list(curr), viewport=viewport,
                             max_elements=int(max_elements),
                             interactive_only=bool(interactive_only),
                             max_lines=int(max_lines))
    delta = delta_index(list(prev), list(curr))
    return {"summary": text, "added": len(delta["added"]),
            "removed": len(delta["removed"]), "changed": len(delta["changed"])}


def _classify_effect(before: Any, after: Any, action: Any,
                     radius: Any = 64) -> Dict[str, Any]:
    """Adapter: classify whether an action changed the screen (target-local)."""
    import json
    from je_auto_control.utils.action_effect import classify_effect
    if isinstance(before, str):
        before = json.loads(before)
    if isinstance(after, str):
        after = json.loads(after)
    if isinstance(action, str):
        action = json.loads(action)
    return classify_effect(before, after, action, radius=int(radius)).to_dict()


def _effect_near_point(before: Any, after: Any, point: Any,
                       radius: Any = 64) -> Dict[str, Any]:
    """Adapter: did any before/after change land within radius of a point."""
    import json
    from je_auto_control.utils.action_effect import effect_near_point
    if isinstance(before, str):
        before = json.loads(before)
    if isinstance(after, str):
        after = json.loads(after)
    if isinstance(point, str):
        point = json.loads(point)
    return {"near": effect_near_point(before, after, point, radius=int(radius))}


def _check_postcondition(after: Any, spec: Any, before: Any = None) -> Dict[str, Any]:
    """Adapter: evaluate a declarative postcondition spec against after/before frames."""
    import json
    from je_auto_control.utils.postcondition import check_postcondition
    if isinstance(after, str):
        after = json.loads(after)
    if isinstance(spec, str):
        spec = json.loads(spec)
    if isinstance(before, str):
        before = json.loads(before) if before.strip() else None
    return check_postcondition(after, spec, before=before).to_dict()


def _plan_repair(verdict: Any, max_attempts: Any = 3) -> Dict[str, Any]:
    """Adapter: ordered repair tactics for an effect verdict (no_op / changed_…)."""
    import json
    from je_auto_control.utils.step_repair import RepairPolicy, plan_repair
    if isinstance(verdict, str) and verdict.strip().startswith("{"):
        verdict = json.loads(verdict)
    tactics = plan_repair(verdict,
                          policy=RepairPolicy(max_attempts=int(max_attempts)))
    return {"count": len(tactics), "tactics": tactics}


def _consensus_point(candidates: Any, cluster_radius: Any = 24) -> Dict[str, Any]:
    """Adapter: agreed target point from clustered grounding proposals."""
    import json
    from je_auto_control.utils.grounding_consensus import consensus_point
    if isinstance(candidates, str):
        candidates = json.loads(candidates)
    result = consensus_point(candidates, cluster_radius=float(cluster_radius))
    return {"found": result is not None,
            "result": result.to_dict() if result else None}


def _consensus_element(candidates: Any, elements: Any) -> Dict[str, Any]:
    """Adapter: vote grounding proposals to the nearest element."""
    import json
    from je_auto_control.utils.grounding_consensus import consensus_element
    if isinstance(candidates, str):
        candidates = json.loads(candidates)
    if isinstance(elements, str):
        elements = json.loads(elements)
    winner = consensus_element(candidates, elements)
    return {"found": winner is not None,
            "element": winner[0] if winner else None,
            "agreement": winner[1] if winner else 0.0}


def _settle_point(churns: Any, quiet_samples: Any = 3,
                  max_churn: Any = 1.0) -> Dict[str, Any]:
    """Adapter: index at which a churn series first settles (or settled=False)."""
    import json
    from je_auto_control.utils.settle_detector import settle_point
    if isinstance(churns, str):
        churns = json.loads(churns)
    index = settle_point([float(c) for c in churns],
                         quiet_samples=int(quiet_samples),
                         max_churn=float(max_churn))
    return {"settled": index is not None, "index": index}


def _build_critic_record(action: Any, before: Any, after: Any,
                         postcondition: Any = None, radius: Any = 64) -> Dict[str, Any]:
    """Adapter: per-step critic feature bundle (effect + delta + postcondition)."""
    import json
    from je_auto_control.utils.critic_features import build_critic_record
    if isinstance(action, str):
        action = json.loads(action)
    if isinstance(before, str):
        before = json.loads(before)
    if isinstance(after, str):
        after = json.loads(after)
    if isinstance(postcondition, str):
        postcondition = json.loads(postcondition) if postcondition.strip() else None
    return build_critic_record(action, before, after, postcondition=postcondition,
                               radius=int(radius))


def _score_step(record: Any) -> Dict[str, Any]:
    """Adapter: rule-based score of a critic record."""
    import json
    from je_auto_control.utils.critic_features import score_step_rule_based
    if isinstance(record, str):
        record = json.loads(record)
    return score_step_rule_based(record)


def _validate_action(action: Any, screen: Any = None,
                     targets: Any = None) -> Dict[str, Any]:
    """Adapter: validate a coordinate action (bounds + optional snap-to-target)."""
    import json
    from je_auto_control.utils.action_grounding import validate_action
    if isinstance(action, str):
        action = json.loads(action)
    if isinstance(targets, str):
        targets = json.loads(targets) if targets.strip() else None
    if isinstance(screen, str):
        screen = json.loads(screen) if screen.strip() else None
    if not screen:
        from je_auto_control.wrapper.auto_control_screen import screen_size
        screen = list(screen_size())
    return validate_action(action, screen_size=screen,
                           targets=list(targets) if targets else None)


def _replay_trace(trace: Any) -> Dict[str, Any]:
    """Adapter: replay a trajectory by running each step's action via the executor."""
    import json
    from je_auto_control.utils.agent_replay import from_jsonl, replay_trace
    if isinstance(trace, str):
        trace = (json.loads(trace) if trace.strip().startswith("[")
                 else from_jsonl(trace))

    def runner(action):
        record = executor.execute_action([list(action)])
        return next(iter(record.values()), None)

    results = replay_trace(list(trace), runner)
    return {"count": len(results), "results": results}


def _match_elements(before: Any, after: Any,
                    iou_threshold: Any = 0.5) -> Dict[str, Any]:
    """Adapter: geometry-aware match of two element-box lists."""
    import json
    from je_auto_control.utils.element_diff import match_elements
    if isinstance(before, str):
        before = json.loads(before)
    if isinstance(after, str):
        after = json.loads(after)
    result = match_elements(list(before), list(after),
                            iou_threshold=float(iou_threshold))
    return {"matched": result["matched"], "added": result["added"],
            "removed": result["removed"]}


def _assign_stable_ids(elements: Any, prior: Any = None,
                       iou_threshold: Any = 0.5) -> Dict[str, Any]:
    """Adapter: tag element boxes with stable IDs carried from a prior frame."""
    import json
    from je_auto_control.utils.element_diff import assign_stable_ids
    if isinstance(elements, str):
        elements = json.loads(elements)
    if isinstance(prior, str):
        prior = json.loads(prior) if prior.strip() else None
    tagged = assign_stable_ids(list(elements),
                               prior=list(prior) if prior else None,
                               iou_threshold=float(iou_threshold))
    return {"count": len(tagged), "elements": tagged}


def _score_candidates(candidates: Any, want_role: Any = None, want_name: Any = None,
                      anchor: Any = None) -> Dict[str, Any]:
    """Adapter: rank candidate element boxes by role / name / proximity."""
    import json
    from je_auto_control.utils.element_scoring import score_candidates
    if isinstance(candidates, str):
        candidates = json.loads(candidates)
    if isinstance(anchor, str):
        anchor = json.loads(anchor) if anchor.strip() else None
    ranked = score_candidates(list(candidates), want_role=want_role,
                              want_name=want_name, anchor=anchor)
    return {"count": len(ranked), "scored": [c.to_dict() for c in ranked]}


def _best_candidate(candidates: Any, want_role: Any = None, want_name: Any = None,
                    anchor: Any = None) -> Dict[str, Any]:
    """Adapter: the single highest-scoring candidate element."""
    import json
    from je_auto_control.utils.element_scoring import best_candidate
    if isinstance(candidates, str):
        candidates = json.loads(candidates)
    if isinstance(anchor, str):
        anchor = json.loads(anchor) if anchor.strip() else None
    best = best_candidate(list(candidates), want_role=want_role,
                          want_name=want_name, anchor=anchor)
    return {"found": best is not None,
            "best": best.to_dict() if best is not None else None}


def _read_barcodes(source: Any = None, region: Any = None) -> Dict[str, Any]:
    """Adapter: decode 1-D barcodes on screen / in an image."""
    import json
    from je_auto_control.utils.barcode import read_barcodes
    if isinstance(region, str):
        region = json.loads(region) if region.strip() else None
    barcodes = read_barcodes(source, region=region)
    return {"count": len(barcodes), "barcodes": barcodes}


def _with_modifiers(modifiers: Any, actions: Any) -> Dict[str, Any]:
    """Adapter: run nested actions while modifier keys are held down."""
    import json
    from je_auto_control.utils.modifier_state import hold_modifiers
    if isinstance(modifiers, str):
        modifiers = (json.loads(modifiers) if modifiers.strip().startswith("[")
                     else [part.strip() for part in modifiers.split("+")])
    if isinstance(actions, str):
        actions = json.loads(actions)
    with hold_modifiers(list(modifiers)):
        record = executor.execute_action(list(actions), raise_on_error=True)
    return {"modifiers": list(modifiers), "record": record}


def _cas_put(name: str, key: str, value: Any,
             expected_version: Any = None) -> Dict[str, Any]:
    """Adapter: optimistic put into a named versioned store."""
    import json
    from je_auto_control.utils.optimistic import VersionConflict, VersionedStore
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            pass
    store = _VERSIONED_STORES.setdefault(name, VersionedStore())
    expected = int(expected_version) if expected_version is not None else None
    try:
        version = store.put(key, value, expected_version=expected)
    except VersionConflict as error:
        return {"ok": False, "error": str(error)}
    return {"ok": True, "version": version}


def _cas_get(name: str, key: str) -> Dict[str, Any]:
    """Adapter: read a record from a named versioned store."""
    from je_auto_control.utils.optimistic import VersionedStore
    store = _VERSIONED_STORES.setdefault(name, VersionedStore())
    return {"record": store.get(key)}


def _sequence_observe(name: str, stream_id: str, seq: Any) -> Dict[str, Any]:
    """Adapter: observe a sequence number in a named tracker."""
    from je_auto_control.utils.sequence_gap import SequenceTracker
    tracker = _SEQUENCE_TRACKERS.setdefault(name, SequenceTracker())
    return tracker.observe(stream_id, int(seq))


def _dedup_check(name: str, message_id: str,
                 ttl_s: Any = 3600) -> Dict[str, Any]:
    """Adapter: check-and-mark a message id in a named dedup window."""
    from je_auto_control.utils.dedup_window import DedupWindow
    window = _DEDUP_WINDOWS.setdefault(name, DedupWindow(float(ttl_s)))
    return {"first_seen": window.check_and_mark(message_id),
            "size": window.size()}


def _idempotency_begin(name: str, key: str,
                       request: Any = None) -> Dict[str, Any]:
    """Adapter: register/look up an idempotency key in a named store."""
    from je_auto_control.utils.idempotency import (
        IdempotencyStore, request_fingerprint)
    store = _IDEMPOTENCY_STORES.setdefault(name, IdempotencyStore())
    fingerprint = request_fingerprint(request) if request is not None else None
    return store.begin(key, fingerprint)


def _idempotency_complete(name: str, key: str,
                          response: Any) -> Dict[str, Any]:
    """Adapter: store the completed response for an idempotency key."""
    from je_auto_control.utils.idempotency import IdempotencyStore
    store = _IDEMPOTENCY_STORES.setdefault(name, IdempotencyStore())
    store.complete(key, response)
    return {"status": "completed"}


def _bulkhead_run(name: str, max_concurrent: int,
                  actions: Any) -> Dict[str, Any]:
    """Adapter: run an action list under a named bulkhead permit."""
    import json
    from je_auto_control.utils.bulkhead import Bulkhead, BulkheadFullError
    if isinstance(actions, str):
        actions = json.loads(actions)
    bulkhead = _BULKHEADS.setdefault(
        name, Bulkhead(int(max_concurrent), name=name))
    try:
        with bulkhead:
            record = executor.execute_action(list(actions), raise_on_error=True)
    except BulkheadFullError:
        return {"entered": False, "in_flight": bulkhead.in_flight}
    return {"entered": True, "in_flight": bulkhead.in_flight, "record": record}


def _retry_after(response: Any) -> Dict[str, Any]:
    """Adapter: server-advised wait from a response (dict or JSON string)."""
    import json
    from je_auto_control.utils.bulkhead import next_delay
    if isinstance(response, str):
        response = json.loads(response)
    return {"delay": next_delay(response)}


def _http_replay(cassette: Any, url: str,
                 method: str = "GET") -> Dict[str, Any]:
    """Adapter: replay a recorded HTTP response from a cassette (no network)."""
    import json
    from je_auto_control.utils.http_cassette import Cassette
    if isinstance(cassette, str):
        cassette = json.loads(cassette)
    interactions = (cassette.get("interactions", [])
                    if isinstance(cassette, dict) else cassette)
    response = Cassette(interactions).replay(
        {"method": str(method).upper(), "url": url})
    return {"response": response}


def _trace_inject(headers: Any = None,
                  traceparent: Any = None) -> Dict[str, Any]:
    """Adapter: propagate a trace context into outgoing headers.

    With ``traceparent`` set, derive a child span of that parent; otherwise
    start a fresh root. Returns the updated ``headers`` plus the new ids.
    """
    import json
    from je_auto_control.utils.trace_context import (
        child_context, inject_context, new_root_context, parse_traceparent)
    if isinstance(headers, str):
        headers = json.loads(headers)
    ctx = (child_context(parse_traceparent(traceparent))
           if traceparent else new_root_context())
    return {"headers": inject_context(headers, ctx),
            "traceparent": inject_context({}, ctx)["traceparent"],
            "trace_id": ctx.trace_id, "span_id": ctx.span_id}


def _trace_extract(headers: Any) -> Dict[str, Any]:
    """Adapter: extract a trace context from request headers."""
    import json
    from je_auto_control.utils.trace_context import extract_context
    if isinstance(headers, str):
        headers = json.loads(headers)
    ctx = extract_context(headers)
    return {"context": ctx.to_dict() if ctx is not None else None}


def _validate_config(schema: Any, config: Any) -> Dict[str, Any]:
    """Adapter: validate a config mapping against a schema spec."""
    import json
    from je_auto_control.utils.config_schema import validate_config
    if isinstance(schema, str):
        schema = json.loads(schema)
    if isinstance(config, str):
        config = json.loads(config)
    return validate_config(schema, config)


def _resolve_ref(ref: str) -> Dict[str, Any]:
    """Adapter: resolve an env:// / file:// / secret:// reference."""
    from je_auto_control.utils.secret_ref import resolve_ref
    return {"value": resolve_ref(ref)}


def _resolve_refs(obj: Any) -> Dict[str, Any]:
    """Adapter: recursively resolve references in a structure (or JSON str)."""
    import json
    from je_auto_control.utils.secret_ref import resolve_refs_in
    if isinstance(obj, str):
        obj = json.loads(obj)
    return {"resolved": resolve_refs_in(obj)}


def _redact_config(obj: Any, mask: str = "***") -> Dict[str, Any]:
    """Adapter: redact secret-looking values from a config structure."""
    import json
    from je_auto_control.utils.config_redaction import redact_config
    if isinstance(obj, str):
        obj = json.loads(obj)
    return {"redacted": redact_config(obj, mask=mask)}


def _redact_secret_text(text: str, mask: str = "***") -> Dict[str, Any]:
    """Adapter: mask secret-looking tokens within a free-text string."""
    from je_auto_control.utils.config_redaction import redact_secret_text
    return {"text": redact_secret_text(text, mask=mask)}


def _parse_cache_control(headers: Any) -> Dict[str, Any]:
    """Adapter: parse a Cache-Control header into {directives}."""
    import json
    from je_auto_control.utils.http_conditional import parse_cache_control
    if isinstance(headers, str):
        headers = json.loads(headers)
    return {"directives": parse_cache_control(headers)}


def _store_validators(response: Any) -> Dict[str, Any]:
    """Adapter: extract cache validators from an HTTP response."""
    import json
    from je_auto_control.utils.http_conditional import store_validators
    if isinstance(response, str):
        response = json.loads(response)
    return {"validators": store_validators(response)}


def _cookie_header(set_cookies: Any) -> Dict[str, Any]:
    """Adapter: build a Cookie header from one/many Set-Cookie strings."""
    import json
    from je_auto_control.utils.cookie_jar import CookieJar
    if isinstance(set_cookies, str) and set_cookies.strip().startswith("["):
        set_cookies = json.loads(set_cookies)
    jar = CookieJar().update(set_cookies)
    return {"cookie_header": jar.cookie_header(), "cookies": jar.to_dict()}


def _parse_set_cookie(header: str) -> Dict[str, Any]:
    """Adapter: parse one Set-Cookie header into its components."""
    from je_auto_control.utils.cookie_jar import parse_set_cookie
    return {"cookie": parse_set_cookie(header)}


def _decode_body(headers: Any, body_base64: str) -> Dict[str, Any]:
    """Adapter: decode a Content-Encoding (gzip/deflate) base64 body."""
    import base64
    import json
    from je_auto_control.utils.http_content import decode_body
    if isinstance(headers, str):
        headers = json.loads(headers)
    decoded = decode_body(headers, base64.b64decode(body_base64))
    try:
        text: Any = decoded.decode("utf-8")
    except UnicodeDecodeError:
        text = None
    return {"body_base64": base64.b64encode(decoded).decode("ascii"),
            "text": text}


def _parse_quality_values(header: str) -> Dict[str, Any]:
    """Adapter: parse a quality-value header into {values}."""
    from je_auto_control.utils.http_content import parse_quality_values
    return {"values": [list(item) for item in parse_quality_values(header)]}


def _build_multipart(fields: Any = None, files: Any = None,
                     boundary: Any = None) -> Dict[str, Any]:
    """Adapter: build a multipart/form-data body (base64-encoded)."""
    import base64
    import json
    from je_auto_control.utils.multipart import build_multipart
    if isinstance(fields, str):
        fields = json.loads(fields)
    if isinstance(files, str):
        files = json.loads(files)
    content_type, body = build_multipart(fields, files, boundary=boundary)
    return {"content_type": content_type,
            "body_base64": base64.b64encode(body).decode("ascii")}


def _parse_multipart(content_type: str, body_base64: str) -> Dict[str, Any]:
    """Adapter: parse a base64-encoded multipart body into {fields, files}."""
    import base64
    from je_auto_control.utils.multipart import parse_multipart
    body = base64.b64decode(body_base64)
    return parse_multipart(content_type, body)


def _parse_link_header(value: str) -> Dict[str, Any]:
    """Adapter: parse an RFC 8288 Link header into {links}."""
    from je_auto_control.utils.link_header import parse_link_header
    return {"links": [link.to_dict() for link in parse_link_header(value)]}


def _next_url(value: str) -> Dict[str, Any]:
    """Adapter: return the rel=next URL from a Link header."""
    from je_auto_control.utils.link_header import next_url
    return {"url": next_url(value)}


def _baggage_parse(header: str) -> Dict[str, Any]:
    """Adapter: parse a W3C baggage header into {items}."""
    from je_auto_control.utils.baggage import parse_baggage
    return {"items": parse_baggage(header).to_dict()}


def _normalize_text(text: str, form: str = "NFKC", casefold: Any = True,
                    collapse_ws: Any = True) -> Dict[str, Any]:
    """Adapter: Unicode-normalise text into {text}."""
    from je_auto_control.utils.text_normalize import normalize_text
    return {"text": normalize_text(text, form=form, casefold=bool(casefold),
                                   collapse_ws=bool(collapse_ws))}


def _slugify(text: str, sep: str = "-") -> Dict[str, Any]:
    """Adapter: produce an ASCII slug from text."""
    from je_auto_control.utils.text_normalize import slugify
    return {"slug": slugify(text, sep=sep)}


def _text_similarity(a: str, b: str,
                     metric: str = "jaro_winkler") -> Dict[str, Any]:
    """Adapter: normalised string similarity for the chosen metric."""
    from je_auto_control.utils.text_similarity import similarity
    return {"score": similarity(a, b, metric=metric)}


def _simhash(text: str, bits: Any = 64) -> Dict[str, Any]:
    """Adapter: SimHash fingerprint of text (as int)."""
    from je_auto_control.utils.near_dup import simhash
    return {"simhash": simhash(text, bits=int(bits))}


def _near_duplicates(texts: Any, max_distance: Any = 3) -> Dict[str, Any]:
    """Adapter: cluster near-duplicate texts by SimHash distance."""
    import json
    from je_auto_control.utils.near_dup import near_duplicates
    if isinstance(texts, str):
        texts = json.loads(texts)
    return {"clusters": near_duplicates(texts, max_distance=int(max_distance))}


def _canonical_log(fields: Any) -> Dict[str, Any]:
    """Adapter: build a canonical log line from a fields dict."""
    import json
    from je_auto_control.utils.canonical_log import CanonicalLogLine
    if isinstance(fields, str):
        fields = json.loads(fields)
    line = CanonicalLogLine(fields)
    return {"line": line.to_dict(), "json": line.render()}


def _spans_to_otlp(spans: Any, resource_attrs: Any = None) -> Dict[str, Any]:
    """Adapter: wrap spans in an OTLP/JSON resourceSpans envelope."""
    import json
    from je_auto_control.utils.otlp_export import spans_to_otlp
    if isinstance(spans, str):
        spans = json.loads(spans)
    if isinstance(resource_attrs, str):
        resource_attrs = json.loads(resource_attrs)
    return {"payload": spans_to_otlp(spans, resource_attrs=resource_attrs)}


def _baggage_format(items: Any) -> Dict[str, Any]:
    """Adapter: serialise an items dict into a W3C baggage {header}."""
    import json
    from je_auto_control.utils.baggage import Baggage, format_baggage
    if isinstance(items, str):
        items = json.loads(items)
    return {"header": format_baggage(Baggage(items))}


def _profile_rows(rows: Any, columns: Any = None) -> Dict[str, Any]:
    """Adapter: profile a row-set into per-column statistics."""
    import json
    from je_auto_control.utils.data_profile import profile_rows
    if isinstance(rows, str):
        rows = json.loads(rows)
    if isinstance(columns, str):
        columns = json.loads(columns)
    return {"profile": profile_rows(rows, columns)}


def _infer_schema(rows: Any, columns: Any = None) -> Dict[str, Any]:
    """Adapter: infer a validate_rows-compatible schema from rows."""
    import json
    from je_auto_control.utils.data_profile import infer_schema
    if isinstance(rows, str):
        rows = json.loads(rows)
    if isinstance(columns, str):
        columns = json.loads(columns)
    return {"schema": infer_schema(rows, columns)}


def _parse_problem(response: Any) -> Dict[str, Any]:
    """Adapter: parse an RFC 9457 problem+json HTTP response."""
    import json
    from je_auto_control.utils.http_problem import parse_problem
    if isinstance(response, str):
        response = json.loads(response)
    problem = parse_problem(response)
    return {"problem": problem.to_dict() if problem is not None else None}


def _parse_dotenv(text: str) -> Dict[str, Any]:
    """Adapter: parse .env text into a {values} dict."""
    from je_auto_control.utils.dotenv import parse_dotenv
    return {"values": parse_dotenv(text)}


def _load_dotenv(path: str, override: Any = False) -> Dict[str, Any]:
    """Adapter: load a .env file into a fresh {values} dict."""
    from je_auto_control.utils.dotenv import load_dotenv
    return {"values": load_dotenv(path, {}, override=bool(override))}


def _parse_sse(text: str) -> Dict[str, Any]:
    """Adapter: parse a text/event-stream blob into {events}."""
    from je_auto_control.utils.sse_client import parse_event_stream
    return {"events": [event.to_dict() for event in parse_event_stream(text)]}


def _build_layered_config(layers: Any):
    """Build a LayeredConfig from a list of {name, mapping, priority?} dicts."""
    import json
    from je_auto_control.utils.layered_config import LayeredConfig
    if isinstance(layers, str):
        layers = json.loads(layers)
    config = LayeredConfig()
    for layer in layers:
        config.add_layer(layer["name"], layer.get("mapping", {}),
                         layer.get("priority"))
    return config


def _resolve_config(layers: Any) -> Dict[str, Any]:
    """Adapter: deep-merge config layers into a resolved {config}."""
    return {"config": _build_layered_config(layers).resolve()}


def _explain_config(layers: Any, key: str) -> Dict[str, Any]:
    """Adapter: report the value and winning layer for a dotted config key."""
    trace = _build_layered_config(layers).explain(key)
    return {"trace": {"key": trace.key, "value": trace.value,
                      "layer": trace.layer}}


def _check_compatibility(old: Any, new: Any,
                         mode: str = "backward") -> Dict[str, Any]:
    """Adapter: classify JSON-Schema compatibility (backward/forward/full)."""
    import json
    from je_auto_control.utils.schema_compat import check_compatibility
    if isinstance(old, str):
        old = json.loads(old)
    if isinstance(new, str):
        new = json.loads(new)
    return check_compatibility(old, new, mode)


def _detect_drift(reference: Any, current: Any,
                  threshold: Any = 0.25, bins: Any = 10) -> Dict[str, Any]:
    """Adapter: numeric distribution drift report (PSI + KS)."""
    import json
    from je_auto_control.utils.data_drift import detect_drift
    if isinstance(reference, str):
        reference = json.loads(reference)
    if isinstance(current, str):
        current = json.loads(current)
    return detect_drift(reference, current,
                        threshold=float(threshold), bins=int(bins))


def _categorical_drift(reference: Any, current: Any) -> Dict[str, Any]:
    """Adapter: categorical distribution drift summary."""
    import json
    from je_auto_control.utils.data_drift import categorical_drift
    if isinstance(reference, str):
        reference = json.loads(reference)
    if isinstance(current, str):
        current = json.loads(current)
    return categorical_drift(reference, current)


def _json_rows(rows: Any) -> Any:
    import json
    return json.loads(rows) if isinstance(rows, str) else rows


def _check_foreign_key(child_rows: Any, child_col: str, parent_rows: Any,
                       parent_col: str) -> Dict[str, Any]:
    """Adapter: foreign-key referential check across two row-sets."""
    from je_auto_control.utils.referential import check_foreign_key
    return check_foreign_key(_json_rows(child_rows), child_col,
                             _json_rows(parent_rows), parent_col)


def _check_unique_key(rows: Any, cols: Any) -> Dict[str, Any]:
    """Adapter: single/composite key uniqueness check."""
    import json
    from je_auto_control.utils.referential import check_unique_key
    if isinstance(cols, str) and cols.strip().startswith("["):
        cols = json.loads(cols)
    return check_unique_key(_json_rows(rows), cols)


def _check_accepted_values(rows: Any, col: str, allowed: Any) -> Dict[str, Any]:
    """Adapter: accepted-values check for a column."""
    from je_auto_control.utils.referential import check_accepted_values
    return check_accepted_values(_json_rows(rows), col, _json_rows(allowed))


def _check_row_count(rows: Any, minimum: Any = None,
                     maximum: Any = None) -> Dict[str, Any]:
    """Adapter: row-count bounds check."""
    from je_auto_control.utils.referential import check_row_count
    low = int(minimum) if minimum is not None else None
    high = int(maximum) if maximum is not None else None
    return check_row_count(_json_rows(rows), low, high)


def _coerce_diff_inputs(old_rows: Any, new_rows: Any, key: Any):
    import json
    if isinstance(old_rows, str):
        old_rows = json.loads(old_rows)
    if isinstance(new_rows, str):
        new_rows = json.loads(new_rows)
    if isinstance(key, str) and key.strip().startswith("["):
        key = json.loads(key)
    return old_rows, new_rows, key


def _diff_rows(old_rows: Any, new_rows: Any, key: Any) -> Dict[str, Any]:
    """Adapter: diff two row-sets by key into {diff, summary}."""
    from je_auto_control.utils.dataset_diff import diff_rows, summarize_diff
    old_rows, new_rows, key = _coerce_diff_inputs(old_rows, new_rows, key)
    diff = diff_rows(old_rows, new_rows, key)
    return {"diff": diff, "summary": summarize_diff(diff)}


def _cell_changes(old_rows: Any, new_rows: Any, key: Any) -> Dict[str, Any]:
    """Adapter: per-cell changes between two row-sets keyed by key."""
    from je_auto_control.utils.dataset_diff import cell_changes
    old_rows, new_rows, key = _coerce_diff_inputs(old_rows, new_rows, key)
    return {"changes": cell_changes(old_rows, new_rows, key)}


def _percentiles(samples: Any, qs: Any = None) -> Dict[str, Any]:
    """Adapter: exact percentiles of a numeric sample list (or JSON string)."""
    import json
    from je_auto_control.utils.percentiles import exact_percentiles
    if isinstance(samples, str):
        samples = json.loads(samples)
    if isinstance(qs, str):
        qs = json.loads(qs)
    quantiles = tuple(qs) if qs else (50, 90, 95, 99)
    result = exact_percentiles(samples, qs=quantiles)
    return {"percentiles": {str(q): value for q, value in result.items()}}


def _ts_rate(series: Any, window_s: Any = None) -> Dict[str, Any]:
    """Adapter: per-second counter rate over a (ts, value) series."""
    import json
    from je_auto_control.utils.timeseries import ts_rate
    if isinstance(series, str):
        series = json.loads(series)
    window = float(window_s) if window_s is not None else None
    return {"rate": ts_rate(series, window_s=window)}


def _ts_downsample(series: Any, bucket_s: Any,
                   agg: str = "avg") -> Dict[str, Any]:
    """Adapter: downsample a (ts, value) series into tumbling buckets."""
    import json
    from je_auto_control.utils.timeseries import ts_downsample
    if isinstance(series, str):
        series = json.loads(series)
    buckets = ts_downsample(series, float(bucket_s), agg)
    return {"buckets": [list(point) for point in buckets]}


def _detect_anomalies(values: Any, method: str = "mad",
                      threshold: Any = None) -> Dict[str, Any]:
    """Adapter: flag anomalies in a numeric series (mad/zscore)."""
    import json
    from je_auto_control.utils.anomaly import detect_anomalies
    if isinstance(values, str):
        values = json.loads(values)
    return {"results": detect_anomalies(values, method=method,
                                        threshold=threshold)}


def _sma(values: Any, window: Any) -> Dict[str, Any]:
    """Adapter: trailing simple moving average."""
    import json
    from je_auto_control.utils.smoothing import sma
    if isinstance(values, str):
        values = json.loads(values)
    return {"series": sma(values, int(window))}


def _ewma(values: Any, alpha: Any = 0.3) -> Dict[str, Any]:
    """Adapter: exponentially-weighted moving average."""
    import json
    from je_auto_control.utils.smoothing import ewma
    if isinstance(values, str):
        values = json.loads(values)
    return {"series": ewma(values, alpha=float(alpha))}


def _evaluate_slo(records: Any, target: float,
                  window_s: Optional[float] = None) -> Dict[str, Any]:
    """Adapter: SLI + error budget for outcome records (list or JSON string)."""
    import json
    from je_auto_control.utils.slo import evaluate_slo
    if isinstance(records, str):
        records = json.loads(records)
    return evaluate_slo(records, float(target), window_s=window_s)


def _burn_alerts(records: Any, target: float) -> Dict[str, Any]:
    """Adapter: multi-window burn-rate alerts for outcome records."""
    import json
    from je_auto_control.utils.slo import burn_alerts
    if isinstance(records, str):
        records = json.loads(records)
    alerts = burn_alerts(records, float(target))
    return {"alerts": alerts, "firing": bool(alerts)}


def _chaos_probe_call(actions: List[Any]) -> Any:
    def call() -> bool:
        executor.execute_action(list(actions), raise_on_error=True)
        return True
    return call


def _chaos_fault_apply(actions: List[Any]) -> Any:
    def apply() -> Dict[str, Any]:
        return executor.execute_action(list(actions), raise_on_error=True)
    return apply


def _run_chaos(spec: Any) -> Dict[str, Any]:
    """Adapter: run a chaos experiment whose probes/method/rollbacks are actions."""
    import json
    from je_auto_control.utils.chaos import (
        ChaosExperiment, Fault, Probe, run_experiment)
    if isinstance(spec, str):
        spec = json.loads(spec)
    probes = [Probe(p.get("name", "probe"), _chaos_probe_call(p["action"]), True)
              for p in spec.get("probes", [])]
    method = [Fault(f.get("name", "fault"), _chaos_fault_apply(f["action"]))
              for f in spec.get("method", [])]
    rollbacks = [_chaos_fault_apply(actions)
                 for actions in spec.get("rollbacks", [])]
    experiment = ChaosExperiment(spec.get("title", "chaos"), probes, method,
                                 rollbacks)
    return run_experiment(experiment)


def _match_json(actual: Any, expected: Any, partial: bool = False,
                match_type: bool = False) -> Dict[str, Any]:
    """Adapter: match a JSON payload against an expected one (relaxed rules)."""
    import json
    from je_auto_control.utils.json_contract import match_json
    if isinstance(actual, str):
        actual = json.loads(actual)
    if isinstance(expected, str):
        expected = json.loads(expected)
    return match_json(actual, expected, partial=bool(partial),
                      match_type=bool(match_type)).to_dict()


def _diff_json(actual: Any, expected: Any) -> Dict[str, Any]:
    """Adapter: path-tagged diff between two JSON payloads."""
    import json
    from je_auto_control.utils.json_contract import diff_json
    if isinstance(actual, str):
        actual = json.loads(actual)
    if isinstance(expected, str):
        expected = json.loads(expected)
    return {"diffs": diff_json(actual, expected)}


def _build_provenance(paths: Any, builder_id: str = "je_auto_control",
                      build_type: str = "https://je-auto-control/buildtype/v1"
                      ) -> Dict[str, Any]:
    """Adapter: build a SLSA provenance statement over a list of file paths."""
    import json
    from je_auto_control.utils.provenance import build_provenance, subject_for
    if isinstance(paths, str):
        paths = json.loads(paths)
    subjects = [subject_for(path) for path in paths]
    return {"statement": build_provenance(
        subjects, builder_id=builder_id, build_type=build_type)}


def _verify_provenance(statement: Any, files: Any) -> Dict[str, Any]:
    """Adapter: re-hash files (name->path) against a provenance statement."""
    import json
    from je_auto_control.utils.provenance import verify_provenance
    if isinstance(statement, str):
        statement = json.loads(statement)
    if isinstance(files, str):
        files = json.loads(files)
    mismatches = verify_provenance(statement, files)
    return {"ok": not mismatches, "mismatches": mismatches}


def _evaluate_flag(flags: Any, key: str, context: Any = None) -> Dict[str, Any]:
    """Adapter: evaluate a feature flag (flags/context dict or JSON string)."""
    import json
    from je_auto_control.utils.feature_flags import FlagStore, evaluate_flag
    if isinstance(flags, str):
        flags = json.loads(flags)
    if isinstance(context, str):
        context = json.loads(context)
    return evaluate_flag(FlagStore.from_dict(flags), key, context or {})


def _flag_enabled(flags: Any, key: str, context: Any = None,
                  default: bool = False) -> Dict[str, Any]:
    """Adapter: boolean feature-flag check."""
    import json
    from je_auto_control.utils.feature_flags import FlagStore, is_enabled
    if isinstance(flags, str):
        flags = json.loads(flags)
    if isinstance(context, str):
        context = json.loads(context)
    store = FlagStore.from_dict(flags)
    return {"enabled": is_enabled(store, key, context or {}, bool(default))}


def _unified_diff(a: str, b: str) -> Dict[str, Any]:
    """Adapter: unified diff transforming text a into b."""
    from je_auto_control.utils.text_diff import unified_diff
    return {"diff": unified_diff(a, b)}


def _apply_unified(text: str, diff: str) -> Dict[str, Any]:
    """Adapter: apply a unified diff to text."""
    from je_auto_control.utils.text_diff import apply_unified
    return {"result": apply_unified(text, diff)}


def _three_way_merge(base: str, ours: str, theirs: str) -> Dict[str, Any]:
    """Adapter: three-way merge ours/theirs against base."""
    from je_auto_control.utils.text_diff import three_way_merge
    outcome = three_way_merge(base, ours, theirs)
    return {"text": outcome.text, "clean": outcome.clean,
            "conflicts": outcome.conflicts}


def _rrule_occurrences(rule: str, dtstart: str,
                       count: int = 10) -> Dict[str, Any]:
    """Adapter: expand an RRULE from an ISO dtstart into ISO datetimes."""
    import datetime as _dt
    from je_auto_control.utils.recurrence import occurrences, parse_rrule
    start = _dt.datetime.fromisoformat(dtstart)
    moments = occurrences(parse_rrule(rule), start, count=int(count))
    return {"occurrences": [moment.isoformat() for moment in moments]}


def _rrule_next(rule: str, dtstart: str,
                now: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: next RRULE occurrence at/after now (ISO in, ISO out)."""
    import datetime as _dt
    from je_auto_control.utils.recurrence import next_occurrence, parse_rrule
    start = _dt.datetime.fromisoformat(dtstart)
    when = _dt.datetime.fromisoformat(now) if now else None
    moment = next_occurrence(parse_rrule(rule), start, now=when)
    return {"next": moment.isoformat() if moment else None}


def _describe_stats(values: Any) -> Dict[str, Any]:
    """Adapter: summary statistics + percentiles of a numeric list (or JSON)."""
    import json
    from je_auto_control.utils.stats import describe
    if isinstance(values, str):
        values = json.loads(values)
    return describe(values)


def _ab_significance(a_conv: int, a_n: int, b_conv: int,
                     b_n: int) -> Dict[str, Any]:
    """Adapter: two-proportion z-test on A/B conversion counts."""
    from je_auto_control.utils.stats import two_proportion_z_test
    return two_proportion_z_test(int(a_conv), int(a_n), int(b_conv), int(b_n))


def _search_documents(docs: Any, query: str, top_k: int = 10,
                      mode: str = "bm25") -> Dict[str, Any]:
    """Adapter: BM25/TF-IDF search a {doc_id: text} corpus (dict or JSON str)."""
    import json
    from je_auto_control.utils.search_index import search_documents
    if isinstance(docs, str):
        docs = json.loads(docs)
    hits = search_documents(docs, query, top_k=int(top_k), mode=mode)
    return {"hits": [{"doc_id": h.doc_id, "score": h.score} for h in hits]}


def _resolve_pointer(doc: Any, pointer: str) -> Dict[str, Any]:
    """Adapter: resolve a JSON Pointer in doc (a dict/list or JSON string)."""
    import json
    from je_auto_control.utils.json_patch import resolve_pointer
    if isinstance(doc, str):
        doc = json.loads(doc)
    return {"value": resolve_pointer(doc, pointer)}


def _apply_json_patch(doc: Any, patch: Any) -> Dict[str, Any]:
    """Adapter: apply an RFC 6902 JSON Patch (each a list/object or JSON str)."""
    import json
    from je_auto_control.utils.json_patch import apply_patch
    if isinstance(doc, str):
        doc = json.loads(doc)
    if isinstance(patch, str):
        patch = json.loads(patch)
    return {"result": apply_patch(doc, patch)}


def _make_json_patch(old: Any, new: Any) -> Dict[str, Any]:
    """Adapter: compute an RFC 6902 patch turning old into new."""
    import json
    from je_auto_control.utils.json_patch import make_patch
    if isinstance(old, str):
        old = json.loads(old)
    if isinstance(new, str):
        new = json.loads(new)
    return {"patch": make_patch(old, new)}


def _merge_patch(doc: Any, patch: Any) -> Dict[str, Any]:
    """Adapter: apply an RFC 7386 JSON Merge Patch (null deletes)."""
    import json
    from je_auto_control.utils.json_patch import merge_patch
    if isinstance(doc, str):
        doc = json.loads(doc)
    if isinstance(patch, str):
        patch = json.loads(patch)
    return {"result": merge_patch(doc, patch)}


def _jwt_encode(claims: Any, key: str, alg: str = "HS256") -> Dict[str, Any]:
    """Adapter: sign a compact JWT from claims (a dict or JSON string)."""
    import json
    from je_auto_control.utils.jwt import encode_jwt
    if isinstance(claims, str):
        claims = json.loads(claims)
    return {"token": encode_jwt(claims, key, alg=alg)}


def _jwt_decode(token: str, key: str, algorithms: Any = None,
                audience: Optional[str] = None,
                leeway: float = 0.0) -> Dict[str, Any]:
    """Adapter: verify a JWT and return {ok, claims} or {ok: False, error}."""
    import json
    from je_auto_control.utils.jwt import ClaimsPolicy, JwtError, decode_jwt
    if isinstance(algorithms, str):
        algorithms = json.loads(algorithms)
    policy = ClaimsPolicy(algorithms=tuple(algorithms) if algorithms
                          else ("HS256",), audience=audience, leeway=leeway)
    try:
        claims = decode_jwt(token, key, policy)
    except JwtError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "claims": claims}


def _generate_sop(actions: List[Any], title: str = "Automation Procedure",
                  path: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: build (or write) a step-by-step SOP from an action list."""
    from je_auto_control.utils.process_doc import generate_sop, write_sop
    if path:
        return {"path": write_sop(actions, path, title=title)}
    return generate_sop(actions, title=title)


def _tween_drag(start: List[int], end: List[int], steps: int = 30,
                easing: str = "ease_in_out_quad",
                button: str = "mouse_left") -> Dict[str, Any]:
    """Adapter: drag along an eased path from start to end."""
    from je_auto_control.utils.tween_drag import tween_drag
    result = tween_drag(tuple(start), tuple(end), steps=int(steps),
                        easing=easing, button=button)
    return {"points": result["points"]}


def _list_plugins(group: str = "je_auto_control.commands") -> Dict[str, Any]:
    """Adapter: discover third-party plugin command names (no register)."""
    from je_auto_control.utils.plugin_sdk import discover_plugins
    return {"commands": sorted(discover_plugins(group))}


def _load_plugins(group: str = "je_auto_control.commands") -> Dict[str, Any]:
    """Adapter: discover + register third-party plugin commands."""
    from je_auto_control.utils.plugin_sdk import load_plugins
    return {"loaded": load_plugins(group)}


def _approval_request(action: str, requester: str = "",
                      db: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: file a maker-checker approval request; return its token."""
    from je_auto_control.utils.governance import ApprovalGate
    return {"token": ApprovalGate(db).request(action, requester)}


def _approval_approve(token: str, approver: str,
                      db: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: approve a request as ``approver`` (must differ from maker)."""
    from je_auto_control.utils.governance import ApprovalGate
    return {"approved": ApprovalGate(db).approve(token, approver)}


def _approval_reject(token: str, approver: str,
                     db: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: reject a request as ``approver`` (must differ from maker)."""
    from je_auto_control.utils.governance import ApprovalGate
    return {"rejected": ApprovalGate(db).reject(token, approver)}


def _approval_status(token: str, db: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: report the status and approved flag of a request token."""
    from je_auto_control.utils.governance import ApprovalGate
    gate = ApprovalGate(db)
    return {"status": gate.status(token), "approved": gate.is_approved(token)}


def _lease_secret(name: str, ttl: float = 300.0) -> Dict[str, Any]:
    """Adapter: issue a JIT lease for a secret name (no value returned)."""
    from je_auto_control.utils.governance import default_broker
    return {"token": default_broker.lease(name, ttl), "ttl": float(ttl)}


def _lease_valid(token: str) -> Dict[str, Any]:
    """Adapter: report whether a lease token is still valid."""
    from je_auto_control.utils.governance import default_broker
    return {"valid": default_broker.is_valid(token)}


def _revoke_lease(token: str) -> Dict[str, Any]:
    """Adapter: revoke a lease token immediately."""
    from je_auto_control.utils.governance import default_broker
    return {"revoked": default_broker.revoke(token)}


def _lease_active() -> Dict[str, Any]:
    """Adapter: list active (non-expired) leases without any secret values."""
    from je_auto_control.utils.governance import default_broker
    return {"leases": default_broker.active()}


def _egress_allow(allow: Optional[List[str]] = None,
                  deny: Optional[List[str]] = None) -> Dict[str, Any]:
    """Adapter: lock the HTTP client to an egress allow/deny policy."""
    from je_auto_control.utils.egress import set_egress_policy
    policy = set_egress_policy(allow, deny)
    return {"allow": policy.allow, "deny": policy.deny}


def _egress_check(url: str) -> Dict[str, Any]:
    """Adapter: report whether ``url`` is permitted by the egress policy."""
    from je_auto_control.utils.egress import get_egress_policy
    return {"allowed": get_egress_policy().is_allowed(url)}


def _egress_reset() -> Dict[str, Any]:
    """Adapter: clear the egress policy back to allow-all."""
    from je_auto_control.utils.egress import set_egress_policy
    set_egress_policy(None, None)
    return {"allow": None, "deny": []}


def _verify_artifact(name: str, content: Any,
                     approvals_dir: str = _DEFAULT_APPROVALS_DIR,
                     extension: str = "txt") -> Dict[str, Any]:
    """Adapter: verify an artifact against its approved baseline."""
    from je_auto_control.utils.approval import verify_artifact
    result = verify_artifact(name, content, approvals_dir, extension)
    return {"status": result.status, "match": result.match,
            "approved_path": result.approved_path,
            "received_path": result.received_path}


def _approve_artifact(name: str, approvals_dir: str = _DEFAULT_APPROVALS_DIR,
                      extension: str = "txt") -> Dict[str, Any]:
    """Adapter: promote a received artifact to the approved baseline."""
    from je_auto_control.utils.approval import approve_artifact
    return {"approved": approve_artifact(name, approvals_dir, extension)}


def _pending_artifacts(approvals_dir: str = _DEFAULT_APPROVALS_DIR) -> Dict[str, Any]:
    """Adapter: list artifacts awaiting approval."""
    from je_auto_control.utils.approval import pending_artifacts
    return {"pending": pending_artifacts(approvals_dir)}


def _evaluate_trajectory(trajectory: Any, rubric: Any) -> Dict[str, Any]:
    """Adapter: score an agent trajectory against a declarative rubric.

    ``trajectory`` / ``rubric`` may be JSON strings (from the visual builder)
    or already-decoded list/dict (from JSON action files / MCP).
    """
    import json
    from je_auto_control.utils.trajectory_eval import evaluate_trajectory
    if isinstance(trajectory, str):
        trajectory = json.loads(trajectory)
    if isinstance(rubric, str):
        rubric = json.loads(rubric)
    return evaluate_trajectory(trajectory, rubric)


def _compliance_report(evidence: Any, frameworks: Any = None,
                       path: Optional[str] = None,
                       fmt: str = "json") -> Dict[str, Any]:
    """Adapter: map governance evidence to SOC2/ISO controls; optionally write."""
    import json
    from je_auto_control.utils.compliance import (
        build_compliance_report, write_compliance_report)
    if isinstance(evidence, str):
        evidence = json.loads(evidence)
    if isinstance(frameworks, str):
        frameworks = [f.strip() for f in frameworks.split(",") if f.strip()]
    report = build_compliance_report(evidence, frameworks)
    if path:
        report["path"] = write_compliance_report(report, path, fmt)
    return report


def _trace_record(operation: str, model: Optional[str] = None,
                  system: Optional[str] = None,
                  input_tokens: Optional[int] = None,
                  output_tokens: Optional[int] = None,
                  tool_name: Optional[str] = None, duration_s: float = 0.0,
                  status: str = "ok") -> Dict[str, Any]:
    """Adapter: record a GenAI-convention span on the default agent trace."""
    from je_auto_control.utils.agent_trace import default_trace
    return default_trace.record(
        operation, model=model, system=system, input_tokens=input_tokens,
        output_tokens=output_tokens, tool_name=tool_name,
        duration_s=duration_s, status=status)


def _trace_summary() -> Dict[str, Any]:
    """Adapter: roll up the default agent trace (count/tokens/duration)."""
    from je_auto_control.utils.agent_trace import default_trace
    return default_trace.summary()


def _trace_export() -> Dict[str, Any]:
    """Adapter: export the default agent trace in OTLP-friendly shape."""
    from je_auto_control.utils.agent_trace import default_trace
    return {"spans": default_trace.to_otel()}


def _trace_reset() -> Dict[str, Any]:
    """Adapter: clear the default agent trace."""
    from je_auto_control.utils.agent_trace import reset_trace
    reset_trace()
    return {"reset": True}


def _write_step_video(steps: Any, output: str, fps: int = 10,
                      seconds_per_step: float = 2.0) -> Dict[str, Any]:
    """Adapter: render captioned screenshots into a walkthrough video."""
    import json
    from je_auto_control.utils.video_report import write_step_video
    if isinstance(steps, str):
        steps = json.loads(steps)
    return write_step_video(steps, output, fps=fps,
                            seconds_per_step=seconds_per_step)


def _coerce_list(value: Any) -> List[Any]:
    import json
    return json.loads(value) if isinstance(value, str) else list(value)


def _fuzzy_ratio(left: Any, right: Any,
                 ignore_case: bool = True) -> Dict[str, Any]:
    """Adapter: similarity score (0..1) between two values."""
    from je_auto_control.utils.fuzzy import fuzzy_ratio
    return {"score": fuzzy_ratio(left, right, ignore_case=ignore_case)}


def _fuzzy_best_match(query: Any, choices: Any, score_cutoff: float = 0.0,
                      ignore_case: bool = True) -> Dict[str, Any]:
    """Adapter: best fuzzy match from choices, or a null match."""
    from je_auto_control.utils.fuzzy import fuzzy_best_match
    best = fuzzy_best_match(query, _coerce_list(choices),
                            score_cutoff=score_cutoff, ignore_case=ignore_case)
    if best is None:
        return {"match": None, "score": 0.0, "index": -1}
    return {"match": best[0], "score": best[1], "index": best[2]}


def _fuzzy_dedupe(items: Any, threshold: float = 0.9,
                  ignore_case: bool = True) -> Dict[str, Any]:
    """Adapter: drop near-duplicate items, keeping the first of each cluster."""
    from je_auto_control.utils.fuzzy import fuzzy_dedupe
    return {"unique": fuzzy_dedupe(_coerce_list(items), threshold=threshold,
                                   ignore_case=ignore_case)}


def _s3_upload(local_path: str, key: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: upload an artifact to the default S3 store; return the key."""
    from je_auto_control.utils.artifact_store import get_default_store
    return {"key": get_default_store().upload(local_path, key)}


def _s3_download(key: str, local_path: str) -> Dict[str, Any]:
    """Adapter: download an artifact from the default S3 store."""
    from je_auto_control.utils.artifact_store import get_default_store
    return {"path": get_default_store().download(key, local_path)}


def _s3_list(prefix: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: list artifact keys in the default S3 store."""
    from je_auto_control.utils.artifact_store import get_default_store
    return {"keys": get_default_store().list(prefix)}


def _s3_delete(key: str) -> Dict[str, Any]:
    """Adapter: delete an artifact from the default S3 store."""
    from je_auto_control.utils.artifact_store import get_default_store
    return {"deleted": get_default_store().delete(key)}


def _image_hash(path: str, algo: str = "average") -> Dict[str, Any]:
    """Adapter: perceptual hash of an image (average or dhash)."""
    from je_auto_control.utils.image_dedup import average_hash, dhash
    hasher = dhash if algo == "dhash" else average_hash
    return {"hash": hasher(path)}


def _dedupe_images(paths: Any, max_distance: int = 5) -> Dict[str, Any]:
    """Adapter: drop near-duplicate images, keeping the first of each cluster."""
    from je_auto_control.utils.image_dedup import dedupe_images
    return {"unique": dedupe_images(_coerce_list(paths),
                                    max_distance=max_distance)}


def _parse_decimal(text: str, locale: str = "en_US") -> Dict[str, Any]:
    """Adapter: parse a locale-formatted decimal string to a float."""
    from je_auto_control.utils.locale_parse import parse_decimal
    return {"value": parse_decimal(text, locale)}


def _parse_number(text: str, locale: str = "en_US") -> Dict[str, Any]:
    """Adapter: parse a locale-formatted integer string to an int."""
    from je_auto_control.utils.locale_parse import parse_number
    return {"value": parse_number(text, locale)}


def _format_decimal(value: float, locale: str = "en_US") -> Dict[str, Any]:
    """Adapter: format a number for a locale."""
    from je_auto_control.utils.locale_parse import format_decimal
    return {"text": format_decimal(value, locale)}


def _format_currency(value: float, currency: str,
                     locale: str = "en_US") -> Dict[str, Any]:
    """Adapter: format a value as currency for a locale."""
    from je_auto_control.utils.locale_parse import format_currency
    return {"text": format_currency(value, currency, locale)}


def _format_date(value: str, locale: str = "en_US",
                 fmt: str = "medium") -> Dict[str, Any]:
    """Adapter: format an ISO date string for a locale."""
    from je_auto_control.utils.locale_parse import format_date
    return {"text": format_date(value, locale, fmt)}


def _voice_register(phrase: str, actions: Any) -> Dict[str, Any]:
    """Adapter: register a voice command on the default router."""
    from je_auto_control.utils.voice import default_voice_router
    default_voice_router.register(phrase, _coerce_list(actions))
    return {"phrases": default_voice_router.phrases()}


def _voice_dispatch(text: str) -> Dict[str, Any]:
    """Adapter: run the command best matching recognized ``text``."""
    from je_auto_control.utils.voice import default_voice_router
    outcome = default_voice_router.dispatch(text)
    return {"matched": outcome["matched"], "phrase": outcome["phrase"]}


def _voice_list() -> Dict[str, Any]:
    """Adapter: list registered voice-command phrases."""
    from je_auto_control.utils.voice import default_voice_router
    return {"phrases": default_voice_router.phrases()}


def _voice_clear() -> Dict[str, Any]:
    """Adapter: clear all registered voice commands."""
    from je_auto_control.utils.voice import default_voice_router
    default_voice_router.clear()
    return {"cleared": True}


def _to_physical(x: float, y: float, physical_w: int, physical_h: int,
                 model_w: int, model_h: int) -> Dict[str, Any]:
    """Adapter: map a model-grid coordinate to physical pixels."""
    from je_auto_control.utils.coordinate_space import CoordinateSpace
    px, py = CoordinateSpace(physical_w, physical_h, model_w,
                             model_h).to_physical(x, y)
    return {"x": px, "y": py}


def _to_model(x: int, y: int, physical_w: int, physical_h: int,
              model_w: int, model_h: int) -> Dict[str, Any]:
    """Adapter: map a physical-pixel coordinate to a model grid."""
    from je_auto_control.utils.coordinate_space import CoordinateSpace
    mx, my = CoordinateSpace(physical_w, physical_h, model_w,
                             model_h).to_model(x, y)
    return {"x": mx, "y": my}


def _loop_guard_observe(tool: str, args: Any = None,
                        result_digest: str = "") -> Dict[str, Any]:
    """Adapter: feed a step to the default loop guard; report the verdict."""
    from je_auto_control.utils.loop_guard import default_loop_guard
    verdict = default_loop_guard.observe(tool, args, result_digest)
    return {"pattern": verdict.pattern, "level": verdict.level,
            "count": verdict.count}


def _loop_guard_reset() -> Dict[str, Any]:
    """Adapter: clear the default loop guard's history."""
    from je_auto_control.utils.loop_guard import default_loop_guard
    default_loop_guard.reset()
    return {"reset": True}


def _mine_actions(actions: Any, min_len: int = 2, max_len: int = 5,
                  min_count: int = 3) -> Dict[str, Any]:
    """Adapter: mine an action log for repeated, automatable sequences."""
    from je_auto_control.utils.process_mining import mine_action_log
    report = mine_action_log(_coerce_list(actions), min_len=min_len,
                             max_len=max_len, min_count=min_count)
    return {
        "total_actions": report.total_actions,
        "patterns": [{"actions": list(p.actions), "count": p.count}
                     for p in report.patterns],
        "candidates": [{"actions": list(c.pattern.actions),
                        "count": c.pattern.count, "score": c.score}
                       for c in report.candidates],
    }


def _set_asset(name: str, value: Any, asset_type: str = "text",
               environment: str = "default",
               db: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: store a typed, environment-scoped asset."""
    from je_auto_control.utils.assets.assets import store_set
    return store_set(name, value, asset_type=asset_type,
                     environment=environment, db=db)


def _get_asset(name: str, environment: str = "default",
               db: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: read a typed asset (credential stays a reference)."""
    from je_auto_control.utils.assets.assets import store_get
    return store_get(name, environment=environment, db=db)


def _list_assets(environment: Optional[str] = None,
                 db: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: list assets, optionally restricted to one environment."""
    from je_auto_control.utils.assets.assets import store_list
    return store_list(environment=environment, db=db)


def _emit_event(event_type: str, data: Any = None,
                source: str = "je_auto_control",
                subject: Optional[str] = None,
                url: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: build a CloudEvent; optionally POST it (egress-guarded)."""
    from je_auto_control.utils.events import post_cloudevent, to_cloudevent
    if isinstance(data, str):
        import json
        try:
            data = json.loads(data)
        except ValueError:
            pass
    event = to_cloudevent(event_type, source, data, subject=subject)
    result: Dict[str, Any] = {"event": event}
    if url:
        result["status"] = post_cloudevent(url, event)
    return result


def _notify_webhook(url: str, text: str, transport: str = "raw",
                    title: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: send a chat/webhook notification (slack/discord/teams/raw)."""
    from je_auto_control.utils.notify_channels import notify_webhook
    outcome = notify_webhook(url, text, transport=transport, title=title)
    return {"ok": outcome.ok, "status": outcome.status,
            "transport": outcome.transport}


def _json_query(data: Any, path: str) -> Dict[str, Any]:
    """Adapter: return all JSONPath matches in data (JSON string or object)."""
    import json
    from je_auto_control.utils.jsonpath import json_query
    if isinstance(data, str):
        data = json.loads(data)
    return {"matches": json_query(data, path)}


def _json_extract(data: Any, mapping: Any) -> Dict[str, Any]:
    """Adapter: extract a {key: path} mapping from data into a flat dict."""
    import json
    from je_auto_control.utils.jsonpath import json_extract
    if isinstance(data, str):
        data = json.loads(data)
    if isinstance(mapping, str):
        mapping = json.loads(mapping)
    return {"result": json_extract(data, mapping)}


def _validate_json(data: Any, schema: Any) -> Dict[str, Any]:
    """Adapter: validate data against a JSON Schema (each JSON string or object)."""
    import json
    from je_auto_control.utils.json_schema import validate_json
    if isinstance(data, str):
        data = json.loads(data)
    if isinstance(schema, str):
        schema = json.loads(schema)
    return validate_json(data, schema).to_dict()


def _run_saga(steps: Any) -> Dict[str, Any]:
    """Adapter: run a saga (steps with compensating rollback) from a spec."""
    import json
    from je_auto_control.utils.saga import run_saga
    if isinstance(steps, str):
        steps = json.loads(steps)
    result = run_saga(steps)
    return {"ok": result.ok, "completed": result.completed,
            "compensated": result.compensated,
            "failed_step": result.failed_step, "error": result.error}


def _decision_table(spec: Any, context: Any) -> Dict[str, Any]:
    """Adapter: evaluate a DMN-style decision table against a context."""
    import json
    from je_auto_control.utils.decision_table import evaluate_table
    if isinstance(spec, str):
        spec = json.loads(spec)
    if isinstance(context, str):
        context = json.loads(context)
    return {"result": evaluate_table(spec, context)}


def _repair_record(key: str, method: str, coordinates: Any = None,
                   description: Optional[str] = None, confidence: float = 1.0,
                   auto_threshold: float = 0.9,
                   db: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: record a corrected locator from a heal (auto-apply or queue)."""
    import json
    from je_auto_control.utils.locator_repair import RepairStore
    if isinstance(coordinates, str):
        coordinates = json.loads(coordinates)
    sug = RepairStore(db).record(
        key, method=method, coordinates=coordinates, description=description,
        confidence=confidence, auto_threshold=auto_threshold)
    return {"id": sug.id, "status": sug.status}


def _repair_resolved(key: str, db: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: return the learned corrected locator for a key (or null)."""
    from je_auto_control.utils.locator_repair import RepairStore
    return {"locator": RepairStore(db).resolved(key)}


def _repair_pending(db: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: list locator-repair suggestions awaiting review."""
    from je_auto_control.utils.locator_repair import RepairStore
    return {"pending": RepairStore(db).pending()}


def _repair_approve(suggestion_id: str,
                    db: Optional[str] = None) -> Dict[str, Any]:
    """Adapter: approve a pending locator-repair suggestion."""
    from je_auto_control.utils.locator_repair import RepairStore
    return {"approved": RepairStore(db).approve(suggestion_id)}


def _detect_pii(text: str, kinds: Any = None) -> Dict[str, Any]:
    """Adapter: detect PII spans in text."""
    from je_auto_control.utils.pii_text import detect_pii
    findings = detect_pii(text, kinds=_coerce_list(kinds) if kinds else None)
    return {"findings": [{"kind": f.kind, "value": f.value,
                          "start": f.start, "end": f.end} for f in findings]}


def _redact_pii(text: str, kinds: Any = None, mode: str = "label",
                mask_char: str = "*") -> Dict[str, Any]:
    """Adapter: redact PII in text (label/mask/partial/hash)."""
    from je_auto_control.utils.pii_text import redact_pii_text
    return {"text": redact_pii_text(
        text, kinds=_coerce_list(kinds) if kinds else None, mode=mode,
        mask_char=mask_char)}


def _export_sarif(findings: Any, path: Optional[str] = None,
                  tool_name: str = "AutoControl") -> Dict[str, Any]:
    """Adapter: build (and optionally write) a SARIF 2.1.0 document."""
    import json
    from je_auto_control.utils.sarif import to_sarif, write_sarif
    if isinstance(findings, str):
        findings = json.loads(findings)
    document = to_sarif(findings, tool_name=tool_name)
    result: Dict[str, Any] = {"sarif": document}
    if path:
        result["path"] = write_sarif(findings, path, tool_name=tool_name)
    return result


class Executor:
    """
    Executor
    指令執行器
    - 提供 event_dict 對應字串名稱到函式
    - 支援滑鼠、鍵盤、螢幕、影像辨識、報告生成等功能
    - 可執行 action list 或 action file
    - 支援流程控制指令 (AC_loop, AC_if_image_found 等)
    """

    # Args keys that hold nested action lists; runtime interpolation must
    # leave them untouched so each iteration re-reads current variable state.
    _DEFERRED_ARG_KEYS: frozenset = frozenset(
        {"body", "then", "else", "branches"})

    def __init__(self):
        self._block_commands = BLOCK_COMMANDS
        self.variables = VariableScope()
        # Named, parameterised macros registered via AC_define_macro.
        self.macros: Dict[str, Any] = {}
        # 事件字典，對應字串名稱到函式
        self.event_dict: dict = {
            # Mouse 滑鼠相關
            **MOUSE_BUTTON_COMMANDS,
            "AC_click_mouse": click_mouse,
            "AC_get_mouse_table": get_mouse_table,
            "AC_get_mouse_position": get_mouse_position,
            "AC_press_mouse": press_mouse,
            "AC_release_mouse": release_mouse,
            "AC_mouse_scroll": mouse_scroll,
            "AC_set_mouse_position": set_mouse_position,
            "AC_human_move": _human_move,
            "AC_human_type": _human_type,

            # Keyboard 鍵盤相關
            "AC_get_keyboard_keys_table": get_keyboard_keys_table,
            "AC_type_keyboard": type_keyboard,
            "AC_press_keyboard_key": press_keyboard_key,
            "AC_release_keyboard_key": release_keyboard_key,
            "AC_check_key_is_press": check_key_is_press,
            "AC_write": write,
            "AC_hotkey": hotkey,

            # Image 影像辨識
            "AC_locate_all_image": locate_all_image,
            "AC_locate_image_center": locate_image_center,
            "AC_locate_and_click": locate_and_click,

            # Screen 螢幕相關
            "AC_screen_size": screen_size,
            "AC_screenshot": screenshot,

            # Test record 測試紀錄
            "AC_set_record_enable": test_record_instance.set_record_enable,

            # Report 報告生成
            "AC_generate_html": generate_html,
            "AC_generate_json": generate_json,
            "AC_generate_xml": generate_xml,
            "AC_generate_html_report": generate_html_report,
            "AC_generate_json_report": generate_json_report,
            "AC_generate_xml_report": generate_xml_report,
            "AC_generate_code": _generate_code,
            "AC_send_email": _send_email,
            "AC_assert_pdf_text": _assert_pdf_text,
            "AC_take_golden": _take_golden,
            "AC_assert_visual": _assert_visual,
            "AC_run_state_machine": _run_state_machine,
            "AC_http_request": http_request,

            # Record 錄製
            "AC_record": record,
            "AC_stop_record": stop_record,

            # Executor 執行器
            "AC_execute_action": self.execute_action,
            "AC_execute_files": self.execute_files,
            "AC_add_package_to_executor": package_manager.add_package_to_executor,
            "AC_add_package_to_callback_executor": package_manager.add_package_to_callback_executor,

            # Project 專案
            "AC_create_project": create_project_dir,

            # Shell
            "AC_shell_command": default_shell_manager.exec_shell,

            # Process
            "AC_execute_process": start_exe,

            # OCR
            "AC_locate_text": ocr_locate_text_center,
            "AC_wait_text": ocr_wait_for_text,
            "AC_click_text": ocr_click_text,
            "AC_read_text_in_region": _ocr_read_region_as_dicts,
            "AC_find_text_regex": _ocr_find_regex_as_dicts,

            # Window management
            "AC_list_windows": list_windows,
            "AC_focus_window": focus_window,
            "AC_wait_window": wait_for_window,
            "AC_close_window": close_window_by_title,

            # Clipboard
            "AC_clipboard_get": get_clipboard,
            "AC_clipboard_set": set_clipboard,

            # Run history
            "AC_history_list": _history_list_as_dicts,
            "AC_history_clear": default_history_store.clear,

            # Profiler
            "AC_profiler_enable": _profiler_enable,
            "AC_profiler_disable": _profiler_disable,
            "AC_profiler_reset": _profiler_reset,
            "AC_profiler_stats": _profiler_stats_as_dicts,
            "AC_profiler_hot_spots": _profiler_hot_spots_as_dicts,

            # Webhook trigger (HTTP push triggers)
            "AC_webhook_start": _webhook_start,
            "AC_webhook_stop": _webhook_stop,
            "AC_webhook_add": _webhook_add,
            "AC_webhook_remove": _webhook_remove,
            "AC_webhook_list": _webhook_list,
            "AC_webhook_status": _webhook_status,

            # Email/IMAP poll trigger
            "AC_email_trigger_add": _email_trigger_add,
            "AC_email_trigger_remove": _email_trigger_remove,
            "AC_email_trigger_list": _email_trigger_list,
            "AC_email_trigger_start": _email_trigger_start,
            "AC_email_trigger_stop": _email_trigger_stop,
            "AC_email_trigger_poll_once": _email_trigger_poll_once,

            # Secret manager (encrypted vault for ${secrets.NAME})
            "AC_secret_init": _secret_initialize,
            "AC_secret_unlock": _secret_unlock,
            "AC_secret_lock": _secret_lock,
            "AC_secret_set": _secret_set,
            "AC_secret_remove": _secret_remove,
            "AC_secret_list": _secret_list,
            "AC_secret_status": _secret_status,

            # Accessibility-tree widget location
            "AC_a11y_list": _a11y_list_as_dicts,
            "AC_a11y_find": _a11y_find_as_dict,
            "AC_a11y_click": click_accessibility_element,
            "AC_a11y_dump": _a11y_dump,
            "AC_walk_tree": _walk_tree,
            "AC_humanize_role": _humanize_role,
            "AC_tab_order": _tab_order,
            "AC_audit_focus_order": _audit_focus_order,
            "AC_focus_control": _focus_control,
            "AC_control_get_value": _control_get_value,
            "AC_control_set_value": _control_set_value,
            "AC_control_invoke": _control_invoke,
            "AC_control_toggle": _control_toggle,
            "AC_expand_control": _expand_control,
            "AC_collapse_control": _collapse_control,
            "AC_control_expand_state": _control_expand_state,
            "AC_select_control_item": _select_control_item,
            "AC_control_range": _control_range,
            "AC_set_control_range": _set_control_range,
            "AC_scroll_control_into_view": _scroll_control_into_view,
            "AC_realize_item": _realize_item,
            "AC_get_element_properties": _get_element_properties,
            "AC_table_headers": _table_headers,
            "AC_table_cell": _table_cell,
            "AC_cell_by_header": _cell_by_header,
            "AC_move_element": _move_element,
            "AC_resize_element": _resize_element,
            "AC_set_window_state": _set_window_state,
            "AC_window_interaction_state": _window_interaction_state,
            "AC_legacy_info": _legacy_info,
            "AC_legacy_default_action": _legacy_default_action,
            "AC_get_selection": _get_selection,
            "AC_list_views": _list_views,
            "AC_set_view": _set_view,
            "AC_wait_for_focus_change": _wait_for_focus_change,
            "AC_plan_open": _plan_open,
            "AC_open_path": _open_path,
            "AC_idle_seconds": _idle_seconds,
            "AC_is_idle": _is_idle,
            "AC_plan_keep_awake": _plan_keep_awake,
            "AC_keep_awake_on": _keep_awake_on,
            "AC_allow_sleep": _allow_sleep,
            "AC_get_volume": _get_volume,
            "AC_set_volume": _set_volume,
            "AC_change_volume": _change_volume,
            "AC_set_mute": _set_mute,
            "AC_toggle_mute": _toggle_mute,
            "AC_lock_session": _lock_session,
            "AC_plan_lock_session": _plan_lock_session,
            "AC_wait_for_unlock": _wait_for_unlock,
            "AC_classify_lock_transitions": _classify_lock_transitions,
            "AC_ime_state": _ime_state,
            "AC_is_composing": _is_composing,
            "AC_wait_for_composition_commit": _wait_for_composition_commit,
            "AC_decode_conversion_mode": _decode_conversion_mode,
            "AC_retry_delay": _retry_delay,
            "AC_plan_retry_delays": _plan_retry_delays,
            "AC_compare_field_value": _compare_field_value,
            "AC_verify_field_value": _verify_field_value,
            "AC_normalize_ext": _normalize_ext,
            "AC_file_association": _file_association,
            "AC_get_control_text": _get_control_text,
            "AC_find_control_text": _find_control_text,
            "AC_select_control_text": _select_control_text,
            "AC_control_text_attributes": _control_text_attributes,
            "AC_get_selected_text": _get_selected_text,
            "AC_get_visible_text": _get_visible_text,
            "AC_read_table": _read_table,
            "AC_watchdog_add": _watchdog_add,
            "AC_watchdog_start": _watchdog_start,
            "AC_watchdog_stop": _watchdog_stop,
            "AC_watchdog_list": _watchdog_list,
            "AC_handle_file_dialog": _handle_file_dialog,
            "AC_assert_session_active": _assert_session_active,
            "AC_queue_add": _queue_add,
            "AC_queue_next": _queue_next,
            "AC_queue_complete": _queue_complete,
            "AC_queue_fail": _queue_fail,
            "AC_queue_stats": _queue_stats,
            "AC_generate_data": _generate_data,
            "AC_mcp_manifest": _mcp_manifest,
            "AC_rank_tests": _rank_tests,
            "AC_select_tests": _select_tests,
            "AC_element_save": _element_save,
            "AC_element_find": _element_find,
            "AC_element_click": _element_click,
            "AC_element_remove": _element_remove,
            "AC_element_list": _element_list,
            "AC_debug_trace": _debug_trace,
            "AC_skill_save": _skill_save,
            "AC_skill_run": _skill_run,
            "AC_skill_list": _skill_list,
            "AC_skill_remove": _skill_remove,
            "AC_skill_search": _skill_search,
            "AC_guard_text": _guard_text,
            "AC_agent_card": _agent_card,
            "AC_read_workbook": _read_workbook,
            "AC_write_workbook": _write_workbook,
            "AC_read_document": _read_document,
            "AC_write_document": _write_document,
            "AC_read_presentation": _read_presentation,
            "AC_write_presentation": _write_presentation,
            "AC_memory_remember": _memory_remember,
            "AC_memory_recall": _memory_recall,
            "AC_memory_recent": _memory_recent,
            "AC_memory_forget": _memory_forget,
            "AC_memory_stats": _memory_stats,
            "AC_seed_everything": _seed_everything,
            "AC_observe_add": _observe_add,
            "AC_observe_remove": _observe_remove,
            "AC_observe_list": _observe_list,
            "AC_observe_poll": _observe_poll,
            "AC_observe_start": _observe_start,
            "AC_observe_stop": _observe_stop,
            "AC_generate_sbom": _generate_sbom,
            "AC_shard_suite": _shard_suite,
            "AC_merge_results": _merge_results,
            "AC_validate_rows": _validate_rows,
            "AC_extract_fields": _extract_fields,
            "AC_mask_rows": _mask_rows,
            "AC_pseudo_localize": _pseudo_localize,
            "AC_check_overflow": _check_overflow,
            "AC_check_catalog": _check_catalog,
            "AC_run_resumable": _run_resumable,
            "AC_checkpoint_status": _checkpoint_status,
            "AC_checkpoint_clear": _checkpoint_clear,
            "AC_mark_screen": _mark_screen,
            "AC_mark_click": _mark_click,
            "AC_screen_snapshot": _screen_snapshot,
            "AC_screen_diff": _screen_diff,
            "AC_screen_changed": _screen_changed,
            "AC_describe_screen": _describe_screen,
            "AC_replay_timeline": _replay_timeline,
            "AC_input_sequence": _input_sequence,
            "AC_circuit_call": _circuit_call,
            "AC_ci_annotations": _ci_annotations,
            "AC_clip_history_capture": _clip_history_capture,
            "AC_clip_history_list": _clip_history_list,
            "AC_clip_history_search": _clip_history_search,
            "AC_clip_history_start": _clip_history_start,
            "AC_clip_history_stop": _clip_history_stop,
            "AC_heal_stats": _heal_stats,
            "AC_scan_secrets": _scan_secrets,
            "AC_scan_vulns": _scan_vulns,
            "AC_apply_vex": _apply_vex,
            "AC_check_licenses": _check_licenses,
            "AC_jwt_encode": _jwt_encode,
            "AC_jwt_decode": _jwt_decode,
            "AC_rate_limit": _rate_limit,
            "AC_search_documents": _search_documents,
            "AC_describe_stats": _describe_stats,
            "AC_ab_significance": _ab_significance,
            "AC_rrule_occurrences": _rrule_occurrences,
            "AC_rrule_next": _rrule_next,
            "AC_evaluate_flag": _evaluate_flag,
            "AC_flag_enabled": _flag_enabled,
            "AC_build_provenance": _build_provenance,
            "AC_verify_provenance": _verify_provenance,
            "AC_match_json": _match_json,
            "AC_diff_json": _diff_json,
            "AC_run_chaos": _run_chaos,
            "AC_evaluate_slo": _evaluate_slo,
            "AC_burn_alerts": _burn_alerts,
            "AC_percentiles": _percentiles,
            "AC_bulkhead_run": _bulkhead_run,
            "AC_retry_after": _retry_after,
            "AC_http_replay": _http_replay,
            "AC_trace_inject": _trace_inject,
            "AC_trace_extract": _trace_extract,
            "AC_baggage_parse": _baggage_parse,
            "AC_baggage_format": _baggage_format,
            "AC_canonical_log": _canonical_log,
            "AC_spans_to_otlp": _spans_to_otlp,
            "AC_normalize_text": _normalize_text,
            "AC_slugify": _slugify,
            "AC_text_similarity": _text_similarity,
            "AC_simhash": _simhash,
            "AC_near_duplicates": _near_duplicates,
            "AC_validate_config": _validate_config,
            "AC_resolve_ref": _resolve_ref,
            "AC_resolve_refs": _resolve_refs,
            "AC_redact_config": _redact_config,
            "AC_redact_secret_text": _redact_secret_text,
            "AC_parse_link_header": _parse_link_header,
            "AC_next_url": _next_url,
            "AC_build_multipart": _build_multipart,
            "AC_parse_multipart": _parse_multipart,
            "AC_decode_body": _decode_body,
            "AC_parse_quality_values": _parse_quality_values,
            "AC_cookie_header": _cookie_header,
            "AC_parse_set_cookie": _parse_set_cookie,
            "AC_parse_cache_control": _parse_cache_control,
            "AC_store_validators": _store_validators,
            "AC_profile_rows": _profile_rows,
            "AC_infer_schema": _infer_schema,
            "AC_parse_problem": _parse_problem,
            "AC_parse_dotenv": _parse_dotenv,
            "AC_load_dotenv": _load_dotenv,
            "AC_parse_sse": _parse_sse,
            "AC_resolve_config": _resolve_config,
            "AC_explain_config": _explain_config,
            "AC_check_compatibility": _check_compatibility,
            "AC_ts_rate": _ts_rate,
            "AC_ts_downsample": _ts_downsample,
            "AC_detect_anomalies": _detect_anomalies,
            "AC_sma": _sma,
            "AC_ewma": _ewma,
            "AC_idempotency_begin": _idempotency_begin,
            "AC_idempotency_complete": _idempotency_complete,
            "AC_dedup_check": _dedup_check,
            "AC_sequence_observe": _sequence_observe,
            "AC_cas_put": _cas_put,
            "AC_cas_get": _cas_get,
            "AC_outbox_enqueue": _outbox_enqueue,
            "AC_outbox_pending": _outbox_pending,
            "AC_collation_sort": _collation_sort,
            "AC_collation_compare": _collation_compare,
            "AC_confusable_scan": _confusable_scan,
            "AC_confusable_compare": _confusable_compare,
            "AC_readability_report": _readability_report,
            "AC_bidi_check": _bidi_check,
            "AC_bidi_strip": _bidi_strip,
            "AC_format_list": _format_list,
            "AC_format_message": _format_message,
            "AC_gettext_translate": _gettext_translate,
            "AC_gettext_ngettext": _gettext_ngettext,
            "AC_checksum_validate": _checksum_validate,
            "AC_checksum_digit": _checksum_digit,
            "AC_move_along_path": _move_along_path,
            "AC_drag_path": _drag_path,
            "AC_set_field_text": _set_field_text,
            "AC_hold_key": _hold_key,
            "AC_move_mouse_relative": _move_mouse_relative,
            "AC_type_unicode": _type_unicode,
            "AC_with_modifiers": _with_modifiers,
            "AC_grid_cell": _grid_cell,
            "AC_match_template": _match_template,
            "AC_match_template_all": _match_template_all,
            "AC_match_masked": _match_masked,
            "AC_match_masked_all": _match_masked_all,
            "AC_match_rotated": _match_rotated,
            "AC_match_rotated_all": _match_rotated_all,
            "AC_match_with_trust": _match_with_trust,
            "AC_auto_threshold": _auto_threshold,
            "AC_match_auto": _match_auto,
            "AC_edge_match": _edge_match,
            "AC_edge_match_all": _edge_match_all,
            "AC_match_subpixel": _match_subpixel,
            "AC_match_ensemble": _match_ensemble,
            "AC_vote_centers": _vote_centers,
            "AC_match_color": _match_color,
            "AC_match_color_all": _match_color_all,
            "AC_region_stability": _region_stability,
            "AC_match_persistence": _match_persistence,
            "AC_grid_cells": _grid_cells,
            "AC_cell_for_point": _cell_for_point,
            "AC_point_for_cell": _point_for_cell,
            "AC_populate_table": _populate_table,
            "AC_column_gutters": _column_gutters,
            "AC_detect_borderless_table": _detect_borderless_table,
            "AC_associate_fields": _associate_fields,
            "AC_match_labels_to_widgets": _match_labels_to_widgets,
            "AC_flow_order": _flow_order,
            "AC_xy_cut": _xy_cut,
            "AC_group_paragraphs": _group_paragraphs,
            "AC_detect_lists": _detect_lists,
            "AC_classify_lines": _classify_lines,
            "AC_outline": _outline,
            "AC_ssim_compare": _ssim_compare,
            "AC_ssim_changed_regions": _ssim_changed_regions,
            "AC_feature_match": _feature_match,
            "AC_find_shapes": _find_shapes,
            "AC_find_rectangles": _find_rectangles,
            "AC_preprocess_image": _preprocess_image,
            "AC_enumerate_monitors": _enumerate_monitors,
            "AC_monitor_at_point": _monitor_at_point,
            "AC_wait_actionable": _wait_actionable,
            "AC_fuse_elements": _fuse_elements,
            "AC_reading_order": _reading_order,
            "AC_segment_hsv": _segment_hsv,
            "AC_dominant_hue_regions": _dominant_hue_regions,
            "AC_find_text_regions": _find_text_regions,
            "AC_find_text_lines": _find_text_lines,
            "AC_find_lines": _find_lines,
            "AC_find_grid": _find_grid,
            "AC_find_separators": _find_separators,
            "AC_expect_poll": _expect_poll,
            "AC_locate_chain": _locate_chain,
            "AC_set_clipboard_html": _set_clipboard_html,
            "AC_get_clipboard_html": _get_clipboard_html,
            "AC_set_clipboard_files": _set_clipboard_files,
            "AC_get_clipboard_files": _get_clipboard_files,
            "AC_set_clipboard_rtf": _set_clipboard_rtf,
            "AC_get_clipboard_rtf": _get_clipboard_rtf,
            "AC_set_clipboard_csv": _set_clipboard_csv,
            "AC_get_clipboard_csv": _get_clipboard_csv,
            "AC_clipboard_formats": _clipboard_formats,
            "AC_classify_formats": _classify_formats,
            "AC_diff_formats": _diff_formats,
            "AC_plan_file_drop": _plan_file_drop,
            "AC_drop_files": _drop_files,
            "AC_image_quality": _image_quality,
            "AC_quality_gate": _quality_gate,
            "AC_detect_scale": _detect_scale,
            "AC_scale_sweep": _scale_sweep,
            "AC_salient_regions": _salient_regions,
            "AC_most_salient": _most_salient,
            "AC_failure_signature": _failure_signature,
            "AC_group_failures": _group_failures,
            "AC_diff_runs": _diff_runs,
            "AC_failure_clusters": _failure_clusters,
            "AC_cofailure_pairs": _cofailure_pairs,
            "AC_build_timeline": _build_timeline,
            "AC_critical_steps": _critical_steps,
            "AC_image_histogram": _image_histogram,
            "AC_histogram_changed": _histogram_changed,
            "AC_changed_regions": _changed_regions,
            "AC_has_motion": _has_motion,
            "AC_set_topmost": _set_topmost,
            "AC_bring_to_front": _bring_to_front,
            "AC_send_to_back": _send_to_back,
            "AC_soft_assert": _soft_assert,
            "AC_perceptual_diff": _perceptual_diff,
            "AC_get_client_rect": _get_client_rect,
            "AC_client_point": _client_point,
            "AC_cua_command": _cua_command,
            "AC_serialize_observation": _serialize_observation,
            "AC_observation_index": _observation_index,
            "AC_delta_observation": _delta_observation,
            "AC_classify_effect": _classify_effect,
            "AC_effect_near_point": _effect_near_point,
            "AC_check_postcondition": _check_postcondition,
            "AC_plan_repair": _plan_repair,
            "AC_consensus_point": _consensus_point,
            "AC_consensus_element": _consensus_element,
            "AC_settle_point": _settle_point,
            "AC_build_critic_record": _build_critic_record,
            "AC_score_step": _score_step,
            "AC_validate_action": _validate_action,
            "AC_replay_trace": _replay_trace,
            "AC_match_elements": _match_elements,
            "AC_assign_stable_ids": _assign_stable_ids,
            "AC_score_candidates": _score_candidates,
            "AC_best_candidate": _best_candidate,
            "AC_read_barcodes": _read_barcodes,
            "AC_tile_rect": _tile_rect,
            "AC_grid_rects": _grid_rects,
            "AC_cascade_rects": _cascade_rects,
            "AC_find_color_region": _find_color_region,
            "AC_detect_drift": _detect_drift,
            "AC_categorical_drift": _categorical_drift,
            "AC_diff_rows": _diff_rows,
            "AC_cell_changes": _cell_changes,
            "AC_check_foreign_key": _check_foreign_key,
            "AC_check_unique_key": _check_unique_key,
            "AC_check_accepted_values": _check_accepted_values,
            "AC_check_row_count": _check_row_count,
            "AC_unified_diff": _unified_diff,
            "AC_apply_unified": _apply_unified,
            "AC_three_way_merge": _three_way_merge,
            "AC_resolve_pointer": _resolve_pointer,
            "AC_apply_json_patch": _apply_json_patch,
            "AC_make_json_patch": _make_json_patch,
            "AC_merge_patch": _merge_patch,
            "AC_generate_sop": _generate_sop,
            "AC_tween_drag": _tween_drag,
            "AC_list_plugins": _list_plugins,
            "AC_load_plugins": _load_plugins,
            "AC_approval_request": _approval_request,
            "AC_approval_approve": _approval_approve,
            "AC_approval_reject": _approval_reject,
            "AC_approval_status": _approval_status,
            "AC_lease_secret": _lease_secret,
            "AC_lease_valid": _lease_valid,
            "AC_revoke_lease": _revoke_lease,
            "AC_lease_active": _lease_active,
            "AC_egress_allow": _egress_allow,
            "AC_egress_check": _egress_check,
            "AC_egress_reset": _egress_reset,
            "AC_verify_artifact": _verify_artifact,
            "AC_approve_artifact": _approve_artifact,
            "AC_pending_artifacts": _pending_artifacts,
            "AC_evaluate_trajectory": _evaluate_trajectory,
            "AC_compliance_report": _compliance_report,
            "AC_trace_record": _trace_record,
            "AC_trace_summary": _trace_summary,
            "AC_trace_export": _trace_export,
            "AC_trace_reset": _trace_reset,
            "AC_write_step_video": _write_step_video,
            "AC_fuzzy_ratio": _fuzzy_ratio,
            "AC_fuzzy_best_match": _fuzzy_best_match,
            "AC_fuzzy_dedupe": _fuzzy_dedupe,
            "AC_s3_upload": _s3_upload,
            "AC_s3_download": _s3_download,
            "AC_s3_list": _s3_list,
            "AC_s3_delete": _s3_delete,
            "AC_image_hash": _image_hash,
            "AC_dedupe_images": _dedupe_images,
            "AC_parse_decimal": _parse_decimal,
            "AC_parse_number": _parse_number,
            "AC_format_decimal": _format_decimal,
            "AC_format_currency": _format_currency,
            "AC_format_date": _format_date,
            "AC_voice_register": _voice_register,
            "AC_voice_dispatch": _voice_dispatch,
            "AC_voice_list": _voice_list,
            "AC_voice_clear": _voice_clear,
            "AC_to_physical": _to_physical,
            "AC_to_model": _to_model,
            "AC_loop_guard_observe": _loop_guard_observe,
            "AC_loop_guard_reset": _loop_guard_reset,
            "AC_mine_actions": _mine_actions,
            "AC_set_asset": _set_asset,
            "AC_get_asset": _get_asset,
            "AC_list_assets": _list_assets,
            "AC_emit_event": _emit_event,
            "AC_notify_webhook": _notify_webhook,
            "AC_json_query": _json_query,
            "AC_json_extract": _json_extract,
            "AC_validate_json": _validate_json,
            "AC_run_saga": _run_saga,
            "AC_decision_table": _decision_table,
            "AC_repair_record": _repair_record,
            "AC_repair_resolved": _repair_resolved,
            "AC_repair_pending": _repair_pending,
            "AC_repair_approve": _repair_approve,
            "AC_detect_pii": _detect_pii,
            "AC_redact_pii": _redact_pii,
            "AC_export_sarif": _export_sarif,
            "AC_a11y_record_start": _a11y_record_start,
            "AC_a11y_record_stop": _a11y_record_stop,
            "AC_a11y_record_events": _a11y_record_events,

            # VLM-based element locator
            "AC_vlm_locate": _vlm_locate_as_list,
            "AC_vlm_click": click_by_description,

            # Self-healing locator (template-first, VLM fallback, audit log)
            "AC_self_heal_locate": _self_heal_locate,
            "AC_self_heal_click": _self_heal_click,
            "AC_self_heal_log_list": _self_heal_log_list,
            "AC_self_heal_log_clear": _self_heal_log_clear,

            # Assertion DSL (verify screen state; raise on mismatch)
            "AC_assert_text": _assert_text,
            "AC_assert_image": _assert_image,
            "AC_assert_pixel": _assert_pixel,
            "AC_assert_window": _assert_window,
            "AC_assert_vlm": _assert_vlm,
            "AC_assert_clipboard": _assert_clipboard,
            "AC_assert_process": _assert_process,
            "AC_assert_file": _assert_file,
            "AC_assert_http": _assert_http,
            "AC_assert_all": _assert_all,
            "AC_assert_any": _assert_any,
            "AC_assert_eventually": _assert_eventually,

            # Action-file integrity (HMAC-SHA256 sign / verify)
            "AC_sign_action_file": _sign_action_file,
            "AC_verify_action_file": _verify_action_file,
            "AC_encrypt_action_file": _encrypt_action_file,
            "AC_decrypt_action_file": _decrypt_action_file,

            # Data-driven execution (load rows from CSV / JSON / SQLite / ...)
            "AC_load_data": _load_data,

            # Flaky-test detection (analytics over the run-history store)
            "AC_flaky_report": _flaky_report,

            # QA suite runner + CI report output (JUnit / Allure)
            "AC_run_suite": _run_suite,

            # Flaky quarantine (skip known-unstable cases in suites)
            "AC_quarantine_add": _quarantine_add,
            "AC_quarantine_remove": _quarantine_remove,
            "AC_quarantine_list": _quarantine_list,
            "AC_quarantine_clear": _quarantine_clear,
            "AC_quarantine_auto": _quarantine_auto,

            # Accessibility / i18n audit (missing labels, contrast, truncation)
            "AC_audit_accessibility": _audit_accessibility,
            "AC_audit_contrast": _audit_contrast,
            "AC_wcag_audit": _wcag_audit,

            # Mobile device matrix (parallel script across devices)
            "AC_run_device_matrix": _run_device_matrix,

            # Media assertions (audio activity, video motion)
            "AC_assert_audio": _assert_audio,
            "AC_assert_video_changes": _assert_video_changes,

            # Computer-use (Anthropic computer_20250124 closed-loop agent)
            "AC_computer_use": _computer_use,

            # Generic plan→act→verify→retry agent loop (Anthropic / OpenAI)
            "AC_run_agent": _run_agent,

            # Screenshot PII redaction (blur emails / credit cards /
            # password fields / explicit regions before upload).
            "AC_redact_screenshot": _redact_screenshot,

            # Cross-host DAG orchestrator
            "AC_run_dag": _run_dag,

            # Chat-ops slash-command router
            "AC_chatops_dispatch": _chatops_dispatch,

            # Anchor-based locator (spatial composition of locator backends)
            "AC_anchor_locate": _anchor_locate,
            "AC_anchor_locate_all": _anchor_locate_all,
            "AC_anchor_click": _anchor_click,

            # Structured OCR (rows / tables / form fields)
            "AC_ocr_read_structure": _ocr_read_structure,

            # Smart waits (frame-diff replacements for time.sleep)
            "AC_wait_screen_stable": _wait_screen_stable,
            "AC_wait_pixel_changes": _wait_pixel_changes,
            "AC_wait_region_idle": _wait_region_idle,
            "AC_wait_for_file": _wait_for_file,
            "AC_wait_for_port": _wait_for_port,
            "AC_wait_for_process": _wait_for_process,
            "AC_wait_clipboard_change": _wait_clipboard_change,
            "AC_wait_image_gone": _wait_image_gone,
            "AC_wait_text_gone": _wait_text_gone,
            "AC_wait_color": _wait_color,
            "AC_wait_window_title": _wait_window_title,
            "AC_wait_window_closed": _wait_window_closed,

            # Cost telemetry (LLM token + USD tracking)
            "AC_costs_record": _costs_record,
            "AC_costs_summary": _costs_summary,
            "AC_costs_list": _costs_list,
            "AC_costs_clear": _costs_clear,

            # Failure → ticket automation (Jira / Linear / GitHub fan-out)
            "AC_failure_hook_fire": _failure_hook_fire,
            "AC_failure_hook_list": _failure_hook_list,
            "AC_failure_hook_clear": _failure_hook_clear,

            # A/B locator framework (race N locator strategies)
            "AC_ab_locate": _ab_locate,
            "AC_ab_report": _ab_report,
            "AC_ab_best_strategy": _ab_best_strategy,
            "AC_ab_clear": _ab_clear,

            # Multi-viewer presence roster (read-only / controller roles)
            "AC_presence_register": _presence_register,
            "AC_presence_unregister": _presence_unregister,
            "AC_presence_update_cursor": _presence_update_cursor,
            "AC_presence_set_role": _presence_set_role,
            "AC_presence_list": _presence_list,
            "AC_presence_clear": _presence_clear,

            # MCP server (Model Context Protocol stdio bridge)
            "AC_start_mcp_server": start_mcp_stdio_server,
            "AC_start_mcp_http_server": start_mcp_http_server,

            # WebRunner bridge (browser automation via je_web_runner)
            "AC_web_run": _ac_web_run,
            "AC_web_run_actions": _ac_web_run_actions,
            "AC_web_available": _ac_web_available,
            "AC_web_list_commands": _ac_web_list_commands,
            "AC_web_open": _ac_web_open,
            "AC_web_quit": _ac_web_quit,
            "AC_web_screenshot": _ac_web_screenshot,
            "AC_web_current_url": _ac_web_current_url,

            # Android via ADB (Phase 9.7)
            # uiautomator2 widget tree (find / click / dump)
            "AC_android_find_element": _ac_android_find_element,
            "AC_android_click_element": _ac_android_click_element,
            "AC_android_dump_hierarchy": _ac_android_dump_hierarchy,
            # iOS XCUITest (WebDriverAgent / facebook-wda)
            "AC_ios_tap": _ac_ios_tap,
            "AC_ios_swipe": _ac_ios_swipe,
            "AC_ios_type": _ac_ios_type,
            "AC_ios_screenshot": _ac_ios_screenshot,
            "AC_ios_find_element": _ac_ios_find_element,
            "AC_ios_click_element": _ac_ios_click_element,
            "AC_ios_dump_source": _ac_ios_dump_source,
            # Existing adb-based primitives
            "AC_android_tap": _ac_android_tap,
            "AC_android_swipe": _ac_android_swipe,
            "AC_android_key": _ac_android_key,
            "AC_android_text": _ac_android_text,
            "AC_android_screenshot": _ac_android_screenshot,
            "AC_android_list_devices": _ac_android_list_devices,
            "AC_android_shell": _ac_android_shell,

            # LLM action planner
            "AC_llm_plan": _llm_plan_for_executor,
            "AC_llm_run": _llm_run_for_executor,

            # Remote desktop host (this machine streams to others)
            "AC_start_remote_host": _remote_start_host,
            "AC_stop_remote_host": _remote_stop_host,
            "AC_remote_host_status": _remote_host_status,

            # Remote desktop viewer (this machine controls others)
            "AC_remote_connect": _remote_connect,
            "AC_remote_disconnect": _remote_disconnect,
            "AC_remote_viewer_status": _remote_viewer_status,
            "AC_remote_send_input": _remote_send_input,

            # WebSocket-transport remote desktop host
            "AC_start_ws_host": _ws_start_host,
            "AC_stop_ws_host": _ws_stop_host,
            "AC_ws_host_status": _ws_host_status,

            # WebSocket-transport remote desktop viewer
            "AC_ws_connect": _ws_connect,
            "AC_ws_disconnect": _ws_disconnect,
            "AC_ws_viewer_status": _ws_viewer_status,
            "AC_ws_send_input": _ws_send_input,

            # WebRTC-transport host (manual SDP exchange)
            "AC_start_webrtc_host": _webrtc_start_host,
            "AC_webrtc_create_offer": _webrtc_create_offer,
            "AC_webrtc_accept_answer": _webrtc_accept_answer,
            "AC_stop_webrtc_host": _webrtc_stop_host,
            "AC_webrtc_host_status": _webrtc_host_status,

            # WebRTC-transport viewer (manual SDP exchange)
            "AC_start_webrtc_viewer": _webrtc_start_viewer,
            "AC_webrtc_process_offer": _webrtc_process_offer,
            "AC_webrtc_send_input": _webrtc_send_input,
            "AC_stop_webrtc_viewer": _webrtc_stop_viewer,
            "AC_webrtc_viewer_status": _webrtc_viewer_status,

            # Virtual gamepad (ViGEm — drives games that ignore SendInput)
            "AC_gamepad_press": _gamepad_press,
            "AC_gamepad_release": _gamepad_release,
            "AC_gamepad_click": _gamepad_click,
            "AC_gamepad_dpad": _gamepad_dpad,
            "AC_gamepad_left_stick": _gamepad_left_stick,
            "AC_gamepad_right_stick": _gamepad_right_stick,
            "AC_gamepad_left_trigger": _gamepad_left_trigger,
            "AC_gamepad_right_trigger": _gamepad_right_trigger,
            "AC_gamepad_reset": _gamepad_reset,

            # REST API (HTTP front-end exposing the headless API)
            "AC_rest_api_start": _rest_api_start,
            "AC_rest_api_stop": _rest_api_stop,
            "AC_rest_api_status": _rest_api_status,

            # Admin console (manage many remote AutoControl REST hosts)
            "AC_admin_add_host": _admin_add_host,
            "AC_admin_remove_host": _admin_remove_host,
            "AC_admin_list_hosts": _admin_list_hosts,
            "AC_admin_poll": _admin_poll,
            "AC_admin_broadcast_execute": _admin_broadcast_execute,

            # Audit log (tamper-evident security log)
            "AC_audit_log_list": _audit_log_list,
            "AC_audit_log_verify": _audit_log_verify,
            "AC_audit_log_clear": _audit_log_clear,

            # WebRTC inspector (live stat history)
            "AC_inspector_recent": _inspector_recent,
            "AC_inspector_summary": _inspector_summary,
            "AC_inspector_reset": _inspector_reset,

            # USB device enumeration (read-only)
            "AC_list_usb_devices": _list_usb_devices,

            # USB hotplug watcher (Phase 1.5)
            "AC_usb_watch_start": _usb_watch_start,
            "AC_usb_watch_stop": _usb_watch_stop,
            "AC_usb_recent_events": _usb_recent_events,

            # USB passthrough (Phase 2) — flag, ACL, local + remote use
            "AC_usb_passthrough_enable": _usb_passthrough_enable,
            "AC_usb_passthrough_status": _usb_passthrough_status,
            "AC_usb_acl_list": _usb_acl_list,
            "AC_usb_acl_add": _usb_acl_add,
            "AC_usb_acl_remove": _usb_acl_remove,
            "AC_usb_acl_set_default": _usb_acl_set_default,
            "AC_usb_acl_export": _usb_acl_export,
            "AC_usb_acl_import": _usb_acl_import,
            "AC_usb_loopback_list": _usb_loopback_list,
            "AC_usb_loopback_open": _usb_loopback_open,
            "AC_usb_remote_list": _usb_remote_list,
            "AC_usb_remote_open": _usb_remote_open,

            # System diagnostics
            "AC_diagnose": _diagnose,

            # Config bundle export / import
            "AC_config_export": _config_export,
            "AC_config_import": _config_import,

            # Screenshot annotation (boxes / highlights / arrows / labels)
            "AC_annotate_screenshot": _annotate_screenshot,

            # Desktop notification
            "AC_notify": _notify,

            # Region colour statistics (dominant / average colour)
            "AC_region_color_stats": _region_color_stats,

            # Recoverable deletion (move a file to the OS recycle bin)
            "AC_move_to_trash": _move_to_trash,

            # QR code decoding from a screen region
            "AC_read_qr": _read_qr,

            # Scroll until a target image / text is visible
            "AC_scroll_to_find": _scroll_to_find,

            # Per-window capture + window-layout save / restore + snap
            "AC_capture_window": _capture_window,
            "AC_save_window_layout": _save_window_layout,
            "AC_restore_window_layout": _restore_window_layout,
            "AC_snap_window": _snap_window,
            "AC_arrange_grid": _arrange_grid,
            "AC_arrange_cascade": _arrange_cascade,
        }

    def known_commands(self) -> set:
        """Return the set of all command names the executor recognises."""
        return set(self.event_dict.keys()) | set(self._block_commands.keys())

    def _resolve_runtime_args(self, args: Any) -> Any:
        """Interpolate ``${var}`` placeholders against the current scope.

        Keys inside :attr:`_DEFERRED_ARG_KEYS` (``body``/``then``/``else``)
        are left as-is so nested action lists keep their placeholders for
        per-iteration evaluation.
        """
        if not self.variables:
            return args
        if isinstance(args, dict):
            resolved: Dict[str, Any] = {}
            for key, value in args.items():
                if key in self._DEFERRED_ARG_KEYS:
                    resolved[key] = value
                else:
                    resolved[key] = interpolate_value(value, self.variables)
            return resolved
        if isinstance(args, list):
            return [interpolate_value(item, self.variables) for item in args]
        return args

    def _execute_event(self, action: list) -> Any:
        """
        執行單一事件
        Execute a single event
        """
        name = action[0]
        block_handler = self._block_commands.get(name)
        if block_handler is not None:
            args = action[1] if len(action) == 2 else {}
            if not isinstance(args, dict):
                raise AutoControlActionException(
                    f"{name} requires a dict of arguments"
                )
            return block_handler(self, self._resolve_runtime_args(args))

        event = self.event_dict.get(name)
        if event is None:
            raise AutoControlActionException(f"Unknown action: {name}")

        if len(action) == 2:
            resolved = self._resolve_runtime_args(action[1])
            if isinstance(resolved, dict):
                return event(**resolved)
            return event(*resolved)
        if len(action) == 1:
            return event()
        raise AutoControlActionException(cant_execute_action_error_message + " " + str(action))

    def execute_action(self, action_list: Union[list, dict],
                       raise_on_error: bool = False,
                       _validated: bool = False,
                       dry_run: bool = False,
                       step_callback: Optional[Callable[[list], None]] = None,
                       ) -> Dict[str, str]:
        """
        執行 action list
        Execute all actions in action list

        :param action_list: list 或 dict (包含 auto_control key)
        :param raise_on_error: 若為 True，遇到錯誤立即拋出 (流程控制用)
        :param _validated: 內部用；子呼叫已驗證過時避免重複驗證
        :param dry_run: 若為 True，只記錄將執行的動作，不實際呼叫。
        :param step_callback: 每個 action 開始前呼叫此 hook（偵錯用）。
        :return: 執行紀錄字典
        """
        autocontrol_logger.info(f"execute_action, action_list: {action_list}")
        action_list = self._unwrap_action_list(action_list)
        if not _validated:
            validate_actions(action_list, self.known_commands())

        execute_record_dict: Dict[str, Any] = {}
        for action in action_list:
            if step_callback is not None:
                step_callback(action)
            if dry_run:
                execute_record_dict["dry-run: " + str(action)] = "(not executed)"
                continue
            self._run_one_action(action, execute_record_dict, raise_on_error)

        for key, value in execute_record_dict.items():
            autocontrol_logger.info("%s -> %s", key, value)
        return execute_record_dict

    @staticmethod
    def _unwrap_action_list(action_list: Union[list, dict]) -> list:
        """Normalise the ``action_list`` argument or raise on invalid input."""
        if isinstance(action_list, dict):
            action_list = action_list.get("auto_control")
            if action_list is None:
                raise AutoControlActionNullException(executor_list_error_message)
        if not isinstance(action_list, list) or len(action_list) == 0:
            raise AutoControlActionNullException(action_is_null_error_message)
        return action_list

    def _run_one_action(self, action: list, record: Dict[str, Any],
                        raise_on_error: bool) -> None:
        """Execute a single action, recording the result or raising."""
        import time as _time
        key = "execute: " + str(action)
        action_name = action[0] if action and isinstance(action[0], str) else "<invalid>"
        started = _time.monotonic()
        try:
            with default_profiler.measure(action_name):
                record[key] = self._execute_event(action)
            _observe_executor_metrics(action_name, started, error=None)
        except (LoopBreak, LoopContinue):
            raise
        except (AutoControlActionException, OSError, RuntimeError,
                AttributeError, TypeError, ValueError) as error:
            _observe_executor_metrics(action_name, started, error=error)
            if raise_on_error:
                raise
            autocontrol_logger.info(
                f"execute_action failed, action: {action}, error: {repr(error)}"
            )
            record_action_to_list("AC_execute_action", None, repr(error))
            record[key] = repr(error)

    def execute_files(self, execute_files_list: list) -> List[Dict[str, str]]:
        """
        執行 action files
        Execute actions from files

        :param execute_files_list: list of file paths
        :return: 每個檔案的執行結果
        """
        autocontrol_logger.info(f"execute_files, execute_files_list: {execute_files_list}")
        from je_auto_control.utils.action_signing import require_signed_actions
        execute_detail_list = []
        for file in execute_files_list:
            require_signed_actions(file)
            execute_detail_list.append(self.execute_action(read_action_json(file)))
        return execute_detail_list


# === 全域 Executor 實例 Global Executor Instance ===
executor = Executor()
package_manager.executor = executor


def add_command_to_executor(command_dict: dict) -> None:
    """
    新增自訂指令到 Executor
    Add custom commands to Executor

    :param command_dict: dict {command_name: function}
    """
    for command_name, command in command_dict.items():
        if isinstance(command, (types.MethodType, types.FunctionType)):
            executor.event_dict[command_name] = command
        else:
            raise AutoControlAddCommandException(add_command_exception_error_message)


def execute_action(action_list: list) -> Dict[str, str]:
    return executor.execute_action(action_list)


def execute_files(execute_files_list: list) -> List[Dict[str, str]]:
    return executor.execute_files(execute_files_list)


def execute_action_with_vars(action_list: list, variables: dict
                             ) -> Dict[str, str]:
    """Interpolate ``${name}`` placeholders with ``variables`` and execute.

    The same mapping seeds the runtime variable scope so flow-control
    commands (``AC_set_var``/``AC_if_var``/...) can read and mutate the
    same values during execution.
    """
    resolved = interpolate_actions(action_list, variables)
    executor.variables.update_many(variables)
    return executor.execute_action(resolved)
