"""Adapter functions that bridge MCP tool calls to AutoControl's headless API.

Each adapter normalises arguments (parses ints / paths) and return
values (lists / dicts / strings, or :class:`MCPContent`) so they
survive the JSON-RPC boundary. Wrapper imports are lazy to keep the
top-level MCP server boot cheap.
"""
import os
from typing import Any, Dict, List

from je_auto_control.utils.mcp_server.tools._handlers_executor_bridge import (
    anchor_locate,
)
from je_auto_control.utils.mcp_server.tools._handlers_operations import (
    _agent_memory, _skill_lib, _work_queue,
)
from je_auto_control.utils.mcp_server.tools._handlers_locators import (
    _element_repo,
)


# === Semantic locators (a11y / VLM) =========================================


def handle_file_dialog(path, action="open", window_title=None,
                       timeout_s=10.0, confirm_key="enter"):
    from je_auto_control.utils.file_dialog import handle_file_dialog as _h
    return _h(path, action=action, window_title=window_title,
              timeout_s=float(timeout_s), confirm_key=confirm_key)


def queue_add(db, data, reference=None, name="default"):
    return {"id": _work_queue(db, name).add(data, reference=reference)}


def queue_next(db, name="default", stale_after_s=None):
    item = _work_queue(db, name).get_next(stale_after_s=stale_after_s)
    return None if item is None else {
        "id": item.id, "reference": item.reference, "data": item.data,
        "status": item.status, "retries": item.retries, "claim": item.claim}


def queue_complete(db, item_id, output=None, name="default", claim=None):
    _work_queue(db, name).complete(int(item_id), output=output,
                                   claim=None if claim is None else int(claim))
    return {"id": int(item_id), "status": "success"}


def queue_fail(db, item_id, error, kind="application", max_retries=3,
               name="default", claim=None):
    status = _work_queue(db, name).fail(int(item_id), str(error),
                                        kind=str(kind),
                                        max_retries=int(max_retries),
                                        claim=None if claim is None else int(claim))
    return {"id": int(item_id), "status": status}


def queue_stats(db, name="default"):
    if _no_database(db):
        from je_auto_control.utils.work_queue.work_queue import (
            STATUS_FAILED, STATUS_IN_PROGRESS, STATUS_NEW, STATUS_SUCCESS,
        )
        return dict.fromkeys((STATUS_NEW, STATUS_IN_PROGRESS, STATUS_SUCCESS, STATUS_FAILED), 0)
    return _work_queue(db, name).stats()


def _no_database(db) -> bool:
    """Whether a read-only tool's ``db`` does not exist yet.

    Opening it would create an empty SQLite file at a caller-chosen path,
    which a tool advertised as read-only must not do.
    """
    return not os.path.exists(db)


def element_save(path, key, name=None, role=None, app_name=None):
    return {"locator": _element_repo(path).save(
        key, name=name, role=role, app_name=app_name)}


def element_find(path, key):
    return _element_repo(path).find_info(key)


def element_click(path, key):
    return {"clicked": _element_repo(path).click(key)}


def element_remove(path, key):
    return {"removed": _element_repo(path).remove(key)}


def element_list(path):
    return {"keys": _element_repo(path).keys()}


def skill_save(path, name, actions, description="", tags=None):
    skill = _skill_lib(path).save(name, actions, description=description,
                                  tags=tags)
    return {"name": skill.name, "tags": skill.tags}


def skill_run(path, name):
    return {"record": _skill_lib(path).run(name)}


def skill_list(path):
    return {"names": _skill_lib(path).names()}


def skill_remove(path, name):
    return {"removed": _skill_lib(path).remove(name)}


def skill_search(path, query):
    return {"names": [s.name for s in _skill_lib(path).search(query)]}


def read_workbook(path, sheet=""):
    from je_auto_control.utils.office import read_workbook as _read
    return {"rows": _read(path, sheet=sheet)}


def write_workbook(path, rows, sheet="Sheet1"):
    from je_auto_control.utils.office import write_workbook as _write
    return {"path": _write(path, rows, sheet=sheet)}


def read_document(path):
    from je_auto_control.utils.office import read_document as _read
    return _read(path)


def write_document(path, paragraphs):
    from je_auto_control.utils.office import write_document as _write
    return {"path": _write(path, paragraphs)}


def read_presentation(path):
    from je_auto_control.utils.office import read_presentation as _read
    return _read(path)


def write_presentation(path, slides):
    from je_auto_control.utils.office import write_presentation as _write
    return {"path": _write(path, slides)}


def _episode_dict(episode):
    return {"id": episode.id, "goal": episode.goal, "steps": episode.steps,
            "outcome": episode.outcome, "tags": episode.tags,
            "score": episode.score}


def memory_remember(db, goal, steps=None, outcome="", tags=None):
    return {"id": _agent_memory(db).remember(
        goal, steps=steps, outcome=outcome, tags=tags)}


def memory_recall(db, query, limit=5):
    if _no_database(db):
        return {"episodes": []}
    eps = _agent_memory(db).recall(query, limit=int(limit))
    return {"episodes": [_episode_dict(ep) for ep in eps]}


def memory_recent(db, limit=10):
    if _no_database(db):
        return {"episodes": []}
    eps = _agent_memory(db).recent(limit=int(limit))
    return {"episodes": [_episode_dict(ep) for ep in eps]}


def memory_forget(db, episode_id):
    return {"removed": _agent_memory(db).forget(int(episode_id))}


def memory_stats(db):
    if _no_database(db):
        return {"episodes": 0}
    return _agent_memory(db).stats()


def pseudo_localize(text=None, mapping=None, expansion=0.4):
    from je_auto_control.utils.i18n_test import (
        pseudo_localize as _pl, pseudo_localize_catalog as _plc)
    if mapping is not None:
        return {"catalog": _plc(mapping, expansion=float(expansion))}
    return {"text": _pl(text or "", expansion=float(expansion))}


def check_overflow(elements=None, avg_char_px=7.0, app_name=None):
    from je_auto_control.utils.i18n_test import check_overflow as _co
    items = elements
    if items is None:
        from je_auto_control.utils.accessibility.accessibility_api import (
            list_accessibility_elements)
        items = list_accessibility_elements(app_name=app_name)
    return {"issues": _co(items, avg_char_px=float(avg_char_px))}


def check_catalog(base, target):
    from je_auto_control.utils.i18n_test import check_catalog as _cc
    return _cc(base, target)


def replay_timeline(events, speed=1.0):
    from je_auto_control.utils.input_macro import replay_timeline as _rt
    return {"played": _rt(events, speed=float(speed))}


def input_sequence(steps):
    from je_auto_control.utils.input_macro import run_sequence as _rs
    return {"log": _rs(steps)}


def clip_history_capture():
    from je_auto_control.utils.clipboard_history import default_clipboard_history
    return {"added": default_clipboard_history.capture_once()}


def clip_history_list():
    from je_auto_control.utils.clipboard_history import default_clipboard_history
    return {"history": default_clipboard_history.snapshot()}


def clip_history_search(query):
    from je_auto_control.utils.clipboard_history import default_clipboard_history
    return {"matches": default_clipboard_history.search(query)}


def clip_history_start():
    from je_auto_control.utils.clipboard_history import default_clipboard_history
    default_clipboard_history.start()
    return {"running": default_clipboard_history.running}


def clip_history_stop():
    from je_auto_control.utils.clipboard_history import default_clipboard_history
    default_clipboard_history.stop()
    return {"running": default_clipboard_history.running}


def generate_sop(actions, title="Automation Procedure", path=None):
    from je_auto_control.utils.process_doc import generate_sop as _gen
    from je_auto_control.utils.process_doc import write_sop as _write
    if path:
        return {"path": _write(actions, path, title=title)}
    return _gen(actions, title=title)


def tween_drag(start, end, steps=30, easing="ease_in_out_quad",
               button="mouse_left"):
    from je_auto_control.utils.tween_drag import tween_drag as _td
    return {"points": _td(tuple(start), tuple(end), steps=int(steps),
                          easing=easing, button=button)["points"]}


def fuzzy_ratio(left, right, ignore_case=True):
    from je_auto_control.utils.fuzzy import fuzzy_ratio as _ratio
    return {"score": _ratio(left, right, ignore_case=ignore_case)}


def fuzzy_best_match(query, choices, score_cutoff=0.0, ignore_case=True):
    from je_auto_control.utils.fuzzy import fuzzy_best_match as _best
    best = _best(query, choices, score_cutoff=score_cutoff,
                 ignore_case=ignore_case)
    if best is None:
        return {"match": None, "score": 0.0, "index": -1}
    return {"match": best[0], "score": best[1], "index": best[2]}


def fuzzy_dedupe(items, threshold=0.9, ignore_case=True):
    from je_auto_control.utils.fuzzy import fuzzy_dedupe as _dedupe
    return {"unique": _dedupe(items, threshold=threshold,
                              ignore_case=ignore_case)}


def canonicalize_url(url):
    from je_auto_control.utils.url_canon import canonicalize_url as _canon
    return {"url": _canon(url)}


def normalize_url(url, sort_query=False, drop_fragment=False):
    from je_auto_control.utils.url_canon import normalize_url as _norm
    # `drop_fragment` is this surface's name for it; url_canon calls the
    # same flag `strip_fragment`.
    return {"url": _norm(url, sort_query=bool(sort_query),
                         strip_fragment=bool(drop_fragment))}


def urls_equal(first, second):
    from je_auto_control.utils.url_canon import urls_equal as _equal
    return {"equal": _equal(first, second)}


def parse_decimal(text, locale="en_US"):
    from je_auto_control.utils.locale_parse import parse_decimal as _parse
    return {"value": _parse(text, locale)}


def parse_number(text, locale="en_US"):
    from je_auto_control.utils.locale_parse import parse_number as _parse
    return {"value": _parse(text, locale)}


def format_decimal(value, locale="en_US"):
    from je_auto_control.utils.locale_parse import format_decimal as _fmt
    return {"text": _fmt(value, locale)}


def format_currency(value, currency, locale="en_US"):
    from je_auto_control.utils.locale_parse import format_currency as _fmt
    return {"text": _fmt(value, currency, locale)}


def format_date(value, locale="en_US", fmt="medium"):
    from je_auto_control.utils.locale_parse import format_date as _fmt
    return {"text": _fmt(value, locale, fmt)}


def voice_register(phrase, actions):
    from je_auto_control.utils.voice import default_voice_router
    default_voice_router.register(phrase, actions)
    return {"phrases": default_voice_router.phrases()}


def voice_dispatch(text):
    from je_auto_control.utils.voice import default_voice_router
    outcome = default_voice_router.dispatch(text)
    return {"matched": outcome["matched"], "phrase": outcome["phrase"]}


def voice_list():
    from je_auto_control.utils.voice import default_voice_router
    return {"phrases": default_voice_router.phrases()}


def voice_clear():
    from je_auto_control.utils.voice import default_voice_router
    default_voice_router.clear()
    return {"cleared": True}


def json_query(data, path):
    from je_auto_control.utils.jsonpath import json_query as _q
    return {"matches": _q(data, path)}


def json_extract(data, mapping):
    from je_auto_control.utils.jsonpath import json_extract as _x
    return {"result": _x(data, mapping)}


def validate_json(data, schema):
    from je_auto_control.utils.json_schema import validate_json as _v
    return _v(data, schema).to_dict()


def resolve_pointer(doc, pointer):
    from je_auto_control.utils.json_patch import resolve_pointer as _resolve
    return {"value": _resolve(doc, pointer)}


def apply_json_patch(doc, patch):
    from je_auto_control.utils.json_patch import apply_patch
    return {"result": apply_patch(doc, patch)}


def make_json_patch(old, new):
    from je_auto_control.utils.json_patch import make_patch
    return {"patch": make_patch(old, new)}


def merge_patch(doc, patch):
    from je_auto_control.utils.json_patch import merge_patch as _merge
    return {"result": _merge(doc, patch)}


def search_documents(docs, query, top_k=10, mode="bm25"):
    from je_auto_control.utils.search_index import search_documents as _search
    hits = _search(docs, query, top_k=int(top_k), mode=mode)
    return {"hits": [{"doc_id": h.doc_id, "score": h.score} for h in hits]}


def rrule_occurrences(rule, dtstart, count=10):
    import datetime as _dt
    from je_auto_control.utils.recurrence import occurrences, parse_rrule
    start = _dt.datetime.fromisoformat(dtstart)
    moments = occurrences(parse_rrule(rule), start, count=int(count))
    return {"occurrences": [moment.isoformat() for moment in moments]}


def rrule_next(rule, dtstart, now=None):
    import datetime as _dt
    from je_auto_control.utils.recurrence import next_occurrence, parse_rrule
    start = _dt.datetime.fromisoformat(dtstart)
    when = _dt.datetime.fromisoformat(now) if now else None
    moment = next_occurrence(parse_rrule(rule), start, now=when)
    return {"next": moment.isoformat() if moment else None}


def match_json(actual, expected, partial=False, match_type=False):
    from je_auto_control.utils.json_contract import match_json as _match
    return _match(actual, expected, partial=bool(partial),
                  match_type=bool(match_type)).to_dict()


def diff_json(actual, expected):
    from je_auto_control.utils.json_contract import diff_json as _diff
    return {"diffs": _diff(actual, expected)}


def unified_diff(a, b):
    from je_auto_control.utils.text_diff import unified_diff as _diff
    return {"diff": _diff(a, b)}


def apply_unified(text, diff):
    from je_auto_control.utils.text_diff import apply_unified as _apply
    return {"result": _apply(text, diff)}


def three_way_merge(base, ours, theirs):
    from je_auto_control.utils.text_diff import three_way_merge as _merge
    outcome = _merge(base, ours, theirs)
    return {"text": outcome.text, "clean": outcome.clean,
            "conflicts": outcome.conflicts}


def detect_pii(text, kinds=None):
    from je_auto_control.utils.pii_text import detect_pii as _detect
    findings = _detect(text, kinds=kinds)
    return {"findings": [{"kind": f.kind, "value": f.value,
                          "start": f.start, "end": f.end} for f in findings]}


def redact_pii(text, kinds=None, mode="label", mask_char="*"):
    from je_auto_control.utils.pii_text import redact_pii_text
    return {"text": redact_pii_text(text, kinds=kinds, mode=mode,
                                    mask_char=mask_char)}


# === WebRunner bridge (browser automation via je_web_runner) ================

def web_available() -> bool:
    from je_auto_control.utils.webrunner_bridge import is_webrunner_available
    return bool(is_webrunner_available())


def web_list_commands() -> List[str]:
    from je_auto_control.utils.webrunner_bridge import list_webrunner_commands
    return list(list_webrunner_commands())


def web_run(action: Dict[str, Any]) -> Any:
    from je_auto_control.utils.webrunner_bridge import run_webrunner_action
    return run_webrunner_action(action)


def web_run_actions(actions: List[Dict[str, Any]]) -> List[Any]:
    from je_auto_control.utils.webrunner_bridge import run_webrunner_actions
    return list(run_webrunner_actions(actions))


def web_open(url: str, browser: str = "chrome") -> Any:
    from je_auto_control.utils.webrunner_bridge import web_open as _open
    return _open(url, browser=browser)


def web_quit() -> Any:
    from je_auto_control.utils.webrunner_bridge import web_quit as _quit
    return _quit()


def web_screenshot(file_path: str) -> Any:
    from je_auto_control.utils.webrunner_bridge import (
        web_screenshot as _shot,
    )
    return _shot(file_path)


def web_current_url() -> Any:
    from je_auto_control.utils.webrunner_bridge import (
        web_current_url as _url,
    )
    return _url()


def anchor_click(anchor: Dict[str, Any], target: Dict[str, Any],
                 mouse_keycode: str = "mouse_left",
                 relation: str = "near",
                 max_distance_px: float = 200.0) -> Dict[str, Any]:
    outcome = anchor_locate(anchor, target, relation, max_distance_px)
    if outcome.get("found") and outcome.get("target_coords"):
        cx, cy = outcome["target_coords"]
        from je_auto_control.wrapper.auto_control_mouse import (
            click_mouse, set_mouse_position,
        )
        set_mouse_position(int(cx), int(cy))
        click_mouse(mouse_keycode, int(cx), int(cy))
    return outcome


def presence_register(viewer_id: str, label: str = "",
                      role: str = "observer") -> Dict[str, Any]:
    from je_auto_control.utils.remote_desktop.presence import (
        default_presence_registry,
    )
    return default_presence_registry().register(
        viewer_id, label, role=role,
    ).to_dict()


def presence_unregister(viewer_id: str) -> Dict[str, Any]:
    from je_auto_control.utils.remote_desktop.presence import (
        default_presence_registry,
    )
    return {"viewer_id": viewer_id,
            "removed": default_presence_registry().unregister(viewer_id)}


def presence_update_cursor(viewer_id: str, x: int, y: int) -> Dict[str, Any]:
    from je_auto_control.utils.remote_desktop.presence import (
        default_presence_registry,
    )
    return default_presence_registry().update_cursor(
        viewer_id, int(x), int(y),
    ).to_dict()


def presence_set_role(viewer_id: str, role: str) -> Dict[str, Any]:
    from je_auto_control.utils.remote_desktop.presence import (
        default_presence_registry,
    )
    return default_presence_registry().update_role(viewer_id, role).to_dict()


def presence_list() -> List[Dict[str, Any]]:
    from je_auto_control.utils.remote_desktop.presence import (
        default_presence_registry,
    )
    return [row.to_dict() for row in default_presence_registry().list()]


