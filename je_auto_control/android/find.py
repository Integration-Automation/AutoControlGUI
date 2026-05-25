"""Element lookup over the uiautomator2 widget tree.

The Android equivalent of the macOS accessibility-tree locator:
callers describe a widget by ``text`` / ``resource_id`` /
``description`` / ``class_name``, and the helper returns the
bounding rect or taps it. The thin :func:`dump_hierarchy` is
exposed so test code can snapshot the live UI tree.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from je_auto_control.android.client import (
    UIAutomatorDevice, default_ui_device,
)


class ElementNotFoundError(LookupError):
    """Raised when no widget on screen matches the supplied selector."""


def _build_query(handle: Any,
                 text: Optional[str],
                 resource_id: Optional[str],
                 description: Optional[str],
                 class_name: Optional[str]) -> Any:
    """Translate the public kwargs into uiautomator2's chained selector."""
    selectors: Dict[str, Any] = {}
    if text is not None:
        selectors["text"] = text
    if resource_id is not None:
        selectors["resourceId"] = resource_id
    if description is not None:
        selectors["description"] = description
    if class_name is not None:
        selectors["className"] = class_name
    if not selectors:
        raise ValueError(
            "at least one of text/resource_id/description/class_name "
            "is required",
        )
    return handle(**selectors)


def find_element(text: Optional[str] = None,
                 resource_id: Optional[str] = None,
                 description: Optional[str] = None,
                 class_name: Optional[str] = None,
                 *, timeout_s: float = 5.0,
                 device: Optional[UIAutomatorDevice] = None,
                 ) -> Tuple[int, int, int, int]:
    """Return the matched widget's bounding rect ``(x1, y1, x2, y2)``."""
    handle = (device or default_ui_device()).handle
    query = _build_query(handle, text, resource_id, description, class_name)
    if not query.wait(timeout=float(timeout_s)):
        raise ElementNotFoundError(
            f"no widget matched selectors text={text!r} "
            f"resource_id={resource_id!r} description={description!r} "
            f"class_name={class_name!r}",
        )
    info = query.info
    bounds = info.get("bounds") or {}
    return (
        int(bounds.get("left", 0)),
        int(bounds.get("top", 0)),
        int(bounds.get("right", 0)),
        int(bounds.get("bottom", 0)),
    )


def click_element(text: Optional[str] = None,
                  resource_id: Optional[str] = None,
                  description: Optional[str] = None,
                  class_name: Optional[str] = None,
                  *, timeout_s: float = 5.0,
                  device: Optional[UIAutomatorDevice] = None,
                  ) -> Tuple[int, int]:
    """Tap the matched widget; return the click-centre ``(x, y)``.

    Uses the uiautomator2 handle for the tap rather than ``adb shell
    input tap`` so the daemon notices the press synchronously and
    can update its event queue.
    """
    bounds = find_element(
        text=text, resource_id=resource_id, description=description,
        class_name=class_name, timeout_s=timeout_s, device=device,
    )
    cx = (bounds[0] + bounds[2]) // 2
    cy = (bounds[1] + bounds[3]) // 2
    handle = (device or default_ui_device()).handle
    handle.click(int(cx), int(cy))
    return (int(cx), int(cy))


def dump_hierarchy(*, device: Optional[UIAutomatorDevice] = None) -> str:
    """Return the device's current widget tree as an XML string."""
    handle = (device or default_ui_device()).handle
    return str(handle.dump_hierarchy())


__all__ = [
    "ElementNotFoundError", "click_element", "dump_hierarchy",
    "find_element",
]
