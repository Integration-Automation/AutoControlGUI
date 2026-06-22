"""Set-of-Marks overlay — number on-screen elements for VLM grounding.

Modern GUI agents ground far more reliably when shown a screenshot with
numbered boxes drawn over the interactable elements plus an ``id -> bbox``
legend ("Set-of-Marks" prompting): the model picks a *number* instead of
guessing pixel coordinates. This turns AutoControl's existing element
sources (accessibility tree / OCR / template hits) into that two-stage
"mark then pick a number" loop, and resolves a chosen number back to a
click.

The legend computation (:func:`mark_elements` / :func:`resolve_mark`) is
pure Python and unit-testable with synthetic elements; rendering uses
Pillow (already a dependency). Imports no ``PySide6``.
"""
import io
from pathlib import Path
from typing import Any, Dict, List, Optional

_OUTLINE = (255, 0, 0)
_last_marks: List[Dict[str, Any]] = []


def _bbox_of(element: Any) -> List[int]:
    if isinstance(element, dict):
        raw = element.get("bbox") or element.get("bounds") or []
    else:
        raw = getattr(element, "bounds", []) or []
    return list(raw)


def _text_of(element: Any) -> str:
    if isinstance(element, dict):
        return str(element.get("text") or element.get("name") or "")
    return str(getattr(element, "name", "") or "")


def _role_of(element: Any) -> str:
    if isinstance(element, dict):
        return str(element.get("role") or "")
    return str(getattr(element, "role", "") or "")


def mark_elements(elements: List[Any]) -> List[Dict[str, Any]]:
    """Assign a numeric mark to each element with a valid bounds.

    Returns ``[{id, bbox, center, role, text}]`` (ids start at 1).
    """
    marks: List[Dict[str, Any]] = []
    next_id = 1
    for element in elements:
        bbox = _bbox_of(element)
        if len(bbox) < 4:
            continue
        left, top, width, height = (int(bbox[0]), int(bbox[1]),
                                    int(bbox[2]), int(bbox[3]))
        marks.append({
            "id": next_id, "bbox": [left, top, width, height],
            "center": [left + width // 2, top + height // 2],
            "role": _role_of(element), "text": _text_of(element)})
        next_id += 1
    return marks


def resolve_mark(marks: List[Dict[str, Any]],
                 mark_id: int) -> Optional[Dict[str, Any]]:
    """Return the mark whose ``id`` equals ``mark_id`` (or ``None``)."""
    for mark in marks:
        if mark["id"] == int(mark_id):
            return mark
    return None


def _draw_marks(image: Any, marks: List[Dict[str, Any]]) -> Any:
    from PIL import ImageDraw
    draw = ImageDraw.Draw(image)
    for mark in marks:
        left, top, width, height = mark["bbox"]
        draw.rectangle([left, top, left + width, top + height],
                       outline=_OUTLINE, width=2)
        label = str(mark["id"])
        draw.rectangle([left, top, left + 8 + 6 * len(label), top + 12],
                       fill=_OUTLINE)
        draw.text((left + 2, top + 1), label, fill=(255, 255, 255))
    return image


def render_marks(image_bytes: bytes,
                 marks: List[Dict[str, Any]]) -> bytes:
    """Draw numbered boxes for ``marks`` on a PNG; return annotated PNG bytes."""
    from PIL import Image
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    _draw_marks(image, marks)
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def last_marks() -> List[Dict[str, Any]]:
    """Return a copy of the marks from the most recent :func:`mark_screen`."""
    return [dict(mark) for mark in _last_marks]


def mark_screen(app_name: Optional[str] = None,
                render_path: Optional[str] = None) -> Dict[str, Any]:
    """Number the live accessibility elements; optionally render an overlay.

    Stores the marks for a later :func:`mark_click`. When ``render_path`` is
    given, a screenshot is captured, annotated, and saved there.
    """
    from je_auto_control.utils.accessibility.accessibility_api import (
        list_accessibility_elements)
    marks = mark_elements(list_accessibility_elements(app_name=app_name))
    _last_marks.clear()
    _last_marks.extend(marks)
    result: Dict[str, Any] = {"marks": marks}
    if render_path:
        from je_auto_control.utils.cv2_utils.screenshot import pil_screenshot
        image = _draw_marks(pil_screenshot().convert("RGB"), marks)
        target = Path(render_path)
        image.save(str(target), format="PNG")
        result["image_path"] = str(target.resolve())
    return result


def mark_click(mark_id: int,
               marks: Optional[List[Dict[str, Any]]] = None) -> bool:
    """Click the centre of the marked element; return whether it matched.

    Uses ``marks`` if supplied, else the marks from the last
    :func:`mark_screen`.
    """
    mark = resolve_mark(marks if marks is not None else _last_marks, mark_id)
    if mark is None:
        return False
    center_x, center_y = mark["center"]
    from je_auto_control.wrapper.auto_control_mouse import (
        click_mouse, set_mouse_position)
    set_mouse_position(center_x, center_y)
    click_mouse("mouse_left", center_x, center_y)
    return True
