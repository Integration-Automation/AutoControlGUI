import types
from typing import Any, Callable, Dict, List, Optional, Union

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


def _a11y_dump(app_name: Optional[str] = None,
                max_results: int = 500) -> Dict[str, Any]:
    """Executor adapter: dump the accessibility tree as nested dict."""
    from je_auto_control.utils.accessibility import dump_accessibility_tree
    return dump_accessibility_tree(
        app_name=app_name, max_results=int(max_results),
    ).to_dict()


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
                   max_distance_px: float = 200.0) -> Dict[str, Any]:
    """Executor adapter: anchor-based spatial locator."""
    from je_auto_control.utils.anchor_locator import (
        Locator, anchor_locate,
    )
    anchor_loc = Locator(**anchor)
    target_loc = Locator(**target)
    outcome = anchor_locate(
        anchor=anchor_loc, target=target_loc,
        relation=relation, max_distance_px=float(max_distance_px),
    )
    return outcome.to_dict()


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
        AgentBackendError, AnthropicAgentBackend, OpenAIAgentBackend,
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
        backend_obj = OpenAIAgentBackend(
            tools=tools,
            model=model or "gpt-4o",
            max_tokens=int(max_tokens),
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
    _DEFERRED_ARG_KEYS: frozenset = frozenset({"body", "then", "else"})

    def __init__(self):
        self._block_commands = BLOCK_COMMANDS
        self.variables = VariableScope()
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

            # Computer-use (Anthropic computer_20250124 closed-loop agent)
            "AC_computer_use": _computer_use,

            # Generic plan→act→verify→retry agent loop (Anthropic / OpenAI)
            "AC_run_agent": _run_agent,

            # Cross-host DAG orchestrator
            "AC_run_dag": _run_dag,

            # Chat-ops slash-command router
            "AC_chatops_dispatch": _chatops_dispatch,

            # Anchor-based locator (spatial composition of locator backends)
            "AC_anchor_locate": _anchor_locate,
            "AC_anchor_click": _anchor_click,

            # Structured OCR (rows / tables / form fields)
            "AC_ocr_read_structure": _ocr_read_structure,

            # Smart waits (frame-diff replacements for time.sleep)
            "AC_wait_screen_stable": _wait_screen_stable,
            "AC_wait_pixel_changes": _wait_pixel_changes,
            "AC_wait_region_idle": _wait_region_idle,

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

            # System diagnostics
            "AC_diagnose": _diagnose,

            # Config bundle export / import
            "AC_config_export": _config_export,
            "AC_config_import": _config_import,
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
        execute_detail_list = []
        for file in execute_files_list:
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
