"""A VLM strategy version for heal evaluation, with its model usage counted.

:func:`vlm_strategy` asks a ``utils/vision`` backend where the sample's
``description`` is, on the sample's own frame -- the region crop encoded as
PNG, never a new screenshot -- and turns the reply into a screen point through
:meth:`LocateRequest.to_screen`. A reply outside the image it was shown is a
misread and counts as a miss, the same rule ``locate_by_description`` applies.

Every request made is counted on the strategy's
:class:`~je_auto_control.utils.self_healing.evaluation.UsageMeter`. Tokens are
taken from the backend's ``last_usage`` when it reports one; cost is the
backend's own figure, or tokens multiplied by a price the dataset gives. Where
neither exists the column stays ``None``: this module never estimates.

Calling a real backend costs money and needs its API key; the ``null`` backend
and any object with a ``locate`` method (a fake) work offline.

Imports no ``PySide6``; OpenCV is imported when a sample is located.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional, Tuple

from je_auto_control.utils.self_healing.evaluation import (
    HealingEvaluationError, LocateRequest, LocatorStrategy, ModelUsage, Point,
    UsageMeter,
)

STRATEGY_VLM = "vlm"
PRICE_KEYS = ("input_per_mtok", "output_per_mtok")
_PER_MTOK = 1_000_000.0


def _png_of(frame: Any, box: Tuple[int, int, int, int]) -> bytes:
    """The ``box`` of ``frame`` (2-D gray or RGB array) as PNG bytes."""
    import cv2
    import numpy as np
    left, top, right, bottom = box
    crop = np.asarray(frame)[top:bottom, left:right]
    if crop.ndim == 3:
        crop = cv2.cvtColor(crop, cv2.COLOR_RGB2BGR)
    encoded, buffer = cv2.imencode(".png", crop)
    if not encoded:
        raise ValueError("cannot encode the frame as PNG")
    return bytes(buffer.tobytes())


def _checked_price(price: Optional[Mapping[str, Any]]) -> Optional[Tuple[float, float]]:
    if price is None:
        return None
    if not isinstance(price, Mapping) or set(price) != set(PRICE_KEYS):
        raise HealingEvaluationError(
            f"price must be an object with {list(PRICE_KEYS)}, got {price!r}")
    try:
        values = (float(price[PRICE_KEYS[0]]), float(price[PRICE_KEYS[1]]))
    except (TypeError, ValueError) as error:
        raise HealingEvaluationError(f"price values must be numbers, got {price!r}") from error
    if min(values) < 0:
        raise HealingEvaluationError(f"price values must not be negative, got {price!r}")
    return values


def _count(value: Any) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def usage_of_call(reported: Any, price: Optional[Tuple[float, float]]) -> ModelUsage:
    """One request's usage from what the backend reported for it (maybe nothing)."""
    if not isinstance(reported, Mapping):
        return ModelUsage(calls=1)
    tokens_in = _count(reported.get("input_tokens"))
    tokens_out = _count(reported.get("output_tokens"))
    cost = reported.get("cost")
    if isinstance(cost, bool) or not isinstance(cost, (int, float)):
        cost = None
    if cost is None and price is not None and tokens_in is not None and tokens_out is not None:
        cost = (tokens_in * price[0] + tokens_out * price[1]) / _PER_MTOK
    return ModelUsage(1, tokens_in, tokens_out, None if cost is None else float(cost))


def _clear_usage(backend: Any) -> None:
    """Forget the previous request's usage, where the backend lets us."""
    try:
        backend.last_usage = None
    except AttributeError:
        pass  # a fake with fixed attributes: its usage is read as it stands


def vlm_strategy(backend: Any = None, *, model: Optional[str] = None,
                 price: Optional[Mapping[str, Any]] = None) -> LocatorStrategy:
    """A strategy version that asks a VLM backend for the sample's description.

    ``backend`` is a ``utils/vision`` backend (or any object with ``locate``
    and ``available``); ``None`` uses the one ``get_backend()`` picks from the
    environment, resolved at the first sample. ``price`` is
    ``{"input_per_mtok": ..., "output_per_mtok": ...}`` and turns reported
    tokens into a cost. A sample with no ``description`` is that sample's
    error, as is a backend that is not available.
    """
    rates = _checked_price(price)
    meter = UsageMeter()
    bound = {"backend": backend}

    def resolve() -> Any:
        if bound["backend"] is None:
            from je_auto_control.utils.vision.backends import get_backend
            bound["backend"] = get_backend()
        return bound["backend"]

    def locate(request: LocateRequest) -> Optional[Point]:
        if not request.description or not str(request.description).strip():
            raise ValueError(f"sample {request.sample_id!r} has no description")
        chosen = resolve()
        if not getattr(chosen, "available", False):
            from je_auto_control.utils.vision.backends.base import VLMNotAvailableError
            raise VLMNotAvailableError(
                f"VLM backend {getattr(chosen, 'name', '?')!r} is not available")
        shape = getattr(request.frame, "shape", None)
        if shape is None or len(shape) < 2:
            raise ValueError(f"sample {request.sample_id!r}: the frame is not an image array")
        box = request.frame_box(int(shape[1]), int(shape[0]))
        if box is None:
            return None
        image = _png_of(request.frame, box)
        _clear_usage(chosen)
        try:
            reply = chosen.locate(image, str(request.description), model=model)
        finally:
            # A request that failed was still made.
            meter.record(usage_of_call(getattr(chosen, "last_usage", None), rates))
        if reply is None:
            return None
        x, y = int(reply[0]), int(reply[1])
        if not (0 <= x < box[2] - box[0] and 0 <= y < box[3] - box[1]):
            return None  # off the image it was shown: a misread, not a location
        return request.to_screen(box[0] + x, box[1] + y)

    locate.usage_meter = meter  # type: ignore[attr-defined]  # reason: read by evaluate_locators
    return locate


__all__ = ["PRICE_KEYS", "STRATEGY_VLM", "usage_of_call", "vlm_strategy"]
