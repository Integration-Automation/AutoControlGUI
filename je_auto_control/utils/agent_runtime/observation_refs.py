"""Resolve observation-local elements and thumbnail points into host-checked native coordinates."""
from __future__ import annotations

import math
from typing import Any, Mapping

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import detached
from je_auto_control.utils.agent_runtime.browser_commands import BROWSER_ELEMENT_TOOLS

POINT_TOOLS = frozenset({"AC_click_mouse", "AC_set_mouse_position", "AC_press_mouse"})
IMAGE_FIELDS = ("origin", "original_size", "image_size", "format", "redacted_by", "coordinate_space")


def validate_reference(value: Any) -> None:
    """Accept exactly one bounded observation-local element or image point reference."""
    if value is None:
        return
    if not isinstance(value, Mapping) or len(value) != 1:
        raise AgentTaskError("observation reference requires exactly one selector")
    if "element_index" in value:
        index = value["element_index"]
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index <= 10000:
            raise AgentTaskError("element_index must be a nonnegative bounded integer")
        return
    if "image_point" not in value:
        raise AgentTaskError("unknown observation reference")
    _numbers(value["image_point"], 2)


def _numbers(value: Any, length: int) -> list[float]:
    if not isinstance(value, (tuple, list)) or len(value) != length:
        raise AgentTaskError("observation geometry is incomplete")
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in value):
        raise AgentTaskError("observation geometry requires finite numbers")
    if any(abs(item) > 2 ** 31 or not math.isfinite(item) for item in value):
        raise AgentTaskError("observation geometry is outside its bounds")
    return list(value)


def _size(value: Any) -> list[float]:
    result = _numbers(value, 2)
    if any(not 0 < item <= 65536 or int(item) != item for item in result):
        raise AgentTaskError("observation image geometry requires positive integer dimensions")
    return result


def _element(data: Mapping, index: int) -> tuple[list[int], dict]:
    elements = data.get("elements", ())
    if not isinstance(elements, (list, tuple)) or index >= len(elements):
        raise AgentTaskError("element index is outside this observation")
    item = elements[index]
    if not isinstance(item, Mapping) or item.get("index", index) != index:
        raise AgentTaskError("element index is ambiguous in this observation")
    if item.get("enabled", True) is not True:
        raise AgentTaskError("observed element is disabled")
    x, y, width, height = _numbers(item.get("bounds"), 4)
    if width <= 0 or height <= 0:
        raise AgentTaskError("observed element geometry has no area")
    evidence = {name: item[name] for name in ("index", "native_id", "bounds") if name in item}
    return [math.floor(x + width / 2), math.floor(y + height / 2)], detached(evidence)


def _image_point(data: Mapping, value: Any) -> list[int]:
    image = data.get("image")
    if not isinstance(image, Mapping) or image.get("redacted_by") != "strict":
        raise AgentTaskError("image reference requires trusted redacted observation geometry")
    point = _numbers(value, 2)
    origin, original, rendered = _numbers(image.get("origin"), 2), _size(image.get("original_size")), _size(
        image.get("image_size"))
    from je_auto_control.utils.agent_runtime.images import observation_image_bytes
    observation_image_bytes(image)
    if any(int(item) != item for item in origin):
        raise AgentTaskError("image origin geometry requires integer coordinates")
    if any(not 0 <= coordinate < extent for coordinate, extent in zip(point, rendered)):
        raise AgentTaskError("image point is outside this observation")
    return [int(start) + math.floor(position * full / scaled)
            for start, position, full, scaled in zip(origin, point, original, rendered)]


def resolve_action(tool: str, arguments: Mapping, reference: Any, data: Mapping) -> tuple[dict, dict]:
    """Resolve only reviewed point tools, preserving original arguments and non-image provenance."""
    kwargs: dict = detached(arguments)
    evidence = {"requested_arguments": kwargs, "identity": detached(data.get("identity"))}
    image = data.get("image")
    if isinstance(image, Mapping):
        evidence["image_geometry"] = {name: detached(image[name]) for name in IMAGE_FIELDS if name in image}
    if reference is None:
        return kwargs, evidence
    validate_reference(reference)
    if tool in BROWSER_ELEMENT_TOOLS:
        return _browser_element(tool, kwargs, reference, data, evidence)
    return _point_reference(tool, kwargs, reference, data, evidence)


def _point_reference(tool: str, kwargs: dict, reference: Mapping, data: Mapping, evidence: dict) -> tuple[dict, dict]:
    if tool not in POINT_TOOLS:
        raise AgentTaskError("observation references require a reviewed point action")
    if {"x", "y"} & set(kwargs):
        raise AgentTaskError("explicit coordinates cannot be combined with an observation reference")
    evidence["reference"] = detached(reference)
    if "element_index" in reference:
        point, element = _element(data, reference["element_index"])
        evidence["element"] = element
    else:
        point = _image_point(data, reference["image_point"])
    if any(not -(2 ** 31) <= coordinate < 2 ** 31 for coordinate in point):
        raise AgentTaskError("resolved point geometry is outside native coordinate bounds")
    return {**kwargs, "x": point[0], "y": point[1]}, evidence


def _browser_element(tool: str, kwargs: dict, reference: Mapping, data: Mapping, evidence: dict) -> tuple[dict, dict]:
    if "element_index" not in reference or {"selector", "frame"} & set(kwargs):
        raise AgentTaskError("browser reference requires one DOM index without explicit selector or frame")
    index = reference["element_index"]
    element = _observed_dom_element(index, data, require_enabled=tool != "AC_browser_read")
    selector, frame = element.get("selector"), element.get("frame", "")
    if not isinstance(selector, str) or not selector or not isinstance(frame, str):
        raise AgentTaskError("observed DOM locator is unavailable")
    evidence.update(reference=detached(reference), element=detached(element))
    return {**kwargs, "selector": selector, "frame": frame}, evidence


def _observed_dom_element(index: int, data: Mapping, *, require_enabled: bool) -> Mapping:
    elements = data.get("elements", ())
    if not isinstance(elements, (list, tuple)) or index >= len(elements):
        raise AgentTaskError("DOM index is outside this observation")
    element = elements[index]
    if not isinstance(element, Mapping) or element.get("index") != index:
        raise AgentTaskError("DOM observation index is ambiguous")
    if (require_enabled and element.get("enabled") is not True) or element.get("visible") is not True:
        raise AgentTaskError("observed DOM element is not actionable")
    return element
