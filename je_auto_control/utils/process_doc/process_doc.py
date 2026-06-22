"""Generate a step-by-step SOP document from an action list.

AutoControl records actions but doesn't *document* them. This turns a
recorded / authored action list into a numbered, human-readable
standard-operating-procedure — a structured step list plus an HTML
rendering (the UiPath Task-Capture deliverable) — for runbooks and review.

Pure standard library (``html`` escaping); imports no ``PySide6``.
"""
import html
from pathlib import Path
from typing import Any, Dict, List

# Command -> human verb phrase.
_VERBS = {
    "AC_click_mouse": "Click the mouse",
    "AC_press_mouse": "Press the mouse button",
    "AC_release_mouse": "Release the mouse button",
    "AC_set_mouse_position": "Move the mouse",
    "AC_mouse_scroll": "Scroll the wheel",
    "AC_type_keyboard": "Press a key",
    "AC_press_keyboard_key": "Hold a key",
    "AC_release_keyboard_key": "Release a key",
    "AC_write": "Type text",
    "AC_hotkey": "Press a hotkey",
    "AC_screenshot": "Take a screenshot",
    "AC_locate_and_click": "Find an image and click it",
    "AC_locate_image_center": "Locate an image",
    "AC_click_text": "Click on text",
    "AC_set_var": "Set a variable",
}
# Per-command arg whose value is the most descriptive detail.
_DETAIL_KEYS = ("write_string", "text", "keycode", "key_code_list", "image",
                "name", "value", "x")


def describe_step(command: str, args: Dict[str, Any]) -> str:
    """Return a human-readable description for one action."""
    base = _VERBS.get(command,
                      command.replace("AC_", "").replace("_", " ").strip()
                      or "Action")
    for key in _DETAIL_KEYS:
        if key in args and args[key] not in (None, ""):
            return f"{base} ({key}: {args[key]})"
    return base


def generate_sop(actions: List[Any], *,
                 title: str = "Automation Procedure") -> Dict[str, Any]:
    """Return a structured SOP for ``actions`` plus an HTML rendering."""
    steps: List[Dict[str, Any]] = []
    for index, action in enumerate(actions, start=1):
        command = action[0] if action and isinstance(action[0], str) else "?"
        args = (action[1] if len(action) > 1 and isinstance(action[1], dict)
                else {})
        steps.append({"n": index, "command": command,
                      "description": describe_step(command, args),
                      "args": args})
    return {"title": title, "step_count": len(steps), "steps": steps,
            "html": _render_html(title, steps)}


def _render_html(title: str, steps: List[Dict[str, Any]]) -> str:
    items = "\n".join(
        f"  <li><strong>Step {step['n']}:</strong> "
        f"{html.escape(step['description'])}</li>" for step in steps)
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(title)}</title></head>\n<body>\n"
        f"<h1>{html.escape(title)}</h1>\n<ol>\n{items}\n</ol>\n</body></html>\n")


def write_sop(actions: List[Any], path: str, *,
              title: str = "Automation Procedure") -> str:
    """Write the SOP HTML for ``actions`` to ``path``; return the path."""
    document = generate_sop(actions, title=title)
    target = Path(path)
    target.write_text(document["html"], encoding="utf-8")
    return str(target.resolve())
