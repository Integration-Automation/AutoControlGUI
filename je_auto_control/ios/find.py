"""Element lookup via XCUITest accessibility queries.

WebDriverAgent exposes the iOS accessibility tree. We match by
``name`` (label / accessibility identifier), by ``class_name``
(``XCUIElementTypeButton`` …), or by ``predicate`` for the rare
case where a more expressive XCTest NSPredicate is needed.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from je_auto_control.ios.client import IOSDevice, default_ios_device


class ElementNotFoundError(LookupError):
    """Raised when no XCUITest element matches the supplied selector."""


def _build_query(handle: Any,
                 name: Optional[str],
                 class_name: Optional[str],
                 predicate: Optional[str]) -> Any:
    """Translate kwargs into the ``wda`` selector form."""
    selectors: Dict[str, Any] = {}
    if name is not None:
        selectors["name"] = name
    if class_name is not None:
        selectors["className"] = class_name
    if predicate is not None:
        selectors["predicate"] = predicate
    if not selectors:
        raise ValueError(
            "at least one of name / class_name / predicate is required",
        )
    return handle(**selectors)


def find_element(name: Optional[str] = None,
                 class_name: Optional[str] = None,
                 predicate: Optional[str] = None,
                 *, timeout_s: float = 5.0,
                 device: Optional[IOSDevice] = None,
                 ) -> Tuple[int, int, int, int]:
    """Return the matched element's bounding rect ``(x1, y1, x2, y2)``."""
    handle = (device or default_ios_device()).handle
    query = _build_query(handle, name, class_name, predicate)
    if not query.wait(timeout=float(timeout_s)):
        raise ElementNotFoundError(
            f"no XCUITest element matched name={name!r} "
            f"class_name={class_name!r} predicate={predicate!r}",
        )
    bounds = query.bounds
    x = int(getattr(bounds, "x", 0))
    y = int(getattr(bounds, "y", 0))
    width = int(getattr(bounds, "width", 0))
    height = int(getattr(bounds, "height", 0))
    return (x, y, x + width, y + height)


def click_element(name: Optional[str] = None,
                  class_name: Optional[str] = None,
                  predicate: Optional[str] = None,
                  *, timeout_s: float = 5.0,
                  device: Optional[IOSDevice] = None,
                  ) -> Tuple[int, int]:
    """Tap the matched element; return the tap centre ``(x, y)``."""
    bounds = find_element(
        name=name, class_name=class_name, predicate=predicate,
        timeout_s=timeout_s, device=device,
    )
    cx = (bounds[0] + bounds[2]) // 2
    cy = (bounds[1] + bounds[3]) // 2
    handle = (device or default_ios_device()).handle
    handle.tap(int(cx), int(cy))
    return (int(cx), int(cy))


def dump_source(*, device: Optional[IOSDevice] = None) -> str:
    """Return the page source (XCUITest XML tree) as a string."""
    handle = (device or default_ios_device()).handle
    return str(handle.source())


__all__ = [
    "ElementNotFoundError", "click_element", "dump_source", "find_element",
]
