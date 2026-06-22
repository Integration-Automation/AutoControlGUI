"""Semantic screen state — snapshot/diff and a structured description.

AutoControl ships a *pixel* diff (visual regression); this is the *semantic*
companion. A snapshot normalizes the accessibility tree to
``{role, name, bbox}`` rows; :func:`diff_snapshots` reports what **appeared**,
**vanished**, or **moved** ("Save dialog appeared", "row added") — the
feedback signal an agent needs to verify a step's effect. :func:`describe_screen`
returns a compact "where am I" structure (role counts + control labels) for an
agent's orientation.

Pure standard library; imports no ``PySide6``. The pure functions
(``snapshot`` / ``diff_snapshots`` / ``describe_screen`` with supplied
elements) are unit-testable without a live desktop.
"""
from typing import Any, Dict, List, Optional

_INTERACTIVE_HINTS = ("button", "edit", "text", "combo", "check", "radio",
                      "menu", "link", "tab", "list", "slider")
_last_snapshot: List[Dict[str, Any]] = []


def _role_of(element: Any) -> str:
    if isinstance(element, dict):
        return str(element.get("role") or "")
    return str(getattr(element, "role", "") or "")


def _name_of(element: Any) -> str:
    if isinstance(element, dict):
        return str(element.get("name") or element.get("text") or "")
    return str(getattr(element, "name", "") or "")


def _bbox_of(element: Any) -> List[int]:
    if isinstance(element, dict):
        raw = element.get("bbox") or element.get("bounds") or []
    else:
        raw = getattr(element, "bounds", []) or []
    return list(raw)


def snapshot(elements: List[Any]) -> List[Dict[str, Any]]:
    """Normalize elements to ``[{role, name, bbox}]`` for diffing."""
    return [{"role": _role_of(el), "name": _name_of(el), "bbox": _bbox_of(el)}
            for el in elements]


def _key(item: Dict[str, Any]) -> tuple:
    return (item.get("role", ""), item.get("name", ""))


def _moved_items(before_map: Dict[tuple, Dict[str, Any]],
                 after_map: Dict[tuple, Dict[str, Any]]) -> List[Dict[str, Any]]:
    moved = []
    for key, item in after_map.items():
        prior = before_map.get(key)
        if prior is not None and item.get("bbox") != prior.get("bbox"):
            moved.append({"role": key[0], "name": key[1],
                          "before": prior.get("bbox"),
                          "after": item.get("bbox")})
    return moved


def _diff_summary(added: List[Dict[str, Any]], removed: List[Dict[str, Any]],
                  moved: List[Dict[str, Any]]) -> List[str]:
    lines = [f"appeared: {i['role']} {i['name']}".strip() for i in added]
    lines += [f"vanished: {i['role']} {i['name']}".strip() for i in removed]
    lines += [f"moved: {m['role']} {m['name']}".strip() for m in moved]
    return lines


def diff_snapshots(before: List[Dict[str, Any]],
                   after: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Diff two snapshots into ``{added, removed, moved, summary}``.

    Identity is ``(role, name)``; ``moved`` are matched items whose bbox
    changed. ``summary`` is a list of human-readable strings.
    """
    before_map = {_key(i): i for i in before}
    after_map = {_key(i): i for i in after}
    added = [after_map[k] for k in after_map if k not in before_map]
    removed = [before_map[k] for k in before_map if k not in after_map]
    moved = _moved_items(before_map, after_map)
    return {"added": added, "removed": removed, "moved": moved,
            "summary": _diff_summary(added, removed, moved),
            "changed_count": len(added) + len(removed) + len(moved)}


def _live_elements(app_name: Optional[str]) -> List[Any]:
    from je_auto_control.utils.accessibility.accessibility_api import (
        list_accessibility_elements)
    return list_accessibility_elements(app_name=app_name)


def snapshot_screen(app_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """Snapshot the live accessibility tree and cache it as the baseline."""
    snap = snapshot(_live_elements(app_name))
    _last_snapshot.clear()
    _last_snapshot.extend(snap)
    return snap


def screen_changed(app_name: Optional[str] = None) -> Dict[str, Any]:
    """Diff the live screen against the last :func:`snapshot_screen` baseline."""
    before = list(_last_snapshot)
    after = snapshot(_live_elements(app_name))
    _last_snapshot.clear()
    _last_snapshot.extend(after)
    return diff_snapshots(before, after)


def _is_interactive(role: str) -> bool:
    lowered = role.lower()
    return any(hint in lowered for hint in _INTERACTIVE_HINTS)


def describe_screen(elements: Optional[List[Any]] = None,
                    app_name: Optional[str] = None) -> Dict[str, Any]:
    """Return a compact structured description of the screen.

    ``{app, element_count, by_role, controls}`` where ``controls`` lists the
    labels of interactive elements — a cheap "where am I" for an agent.
    """
    items = snapshot(elements if elements is not None
                     else _live_elements(app_name))
    by_role: Dict[str, int] = {}
    controls: List[str] = []
    for item in items:
        role = item["role"] or "(unknown)"
        by_role[role] = by_role.get(role, 0) + 1
        if item["name"] and _is_interactive(role):
            controls.append(item["name"])
    return {"app": app_name or "", "element_count": len(items),
            "by_role": by_role, "controls": controls}
