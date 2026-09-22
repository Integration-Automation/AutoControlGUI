"""MCP adapters for locating things on screen: accessibility tree, waits, vision.

Same contract as :mod:`._handlers` -- normalise arguments and return values so
they survive the JSON-RPC boundary, with every project import lazy -- split out
by theme because ``_handlers.py`` is over the 750-line limit.
"""
from typing import Any, Dict, List, Optional

from je_auto_control.utils.mcp_server.tools._handlers_executor_bridge import (
    _observe_handler,
)


def a11y_list(app_name: Optional[str] = None,
              max_results: int = 100,
              window_title: Optional[str] = None) -> List[Dict[str, Any]]:
    from je_auto_control.utils.accessibility.accessibility_api import (
        list_accessibility_elements,
    )
    return [element.to_dict()
            for element in list_accessibility_elements(
                app_name=app_name, max_results=int(max_results),
                window_title=window_title,
            )]


def a11y_find(name: Optional[str] = None,
              role: Optional[str] = None,
              app_name: Optional[str] = None,
              window_title: Optional[str] = None,
              contains: bool = False) -> Optional[Dict[str, Any]]:
    from je_auto_control.utils.accessibility import accessibility_api as api
    element = api.find_accessibility_element(
        name=name, role=role, app_name=app_name, window_title=window_title,
        contains=bool(contains))
    return None if element is None else element.to_dict()


def a11y_find_all(name: Optional[str] = None,
                  role: Optional[str] = None,
                  app_name: Optional[str] = None,
                  window_title: Optional[str] = None,
                  contains: bool = False,
                  max_results: int = 50,
                  scan_limit: int = 1500) -> List[Dict[str, Any]]:
    from je_auto_control.utils.accessibility import accessibility_api as api
    return [element.to_dict() for element in api.find_accessibility_elements(
        name=name, role=role, app_name=app_name, window_title=window_title,
        contains=bool(contains), max_results=int(max_results),
        scan_limit=int(scan_limit))]


def a11y_click(name: Optional[str] = None,
               role: Optional[str] = None,
               app_name: Optional[str] = None) -> bool:
    from je_auto_control.utils.accessibility.accessibility_api import (
        click_accessibility_element,
    )
    return bool(click_accessibility_element(name=name, role=role,
                                             app_name=app_name))


def control_get_value(name=None, role=None, app_name=None,
                      automation_id=None):
    from je_auto_control.utils.accessibility import control_get_value as _g
    return _g(name=name, role=role, app_name=app_name,
              automation_id=automation_id)


def control_get_state(name=None, role=None, app_name=None,
                      automation_id=None):
    from je_auto_control.utils.accessibility import control_get_state as _g
    return _g(name=name, role=role, app_name=app_name,
              automation_id=automation_id)


def control_set_value(value, name=None, role=None, app_name=None,
                      automation_id=None):
    from je_auto_control.utils.accessibility import control_set_value as _s
    return _s(value, name=name, role=role, app_name=app_name,
              automation_id=automation_id)


def control_invoke(name=None, role=None, app_name=None, automation_id=None):
    from je_auto_control.utils.accessibility import control_invoke as _i
    return _i(name=name, role=role, app_name=app_name,
              automation_id=automation_id)


def control_toggle(name=None, role=None, app_name=None, automation_id=None):
    from je_auto_control.utils.accessibility import control_toggle as _t
    return _t(name=name, role=role, app_name=app_name,
              automation_id=automation_id)


def read_table(name=None, role=None, app_name=None, automation_id=None):
    from je_auto_control.utils.accessibility import read_control_table as _r
    return _r(name=name, role=role, app_name=app_name,
              automation_id=automation_id)


def _element_repo(path):
    from je_auto_control.utils.element_repository import ElementRepository
    return ElementRepository(path)


def _observe_predicate(kind, params):
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
        raise ValueError(f"unknown observe kind: {kind!r}")
    return builders[kind]()


def observe_add(name, kind="image", event="appear", actions=None, **params):
    from je_auto_control.utils.observer import default_observer
    default_observer.add(name, _observe_predicate(kind, params),
                         _observe_handler(actions or []), events=(event,))
    return {"name": name, "kind": kind, "event": event}


def observe_remove(name):
    from je_auto_control.utils.observer import default_observer
    return {"removed": default_observer.remove(name)}


def observe_list():
    from je_auto_control.utils.observer import default_observer
    return {"names": default_observer.names()}


def observe_poll():
    from je_auto_control.utils.observer import default_observer
    return {"fired": default_observer.poll_once()}


def observe_start():
    from je_auto_control.utils.observer import default_observer
    default_observer.start()
    return {"running": default_observer.running}


def observe_stop():
    from je_auto_control.utils.observer import default_observer
    default_observer.stop()
    return {"running": default_observer.running}


def mark_screen(app_name=None, render_path=None):
    from je_auto_control.utils.set_of_marks import mark_screen as _ms
    return _ms(app_name=app_name, render_path=render_path)


def mark_click(mark_id):
    from je_auto_control.utils.set_of_marks import mark_click as _mc
    return {"clicked": _mc(int(mark_id))}


def screen_snapshot(app_name=None):
    from je_auto_control.utils.screen_state import snapshot_screen
    return {"snapshot": snapshot_screen(app_name=app_name)}


def screen_diff(before, after):
    from je_auto_control.utils.screen_state import diff_snapshots
    return diff_snapshots(before, after)


def screen_changed(app_name=None):
    from je_auto_control.utils.screen_state import screen_changed as _sc
    return _sc(app_name=app_name)


def describe_screen(app_name=None):
    from je_auto_control.utils.screen_state import describe_screen as _ds
    return _ds(app_name=app_name)


def heal_stats(limit=200):
    from je_auto_control.utils.heal_analytics import analyze_heal_log
    return analyze_heal_log(limit=int(limit))


def image_hash(path, algo="average"):
    from je_auto_control.utils.image_dedup import average_hash, dhash
    hasher = dhash if algo == "dhash" else average_hash
    return {"hash": hasher(path)}


def dedupe_images(paths, max_distance=5):
    from je_auto_control.utils.image_dedup import dedupe_images as _dedupe
    return {"unique": _dedupe(paths, max_distance=max_distance)}


def to_physical(x, y, physical_w, physical_h, model_w, model_h):
    from je_auto_control.utils.coordinate_space import CoordinateSpace
    px, py = CoordinateSpace(physical_w, physical_h, model_w,
                             model_h).to_physical(x, y)
    return {"x": px, "y": py}


def to_model(x, y, physical_w, physical_h, model_w, model_h):
    from je_auto_control.utils.coordinate_space import CoordinateSpace
    mx, my = CoordinateSpace(physical_w, physical_h, model_w,
                             model_h).to_model(x, y)
    return {"x": mx, "y": my}


def repair_record(key, method, coordinates=None, description=None,
                  confidence=1.0, auto_threshold=0.9, db=None):
    from je_auto_control.utils.locator_repair import RepairStore
    sug = RepairStore(db).record(
        key, method=method, coordinates=coordinates, description=description,
        confidence=confidence, auto_threshold=auto_threshold)
    return {"id": sug.id, "status": sug.status}


def repair_resolved(key, db=None):
    from je_auto_control.utils.locator_repair import RepairStore
    return {"locator": RepairStore(db).resolved(key)}


def repair_pending(db=None):
    from je_auto_control.utils.locator_repair import RepairStore
    return {"pending": RepairStore(db).pending()}


def repair_approve(suggestion_id, db=None):
    from je_auto_control.utils.locator_repair import RepairStore
    return {"approved": RepairStore(db).approve(suggestion_id)}


def vlm_locate(description: str,
               screen_region: Optional[List[int]] = None,
               model: Optional[str] = None) -> Optional[List[int]]:
    from je_auto_control.utils.vision.vlm_api import locate_by_description
    coords = locate_by_description(description, screen_region=screen_region,
                                    model=model)
    return None if coords is None else [int(coords[0]), int(coords[1])]


def vlm_click(description: str,
              screen_region: Optional[List[int]] = None,
              model: Optional[str] = None) -> bool:
    from je_auto_control.utils.vision.vlm_api import click_by_description
    return bool(click_by_description(description,
                                      screen_region=screen_region,
                                      model=model))


def self_heal_locate(template_path: Optional[str] = None,
                     description: Optional[str] = None,
                     detect_threshold: float = 0.9,
                     screen_region: Optional[List[int]] = None,
                     model: Optional[str] = None,
                     raise_on_miss: bool = False) -> Dict[str, Any]:
    from je_auto_control.utils.self_healing import self_heal_locate as _impl
    return _impl(
        template_path=template_path, description=description,
        detect_threshold=float(detect_threshold),
        screen_region=screen_region, model=model,
        raise_on_miss=bool(raise_on_miss),
    ).to_dict()


def self_heal_click(template_path: Optional[str] = None,
                    description: Optional[str] = None,
                    mouse_keycode: str = "mouse_left",
                    detect_threshold: float = 0.9,
                    screen_region: Optional[List[int]] = None,
                    model: Optional[str] = None,
                    raise_on_miss: bool = False) -> Dict[str, Any]:
    from je_auto_control.utils.self_healing import self_heal_click as _impl
    return _impl(
        template_path=template_path, description=description,
        mouse_keycode=mouse_keycode,
        detect_threshold=float(detect_threshold),
        screen_region=screen_region, model=model,
        raise_on_miss=bool(raise_on_miss),
    ).to_dict()


def self_heal_log_list(limit: int = 50) -> List[Dict[str, Any]]:
    from je_auto_control.utils.self_healing import default_heal_log
    return [event.to_dict()
            for event in default_heal_log.list_events(limit=int(limit))]


def self_heal_log_clear() -> Dict[str, Any]:
    from je_auto_control.utils.self_healing import default_heal_log
    default_heal_log.clear()
    return {"cleared": True, "path": str(default_heal_log.path)}


def a11y_dump(app_name: Optional[str] = None,
              max_results: int = 500) -> Dict[str, Any]:
    from je_auto_control.utils.accessibility import dump_accessibility_tree
    return dump_accessibility_tree(
        app_name=app_name, max_results=int(max_results),
    ).to_dict()


def ab_locate(target_id: str,
              strategies: Dict[str, Dict[str, Any]],
              max_parallel: int = 4,
              record: bool = True) -> Dict[str, Any]:
    from je_auto_control.utils.ab_locator import ab_locate as _impl
    from je_auto_control.utils.anchor_locator import (
        Locator as AnchorLocator,
    )
    locators = {name: AnchorLocator(**spec)
                for name, spec in strategies.items()}
    return _impl(
        target_id=target_id, strategies=locators,
        max_parallel=int(max_parallel), record=bool(record),
    ).to_dict()


def ab_report(target_id: str) -> Dict[str, Any]:
    from je_auto_control.utils.ab_locator import ab_report_for
    return ab_report_for(target_id).to_dict()


def ab_best_strategy(target_id: str) -> Dict[str, Any]:
    from je_auto_control.utils.ab_locator import ab_best_strategy as _impl
    return {"target_id": target_id, "strategy": _impl(target_id)}


def wait_screen_stable(region: Optional[List[int]] = None,
                        timeout_s: float = 10.0,
                        poll_interval_s: float = 0.2,
                        stable_for_s: float = 0.5,
                        max_pixel_diff: int = 0) -> Dict[str, Any]:
    from je_auto_control.utils.smart_waits import wait_until_screen_stable
    return wait_until_screen_stable(
        region=region, timeout_s=float(timeout_s),
        poll_interval_s=float(poll_interval_s),
        stable_for_s=float(stable_for_s),
        max_pixel_diff=int(max_pixel_diff),
    ).to_dict()


def wait_for_file(path: str, timeout_s: float = 30.0,
                  poll_interval_s: float = 0.25,
                  stable_for_s: float = 1.0,
                  min_size: int = 1) -> Dict[str, Any]:
    from je_auto_control.utils.smart_waits import wait_until_file
    return wait_until_file(
        path, timeout_s=float(timeout_s),
        poll_interval_s=float(poll_interval_s),
        stable_for_s=float(stable_for_s), min_size=int(min_size),
    ).to_dict()


def wait_for_port(host: str, port: int, timeout_s: float = 30.0,
                  poll_interval_s: float = 0.25,
                  connect_timeout_s: float = 1.0) -> Dict[str, Any]:
    from je_auto_control.utils.smart_waits import wait_until_port
    return wait_until_port(
        host, int(port), timeout_s=float(timeout_s),
        poll_interval_s=float(poll_interval_s),
        connect_timeout_s=float(connect_timeout_s),
    ).to_dict()


def wait_for_process(name: str, present: bool = True, timeout_s: float = 30.0,
                     poll_interval_s: float = 0.25) -> Dict[str, Any]:
    from je_auto_control.utils.smart_waits import wait_until_process
    return wait_until_process(
        name, present=bool(present), timeout_s=float(timeout_s),
        poll_interval_s=float(poll_interval_s),
    ).to_dict()


def wait_pixel_changes(x: int, y: int,
                        timeout_s: float = 10.0,
                        poll_interval_s: float = 0.1,
                        rgb_tolerance: int = 5) -> Dict[str, Any]:
    from je_auto_control.utils.smart_waits import wait_until_pixel_changes
    return wait_until_pixel_changes(
        x=int(x), y=int(y),
        timeout_s=float(timeout_s),
        poll_interval_s=float(poll_interval_s),
        rgb_tolerance=int(rgb_tolerance),
    ).to_dict()


def wait_region_idle(region: List[int],
                      timeout_s: float = 10.0,
                      poll_interval_s: float = 0.2,
                      stable_for_s: float = 0.5,
                      max_pixel_diff: int = 0) -> Dict[str, Any]:
    from je_auto_control.utils.smart_waits import wait_until_region_idle
    return wait_until_region_idle(
        region=region, timeout_s=float(timeout_s),
        poll_interval_s=float(poll_interval_s),
        stable_for_s=float(stable_for_s),
        max_pixel_diff=int(max_pixel_diff),
    ).to_dict()


def ocr_read_structure(region: Optional[List[int]] = None,
                        lang: str = "eng",
                        min_confidence: float = 60.0,
                        ) -> Dict[str, Any]:
    from je_auto_control.utils.ocr.structure import read_structure
    return read_structure(
        region=region, lang=lang,
        min_confidence=float(min_confidence),
    ).to_dict()
