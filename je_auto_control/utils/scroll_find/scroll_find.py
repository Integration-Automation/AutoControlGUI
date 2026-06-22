"""Scroll a direction until a target image / text appears on screen.

The standard "find the element in a long list" pattern: scroll, check,
repeat until the target template (or OCR text) is visible or the scroll
budget is exhausted. The locate and scroll operations are injectable so
the loop is fully unit-testable without a real screen.
"""
from typing import Any, Callable, Dict, Optional, Tuple

Coords = Optional[Tuple[int, int]]
Locator = Callable[[str], Coords]
Scroller = Callable[[str, int], None]

_DEFAULT_THRESHOLD = 0.8
_DEFAULT_LANG = "eng"


def _make_text_locator(lang: str) -> Locator:
    def locate(target: str) -> Coords:
        from je_auto_control.utils.ocr.ocr_engine import find_text_matches
        matches = find_text_matches(target, lang=lang)
        return matches[0].center if matches else None
    return locate


def _make_image_locator(threshold: float) -> Locator:
    def locate(target: str) -> Coords:
        from je_auto_control.utils.exception.exceptions import (
            ImageNotFoundException,
        )
        from je_auto_control.wrapper.auto_control_image import (
            locate_image_center,
        )
        try:
            return locate_image_center(target, threshold, False)
        except (ImageNotFoundException, OSError, RuntimeError, ValueError,
                TypeError):
            return None
    return locate


def _default_locator(kind: str, threshold: float, lang: str) -> Locator:
    if str(kind) == "text":
        return _make_text_locator(lang)
    return _make_image_locator(threshold)


def _default_scroller(direction: str, amount: int) -> None:
    from je_auto_control.wrapper.auto_control_mouse import mouse_scroll
    sign = -1 if str(direction).lower() in ("down", "right") else 1
    mouse_scroll(sign * int(amount))


def scroll_until_visible(target: str, *, kind: str = "image",
                         direction: str = "down", max_scrolls: int = 10,
                         scroll_amount: int = 3,
                         locator: Optional[Locator] = None,
                         scroller: Optional[Scroller] = None
                         ) -> Dict[str, Any]:
    """Scroll ``direction`` until ``target`` is visible; return the outcome.

    ``kind`` is ``"image"`` (template path) or ``"text"`` (OCR). Returns
    ``{found, coords, scrolls}`` where ``scrolls`` is how many scrolls
    happened before the target appeared (or the budget when not found).
    ``locator`` / ``scroller`` are injectable; the default image locator
    uses a 0.8 threshold and the default text locator the ``eng`` model.
    """
    locate = locator or _default_locator(kind, _DEFAULT_THRESHOLD,
                                         _DEFAULT_LANG)
    scroll = scroller or _default_scroller
    budget = max(0, int(max_scrolls))
    for scrolls in range(budget + 1):
        coords = locate(target)
        if coords is not None:
            return {"found": True,
                    "coords": [int(coords[0]), int(coords[1])],
                    "scrolls": scrolls}
        if scrolls < budget:
            scroll(direction, int(scroll_amount))
    return {"found": False, "coords": None, "scrolls": budget}
