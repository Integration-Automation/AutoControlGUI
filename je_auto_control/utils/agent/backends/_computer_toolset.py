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
import re
from typing import Any, Dict, List, Optional, Tuple

TOOLSET_TYPE = "computer_toolset_20260801"
TOOLSET_NAME = "computer"

#: Models that take computer use only as the toolset: ``computer_20251124``
#: is a 400 on them.
TOOLSET_ONLY_MODELS = frozenset({"claude-opus-5-5"})

#: The toolset definition sent to the API; every member, ``zoom`` included,
#: is enabled by default.
TOOLSET_SCHEMA: Dict[str, Any] = {"type": TOOLSET_TYPE}

#: Image limits per tier, as (long edge px, visual tokens), one token per
#: started 28 x 28 patch (vision docs). Claude 4.7 and later -- every model the
#: toolset runs on -- are high-resolution; older models are standard. The
#: toolset rejects a larger tool_result image; for the beta tool the API
#: downscales it and the model's coordinates then no longer match the screen.
HIGH_RES_TIER = (2576, 4784)
STANDARD_TIER = (1568, 1568)
MAX_LONG_EDGE_PX, MAX_VISUAL_TOKENS = HIGH_RES_TIER
PATCH_PX = 28

#: "claude-<family>-<major>[-<minor>]", minor being one or two digits (a date
#: suffix is eight), anywhere in the id so Bedrock / Vertex ids match too.
_MODEL_VERSION = re.compile(r"claude-[a-z]+-(\d+)(?:-(\d{1,2}))?(?![0-9])")


def image_tier(model: Optional[str]) -> Tuple[int, int]:
    """The image tier of ``model``: high-resolution from Claude 4.7 on, else standard.

    An id this cannot read gets the standard tier, whose limits every model accepts.
    """
    match = _MODEL_VERSION.search(model or "")
    if match is None:
        return STANDARD_TIER
    version = (int(match.group(1)), int(match.group(2) or 0))
    return HIGH_RES_TIER if version >= (4, 7) else STANDARD_TIER

_SKIPPED = "not run: an earlier action in this batch failed"


def visual_tokens(width: int, height: int) -> int:
    """What an image of ``width`` x ``height`` costs: one token per started patch."""
    return math.ceil(width / PATCH_PX) * math.ceil(height / PATCH_PX)


def _fits(width: int, height: int, tier: Tuple[int, int]) -> bool:
    """Whether an image of this size is inside both limits (padded edges, tokens)."""
    long_edge, max_tokens = tier
    return (math.ceil(width / PATCH_PX) * PATCH_PX <= long_edge
            and math.ceil(height / PATCH_PX) * PATCH_PX <= long_edge
            and visual_tokens(width, height) <= max_tokens)


def fitted_size(width: int, height: int,
                tier: Tuple[int, int] = HIGH_RES_TIER) -> Tuple[int, int]:
    """The size Claude itself resizes an image to: the largest inside ``tier``.

    The vision docs' reference rule: a binary search along the long edge, the
    short edge rounded half to even. Matching it exactly means the model sees
    precisely the image sent (1920x1080 on the standard tier is 1456x819).
    """
    if _fits(width, height, tier):
        return width, height
    if height > width:
        fitted_height, fitted_width = fitted_size(height, width, tier)
        return fitted_width, fitted_height
    aspect = width / height
    low, high = 1, width            # low always fits; high never does
    while low + 1 < high:
        middle = (low + high) // 2
        if _fits(middle, max(round(middle / aspect), 1), tier):
            low = middle
        else:
            high = middle
    return low, max(round(low / aspect), 1)


def fit_screenshot(png: bytes, tier: Tuple[int, int] = HIGH_RES_TIER,
                   ) -> Tuple[bytes, Tuple[float, float]]:
    """Downscale ``png`` into ``tier``'s limits; return it and the ``(sx, sy)`` scale.

    The scale maps screen pixels to screenshot pixels, so a coordinate the
    model gives is divided by it to reach the screen. An image already inside
    the limits comes back unchanged with a scale of 1.
    """
    from PIL import Image
    try:
        image = Image.open(io.BytesIO(png))
    except OSError:   # PIL.UnidentifiedImageError: nothing to fit, send as is
        return png, (1.0, 1.0)
    with image:
        width, height = image.size
        size = fitted_size(width, height, tier)
        if size == (width, height):
            return png, (1.0, 1.0)
        resized = image.resize(size, Image.Resampling.LANCZOS)
    return _png_bytes(resized), (size[0] / width, size[1] / height)


def resize_png(png: bytes, size: Tuple[int, int]) -> bytes:
    """``png`` at exactly ``size``; unchanged when it already is, or is not an image."""
    from PIL import Image
    try:
        image = Image.open(io.BytesIO(png))
    except OSError:   # PIL.UnidentifiedImageError: nothing to resize, send as is
        return png
    with image:
        if image.size == tuple(size):
            return png
        return _png_bytes(image.resize(tuple(size), Image.Resampling.LANCZOS))


def zoom_image(png: bytes, region: Tuple[int, int, int, int],
               tier: Tuple[int, int] = HIGH_RES_TIER) -> bytes:
    """The ``(x0, y0, x1, y1)`` part of ``png`` at full resolution, fitted into ``tier``."""
    from PIL import Image
    with Image.open(io.BytesIO(png)) as image:
        x0, y0, x1, y1 = _clip_region(region, image.size)
        crop = image.crop((x0, y0, x1, y1))
        size = fitted_size(*crop.size, tier)
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
        for key, factor in (("x", sx), ("y", sy)):
            value = _coordinate(inputs.get(key))
            # Only numbers, or numeric strings -- a model following a schema
            # that said "string" sent "1400", which went to the screen
            # unscaled: a generic tool call's x may be anything else too.
            if value is not None:
                inputs[key] = int(round(value / factor))
    return decision


def _coordinate(value: Any) -> Optional[float]:
    """``value`` as a finite number if it is one or spells one; else ``None``."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError:
            return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return None


def _all_inputs(decision: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The decision's own inputs and those of every nested action."""
    inputs = decision.get("input") or {}
    found = [inputs]
    for key in ("action_list", "actions"):
        for action in inputs.get(key) or []:
            # A malformed action (a dict, [None], [5]) raised KeyError / TypeError.
            if isinstance(action, (list, tuple)) and len(action) == 2 and isinstance(action[1], dict):
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
