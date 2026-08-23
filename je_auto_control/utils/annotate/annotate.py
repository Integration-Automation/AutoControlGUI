"""Draw labelled boxes / highlights / arrows / text onto a screenshot.

A reporting + debugging complement to the redaction engine (which blurs
sensitive regions): annotation *marks* regions of interest on a captured
screen so failure artifacts and docs point straight at what matters.
Pure Pillow — no Qt, no screen capture — so it is fully unit-testable.

An annotation is a dict with a ``type`` and type-specific fields::

    {"type": "box", "rect": [x1, y1, x2, y2], "color": [255, 0, 0],
     "width": 3, "label": "Login button"}
    {"type": "highlight", "rect": [...], "color": [255, 235, 0], "alpha": 80}
    {"type": "arrow", "start": [x1, y1], "end": [x2, y2], "color": [...]}
    {"type": "text", "position": [x, y], "text": "step 3", "color": [...]}
"""
from __future__ import annotations

import io
import math
from pathlib import Path
from typing import (
    TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Tuple, Union,
)

if TYPE_CHECKING:  # pragma: no cover - annotations only
    from PIL import Image, ImageDraw

ImageSource = Union[str, Path, bytes, "Image.Image"]


def _load_image(source: ImageSource) -> "Image.Image":
    """Load ``source`` (path / bytes / PIL image) as an RGBA image."""
    from PIL import Image
    if isinstance(source, Image.Image):
        return source.convert("RGBA")
    if isinstance(source, bytes):
        return Image.open(io.BytesIO(source)).convert("RGBA")
    return Image.open(str(source)).convert("RGBA")


def _color(value: Optional[Sequence[int]],
           default: Tuple[int, int, int] = (255, 0, 0)
           ) -> Tuple[int, int, int]:
    if not value or len(value) < 3:
        return default
    return (int(value[0]), int(value[1]), int(value[2]))


def _draw_box(draw: ImageDraw.ImageDraw, ann: Dict[str, Any]) -> None:
    rect = [int(v) for v in ann["rect"]]
    color = _color(ann.get("color"))
    draw.rectangle(rect, outline=color, width=int(ann.get("width", 3)))
    label = ann.get("label")
    if label:
        draw.text((rect[0] + 2, max(0, rect[1] - 12)), str(label), fill=color)


def _draw_highlight(overlay: ImageDraw.ImageDraw, ann: Dict[str, Any]) -> None:
    rect = [int(v) for v in ann["rect"]]
    color = _color(ann.get("color"), (255, 235, 0))
    alpha = max(0, min(255, int(ann.get("alpha", 80))))
    overlay.rectangle(rect, fill=(color[0], color[1], color[2], alpha))


def _draw_arrow(draw: ImageDraw.ImageDraw, ann: Dict[str, Any]) -> None:
    start = tuple(int(v) for v in ann["start"])
    end = tuple(int(v) for v in ann["end"])
    color = _color(ann.get("color"))
    width = int(ann.get("width", 3))
    draw.line([start, end], fill=color, width=width)
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    head = max(8, width * 4)
    for offset in (math.radians(150), math.radians(-150)):
        wing = (end[0] + head * math.cos(angle + offset),
                end[1] + head * math.sin(angle + offset))
        draw.line([end, wing], fill=color, width=width)


def _draw_text(draw: ImageDraw.ImageDraw, ann: Dict[str, Any]) -> None:
    raw = ann["position"]
    pos = (float(raw[0]), float(raw[1]))
    draw.text(pos, str(ann.get("text", "")), fill=_color(ann.get("color")))


def annotate_screenshot(source: ImageSource,
                        annotations: List[Dict[str, Any]],
                        output_path: Union[str, Path]) -> str:
    """Draw ``annotations`` onto ``source`` and save the result as PNG.

    Returns the output path. ``source`` may be a file path, PNG bytes, or a
    PIL image; ``annotations`` is a list of box / highlight / arrow / text
    dicts. Unknown annotation types are ignored.
    """
    from PIL import Image, ImageDraw
    base = _load_image(source)
    highlight_layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    highlight_draw = ImageDraw.Draw(highlight_layer)
    for ann in annotations:
        if ann.get("type") == "highlight":
            _draw_highlight(highlight_draw, ann)
    base = Image.alpha_composite(base, highlight_layer)
    draw = ImageDraw.Draw(base)
    dispatch = {"box": _draw_box, "arrow": _draw_arrow, "text": _draw_text}
    for ann in annotations:
        handler = dispatch.get(str(ann.get("type", "")))
        if handler is not None:
            handler(draw, ann)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    base.convert("RGB").save(str(out), format="PNG")
    return str(out)
