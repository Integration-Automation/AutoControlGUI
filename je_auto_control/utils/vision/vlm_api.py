"""Public VLM-locator API.

Locate UI elements by natural-language description using a
vision-language model, as a fallback for cases where pixel templates
and accessibility lookups both come up empty. The backend is chosen
per :mod:`je_auto_control.utils.vision.backends` by env vars.
"""
import os
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from je_auto_control.utils.vision.backends import get_backend
from je_auto_control.utils.vision.backends.base import (
    VLMBackend, VLMNotAvailableError,
)


def locate_by_description(description: str,
                          screen_region: Optional[List[int]] = None,
                          model: Optional[str] = None,
                          backend: Optional[VLMBackend] = None,
                          ) -> Optional[Tuple[int, int]]:
    """Ask a VLM where ``description`` is on screen; return ``(x, y)`` or None.

    ``screen_region`` is ``[x1, y1, x2, y2]`` in screen pixels. When
    supplied, only that region is sent to the model and the returned
    coordinates are translated back into absolute screen space so
    callers can feed them straight into mouse operations. Raises
    :class:`VLMNotAvailableError` if no backend is configured.
    """
    if not description or not description.strip():
        raise ValueError("description must be a non-empty string")
    bound = backend if backend is not None else get_backend()
    if not bound.available:
        raise VLMNotAvailableError(
            "no VLM backend configured; set ANTHROPIC_API_KEY or "
            "OPENAI_API_KEY and install the matching SDK",
        )
    image_bytes = _capture_screenshot_bytes(screen_region)
    coords = bound.locate(image_bytes, description, model=model)
    if coords is None:
        return None
    x, y = coords
    if screen_region is not None:
        x += int(screen_region[0])
        y += int(screen_region[1])
    return (int(x), int(y))


def click_by_description(description: str,
                         screen_region: Optional[List[int]] = None,
                         model: Optional[str] = None,
                         backend: Optional[VLMBackend] = None,
                         ) -> bool:
    """Locate by description, then click the center of the match.

    Returns ``True`` on a successful click, ``False`` if no element was
    found. Raises :class:`VLMNotAvailableError` when no backend exists.
    """
    coords = locate_by_description(
        description, screen_region=screen_region,
        model=model, backend=backend,
    )
    if coords is None:
        return False
    cx, cy = coords
    from je_auto_control.wrapper.auto_control_mouse import (
        click_mouse, set_mouse_position,
    )
    set_mouse_position(cx, cy)
    click_mouse("mouse_left", cx, cy)
    return True


def _capture_screenshot_bytes(
        screen_region: Optional[List[int]] = None) -> bytes:
    """Take a screenshot (optionally cropped) and return PNG bytes."""
    fd, tmp = tempfile.mkstemp(prefix="vlm_", suffix=".png")
    os.close(fd)
    tmp_path = Path(tmp)
    try:
        from je_auto_control.wrapper.auto_control_screen import screenshot
        screenshot(str(tmp_path), screen_region=screen_region)
        return tmp_path.read_bytes()
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass


__all__ = [
    "VLMNotAvailableError", "locate_by_description", "click_by_description",
]
