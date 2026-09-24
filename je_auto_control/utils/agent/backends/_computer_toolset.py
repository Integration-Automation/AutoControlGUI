"""The GA computer toolset (``computer_toolset_20260801``) on top of the computer-use backend.

The toolset differs from the beta ``computer_20251124`` tool in four ways the
agent loop has to follow:

* each action is its own ``tool_use`` whose ``name`` is the member
  (``left_click``, ``type``…), not one ``computer`` call with ``input.action``;
* one turn may hold several such calls, answered together in the next user
  message, one ``tool_result`` each;
* every ``tool_result`` carries ``"toolset_name": "computer"`` (the API rejects
  one without it);
* the tool takes no display size and the API does not downscale, so a
  screenshot must already fit the image limits, and the model's coordinates
  are in that screenshot's pixel space;
* ``zoom`` asks for a region at full resolution; the answer is that crop,
  fitted into the same limits, and later coordinates stay in the full
  screenshot's space.

``AgentLoop`` runs one decision per ``decide_next_action`` call, so
:class:`ToolsetBatch` hands a turn's calls out one at a time and gathers the
results until the batch is answered.
"""
from __future__ import annotations

import io
import math
from typing import Any, Dict, List, Optional, Tuple

TOOLSET_TYPE = "computer_toolset_20260801"
TOOLSET_NAME = "computer"

#: Models that take computer use only as the toolset: ``computer_20251124``
#: is a 400 on them.
TOOLSET_ONLY_MODELS = frozenset({"claude-opus-5-5"})

#: The toolset definition sent to the API; every member, ``zoom`` included,
#: is enabled by default.
TOOLSET_SCHEMA: Dict[str, Any] = {"type": TOOLSET_TYPE}

#: Image limits of the models the toolset runs on (Claude 4.7 and later, the
#: high-resolution tier): a long edge of 2576 px and 4784 visual tokens, one
#: token per started 28 x 28 patch. The API rejects a larger tool_result image
#: instead of downscaling it.
MAX_LONG_EDGE_PX = 2576
MAX_VISUAL_TOKENS = 4784
PATCH_PX = 28

_SKIPPED = "not run: an earlier action in this batch failed"


def visual_tokens(width: int, height: int) -> int:
    """What an image of ``width`` x ``height`` costs: one token per started patch."""
    return math.ceil(width / PATCH_PX) * math.ceil(height / PATCH_PX)


def fitted_size(width: int, height: int) -> Tuple[int, int]:
    """The largest size, aspect ratio kept, inside both image limits."""
    scale = min(1.0, MAX_LONG_EDGE_PX / max(width, height),
                math.sqrt(MAX_VISUAL_TOKENS * PATCH_PX * PATCH_PX / float(width * height)))
    size = (max(1, int(width * scale)), max(1, int(height * scale)))
    # Patches round up, so the pixel bound can still be a few tokens over.
    while visual_tokens(*size) > MAX_VISUAL_TOKENS:
        scale *= 0.995
        size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return size


def fit_screenshot(png: bytes) -> Tuple[bytes, Tuple[float, float]]:
    """Downscale ``png`` into the toolset's limits; return it and the ``(sx, sy)`` scale.

    The scale maps screen pixels to screenshot pixels, so a coordinate the
    model gives is divided by it to reach the screen. An image already inside
    the limits comes back unchanged with a scale of 1.
    """
    from PIL import Image
    with Image.open(io.BytesIO(png)) as image:
        width, height = image.size
        size = fitted_size(width, height)
        if size == (width, height):
            return png, (1.0, 1.0)
        resized = image.resize(size, Image.Resampling.LANCZOS)
    return _png_bytes(resized), (size[0] / width, size[1] / height)


def zoom_image(png: bytes, region: Tuple[int, int, int, int]) -> bytes:
    """The ``(x0, y0, x1, y1)`` part of ``png`` at full resolution, fitted into the limits."""
    from PIL import Image
    with Image.open(io.BytesIO(png)) as image:
        x0, y0, x1, y1 = _clip_region(region, image.size)
        crop = image.crop((x0, y0, x1, y1))
        size = fitted_size(*crop.size)
        if size != crop.size:
            crop = crop.resize(size, Image.Resampling.LANCZOS)
        return _png_bytes(crop)


def screen_region(region: Any, scale: Tuple[float, float]) -> Tuple[int, int, int, int]:
    """A zoom ``region`` in the model's screenshot space as screenshot pixels."""
    if not isinstance(region, (list, tuple)) or len(region) != 4:
        raise ValueError(f"zoom region must be [x0, y0, x1, y1], got {region!r}")
    x0, y0, x1, y1 = (float(value) for value in region)
    if not all(math.isfinite(value) for value in (x0, y0, x1, y1)):
        raise ValueError(f"zoom region must be finite, got {region!r}")
    sx, sy = scale
    return (int(min(x0, x1) / sx), int(min(y0, y1) / sy),
            int(math.ceil(max(x0, x1) / sx)), int(math.ceil(max(y0, y1) / sy)))


def _clip_region(region: Tuple[int, int, int, int],
                 size: Tuple[int, int]) -> Tuple[int, int, int, int]:
    """``region`` inside an image of ``size``, at least one pixel each way."""
    width, height = size
    x0 = min(max(0, region[0]), width - 1)
    y0 = min(max(0, region[1]), height - 1)
    return x0, y0, min(max(x0 + 1, region[2]), width), min(max(y0 + 1, region[3]), height)


def _png_bytes(image: Any) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def unscale_decision(decision: Dict[str, Any], scale: Tuple[float, float]) -> Dict[str, Any]:
    """Map every ``x`` / ``y`` in ``decision`` from screenshot to screen pixels."""
    sx, sy = scale
    if (sx, sy) == (1.0, 1.0):
        return decision
    for inputs in _all_inputs(decision):
        if "x" in inputs:
            inputs["x"] = int(round(inputs["x"] / sx))
        if "y" in inputs:
            inputs["y"] = int(round(inputs["y"] / sy))
    return decision


def _all_inputs(decision: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The decision's own inputs and those of every nested action."""
    inputs = decision.get("input") or {}
    found = [inputs]
    for key in ("action_list", "actions"):
        for action in inputs.get(key) or []:
            if len(action) == 2 and isinstance(action[1], dict):
                found.append(action[1])
    return found


class ToolsetBatch:
    """The member calls of one toolset turn, handed to the loop one at a time."""

    def __init__(self) -> None:
        self._queue: List[Tuple[str, Dict[str, Any]]] = []
        self._results: List[Dict[str, Any]] = []
        self.inflight: Optional[str] = None

    def load(self, calls: List[Tuple[str, Dict[str, Any]]]) -> None:
        """Queue ``(tool_use_id, decision)`` for every call in a turn."""
        self._queue = list(calls)

    def has_next(self) -> bool:
        """Whether a call of the current turn is still to run."""
        return bool(self._queue)

    def next_decision(self) -> Dict[str, Any]:
        """The next call's decision; its id is in flight until :meth:`record`."""
        self.inflight, decision = self._queue.pop(0)
        return decision

    def record(self, content: List[Dict[str, Any]], is_error: bool) -> None:
        """Answer the in-flight call; after a failure, answer the rest as skipped.

        Every call in the turn must get a result, and running the rest of a
        batch after one of its steps failed would act on a screen the model
        did not plan for.
        """
        if self.inflight is None:
            return
        self._results.append(result_block(self.inflight, content, is_error))
        self.inflight = None
        if is_error:
            for tool_use_id, _decision in self._queue:
                self._results.append(result_block(
                    tool_use_id, [{"type": "text", "text": _SKIPPED}], True))
            self._queue = []

    def drain_results(self) -> List[Dict[str, Any]]:
        """Every result gathered since the last drain, in call order."""
        results, self._results = self._results, []
        return results


def result_block(tool_use_id: str, content: List[Dict[str, Any]],
                 is_error: bool) -> Dict[str, Any]:
    """One toolset ``tool_result``, carrying the ``toolset_name`` the API requires."""
    return {"type": "tool_result", "tool_use_id": tool_use_id,
            "toolset_name": TOOLSET_NAME, "content": content,
            "is_error": bool(is_error)}
